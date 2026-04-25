"""Tests for the PMS automation subsystem."""

import asyncio

import pytest

from pms.automation.events import (
    Event,
    EventBus,
    EventPattern,
    EventType,
)
from pms.automation.triggers import (
    Trigger,
    TriggerBuilder,
    TriggerManager,
    TriggerType,
)
from pms.automation.workflows import (
    StepType,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEngine,
    WorkflowStatus,
    WorkflowStep,
)

# =============================================================================
# Event Bus Tests
# =============================================================================


class TestEventBus:
    """Tests for EventBus."""

    @pytest.mark.asyncio
    async def test_emit_and_receive(self):
        """Test basic emit and receive."""
        bus = EventBus()
        received = []

        @bus.on(EventType.TASK_COMPLETED)
        async def handler(event: Event):
            received.append(event)

        event = Event(
            type=EventType.TASK_COMPLETED,
            data={"task_id": "123"},
        )
        count = await bus.emit(event)

        assert count == 1
        assert len(received) == 1
        assert received[0].data["task_id"] == "123"

    @pytest.mark.asyncio
    async def test_pattern_matching(self):
        """Test wildcard pattern matching."""
        bus = EventBus()
        received = []

        @bus.on("task.*")
        async def handler(event: Event):
            received.append(event)

        # Should match
        await bus.emit(Event(type=EventType.TASK_COMPLETED, data={}))
        await bus.emit(Event(type=EventType.TASK_STARTED, data={}))

        # Should not match
        await bus.emit(Event(type=EventType.PROJECT_CREATED, data={}))

        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_once_subscription(self):
        """Test one-time subscription."""
        bus = EventBus()
        count = 0

        @bus.on(EventType.TASK_COMPLETED, once=True)
        async def handler(event: Event):
            nonlocal count
            count += 1

        await bus.emit(Event(type=EventType.TASK_COMPLETED, data={}))
        await bus.emit(Event(type=EventType.TASK_COMPLETED, data={}))

        assert count == 1

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """Test handler priority ordering."""
        bus = EventBus()
        order = []

        @bus.on(EventType.TASK_COMPLETED, priority=1)
        async def low_priority(event: Event):
            order.append("low")

        @bus.on(EventType.TASK_COMPLETED, priority=10)
        async def high_priority(event: Event):
            order.append("high")

        await bus.emit(Event(type=EventType.TASK_COMPLETED, data={}))

        assert order == ["high", "low"]

    @pytest.mark.asyncio
    async def test_event_history(self):
        """Test event history."""
        bus = EventBus(history_size=10)

        for i in range(5):
            await bus.emit(
                Event(
                    type=EventType.TASK_COMPLETED,
                    data={"index": i},
                )
            )

        history = bus.get_history(limit=3)

        assert len(history) == 3
        assert history[0].data["index"] == 4  # Newest first

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        """Test unsubscribing."""
        bus = EventBus()
        received = []

        async def handler(event: Event):
            received.append(event)

        sub_id = bus.subscribe(
            EventPattern(type_pattern=EventType.TASK_COMPLETED),
            handler,
        )

        await bus.emit(Event(type=EventType.TASK_COMPLETED, data={}))
        assert len(received) == 1

        bus.unsubscribe(sub_id)

        await bus.emit(Event(type=EventType.TASK_COMPLETED, data={}))
        assert len(received) == 1  # No new events

    def test_event_to_dict(self):
        """Test event serialization."""
        event = Event(
            type=EventType.TASK_COMPLETED,
            data={"task_id": "123"},
            source="test",
        )

        data = event.to_dict()

        assert data["type"] == "task.completed"
        assert data["data"]["task_id"] == "123"
        assert data["source"] == "test"

    def test_event_from_dict(self):
        """Test event deserialization."""
        data = {
            "id": "abc123",
            "type": "task.completed",
            "data": {"task_id": "123"},
            "source": "test",
            "correlation_id": None,
            "timestamp": "2024-01-01T00:00:00+00:00",
        }

        event = Event.from_dict(data)

        assert event.type == EventType.TASK_COMPLETED
        assert event.data["task_id"] == "123"


