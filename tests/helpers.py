"""Shared test helpers (importable explicitly: ``from tests.helpers import tool_text``)."""
from typing import Any


def tool_text(result: Any) -> str:
    """Join the text of a ``call_tool`` result.

    Supports the fastmcp 4 ToolResult-style object (``.content``) and the
    legacy ``List[TextContent]`` shape.
    """
    content = getattr(result, "content", result)
    return "\n".join(item.text for item in content if hasattr(item, "text"))
