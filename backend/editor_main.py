# EDITOR MODULE — Isolated module, no dependencies on other project files

from editor_routes import editor_router

# ADD THIS ONE LINE TO main.py:
# app.include_router(editor_router)

__all__ = ["editor_router"]
