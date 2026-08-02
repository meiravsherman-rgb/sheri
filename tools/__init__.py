"""Tool registry — every tool registers itself here on import."""

from typing import Any, Callable, TypedDict


class ToolDef(TypedDict):
    schema: dict[str, Any]
    fn: Callable


TOOL_REGISTRY: dict[str, ToolDef] = {}
