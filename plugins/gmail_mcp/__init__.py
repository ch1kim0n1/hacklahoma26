from .client import get_google_service
from .tools import list_messages_tool, get_message_tool, send_message_tool

def register(api):
    cfg = api.plugin_config

    service = get_google_service(
        api_name="gmail",
        api_version="v1",
        credentials_path=cfg["credentials_path"],
        token_path=cfg.get("token_path", "token.json")
    )

    api.register_tool(list_messages_tool(service))
    api.register_tool(get_message_tool(service))
    api.register_tool(send_message_tool(service))
