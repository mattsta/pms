"""Workflow Engine - Multi-step automation orchestration.

The Workflow Engine enables complex, multi-step automations:
- Define workflows as sequences of steps
- Support parallel and conditional execution
- Integrate with tools and agents
- Track progress and handle failures

Usage:
    from pms.automation import Workflow, WorkflowEngine, WorkflowStep

    # Define a workflow
    workflow = Workflow(
        name="deploy_feature",
        steps=[
            WorkflowStep(name="run_tests", action="tool:run_tests"),
            WorkflowStep(name="build", action="tool:build_project"),
            WorkflowStep(
                name="deploy",
                action="tool:deploy",
                condition="steps.run_tests.success and steps.build.success"
            ),
        ]
    )

    # Execute
    engine = WorkflowEngine()
    result = await engine.run(workflow, context={"project": "myapp"})
"""

from __future__ import annotations

import ast
import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pms.automation.events import Event, EventBus, EventType, get_event_bus

if TYPE_CHECKING:
    from pms.services.checkout_manager import CheckoutManager

logger = logging.getLogger(__name__)


# =============================================================================
# Workflow Status
# =============================================================================


class WorkflowStatus(Enum):
    """Status of a workflow or step."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class StepType(Enum):
    """Types of workflow steps."""

    ACTION = "action"  # Execute a tool or agent
    PARALLEL = "parallel"  # Execute multiple steps in parallel
    CONDITION = "condition"  # Conditional branching
    WAIT = "wait"  # Wait for event or duration
    APPROVAL = "approval"  # Wait for human approval
    LOOP = "loop"  # Iterate over items
    SUBWORKFLOW = "subworkflow"  # Execute another workflow


# =============================================================================
# Workflow Context
# =============================================================================


@dataclass
class StepResult:
    """Result of a workflow step execution."""

    step_name: str
    status: WorkflowStatus
    output: Any = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float = 0.0

    @property
    def success(self) -> bool:
        """Check if step succeeded."""
        return self.status == WorkflowStatus.COMPLETED


@dataclass
class WorkflowContext:
    """Context passed through workflow execution.

    Contains:
    - Input parameters
    - Step results
    - Shared state
    - Environment info
    """

    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    inputs: dict[str, Any] = field(default_factory=dict)
    steps: dict[str, StepResult] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    correlation_id: str | None = None

    def get(self, key: str, default: Any = None) -> Any:
        """Get value from inputs or state."""
        if key in self.inputs:
            return self.inputs[key]
        return self.state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set value in state."""
        self.state[key] = value

    def get_step_result(self, step_name: str) -> StepResult | None:
        """Get result of a previous step."""
        return self.steps.get(step_name)

    def evaluate_expression(self, expression: str) -> Any:
        """Evaluate a constrained workflow expression.

        Supports:
        - steps.<name>.success
        - steps.<name>.output.<field>
        - inputs.<field>
        - state.<field>
        - Basic comparisons and boolean operators
        - List / tuple / dict literals

        Example:
            "steps.tests.success and inputs.deploy_enabled"
        """
        eval_context = {
            "steps": _StepAccessor(self.steps),
            "inputs": _DictAccessor(self.inputs),
            "state": _DictAccessor(self.state),
            "True": True,
            "False": False,
            "None": None,
        }

        try:
            tree = ast.parse(expression, mode="eval")
            return _SafeExpressionEvaluator(eval_context).visit(tree.body)
        except Exception as e:
            logger.warning(f"Condition evaluation failed: {expression} - {e}")
            return False

    def evaluate_condition(self, condition: str) -> bool:
        """Evaluate a condition expression to a boolean."""
        try:
            return bool(self.evaluate_expression(condition))
        except Exception as e:
            logger.warning(f"Condition evaluation failed: {condition} - {e}")
            return False


class _DictAccessor:
    """Helper for accessing dict values with dot notation in conditions."""

    def __init__(self, data: dict[str, Any]):
        self._data = data

    def __getattr__(self, name: str) -> Any:
        value = self._data.get(name)
        if isinstance(value, dict):
            return _DictAccessor(value)
        return value

    def __bool__(self) -> bool:
        return bool(self._data)


