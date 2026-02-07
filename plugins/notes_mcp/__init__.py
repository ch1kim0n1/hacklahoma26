from .tools import list_folders_tool, list_notes_tool, create_note_tool

def register(api):
    api.register_tool(list_folders_tool())
    api.register_tool(list_notes_tool())
    api.register_tool(create_note_tool())