class TestEventPattern:
    """Tests for EventPattern."""

    def test_exact_type_match(self):
        """Test exact type matching."""
        pattern = EventPattern(type_pattern=EventType.TASK_COMPLETED)
        event = Event(type=EventType.TASK_COMPLETED, data={})

        assert pattern.matches(event)

    def test_wildcard_match(self):
        """Test wildcard matching."""
        pattern = EventPattern(type_pattern="task.*")

        assert pattern.matches(Event(type=EventType.TASK_COMPLETED, data={}))
        assert pattern.matches(Event(type=EventType.TASK_STARTED, data={}))
        assert not pattern.matches(Event(type=EventType.PROJECT_CREATED, data={}))

    def test_data_pattern_match(self):
        """Test data field matching."""
        pattern = EventPattern(
            type_pattern=EventType.TASK_COMPLETED,
            data_patterns={"project": "myproject"},
        )

        assert pattern.matches(
            Event(
                type=EventType.TASK_COMPLETED,
                data={"project": "myproject", "task_id": "123"},
            )
        )

        assert not pattern.matches(
            Event(
                type=EventType.TASK_COMPLETED,
                data={"project": "other", "task_id": "123"},
            )
        )


# =============================================================================
# Workflow Tests
# =============================================================================


class TestWorkflowContext:
    """Tests for WorkflowContext."""

    def test_get_and_set(self):
        """Test getting and setting values."""
        ctx = WorkflowContext(inputs={"a": 1})

        assert ctx.get("a") == 1
        assert ctx.get("b") is None
        assert ctx.get("b", "default") == "default"

        ctx.set("b", 2)
        assert ctx.get("b") == 2

    def test_evaluate_condition(self):
        """Test condition evaluation."""
        ctx = WorkflowContext(
            inputs={"enabled": True, "count": 5},
            state={"ready": True},
        )

        assert ctx.evaluate_condition("inputs.enabled")
        assert ctx.evaluate_condition("inputs.count > 3")
        assert ctx.evaluate_condition("state.ready")
        assert not ctx.evaluate_condition("inputs.count > 10")

    def test_evaluate_step_condition(self):
        """Test step result in conditions."""
        from pms.automation.workflows import StepResult

        ctx = WorkflowContext()
        ctx.steps["test"] = StepResult(
            step_name="test",
            status=WorkflowStatus.COMPLETED,
            output={"passed": True},
        )

        assert ctx.evaluate_condition("steps.test.success")
        assert not ctx.evaluate_condition("steps.test.failed")

    def test_evaluate_expression_supports_non_boolean_values(self):
        """Loop/input expressions should resolve values without eval()."""
        ctx = WorkflowContext(inputs={"items": ["a", "b"]}, state={"retries": 2})

        assert ctx.evaluate_expression("inputs.items") == ["a", "b"]
        assert ctx.evaluate_expression("[state.retries, 3]") == [2, 3]

    def test_evaluate_expression_rejects_function_calls(self, caplog):
        """Unsafe expression nodes should fail closed."""
        ctx = WorkflowContext(inputs={"enabled": True})

        with caplog.at_level("WARNING"):
            assert ctx.evaluate_condition("__import__('os').system('true')") is False
        assert "Unsupported expression node: Call" in caplog.text