class _StepAccessor:
    """Helper for accessing step results in conditions."""

    def __init__(self, steps: dict[str, StepResult]):
        self._steps = steps

    def __getattr__(self, name: str) -> _StepResultAccessor:
        result = self._steps.get(name)
        return _StepResultAccessor(result)


class _StepResultAccessor:
    """Helper for accessing step result properties."""

    def __init__(self, result: StepResult | None):
        self._result = result

    @property
    def success(self) -> bool:
        return self._result.success if self._result else False

    @property
    def failed(self) -> bool:
        return self._result.status == WorkflowStatus.FAILED if self._result else False

    @property
    def output(self) -> Any:
        return self._result.output if self._result else None

    def __getattr__(self, name: str) -> Any:
        if self._result and isinstance(self._result.output, dict):
            return self._result.output.get(name)
        return None


class _SafeExpressionEvaluator(ast.NodeVisitor):
    """Evaluate a narrow expression subset for workflow conditions."""

    def __init__(self, context: dict[str, Any]) -> None:
        self._context = context

    def visit_Constant(self, node: ast.Constant) -> Any:
        return node.value

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in self._context:
            return self._context[node.id]
        raise ValueError(f"Unsupported name: {node.id}")

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        value = self.visit(node.value)
        return getattr(value, node.attr, None)

    def visit_List(self, node: ast.List) -> list[Any]:
        return [self.visit(item) for item in node.elts]

    def visit_Tuple(self, node: ast.Tuple) -> tuple[Any, ...]:
        return tuple(self.visit(item) for item in node.elts)

    def visit_Dict(self, node: ast.Dict) -> dict[Any, Any]:
        return {
            self.visit(key): self.visit(value)
            for key, value in zip(node.keys, node.values, strict=False)
        }

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return not bool(operand)
        if isinstance(node.op, ast.USub):
            return -operand
        raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        values = [self.visit(value) for value in node.values]
        if isinstance(node.op, ast.And):
            result = True
            for value in values:
                result = result and value
            return result
        if isinstance(node.op, ast.Or):
            result = False
            for value in values:
                result = result or value
            return result
        raise ValueError(f"Unsupported boolean operator: {type(node.op).__name__}")

    def visit_Compare(self, node: ast.Compare) -> bool:
        left = self.visit(node.left)
        for operator_node, comparator in zip(node.ops, node.comparators, strict=False):
            right = self.visit(comparator)
            if isinstance(operator_node, ast.Eq):
                passed = left == right
            elif isinstance(operator_node, ast.NotEq):
                passed = left != right
            elif isinstance(operator_node, ast.Gt):
                passed = left > right
            elif isinstance(operator_node, ast.GtE):
                passed = left >= right
            elif isinstance(operator_node, ast.Lt):
                passed = left < right
            elif isinstance(operator_node, ast.LtE):
                passed = left <= right
            elif isinstance(operator_node, ast.In):
                passed = left in right
            elif isinstance(operator_node, ast.NotIn):
                passed = left not in right
            elif isinstance(operator_node, ast.Is):
                passed = left is right
            elif isinstance(operator_node, ast.IsNot):
                passed = left is not right
            else:
                raise ValueError(
                    f"Unsupported comparison operator: {type(operator_node).__name__}"
                )
            if not passed:
                return False
            left = right
        return True

    def generic_visit(self, node: ast.AST) -> Any:
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")


# =============================================================================
# Workflow Step
# =============================================================================


@dataclass
class WorkflowStep:
    """A single step in a workflow.

    Attributes:
        name: Unique step identifier
        action: Action to execute (tool:name, agent:name, or custom)
        type: Type of step (action, parallel, condition, etc.)
        inputs: Input parameters for the action
        condition: Condition to check before executing
        on_failure: What to do on failure (stop, continue, retry)
        retry_count: Number of retries on failure
        timeout: Step timeout in seconds
        parallel_steps: For parallel type, steps to run concurrently
        branches: For condition type, conditional branches
    """

    name: str
    action: str = ""
    type: StepType = StepType.ACTION
    inputs: dict[str, Any] = field(default_factory=dict)
    condition: str | None = None
    on_failure: str = "stop"  # stop, continue, retry
    retry_count: int = 0
    timeout: float | None = None
    parallel_steps: list[WorkflowStep] = field(default_factory=list)
    branches: dict[str, list[WorkflowStep]] = field(default_factory=dict)
    loop_items: str | None = None  # Expression for items to iterate
    checkout: dict[str, Any] | None = None  # Optional task checkout config


