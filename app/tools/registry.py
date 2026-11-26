"""Registry of available tools, keyed by name.

It stores :class:`ToolAdapter` objects, so local and MCP tools live side by side. Tools are
registered by the composition root (``app/container.py``); agents only look them up.
"""

from collections.abc import Iterable, Iterator

from app.tools.interfaces import ToolAdapter, ToolAlreadyRegisteredError, ToolNotFoundError, ToolSpec


class ToolRegistry:
    def __init__(self, adapters: Iterable[ToolAdapter] = ()) -> None:
        self._adapters: dict[str, ToolAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: ToolAdapter, *, replace: bool = False) -> None:
        if adapter.name in self._adapters and not replace:
            raise ToolAlreadyRegisteredError(f"Tool {adapter.name!r} is already registered")
        self._adapters[adapter.name] = adapter

    def unregister(self, name: str) -> None:
        if self._adapters.pop(name, None) is None:
            raise ToolNotFoundError(f"Tool {name!r} is not registered")

    def get(self, name: str) -> ToolAdapter:
        try:
            return self._adapters[name]
        except KeyError:
            available = ", ".join(sorted(self._adapters)) or "none"
            raise ToolNotFoundError(f"Unknown tool {name!r}. Available: {available}") from None

    def list_specs(self) -> list[ToolSpec]:
        return [self._adapters[name].spec for name in sorted(self._adapters)]

    def names(self) -> list[str]:
        return sorted(self._adapters)

    def __contains__(self, name: object) -> bool:
        return name in self._adapters

    def __len__(self) -> int:
        return len(self._adapters)

    def __iter__(self) -> Iterator[ToolAdapter]:
        return iter(self._adapters.values())
