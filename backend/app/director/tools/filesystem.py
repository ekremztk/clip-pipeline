"""Director filesystem tools — read/search/edit project files."""

import os
import re
from pathlib import Path
from app.config import settings

PROJECT_ROOT = Path(settings.PROJECT_ROOT)

# Paths Director can read freely
READABLE_PATTERNS = [
    "docs/**/*.md",
    "backend/app/**/*.py",
    "backend/migrations/**/*.sql",
    "frontend/app/**/*.tsx",
    "frontend/app/**/*.ts",
    "backend/requirements.txt",
    "backend/app/config.py",
]

# Paths Director can NEVER touch
LOCKED_PATHS = [
    "backend/reframer.py",
    "backend/app/memory/",
    "frontend/next.config.js",
    "backend/app/pipeline/steps/s01_",
    "backend/app/pipeline/steps/s02_",
    "backend/app/pipeline/steps/s03_",
    "backend/app/pipeline/steps/s04_",
]

# Code files require user confirmation before edit (enforced in router/agent)
CODE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".json"}
MD_EXTENSIONS = {".md", ".txt"}


def _resolve_path(path: str) -> Path:
    """Resolve a relative path against PROJECT_ROOT safely."""
    resolved = (PROJECT_ROOT / path).resolve()
    if not str(resolved).startswith(str(PROJECT_ROOT)):
        raise ValueError(f"Path outside project root: {path}")
    return resolved


def _is_locked(path: str) -> bool:
    for locked in LOCKED_PATHS:
        if locked in path:
            return True
    return False


def read_file(path: str) -> str:
    """
    Read any project file (MD, Python, TypeScript, SQL, JSON).
    path is relative to project root.
    """
    try:
        if _is_locked(path):
            return f"[LOCKED] {path} is protected and cannot be read by Director."
        resolved = _resolve_path(path)
        if not resolved.exists():
            return f"[NOT FOUND] {path}"
        content = resolved.read_text(encoding="utf-8", errors="replace")
        # Truncate very large files
        if len(content) > 50_000:
            content = content[:50_000] + f"\n\n[TRUNCATED — file is {len(content)} chars, showing first 50000]"
        return content
    except Exception as e:
        return f"[ERROR] read_file({path}): {e}"


def list_files(directory: str, pattern: str = "*") -> list[str]:
    """List files in a directory matching a glob pattern."""
    try:
        resolved = _resolve_path(directory)
        if not resolved.exists():
            return [f"[NOT FOUND] {directory}"]
        matches = list(resolved.glob(pattern))
        return [str(m.relative_to(PROJECT_ROOT)) for m in sorted(matches) if m.is_file()]
    except Exception as e:
        return [f"[ERROR] list_files({directory}): {e}"]


def search_codebase(query: str, file_pattern: str | None = None) -> list[dict]:
    """
    Search codebase with regex. Returns [{file, line, content}].
    file_pattern: e.g. "*.py", "*.md"
    """
    try:
        results = []
        glob_pattern = f"**/{file_pattern}" if file_pattern else "**/*"

        for filepath in PROJECT_ROOT.glob(glob_pattern):
            if not filepath.is_file():
                continue
            if _is_locked(str(filepath.relative_to(PROJECT_ROOT))):
                continue
            # Skip binaries and node_modules
            rel = str(filepath.relative_to(PROJECT_ROOT))
            if any(skip in rel for skip in ["node_modules", "__pycache__", ".git", "output/", "temp_uploads/"]):
                continue
            try:
                text = filepath.read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(text.splitlines(), 1):
                    if re.search(query, line, re.IGNORECASE):
                        results.append({
                            "file": rel,
                            "line": i,
                            "content": line.strip()
                        })
                        if len(results) >= 100:
                            return results
            except Exception:
                continue
        return results
    except Exception as e:
        return [{"error": str(e)}]


def edit_file(path: str, old_content: str, new_content: str) -> dict:
    """
    Replace old_content with new_content in a file.
    MD files: immediate.
    Code files: returns {"requires_confirmation": True, ...} — agent must ask user first.
    """
    try:
        if _is_locked(path):
            return {"success": False, "error": f"{path} is locked and cannot be edited."}

        resolved = _resolve_path(path)
        if not resolved.exists():
            return {"success": False, "error": f"File not found: {path}"}

        ext = resolved.suffix.lower()
        if ext in CODE_EXTENSIONS:
            return {
                "requires_confirmation": True,
                "path": path,
                "old_content": old_content,
                "new_content": new_content,
                "message": f"This will edit a code file ({path}). Please confirm."
            }

        current = resolved.read_text(encoding="utf-8")
        if old_content not in current:
            return {"success": False, "error": f"old_content not found in {path}"}

        updated = current.replace(old_content, new_content, 1)
        resolved.write_text(updated, encoding="utf-8")
        return {"success": True, "path": path}
    except Exception as e:
        return {"success": False, "error": str(e)}


def apply_confirmed_edit(path: str, old_content: str, new_content: str) -> dict:
    """Apply a code file edit that the user has explicitly confirmed."""
    try:
        if _is_locked(path):
            return {"success": False, "error": f"{path} is locked."}
        resolved = _resolve_path(path)
        if not resolved.exists():
            return {"success": False, "error": f"File not found: {path}"}
        current = resolved.read_text(encoding="utf-8")
        if old_content not in current:
            return {"success": False, "error": "old_content not found (file may have changed)"}
        updated = current.replace(old_content, new_content, 1)
        resolved.write_text(updated, encoding="utf-8")
        return {"success": True, "path": path}
    except Exception as e:
        return {"success": False, "error": str(e)}