class TestWorkflowEngine:
    """Tests for WorkflowEngine."""

    @pytest.mark.asyncio
    async def test_simple_workflow(self):
        """Test simple workflow execution."""
        engine = WorkflowEngine(event_bus=EventBus())

        workflow = Workflow(
            name="test_workflow",
            steps=[
                WorkflowStep(
                    name="log_start",
                    action="log:start",
                    inputs={"message": "Starting"},
                ),
                WorkflowStep(
                    name="log_end",
                    action="log:end",
                    inputs={"message": "Ending"},
                ),
            ],
        )

        result = await engine.run(workflow)

        assert result.status == WorkflowStatus.COMPLETED
        assert "log_start" in result.context.steps
        assert "log_end" in result.context.steps

    @pytest.mark.asyncio
    async def test_workflow_step_checkout(self):
        """Test workflow step checkout integration."""
        from contextlib import asynccontextmanager

        class DummyCheckoutManager:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str, str]] = []

            @asynccontextmanager
            async def checkout_task(
                self,
                task_id: str,
                agent_session_id: str,
                lease_seconds: int = 300,
                force: bool = False,
                checkout_parent: bool = True,
                release_on_failure: bool = True,
            ):
                self.calls.append(("checkout", task_id, agent_session_id))
                try:
                    yield
                finally:
                    self.calls.append(("release", task_id, agent_session_id))

        manager = DummyCheckoutManager()
        engine = WorkflowEngine(event_bus=EventBus(), checkout_manager=manager)

        workflow = Workflow(
            name="checkout_flow",
            steps=[
                WorkflowStep(
                    name="run",
                    action="log:run",
                    checkout={
                        "task_id": "task_1",
                        "agent_session_id": "agent_1",
                        "lease_seconds": 120,
                    },
                )
            ],
        )

        result = await engine.run(workflow)

        assert result.status == WorkflowStatus.COMPLETED
        assert manager.calls == [
            ("checkout", "task_1", "agent_1"),
            ("release", "task_1", "agent_1"),
        ]

    @pytest.mark.asyncio
    async def test_workflow_step_checkout_missing_manager(self):
        """Test checkout config without manager fails the workflow."""
        engine = WorkflowEngine(event_bus=EventBus())

        workflow = Workflow(
            name="checkout_flow",
            steps=[
                WorkflowStep(
                    name="run",
                    action="log:run",
                    checkout={
                        "task_id": "task_1",
                        "agent_session_id": "agent_1",
                    },
                )
            ],
        )

        result = await engine.run(workflow)

        assert result.status == WorkflowStatus.FAILED
        assert "Checkout manager not configured" in (result.error or "")

    @pytest.mark.asyncio
    async def test_workflow_with_inputs(self):
        """Test workflow with input parameters."""
        engine = WorkflowEngine(event_bus=EventBus())

        workflow = Workflow(
            name="test_inputs",
            inputs_schema={
                "name": {"required": True},
            },
            steps=[
                WorkflowStep(
                    name="greet",
                    action="log:greet",
                    inputs={"message": "Hello"},
                ),
            ],
        )

        result = await engine.run(workflow, inputs={"name": "World"})

        assert result.status == WorkflowStatus.COMPLETED
        assert result.context.inputs["name"] == "World"

    @pytest.mark.asyncio
    async def test_workflow_validation(self):
        """Test input validation."""
        engine = WorkflowEngine(event_bus=EventBus())

        workflow = Workflow(
            name="test_validation",
            inputs_schema={
                "required_param": {"required": True},
            },
            steps=[],
        )

        with pytest.raises(ValueError, match="Missing required input"):
            await engine.run(workflow, inputs={})

    @pytest.mark.asyncio
    async def test_conditional_step(self):
        """Test conditional step execution."""
        engine = WorkflowEngine(event_bus=EventBus())

        workflow = Workflow(
            name="test_conditional",
            steps=[
                WorkflowStep(
                    name="always_run",
                    action="log:always",
                ),
                WorkflowStep(
                    name="skip_this",
                    action="log:skipped",
                    condition="False",
                ),
            ],
        )

        result = await engine.run(workflow)

        assert result.status == WorkflowStatus.COMPLETED
        assert result.context.steps["always_run"].success
        assert result.context.steps["skip_this"].status == WorkflowStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_parallel_steps(self):
        """Test parallel step execution."""
        engine = WorkflowEngine(event_bus=EventBus())

        workflow = Workflow(
            name="test_parallel",
            steps=[
                WorkflowStep(
                    name="parallel_group",
                    type=StepType.PARALLEL,
                    parallel_steps=[
                        WorkflowStep(
                            name="task1", action="wait:1", inputs={"seconds": 0.1}
                        ),
                        WorkflowStep(
                            name="task2", action="wait:2", inputs={"seconds": 0.1}
                        ),
                    ],
                ),
            ],
        )

        result = await engine.run(workflow)

        assert result.status == WorkflowStatus.COMPLETED
        assert result.context.steps["task1"].success
        assert result.context.steps["task2"].success

    @pytest.mark.asyncio
    async def test_workflow_failure(self):
        """Test workflow failure handling."""
        engine = WorkflowEngine(event_bus=EventBus())

        # Register failing handler
        async def fail_handler(name: str, inputs: dict, ctx):
            raise Exception("Intentional failure")

        engine.action_registry.register("fail", fail_handler)

        workflow = Workflow(
            name="test_failure",
            steps=[
                WorkflowStep(name="will_fail", action="fail:now"),
            ],
        )

        result = await engine.run(workflow)

        assert result.status == WorkflowStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_on_failure_continue(self):
        """Test continuing on failure."""
        engine = WorkflowEngine(event_bus=EventBus())

        async def fail_handler(name: str, inputs: dict, ctx):
            raise Exception("Intentional failure")

        engine.action_registry.register("fail", fail_handler)

        workflow = Workflow(
            name="test_continue",
            steps=[
                WorkflowStep(
                    name="will_fail",
                    action="fail:now",
                    on_failure="continue",
                ),
                WorkflowStep(name="should_run", action="log:after"),
            ],
        )

        result = await engine.run(workflow)

        assert result.status == WorkflowStatus.COMPLETED
        assert result.context.steps["will_fail"].status == WorkflowStatus.FAILED
        assert result.context.steps["should_run"].success


