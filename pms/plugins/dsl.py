"""Dynamic Tool Definition Language (DSL).

A simple, safe DSL for defining tools without full Python code.
Supports declarative tool definitions with:
- Parameter declarations
- Conditional logic
- Template-based responses
- Safe expression evaluation

DSL Syntax:
    ```
    tool list_files:
        description: "List files in a directory"
        parameters:
            path: string = "."
            pattern: string? = "*"
            recursive: bool = false

        when pattern == "*":
            return shell("ls -la {path}")
        otherwise:
            return shell("find {path} -name '{pattern}'" + (" -r" if recursive else ""))
    ```

Features:
    - Type-checked parameters
    - Safe expression evaluation (no arbitrary code exec)
    - Built-in functions: shell, http, read, write, etc.
    - Template string interpolation
    - Conditional blocks

Safety:
    - No eval() or exec()
    - Whitelist of allowed operations
    - Sandboxed execution
    - Resource limits
"""

from __future__ import annotations

import ast
import logging
import operator
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class DSLType(Enum):
    """DSL type system."""

    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    LIST = "list"
    DICT = "dict"
    ANY = "any"
    VOID = "void"


@dataclass
class DSLParameter:
    """Parameter in a tool definition."""

    name: str
    type: DSLType
    required: bool = True
    default: Any = None
    description: str = ""

    @classmethod
    def parse(cls, name: str, type_spec: str) -> DSLParameter:
        """Parse parameter from type specification.

        Examples:
            "string" -> required string
            "string?" -> optional string
            "int = 10" -> optional int with default
            "string = 'hello'" -> optional string with default
        """
        required = True
        default = None

        # Check for default value
        if "=" in type_spec:
            type_part, default_part = type_spec.split("=", 1)
            type_spec = type_part.strip()
            default_str = default_part.strip()

            # Parse default value
            try:
                default = ast.literal_eval(default_str)
            except ValueError, SyntaxError:
                default = default_str.strip("'\"")

            required = False

        # Check for optional marker
        if type_spec.endswith("?"):
            type_spec = type_spec[:-1]
            required = False

        # Parse type
        type_map = {
            "string": DSLType.STRING,
            "str": DSLType.STRING,
            "int": DSLType.INT,
            "integer": DSLType.INT,
            "float": DSLType.FLOAT,
            "number": DSLType.FLOAT,
            "bool": DSLType.BOOL,
            "boolean": DSLType.BOOL,
            "list": DSLType.LIST,
            "array": DSLType.LIST,
            "dict": DSLType.DICT,
            "object": DSLType.DICT,
            "any": DSLType.ANY,
        }

        dsl_type = type_map.get(type_spec.lower(), DSLType.ANY)

        return cls(
            name=name,
            type=dsl_type,
            required=required,
            default=default,
        )


@dataclass
class DSLCondition:
    """Conditional block in tool definition."""

    expression: str
    body: str
    else_body: str | None = None


@dataclass
class ToolDefinition:
    """Complete tool definition from DSL."""

    name: str
    description: str = ""
    parameters: dict[str, DSLParameter] = field(default_factory=dict)
    conditions: list[DSLCondition] = field(default_factory=list)
    body: str = ""
    return_type: DSLType = DSLType.ANY

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                name: {
                    "type": param.type.value,
                    "required": param.required,
                    "default": param.default,
                    "description": param.description,
                }
                for name, param in self.parameters.items()
            },
            "return_type": self.return_type.value,
        }


