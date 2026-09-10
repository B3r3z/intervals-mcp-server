"""Declare coach tools once and install an immutable catalogue for each server."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
import os
from typing import Any, Literal, TypeVar, cast
from weakref import WeakKeyDictionary

from mcp.server.fastmcp import FastMCP
from intervals_mcp_server.contracts import ReadResponse

AccessMode = Literal["admin", "coach", "readonly"]
Access = Literal["read", "introspection", "safe_write", "write_status", "legacy_write"]
Effect = Literal["none", "read", "write", "memory"]
F = TypeVar("F", bound=Callable[..., Any])
_MODES: tuple[AccessMode, ...] = ("admin", "coach", "readonly")


@dataclass(frozen=True)
class ToolDefinition:
    handler: Callable[..., Any]
    access: Access
    upstream: Effect
    local: Effect

    @property
    def name(self) -> str:
        return self.handler.__name__

    def allowed(self, mode: AccessMode) -> bool:
        if self.access == "legacy_write":
            return mode == "admin"
        if self.access == "safe_write":
            return mode in {"admin", "coach"}
        return True


_definitions: dict[str, ToolDefinition] = {}
_installed: WeakKeyDictionary[FastMCP, ToolCatalogue] = WeakKeyDictionary()


def coach_tool(*, access: Access, upstream: Effect, local: Effect = "none") -> Callable[[F], F]:
    """Declare availability and effects without registering a callable server tool."""
    if access not in {"read", "introspection", "safe_write", "write_status", "legacy_write"}:
        raise ValueError("tool requires a known access classification")
    if upstream not in {"none", "read", "write"} or local not in {"none", "read", "write", "memory"}:
        raise ValueError("tool requires known upstream and local effects")
    if upstream == "write" and access not in {"safe_write", "legacy_write"}:
        raise ValueError("upstream mutations require write access")
    if access in {"safe_write", "legacy_write"} and upstream != "write":
        raise ValueError("write access requires an upstream mutation effect")

    def declare(handler: F) -> F:
        name = handler.__name__
        if name in _definitions:
            raise ValueError(f"duplicate tool identity: {name}")
        _definitions[name] = ToolDefinition(handler, access, upstream, local)
        return handler

    return declare


def resolve_access_mode(value: str) -> AccessMode:
    """Unknown configuration fails closed; mode changes require a new server."""
    mode = value.lower()
    return cast(AccessMode, mode) if mode in {"admin", "coach", "readonly"} else "readonly"


@dataclass(frozen=True)
class ToolCatalogue:
    mode: AccessMode
    definitions: tuple[ToolDefinition, ...]

    def selected(self) -> tuple[ToolDefinition, ...]:
        return tuple(tool for tool in self.definitions if tool.allowed(self.mode))

    def names(self, *access: Access) -> list[str]:
        return [tool.name for tool in self.selected() if not access or tool.access in access]

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "access": tool.access,
                "effects": {"upstream": tool.upstream, "local": tool.local},
                "allowed_modes": [
                    mode for mode in _MODES if tool.allowed(mode)
                ],
                "implemented": True,
                "live_verified": False,
            }
            for tool in self.selected()
        ]


def tool_catalogue(mode: str) -> ToolCatalogue:
    # Load declarations before taking a snapshot. Imports do not install tools.
    from intervals_mcp_server import tools as _tools  # noqa: F401

    return ToolCatalogue(resolve_access_mode(mode), tuple(_definitions.values()))


@lru_cache(maxsize=1)
def default_catalogue() -> ToolCatalogue:
    return tool_catalogue(os.getenv("INTERVALS_ACCESS_MODE", "admin"))


def register_tools(mcp_instance: FastMCP, mode: str | None = None) -> ToolCatalogue:
    """Install declared tools; repeated installation cannot change a server's mode."""
    catalogue = default_catalogue() if mode is None else tool_catalogue(mode)
    previous = _installed.get(mcp_instance)
    if previous is not None:
        if previous != catalogue:
            raise ValueError("server already has a different tool catalogue")
        return previous

    from intervals_mcp_server.tools.capabilities import capabilities_for

    async def installed_capabilities() -> ReadResponse[dict]:
        return capabilities_for(catalogue)

    for definition in catalogue.selected():
        handler = definition.handler
        if definition.name == "get_capabilities":
            handler = installed_capabilities
        mcp_instance.add_tool(
            handler, name=definition.name, description=definition.handler.__doc__
        )
    _installed[mcp_instance] = catalogue
    return catalogue