class TestWorkflowBuilder:
    """Tests for WorkflowBuilder."""

    def test_build_simple_workflow(self):
        """Test building a simple workflow."""
        workflow = (
            WorkflowBuilder("test")
            .description("Test workflow")
            .step("first", action="log:first")
            .step("second", action="log:second")
            .build()
        )

        assert workflow.name == "test"
        assert workflow.description == "Test workflow"
        assert len(workflow.steps) == 2

    def test_build_with_parallel(self):
        """Test building workflow with parallel steps."""
        workflow = (
            WorkflowBuilder("parallel_test")
            .parallel(
                "concurrent",
                [
                    ("task1", "log:1"),
                    ("task2", "log:2"),
                ],
            )
            .build()
        )

        assert len(workflow.steps) == 1
        assert workflow.steps[0].type == StepType.PARALLEL
        assert len(workflow.steps[0].parallel_steps) == 2

    def test_build_with_inputs(self):
        """Test building workflow with input schema."""
        workflow = (
            WorkflowBuilder("inputs_test")
            .input("name", type_="string", required=True)
            .input("count", type_="integer", default=10)
            .step("use_inputs", action="log:inputs")
            .build()
        )

        assert "name" in workflow.inputs_schema
        assert workflow.inputs_schema["name"]["required"] is True
        assert workflow.inputs_schema["count"]["default"] == 10


# =============================================================================
# Trigger Tests
# =============================================================================


class TestTrigger:
    """Tests for Trigger."""

    def test_matches_event(self):
        """Test event matching."""
        trigger = Trigger(
            name="test",
            type=TriggerType.EVENT,
            workflow_name="test_workflow",
            event_pattern="task.completed",
        )

        assert trigger.matches_event(Event(type=EventType.TASK_COMPLETED, data={}))
        assert not trigger.matches_event(Event(type=EventType.TASK_STARTED, data={}))

    def test_extract_inputs(self):
        """Test input extraction from event."""
        trigger = Trigger(
            name="test",
            type=TriggerType.EVENT,
            workflow_name="test_workflow",
            inputs={"static": "value"},
            input_mapping={
                "task_id": "task_id",
                "project": "project.name",
            },
        )

        event = Event(
            type=EventType.TASK_COMPLETED,
            data={
                "task_id": "123",
                "project": {"name": "myproject", "id": "456"},
            },
        )

        inputs = trigger.extract_inputs(event)

        assert inputs["static"] == "value"
        assert inputs["task_id"] == "123"
        assert inputs["project"] == "myproject"