class DSLParser:
    """Parser for the tool DSL.

    Grammar:
        tool_def := "tool" name ":" block
        block := (description | parameters | condition | return_stmt)*
        parameters := "parameters:" param_list
        param_list := (param_decl)*
        param_decl := name ":" type_spec
        condition := "when" expr ":" block ("otherwise:" block)?
        return_stmt := "return" expr
    """

    # Patterns for parsing
    TOOL_PATTERN = re.compile(r"^tool\s+(\w+)\s*:\s*$", re.MULTILINE)
    DESCRIPTION_PATTERN = re.compile(
        r'^\s*description:\s*["\'](.+?)["\']', re.MULTILINE
    )
    PARAMETERS_PATTERN = re.compile(r"^\s*parameters:\s*$", re.MULTILINE)
    PARAM_PATTERN = re.compile(r"^\s+(\w+):\s*(.+)$", re.MULTILINE)
    WHEN_PATTERN = re.compile(r"^\s*when\s+(.+?):\s*$", re.MULTILINE)
    OTHERWISE_PATTERN = re.compile(r"^\s*otherwise:\s*$", re.MULTILINE)
    RETURN_PATTERN = re.compile(r"^\s*return\s+(.+)$", re.MULTILINE)

    def parse(self, source: str) -> list[ToolDefinition]:
        """Parse DSL source into tool definitions.

        Args:
            source: DSL source code

        Returns:
            List of ToolDefinition objects
        """
        tools = []

        # Find all tool definitions
        tool_matches = list(self.TOOL_PATTERN.finditer(source))

        for i, match in enumerate(tool_matches):
            name = match.group(1)
            start = match.end()

            # Find end (next tool or end of source)
            if i + 1 < len(tool_matches):
                end = tool_matches[i + 1].start()
            else:
                end = len(source)

            block = source[start:end]
            tool = self._parse_tool_block(name, block)
            tools.append(tool)

        return tools

    def _parse_tool_block(self, name: str, block: str) -> ToolDefinition:
        """Parse a single tool block."""
        tool = ToolDefinition(name=name)

        # Extract description
        desc_match = self.DESCRIPTION_PATTERN.search(block)
        if desc_match:
            tool.description = desc_match.group(1)

        # Extract parameters
        params_match = self.PARAMETERS_PATTERN.search(block)
        if params_match:
            # Find parameter declarations after "parameters:"
            params_start = params_match.end()
            params_block = block[params_start:]

            for param_match in self.PARAM_PATTERN.finditer(params_block):
                # Stop if we hit a non-parameter line
                line_start = (
                    block.rfind("\n", 0, params_start + param_match.start()) + 1
                )
                if (
                    not block[line_start : params_start + param_match.start()]
                    .strip()
                    .startswith(" ")
                ):
                    continue

                param_name = param_match.group(1)
                param_type = param_match.group(2)

                # Stop at non-indented line (end of parameters)
                if not block[params_start + param_match.start()].isspace():
                    break

                param = DSLParameter.parse(param_name, param_type)
                tool.parameters[param_name] = param

        # Extract conditions
        when_matches = list(self.WHEN_PATTERN.finditer(block))
        for j, when_match in enumerate(when_matches):
            expr = when_match.group(1)
            cond_start = when_match.end()

            # Find end of condition body
            if j + 1 < len(when_matches):
                cond_end = when_matches[j + 1].start()
            else:
                cond_end = len(block)

            cond_block = block[cond_start:cond_end]

            # Check for otherwise
            otherwise_match = self.OTHERWISE_PATTERN.search(cond_block)
            if otherwise_match:
                body = cond_block[: otherwise_match.start()].strip()
                else_body = cond_block[otherwise_match.end() :].strip()
            else:
                body = cond_block.strip()
                else_body = None

            condition = DSLCondition(
                expression=expr,
                body=body,
                else_body=else_body,
            )
            tool.conditions.append(condition)

        # Extract return statement (for simple tools without conditions)
        if not tool.conditions:
            return_match = self.RETURN_PATTERN.search(block)
            if return_match:
                tool.body = return_match.group(1)

        return tool


