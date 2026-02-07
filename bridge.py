import json
import importlib
import sys
from pathlib import Path

class PluginAPI:
    def __init__(self, plugin_config, tools):
        self.plugin_config = plugin_config
        self._tools = tools

    def register_tool(self, tool):
        self._tools.append(tool)


def load_plugins(plugins_dir: str, user_config: dict):
    tools = []

    plugins_path = Path(plugins_dir)

    for plugin_dir in plugins_path.iterdir():
        if not plugin_dir.is_dir():
            continue

        manifest_path = plugin_dir / "plugin.json"
        if not manifest_path.exists():
            continue

        manifest = json.loads(manifest_path.read_text())
        plugin_id = manifest["id"]

        if plugin_id not in user_config:
            continue

        # Only load on allowed platforms (e.g. ["darwin"] for Mac-only)
        platforms = manifest.get("platforms")
        if platforms is not None and sys.platform not in platforms:
            continue

        try:
            module = importlib.import_module(f"plugins.{plugin_dir.name}")

            api = PluginAPI(
                plugin_config=user_config[plugin_id],
                tools=tools,
            )

            module.register(api)
        except Exception as exc:
            # Plugin dependencies can be optional (e.g. Google OAuth libs).
            # Skip failed plugins so other tools can still load.
            print(f"[bridge] Skipping plugin '{plugin_id}' due to error: {exc}", file=sys.stderr)
            continue

    return tools