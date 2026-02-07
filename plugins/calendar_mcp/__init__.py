from .client import get_google_service
from .tools import list_events_tool, create_event_tool, delete_event_tool

def register(api):
    cfg = api.plugin_config

    credentials_path = cfg.get("credentials_path")
    if not credentials_path:
        # Plugin enabled but not configured; don't register tools.
        return

    service = get_google_service(
        api_name="calendar",
        api_version="v3",
        credentials_path=credentials_path,
        token_path=cfg.get("token_path", "token.json")
    )

    api.register_tool(list_events_tool(service))
    api.register_tool(create_event_tool(service))
    api.register_tool(delete_event_tool(service))