# =============================================================================
# Workflow Definition
# =============================================================================


@dataclass
class Workflow:
    """A workflow definition.

    Attributes:
        name: Workflow name
        description: Human-readable description
        steps: List of steps to execute
        inputs_schema: Expected input parameters
        version: Workflow version
        tags: Tags for categorization
    """

    name: str
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    inputs_schema: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def validate_inputs(self, inputs: dict[str, Any]) -> list[str]:
        """Validate inputs against schema.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        for param_name, param_spec in self.inputs_schema.items():
            if param_spec.get("required", False) and param_name not in inputs:
                errors.append(f"Missing required input: {param_name}")

        return errors


@dataclass
class WorkflowRun:
    """A running workflow instance."""

    workflow: Workflow
    context: WorkflowContext
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_step: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    @property
    def duration_seconds(self) -> float:
        """Get run duration."""
        if not self.started_at:
            return 0.0
        end = self.completed_at or datetime.now(UTC)
        return (end - self.started_at).total_seconds()


# =============================================================================
# Action Handlers
# =============================================================================

ActionHandler = Callable[
    [str, dict[str, Any], WorkflowContext], Coroutine[Any, Any, Any]
]


class ActionRegistry:
    """Registry of action handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, ActionHandler] = {}

    def register(self, prefix: str, handler: ActionHandler) -> None:
        """Register an action handler.

        Args:
            prefix: Action prefix (e.g., "tool", "agent")
            handler: Async function to handle actions
        """
        self._handlers[prefix] = handler

    async def execute(
        self,
        action: str,
        inputs: dict[str, Any],
        context: WorkflowContext,
    ) -> Any:
        """Execute an action.

        Args:
            action: Action string (e.g., "tool:create_task")
            inputs: Action inputs
            context: Workflow context

        Returns:
            Action output
        """
        if ":" in action:
            prefix, name = action.split(":", 1)
        else:
            prefix = "custom"
            name = action

        handler = self._handlers.get(prefix)
        if not handler:
            raise ValueError(f"No handler for action prefix: {prefix}")

        return await handler(name, inputs, context)


# =============================================================================
# Workflow Engine
# =============================================================================