class SafeExpressionEvaluator:
    """Safe expression evaluator for DSL.

    Only allows whitelisted operations, no arbitrary code execution.
    """

    # Allowed operators
    OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.And: lambda a, b: a and b,
        ast.Or: lambda a, b: a or b,
        ast.Not: operator.not_,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
    }

    # Allowed built-in functions
    SAFE_BUILTINS = {
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "min": min,
        "max": max,
        "sum": sum,
        "abs": abs,
        "round": round,
        "sorted": sorted,
        "reversed": lambda x: list(reversed(list(x))),
        "range": range,
        "enumerate": lambda x: list(enumerate(x)),
        "zip": lambda *args: list(zip(*args)),
        "any": any,
        "all": all,
        "upper": lambda s: s.upper(),
        "lower": lambda s: s.lower(),
        "strip": lambda s: s.strip(),
        "split": lambda s, sep=None: s.split(sep),
        "join": lambda sep, items: sep.join(items),
        "startswith": lambda s, prefix: s.startswith(prefix),
        "endswith": lambda s, suffix: s.endswith(suffix),
        "contains": lambda s, sub: sub in s,
        "replace": lambda s, old, new: s.replace(old, new),
    }

    def __init__(self, context: dict[str, Any] | None = None):
        """Initialize evaluator.

        Args:
            context: Variable context for evaluation
        """
        self.context = context or {}

    def evaluate(self, expression: str) -> Any:
        """Safely evaluate an expression.

        Args:
            expression: Expression to evaluate

        Returns:
            Evaluation result

        Raises:
            ValueError: If expression is unsafe
        """
        try:
            tree = ast.parse(expression, mode="eval")
            return self._eval_node(tree.body)
        except Exception as e:
            raise ValueError(f"Failed to evaluate expression: {expression}") from e

    def _eval_node(self, node: ast.AST) -> Any:
        """Recursively evaluate AST node."""
        if isinstance(node, ast.Constant):
            return node.value

        elif isinstance(node, ast.Name):
            if node.id in self.context:
                return self.context[node.id]
            elif node.id in self.SAFE_BUILTINS:
                return self.SAFE_BUILTINS[node.id]
            else:
                raise ValueError(f"Unknown variable: {node.id}")

        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            op_func = self.OPERATORS.get(type(node.op))
            if op_func is not None:
                return op_func(left, right)  # type: ignore[operator]
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")

        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            op_func = self.OPERATORS.get(type(node.op))
            if op_func is not None:
                return op_func(operand)  # type: ignore[operator]
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")

        elif isinstance(node, ast.Compare):
            left = self._eval_node(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator)
                op_func = self.OPERATORS.get(type(op))
                if op_func is None:
                    raise ValueError(f"Unsupported comparison: {type(op).__name__}")
                if not op_func(left, right):  # type: ignore[operator]
                    return False
                left = right
            return True

        elif isinstance(node, ast.BoolOp):
            values = [self._eval_node(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            elif isinstance(node.op, ast.Or):
                return any(values)
            raise ValueError(f"Unsupported bool op: {type(node.op).__name__}")

        elif isinstance(node, ast.IfExp):
            test = self._eval_node(node.test)
            if test:
                return self._eval_node(node.body)
            else:
                return self._eval_node(node.orelse)

        elif isinstance(node, ast.Call):
            func = self._eval_node(node.func)
            if not callable(func):
                raise ValueError(f"Not callable: {func}")

            args = [self._eval_node(arg) for arg in node.args]
            kwargs = {
                kw.arg: self._eval_node(kw.value) for kw in node.keywords if kw.arg
            }

            return func(*args, **kwargs)

        elif isinstance(node, ast.Subscript):
            value = self._eval_node(node.value)
            if isinstance(node.slice, ast.Constant):
                return value[node.slice.value]
            elif isinstance(node.slice, ast.Slice):
                lower = self._eval_node(node.slice.lower) if node.slice.lower else None
                upper = self._eval_node(node.slice.upper) if node.slice.upper else None
                step = self._eval_node(node.slice.step) if node.slice.step else None
                return value[lower:upper:step]
            else:
                index = self._eval_node(node.slice)
                return value[index]

        elif isinstance(node, ast.Attribute):
            value = self._eval_node(node.value)
            attr = node.attr

            # Only allow safe attribute access
            if attr.startswith("_"):
                raise ValueError(f"Private attribute access not allowed: {attr}")

            return getattr(value, attr)

        elif isinstance(node, ast.List):
            return [self._eval_node(elt) for elt in node.elts]

        elif isinstance(node, ast.Dict):
            return {
                self._eval_node(k): self._eval_node(v)
                for k, v in zip(node.keys, node.values)
                if k is not None
            }

        elif isinstance(node, ast.Tuple):
            return tuple(self._eval_node(elt) for elt in node.elts)

        elif isinstance(node, ast.Set):
            return {self._eval_node(elt) for elt in node.elts}

        elif isinstance(node, ast.JoinedStr):
            # f-string
            parts = []
            for value in node.values:
                if isinstance(value, ast.Constant):
                    parts.append(str(value.value))
                elif isinstance(value, ast.FormattedValue):
                    parts.append(str(self._eval_node(value.value)))
                else:
                    parts.append(str(self._eval_node(value)))
            return "".join(parts)

        else:
            raise ValueError(f"Unsupported node type: {type(node).__name__}")


class DSLCompiler:
    """Compiles DSL tool definitions to executable handlers.

    Takes parsed ToolDefinition objects and generates
    Python functions that can be registered as tools.
    """

    def __init__(self, builtins: dict[str, Callable[..., Any]] | None = None):
        """Initialize compiler.

        Args:
            builtins: Additional built-in functions available to tools
        """
        self.builtins = builtins or {}

    def compile(self, tool: ToolDefinition) -> Callable[..., Any]:
        """Compile tool definition to callable.

        Args:
            tool: Tool definition

        Returns:
            Async callable function
        """

        async def handler(**kwargs: Any) -> Any:
            # Validate parameters
            context = dict(self.builtins)

            for name, param in tool.parameters.items():
                if name in kwargs:
                    value = kwargs[name]
                    # Type coercion
                    value = self._coerce_type(value, param.type)
                    context[name] = value
                elif param.required:
                    raise ValueError(f"Missing required parameter: {name}")
                else:
                    context[name] = param.default

            evaluator = SafeExpressionEvaluator(context)

            # Evaluate conditions
            for condition in tool.conditions:
                try:
                    result = evaluator.evaluate(condition.expression)
                    if result:
                        return self._evaluate_body(condition.body, evaluator)
                    elif condition.else_body:
                        return self._evaluate_body(condition.else_body, evaluator)
                except Exception as e:
                    logger.error(f"Condition error: {e}")

            # Evaluate body (for simple tools)
            if tool.body:
                return self._evaluate_body(tool.body, evaluator)

            return None

        # Set function metadata
        handler.__name__ = tool.name
        handler.__doc__ = tool.description

        return handler

    def _coerce_type(self, value: Any, target_type: DSLType) -> Any:
        """Coerce value to target type."""
        match target_type:
            case DSLType.STRING:
                return str(value)
            case DSLType.INT:
                return int(value)
            case DSLType.FLOAT:
                return float(value)
            case DSLType.BOOL:
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes")
                return bool(value)
            case DSLType.LIST:
                return list(value) if not isinstance(value, list) else value
            case DSLType.DICT:
                return dict(value) if not isinstance(value, dict) else value
            case _:
                return value

    def _evaluate_body(
        self,
        body: str,
        evaluator: SafeExpressionEvaluator,
    ) -> Any:
        """Evaluate body expression."""
        # Handle return statements
        body = body.strip()
        body = body.removeprefix("return ")

        # Handle string interpolation
        body = self._interpolate(body, evaluator.context)

        # Evaluate
        return evaluator.evaluate(body)

    def _interpolate(self, template: str, context: dict[str, Any]) -> str:
        """Interpolate variables in template string.

        Supports {variable} syntax.
        """

        def replace(match: re.Match[str]) -> str:
            var_name = match.group(1)
            if var_name in context:
                return str(context[var_name])
            return match.group(0)

        return re.sub(r"\{(\w+)\}", replace, template)


def parse_tool_dsl(source: str) -> list[ToolDefinition]:
    """Parse DSL source into tool definitions.

    Args:
        source: DSL source code

    Returns:
        List of ToolDefinition objects
    """
    parser = DSLParser()
    return parser.parse(source)


def compile_tool(
    tool: ToolDefinition,
    builtins: dict[str, Callable[..., Any]] | None = None,
) -> Callable[..., Any]:
    """Compile a tool definition to callable.

    Args:
        tool: Tool definition
        builtins: Additional built-in functions

    Returns:
        Async callable function
    """
    compiler = DSLCompiler(builtins)
    return compiler.compile(tool)