class TestTriggerBuilder:
    """Tests for TriggerBuilder."""

    def test_build_event_trigger(self):
        """Test building event trigger."""
        trigger = (
            TriggerBuilder("on_complete")
            .on_event("task.completed")
            .workflow("notify")
            .map_input("task_id", "task_id")
            .with_cooldown(60)
            .build()
        )

        assert trigger.name == "on_complete"
        assert trigger.type == TriggerType.EVENT
        assert trigger.event_pattern == "task.completed"
        assert trigger.workflow_name == "notify"
        assert trigger.cooldown_seconds == 60

    def test_build_schedule_trigger(self):
        """Test building scheduled trigger."""
        trigger = (
            TriggerBuilder("daily_report")
            .on_schedule("0 9 * * *")
            .workflow("generate_report")
            .build()
        )

        assert trigger.type == TriggerType.SCHEDULE
        assert trigger.schedule == "0 9 * * *"


class TestTriggerManager:
    """Tests for TriggerManager."""

    @pytest.mark.asyncio
    async def test_register_and_fire(self):
        """Test registering trigger and firing on event."""
        bus = EventBus()
        engine = WorkflowEngine(event_bus=bus)
        manager = TriggerManager(engine, bus)

        # Register workflow
        workflow = Workflow(
            name="test_workflow",
            steps=[
                WorkflowStep(name="log", action="log:triggered"),
            ],
        )
        manager.register_workflow(workflow)

        # Register trigger
        trigger = Trigger(
            name="on_task",
            type=TriggerType.EVENT,
            workflow_name="test_workflow",
            event_pattern="task.completed",
        )
        manager.register(trigger)

        # Start manager
        await manager.start()

        # Emit event
        await bus.emit(Event(type=EventType.TASK_COMPLETED, data={}))

        # Give time for async processing
        await asyncio.sleep(0.1)

        # Check execution
        executions = manager.get_executions()
        assert len(executions) == 1
        assert executions[0].trigger_name == "on_task"

        await manager.stop()

    @pytest.mark.asyncio
    async def test_cooldown(self):
        """Test trigger cooldown."""
        bus = EventBus()
        engine = WorkflowEngine(event_bus=bus)
        manager = TriggerManager(engine, bus)

        workflow = Workflow(name="test", steps=[])
        manager.register_workflow(workflow)

        trigger = Trigger(
            name="with_cooldown",
            type=TriggerType.EVENT,
            workflow_name="test",
            event_pattern="task.completed",
            cooldown_seconds=10,  # 10 second cooldown
        )
        manager.register(trigger)

        await manager.start()

        # First event should fire
        await bus.emit(Event(type=EventType.TASK_COMPLETED, data={}))
        await asyncio.sleep(0.1)

        # Second event should be blocked by cooldown
        await bus.emit(Event(type=EventType.TASK_COMPLETED, data={}))
        await asyncio.sleep(0.1)

        executions = manager.get_executions()
        assert len(executions) == 1  # Only one execution

        await manager.stop()

    @pytest.mark.asyncio
    async def test_manual_fire(self):
        """Test manual trigger firing."""
        bus = EventBus()
        engine = WorkflowEngine(event_bus=bus)
        manager = TriggerManager(engine, bus)

        workflow = Workflow(name="manual_test", steps=[])
        manager.register_workflow(workflow)

        trigger = Trigger(
            name="manual",
            type=TriggerType.MANUAL,
            workflow_name="manual_test",
        )
        manager.register(trigger)

        workflow_id = await manager.fire_manual("manual", inputs={"test": "value"})

        assert workflow_id is not None
        executions = manager.get_executions()
        assert len(executions) == 1