class WorkflowEngine:
    """Engine for executing workflows.

    Features:
    - Step-by-step execution
    - Parallel step support
    - Conditional branching
    - Event emission
    - Error handling and retries
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        action_registry: ActionRegistry | None = None,
        checkout_manager: CheckoutManager | None = None,
    ):
        """Initialize workflow engine.

        Args:
            event_bus: Event bus for notifications
            action_registry: Registry of action handlers
            checkout_manager: Optional task checkout manager
        """
        self.event_bus = event_bus or get_event_bus()
        self.action_registry = action_registry or ActionRegistry()
        self.checkout_manager = checkout_manager
        self._active_runs: dict[str, WorkflowRun] = {}

        # Register default handlers
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register default action handlers."""

        async def log_handler(
            name: str, inputs: dict[str, Any], ctx: WorkflowContext
        ) -> dict[str, Any]:
            """Simple log action for testing."""
            message = inputs.get("message", f"Step: {name}")
            logger.info(f"[Workflow {ctx.workflow_id}] {message}")
            return {"logged": message}

        async def wait_handler(
            name: str, inputs: dict[str, Any], ctx: WorkflowContext
        ) -> dict[str, Any]:
            """Wait for specified duration."""
            seconds = inputs.get("seconds", 1)
            await asyncio.sleep(seconds)
            return {"waited": seconds}

        async def set_state_handler(
            name: str, inputs: dict[str, Any], ctx: WorkflowContext
        ) -> dict[str, Any]:
            """Set context state."""
            for key, value in inputs.items():
                ctx.set(key, value)
            return {"set": list(inputs.keys())}

        self.action_registry.register("log", log_handler)
        self.action_registry.register("wait", wait_handler)
        self.action_registry.register("state", set_state_handler)

    async def run(
        self,
        workflow: Workflow,
        inputs: dict[str, Any] | None = None,
        context: WorkflowContext | None = None,
    ) -> WorkflowRun:
        """Execute a workflow.

        Args:
            workflow: Workflow to execute
            inputs: Input parameters
            context: Optional pre-configured context

        Returns:
            WorkflowRun with results
        """
        # Create context
        if context is None:
            context = WorkflowContext(inputs=inputs or {})
        elif inputs:
            context.inputs.update(inputs)

        # Validate inputs
        errors = workflow.validate_inputs(context.inputs)
        if errors:
            raise ValueError(f"Invalid inputs: {', '.join(errors)}")

        # Create run
        run = WorkflowRun(
            workflow=workflow,
            context=context,
            status=WorkflowStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        self._active_runs[context.workflow_id] = run

        # Emit start event
        await self.event_bus.emit(
            Event(
                type=EventType.WORKFLOW_STARTED,
                data={
                    "workflow_id": context.workflow_id,
                    "workflow_name": workflow.name,
                    "inputs": context.inputs,
                },
                correlation_id=context.correlation_id,
            )
        )

        try:
            # Execute steps
            for step in workflow.steps:
                run.current_step = step.name

                result = await self._execute_step(step, context)
                context.steps[step.name] = result

                if result.status == WorkflowStatus.FAILED and step.on_failure == "stop":
                    run.status = WorkflowStatus.FAILED
                    run.error = result.error
                    break
                    # on_failure == "continue" - keep going

            # Mark complete if not failed
            if run.status == WorkflowStatus.RUNNING:
                run.status = WorkflowStatus.COMPLETED

        except Exception as e:
            run.status = WorkflowStatus.FAILED
            run.error = str(e)
            logger.exception(f"Workflow {workflow.name} failed: {e}")

        finally:
            run.completed_at = datetime.now(UTC)
            run.current_step = None

            # Emit completion event
            match run.status:
                case WorkflowStatus.COMPLETED:
                    event_type = EventType.WORKFLOW_COMPLETED
                case WorkflowStatus.FAILED:
                    event_type = EventType.WORKFLOW_FAILED
                case _:
                    event_type = EventType.WORKFLOW_FAILED
            await self.event_bus.emit(
                Event(
                    type=event_type,
                    data={
                        "workflow_id": context.workflow_id,
                        "workflow_name": workflow.name,
                        "status": run.status.value,
                        "duration": run.duration_seconds,
                        "error": run.error,
                    },
                    correlation_id=context.correlation_id,
                )
            )

            # Cleanup
            self._active_runs.pop(context.workflow_id, None)

        return run

    async def _execute_step(
        self,
        step: WorkflowStep,
        context: WorkflowContext,
    ) -> StepResult:
        """Execute a single workflow step."""
        result = StepResult(
            step_name=step.name,
            status=WorkflowStatus.PENDING,
            started_at=datetime.now(UTC),
        )

        # Check condition
        if step.condition and not context.evaluate_condition(step.condition):
            result.status = WorkflowStatus.SKIPPED
            result.completed_at = datetime.now(UTC)
            return result

        # Emit step started
        await self.event_bus.emit(
            Event(
                type=EventType.WORKFLOW_STEP_STARTED,
                data={
                    "workflow_id": context.workflow_id,
                    "step_name": step.name,
                    "step_type": step.type.value,
                },
                correlation_id=context.correlation_id,
            )
        )

        result.status = WorkflowStatus.RUNNING

        try:
            # Execute based on step type
            match step.type:
                case StepType.ACTION:
                    result.output = await self._execute_action_with_checkout(
                        step, context
                    )
                case StepType.PARALLEL:
                    result.output = await self._execute_parallel(step, context)
                case StepType.WAIT:
                    await self._execute_wait(step, context)
                    result.output = {"waited": True}
                case StepType.LOOP:
                    result.output = await self._execute_loop(step, context)
                case _:
                    pass

            result.status = WorkflowStatus.COMPLETED

        except Exception as e:
            result.status = WorkflowStatus.FAILED
            result.error = str(e)
            logger.error(f"Step {step.name} failed: {e}")

            # Handle retries
            if step.retry_count > 0:
                for attempt in range(step.retry_count):
                    logger.info(f"Retrying step {step.name} (attempt {attempt + 1})")
                    try:
                        result.output = await self._execute_action_with_checkout(
                            step, context
                        )
                        result.status = WorkflowStatus.COMPLETED
                        result.error = None
                        break
                    except Exception as retry_error:
                        result.error = str(retry_error)

        finally:
            result.completed_at = datetime.now(UTC)
            if result.started_at:
                result.duration_seconds = (
                    result.completed_at - result.started_at
                ).total_seconds()

            # Emit step completed/failed
            event_type = (
                EventType.WORKFLOW_STEP_COMPLETED
                if result.success
                else EventType.WORKFLOW_STEP_FAILED
            )
            await self.event_bus.emit(
                Event(
                    type=event_type,
                    data={
                        "workflow_id": context.workflow_id,
                        "step_name": step.name,
                        "status": result.status.value,
                        "duration": result.duration_seconds,
                        "error": result.error,
                    },
                    correlation_id=context.correlation_id,
                )
            )

        return result

    async def _execute_action(
        self,
        step: WorkflowStep,
        context: WorkflowContext,
    ) -> Any:
        """Execute an action step."""
        # Resolve input values from context
        resolved_inputs = self._resolve_inputs(step.inputs, context)

        # Execute with timeout
        if step.timeout:
            return await asyncio.wait_for(
                self.action_registry.execute(step.action, resolved_inputs, context),
                timeout=step.timeout,
            )
        else:
            return await self.action_registry.execute(
                step.action, resolved_inputs, context
            )

    async def _execute_action_with_checkout(
        self,
        step: WorkflowStep,
        context: WorkflowContext,
    ) -> Any:
        """Execute an action step with optional checkout."""
        async with self.checkout_task_for_step(step, context):
            return await self._execute_action(step, context)

    @asynccontextmanager
    async def checkout_task_for_step(
        self,
        step: WorkflowStep,
        context: WorkflowContext,
    ) -> AsyncIterator[None]:
        """Checkout a task for the duration of a workflow step."""
        if not step.checkout:
            yield
            return

        if self.checkout_manager is None:
            raise ValueError("Checkout manager not configured for workflow engine")

        resolved = self._resolve_inputs(step.checkout, context)
        task_id = resolved.get("task_id")
        agent_session_id = resolved.get("agent_session_id")
        if not task_id or not agent_session_id:
            raise ValueError("checkout requires task_id and agent_session_id")

        lease_seconds = int(resolved.get("lease_seconds", 300))
        force = bool(resolved.get("force", False))
        checkout_parent = bool(resolved.get("checkout_parent", True))
        release_on_failure = bool(resolved.get("release_on_failure", True))

        async with self.checkout_manager.checkout_task(
            task_id=task_id,
            agent_session_id=agent_session_id,
            lease_seconds=lease_seconds,
            force=force,
            checkout_parent=checkout_parent,
            release_on_failure=release_on_failure,
        ):
            yield

    async def _execute_parallel(
        self,
        step: WorkflowStep,
        context: WorkflowContext,
    ) -> dict[str, Any]:
        """Execute parallel steps concurrently."""
        tasks = []
        for sub_step in step.parallel_steps:
            tasks.append(self._execute_step(sub_step, context))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = {}
        for sub_step, result in zip(step.parallel_steps, results):
            if isinstance(result, Exception):
                output[sub_step.name] = {"error": str(result)}
                context.steps[sub_step.name] = StepResult(
                    step_name=sub_step.name,
                    status=WorkflowStatus.FAILED,
                    error=str(result),
                )
            elif isinstance(result, StepResult):
                output[sub_step.name] = result.output
                context.steps[sub_step.name] = result

        return output

    async def _execute_wait(
        self,
        step: WorkflowStep,
        context: WorkflowContext,
    ) -> None:
        """Execute a wait step."""
        duration = step.inputs.get("seconds", 0)
        if duration > 0:
            await asyncio.sleep(duration)

    async def _execute_loop(
        self,
        step: WorkflowStep,
        context: WorkflowContext,
    ) -> list[Any]:
        """Execute a loop step."""
        # Get items to iterate
        items_expr = step.loop_items or "[]"
        items = context.evaluate_expression(items_expr)

        items_list: list[Any] = (
            list(items) if isinstance(items, (list, tuple)) else [items]
        )

        results: list[Any] = []
        for i, item in enumerate(items_list):
            # Set loop variables
            context.set("loop_index", i)
            context.set("loop_item", item)

            # Execute sub-steps
            for sub_step in step.parallel_steps:  # Reuse parallel_steps for loop body
                result = await self._execute_step(sub_step, context)
                results.append(result.output)

        return results

    def _resolve_inputs(
        self,
        inputs: dict[str, Any],
        context: WorkflowContext,
    ) -> dict[str, Any]:
        """Resolve input expressions to values."""
        resolved = {}

        for key, value in inputs.items():
            if isinstance(value, str) and value.startswith("$"):
                # Expression reference
                expr = value[1:]  # Remove $
                resolved[key] = context.evaluate_expression(expr)
            else:
                resolved[key] = value

        return resolved

    def get_active_runs(self) -> list[WorkflowRun]:
        """Get all active workflow runs."""
        return list(self._active_runs.values())

    async def cancel(self, workflow_id: str) -> bool:
        """Cancel a running workflow.

        Args:
            workflow_id: ID of workflow to cancel

        Returns:
            True if cancelled
        """
        run = self._active_runs.get(workflow_id)
        if run and run.status == WorkflowStatus.RUNNING:
            run.status = WorkflowStatus.CANCELLED
            run.completed_at = datetime.now(UTC)
            return True
        return False


# =============================================================================
# Workflow Builder (Fluent API)
# =============================================================================


class WorkflowBuilder:
    """Fluent API for building workflows.

    Example:
        workflow = (
            WorkflowBuilder("deploy")
            .description("Deploy to production")
            .step("test", action="tool:run_tests")
            .step("build", action="tool:build")
            .parallel("deploy_services", [
                ("api", "tool:deploy_api"),
                ("web", "tool:deploy_web"),
            ])
            .step("notify", action="tool:send_slack", condition="steps.test.success")
            .build()
        )
    """

    def __init__(self, name: str):
        self._name = name
        self._description = ""
        self._steps: list[WorkflowStep] = []
        self._inputs_schema: dict[str, Any] = {}
        self._tags: list[str] = []

    def description(self, desc: str) -> WorkflowBuilder:
        """Set workflow description."""
        self._description = desc
        return self

    def tag(self, *tags: str) -> WorkflowBuilder:
        """Add tags."""
        self._tags.extend(tags)
        return self

    def input(
        self,
        name: str,
        type_: str = "string",
        required: bool = False,
        default: Any = None,
    ) -> WorkflowBuilder:
        """Define an input parameter."""
        self._inputs_schema[name] = {
            "type": type_,
            "required": required,
            "default": default,
        }
        return self

    def step(
        self,
        name: str,
        action: str,
        inputs: dict[str, Any] | None = None,
        condition: str | None = None,
        on_failure: str = "stop",
        timeout: float | None = None,
        checkout: dict[str, Any] | None = None,
    ) -> WorkflowBuilder:
        """Add an action step."""
        self._steps.append(
            WorkflowStep(
                name=name,
                action=action,
                type=StepType.ACTION,
                inputs=inputs or {},
                condition=condition,
                on_failure=on_failure,
                timeout=timeout,
                checkout=checkout,
            )
        )
        return self

    def parallel(
        self,
        name: str,
        steps: list[tuple[str, str]],
        condition: str | None = None,
    ) -> WorkflowBuilder:
        """Add parallel steps.

        Args:
            name: Step name
            steps: List of (name, action) tuples
            condition: Optional condition
        """
        parallel_steps = [
            WorkflowStep(name=step_name, action=step_action, type=StepType.ACTION)
            for step_name, step_action in steps
        ]
        self._steps.append(
            WorkflowStep(
                name=name,
                type=StepType.PARALLEL,
                parallel_steps=parallel_steps,
                condition=condition,
            )
        )
        return self

    def wait(
        self,
        name: str,
        seconds: float,
        condition: str | None = None,
    ) -> WorkflowBuilder:
        """Add a wait step."""
        self._steps.append(
            WorkflowStep(
                name=name,
                type=StepType.WAIT,
                inputs={"seconds": seconds},
                condition=condition,
            )
        )
        return self

    def build(self) -> Workflow:
        """Build the workflow."""
        return Workflow(
            name=self._name,
            description=self._description,
            steps=self._steps,
            inputs_schema=self._inputs_schema,
            tags=self._tags,
        )
