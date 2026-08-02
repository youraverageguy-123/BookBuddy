"""Compile-time reader plugin registry; arbitrary code loading is intentionally unsupported."""
from __future__ import annotations
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ReaderPlugin:
    plugin_id: str
    version: str
    capabilities: tuple[str, ...]
    background_task_types: tuple[str, ...] = ()
    enabled: bool = True


class ReaderPluginRegistry:
    API_VERSION = "reader-plugin-v1"
    def __init__(self):
        plugins = (
            ReaderPlugin("dictionary", "1.0.0", ("dictionary",)),
            ReaderPlugin("story", "1.0.0", ("selection_explanation",), ("analysis",)),
            ReaderPlugin("characters", "1.0.0", ("reader_entity",)),
            ReaderPlugin("translation", "1.0.0", ("translation",), ("translation",)),
            ReaderPlugin("cypher", "0.1.0", ("cypher",), enabled=False),
            ReaderPlugin("timeline", "0.1.0", ("timeline",), enabled=False),
            ReaderPlugin("relationships", "0.1.0", ("relationships",), enabled=False),
            ReaderPlugin("web", "0.1.0", ("web",), ("web",), enabled=False),
        )
        self._plugins = {plugin.plugin_id: plugin for plugin in plugins}

    def list(self) -> list[dict]:
        return [{"api_version": self.API_VERSION, **asdict(plugin)} for plugin in self._plugins.values()]


reader_plugin_registry = ReaderPluginRegistry()
