"""Pattern Learning - Recognize and reuse successful patterns.

Patterns are reusable templates for solving common problems:
- Code patterns (implementations, architectures)
- Workflow patterns (sequences of actions)
- Error resolution patterns (how to fix issues)
- Communication patterns (how to respond)

Usage:
    from pms.memory import Pattern, PatternMatcher, PatternType

    matcher = PatternMatcher()

    # Register patterns
    matcher.register(Pattern(
        type=PatternType.WORKFLOW,
        name="test_deploy",
        description="Run tests, build, deploy",
        template=["run_tests", "build", "deploy"],
        triggers=["deploy", "release", "ship"],
    ))

    # Find matching patterns
    matches = await matcher.match("deploy the application")
    for pattern, score in matches:
        print(f"{pattern.name}: {score:.2f}")
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Pattern Types
# =============================================================================


class PatternType(Enum):
    """Types of patterns."""

    CODE = "code"  # Code implementation patterns
    WORKFLOW = "workflow"  # Sequences of actions
    ERROR = "error"  # Error resolution patterns
    COMMUNICATION = "communication"  # Response patterns
    ARCHITECTURE = "architecture"  # System design patterns
    REFACTOR = "refactor"  # Code transformation patterns
    TEST = "test"  # Testing patterns


# =============================================================================
# Pattern Model
# =============================================================================


@dataclass
class Pattern:
    """A reusable pattern.

    Attributes:
        type: Category of pattern
        name: Unique pattern name
        description: Human-readable description
        template: The pattern template (code, steps, etc.)
        triggers: Words/phrases that trigger this pattern
        examples: Example usages
        parameters: Parameters that can be substituted
        success_rate: How often this pattern succeeds
        use_count: Number of times used
        created_at: When first created
        id: Unique identifier
    """

    type: PatternType
    name: str
    description: str
    template: Any  # str for code, list for workflow, dict for structured
    triggers: list[str] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    success_rate: float = 1.0
    use_count: int = 0
    last_used: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def match_score(self, query: str) -> float:
        """Calculate match score for a query.

        Args:
            query: The input query to match

        Returns:
            Score from 0.0 to 1.0
        """
        query_lower = query.lower()
        query_terms = set(re.findall(r"\w+", query_lower))
        score = 0.0

        # Check triggers (highest weight)
        for trigger in self.triggers:
            trigger_lower = trigger.lower()
            if trigger_lower in query_lower:
                score += 0.5
            elif any(t in query_lower for t in trigger_lower.split()):
                score += 0.3

        # Check name
        name_terms = set(re.findall(r"\w+", self.name.lower()))
        name_overlap = len(query_terms & name_terms) / max(len(name_terms), 1)
        score += name_overlap * 0.3

        # Check description
        desc_terms = set(re.findall(r"\w+", self.description.lower()))
        desc_overlap = len(query_terms & desc_terms) / max(len(desc_terms), 1)
        score += desc_overlap * 0.2

        # Apply success rate factor
        score *= self.success_rate

        return min(score, 1.0)

    def apply(self, **params: Any) -> Any:
        """Apply pattern with parameters.

        Args:
            **params: Parameter substitutions

        Returns:
            Applied pattern template
        """
        if isinstance(self.template, str):
            # String template - substitute parameters
            result_str = self.template
            for key, value in params.items():
                result_str = result_str.replace(f"{{{{{key}}}}}", str(value))
                result_str = result_str.replace(f"${key}", str(value))
            return result_str

        elif isinstance(self.template, list):
            # List template (workflow steps) - substitute in each item
            result_list: list[Any] = []
            for item in self.template:
                if isinstance(item, str):
                    processed = item
                    for key, value in params.items():
                        processed = processed.replace(f"{{{{{key}}}}}", str(value))
                    result_list.append(processed)
                else:
                    result_list.append(item)
            return result_list

        elif isinstance(self.template, dict):
            # Dict template - deep substitute
            return self._substitute_dict(self.template, params)

        return self.template

    def _substitute_dict(
        self, d: dict[str, Any], params: dict[str, Any]
    ) -> dict[str, Any]:
        """Recursively substitute parameters in dict."""
        result: dict[str, Any] = {}
        for key, value in d.items():
            if isinstance(value, str):
                for pk, pv in params.items():
                    value = value.replace(f"{{{{{pk}}}}}", str(pv))
                result[key] = value
            elif isinstance(value, dict):
                result[key] = self._substitute_dict(value, params)
            elif isinstance(value, list):
                result[key] = (
                    [
                        self._substitute_dict(v, params)
                        if isinstance(v, dict)
                        else v.replace(f"{{{{{pk}}}}}", str(pv))
                        if isinstance(v, str)
                        else v
                        for v in value
                        for pk, pv in params.items()
                    ]
                    if value
                    else value
                )
            else:
                result[key] = value
        return result

    def record_use(self, success: bool = True) -> None:
        """Record a use of this pattern.

        Args:
            success: Whether the use was successful
        """
        self.use_count += 1
        self.last_used = datetime.now(UTC)

        # Update success rate (exponential moving average)
        alpha = 0.1
        self.success_rate = (1 - alpha) * self.success_rate + alpha * (
            1.0 if success else 0.0
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "description": self.description,
            "template": self.template,
            "triggers": self.triggers,
            "examples": self.examples,
            "parameters": self.parameters,
            "success_rate": self.success_rate,
            "use_count": self.use_count,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Pattern:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            type=PatternType(data["type"]),
            name=data["name"],
            description=data["description"],
            template=data["template"],
            triggers=data.get("triggers", []),
            examples=data.get("examples", []),
            parameters=data.get("parameters", []),
            success_rate=data.get("success_rate", 1.0),
            use_count=data.get("use_count", 0),
            last_used=datetime.fromisoformat(data["last_used"])
            if data.get("last_used")
            else None,
            created_at=datetime.fromisoformat(data["created_at"]),
        )


# =============================================================================
# Pattern Matcher
# =============================================================================


class PatternMatcher:
    """Matches queries to registered patterns.

    Features:
    - Register/unregister patterns
    - Match patterns by query
    - Track usage and success rates
    - Learn new patterns from examples
    """

    def __init__(self) -> None:
        """Initialize pattern matcher."""
        self._patterns: dict[str, Pattern] = {}

    def register(self, pattern: Pattern) -> str:
        """Register a pattern.

        Args:
            pattern: Pattern to register

        Returns:
            Pattern ID
        """
        self._patterns[pattern.id] = pattern
        logger.info(f"Registered pattern: {pattern.name} ({pattern.type.value})")
        return pattern.id

    def unregister(self, pattern_id: str) -> bool:
        """Unregister a pattern.

        Returns:
            True if found and removed
        """
        if pattern_id in self._patterns:
            del self._patterns[pattern_id]
            return True
        return False

    def get(self, pattern_id: str) -> Pattern | None:
        """Get pattern by ID."""
        return self._patterns.get(pattern_id)

    def get_by_name(self, name: str) -> Pattern | None:
        """Get pattern by name."""
        for pattern in self._patterns.values():
            if pattern.name == name:
                return pattern
        return None

    async def match(
        self,
        query: str,
        type_filter: PatternType | None = None,
        min_score: float = 0.3,
        limit: int = 5,
    ) -> list[tuple[Pattern, float]]:
        """Find patterns matching a query.

        Args:
            query: Query to match
            type_filter: Optional type filter
            min_score: Minimum match score
            limit: Maximum results

        Returns:
            List of (pattern, score) tuples
        """
        results: list[tuple[Pattern, float]] = []

        for pattern in self._patterns.values():
            # Apply type filter
            if type_filter and pattern.type != type_filter:
                continue

            # Calculate match score
            score = pattern.match_score(query)

            if score >= min_score:
                results.append((pattern, score))

        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)

        return results[:limit]

    async def apply_pattern(
        self,
        pattern_id: str,
        success: bool = True,
        **params: Any,
    ) -> Any:
        """Apply a pattern and record usage.

        Args:
            pattern_id: ID of pattern to apply
            success: Whether application was successful
            **params: Parameter substitutions

        Returns:
            Applied pattern template
        """
        pattern = self._patterns.get(pattern_id)
        if not pattern:
            raise ValueError(f"Pattern not found: {pattern_id}")

        result = pattern.apply(**params)
        pattern.record_use(success)

        logger.info(f"Applied pattern: {pattern.name} (success={success})")
        return result

    def list_patterns(
        self,
        type_filter: PatternType | None = None,
    ) -> list[Pattern]:
        """List all patterns.

        Args:
            type_filter: Optional type filter

        Returns:
            List of patterns
        """
        patterns = list(self._patterns.values())

        if type_filter:
            patterns = [p for p in patterns if p.type == type_filter]

        # Sort by use count descending
        patterns.sort(key=lambda p: p.use_count, reverse=True)

        return patterns

    def get_stats(self) -> dict[str, Any]:
        """Get pattern matcher statistics."""
        by_type: dict[str, int] = {}
        total_uses = 0
        avg_success = 0.0

        for p in self._patterns.values():
            by_type[p.type.value] = by_type.get(p.type.value, 0) + 1
            total_uses += p.use_count
            avg_success += p.success_rate

        if self._patterns:
            avg_success /= len(self._patterns)

        return {
            "total_patterns": len(self._patterns),
            "by_type": by_type,
            "total_uses": total_uses,
            "average_success_rate": avg_success,
        }


# =============================================================================
# Built-in Patterns
# =============================================================================


def get_builtin_patterns() -> list[Pattern]:
    """Get built-in workflow patterns."""
    return [
        # Workflow patterns
        Pattern(
            type=PatternType.WORKFLOW,
            name="test_and_deploy",
            description="Run tests, then build and deploy if tests pass",
            template=[
                {"action": "run_tests", "on_failure": "stop"},
                {"action": "build", "on_failure": "stop"},
                {"action": "deploy", "condition": "steps.build.success"},
            ],
            triggers=["deploy", "release", "ship", "publish"],
            parameters=["environment", "version"],
        ),
        Pattern(
            type=PatternType.WORKFLOW,
            name="sync_and_test",
            description="Sync to remote server and run tests",
            template=[
                {"action": "sync_push", "params": {"host": "{{host}}"}},
                {"action": "run_remote_tests", "params": {"host": "{{host}}"}},
            ],
            triggers=["sync", "test remote", "remote test"],
            parameters=["host", "project"],
        ),
        Pattern(
            type=PatternType.WORKFLOW,
            name="create_feature_branch",
            description="Create a new feature branch with standard setup",
            template=[
                {"action": "git_checkout", "params": {"branch": "main"}},
                {"action": "git_pull"},
                {
                    "action": "git_branch",
                    "params": {"name": "feature/{{feature_name}}"},
                },
            ],
            triggers=["new feature", "feature branch", "start feature"],
            parameters=["feature_name"],
        ),
        # Code patterns
        Pattern(
            type=PatternType.CODE,
            name="async_crud_service",
            description="Async CRUD service pattern",
            template='''class {{name}}Service:
    """Service for {{entity}} operations."""

    def __init__(self, repository: {{name}}Repository):
        self._repo = repository

    async def create(self, data: {{name}}Create) -> {{name}}:
        """Create a new {{entity}}."""
        return await self._repo.create(data)

    async def get(self, id: str) -> {{name}} | None:
        """Get {{entity}} by ID."""
        return await self._repo.get(id)

    async def list(self, limit: int = 100) -> list[{{name}}]:
        """List all {{entity}}s."""
        return await self._repo.list(limit=limit)

    async def update(self, id: str, data: {{name}}Update) -> {{name}} | None:
        """Update {{entity}}."""
        return await self._repo.update(id, data)

    async def delete(self, id: str) -> bool:
        """Delete {{entity}}."""
        return await self._repo.delete(id)
''',
            triggers=["crud service", "service layer", "async service"],
            parameters=["name", "entity"],
        ),
        Pattern(
            type=PatternType.CODE,
            name="pytest_async_test",
            description="Async pytest test pattern",
            template='''import pytest

@pytest.fixture
async def {{fixture_name}}():
    """Create {{entity}} fixture."""
    {{entity}} = await create_{{entity}}()
    yield {{entity}}
    await cleanup_{{entity}}({{entity}})


class Test{{name}}:
    """Tests for {{name}}."""

    @pytest.mark.anyio
    async def test_{{action}}(self, {{fixture_name}}):
        """Test {{action}} functionality."""
        result = await {{fixture_name}}.{{action}}()
        assert result is not None
''',
            triggers=["async test", "pytest async", "test fixture"],
            parameters=["name", "fixture_name", "entity", "action"],
        ),
        # Error patterns
        Pattern(
            type=PatternType.ERROR,
            name="import_cycle_fix",
            description="Fix circular import errors",
            template={
                "problem": "Circular import between modules",
                "solution": [
                    "Identify the shared types causing the cycle",
                    "Create a separate types.py module",
                    "Move shared types to the new module",
                    "Import from types.py in both original modules",
                ],
                "prevention": "Use TYPE_CHECKING for type-only imports",
            },
            triggers=["import cycle", "circular import", "importerror"],
            parameters=[],
        ),
        Pattern(
            type=PatternType.ERROR,
            name="async_not_awaited_fix",
            description="Fix 'coroutine was never awaited' warning",
            template={
                "problem": "Coroutine was never awaited",
                "solution": [
                    "Find the async function call",
                    "Add 'await' before the call",
                    "Ensure calling function is also async",
                ],
                "code_example": "result = await async_function()  # Add await",
            },
            triggers=["never awaited", "coroutine", "async warning"],
            parameters=[],
        ),
        # Architecture patterns
        Pattern(
            type=PatternType.ARCHITECTURE,
            name="repository_pattern",
            description="Repository pattern for data access",
            template={
                "layers": [
                    {"name": "Model", "purpose": "Data structure definition"},
                    {"name": "Repository", "purpose": "Data access abstraction"},
                    {"name": "Service", "purpose": "Business logic"},
                    {"name": "Controller/CLI", "purpose": "Interface layer"},
                ],
                "benefits": [
                    "Separation of concerns",
                    "Testability (mock repository)",
                    "Swappable storage backends",
                ],
            },
            triggers=["repository", "data access", "architecture pattern"],
            parameters=[],
        ),
    ]


# =============================================================================
# Global Instance
# =============================================================================

_global_matcher: PatternMatcher | None = None


def get_pattern_matcher() -> PatternMatcher:
    """Get the global pattern matcher instance."""
    global _global_matcher
    if _global_matcher is None:
        _global_matcher = PatternMatcher()
        # Register built-in patterns
        for pattern in get_builtin_patterns():
            _global_matcher.register(pattern)
    return _global_matcher


def set_pattern_matcher(matcher: PatternMatcher) -> None:
    """Set the global pattern matcher instance."""
    global _global_matcher
    _global_matcher = matcher
