from .tools import list_lists_tool, list_reminders_tool, create_reminder_tool

def register(api):
    api.register_tool(list_lists_tool())
    api.register_tool(list_reminders_tool())
    api.register_tool(create_reminder_tool())
