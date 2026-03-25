"""Director filesystem tools — read/search/edit project files."""

import os
import re
from pathlib import Path

# ─── Auto-detect roots (works both locally and in Docker) ───────────────────
# This file: .../backend/app/director/tools/filesystem.py
#         or /app/app/director/tools/filesystem.py (Docker WORKDIR=/app)
_THIS_FILE = Path(os.path.abspath(__file__))
# Go up 4 levels to find backend root: tools → director → app → backend (or /app)
BACKEND_ROOT = _THIS_FILE.parent.parent.parent.parent

# If monorepo root has a "frontend/" sibling next to backend, use that as project root
_maybe_project = BACKEND_ROOT.parent
if (_maybe_project / "frontend").exists():
    PROJECT_ROOT = _maybe_project    # local: /Users/.../prognot
    _LOCAL_MODE = True
else:
    PROJECT_ROOT = BACKEND_ROOT      # Docker: /app
    _LOCAL_MODE = False

# Alternate backend prefix for path normalization
# Local: "backend/" prefix in paths; Docker: paths start with "app/" directly
_BACKEND_PREFIX = "backend/" if _LOCAL_MODE else ""
_APP_PREFIX = "app/" if not _LOCAL_MODE else "backend/app/"


# Paths Director can NEVER touch (read or write)
LOCKED_PATHS = [
    "reframer.py",
    "app/memory/",
    "backend/app/memory/",
    "frontend/next.config.js",
    "next.config.js",
    "pipeline/steps/s01_",
    "pipeline/steps/s02_",
    "pipeline/steps/s03_",
    "pipeline/steps/s04_",
]

# Code files require user confirmation before edit (enforced in router/agent)
CODE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".json"}
MD_EXTENSIONS = {".md", ".txt"}


def _normalize_path(path: str) -> str:
    """
    Normalize path to work in both local and Docker environments.
    - Local paths use 'backend/app/...' or 'frontend/...' or 'docs/...'
    - Docker paths use 'app/...' (no backend prefix)
    Director can pass either form — we try to resolve both.
    """
    return path


def _resolve_path(path: str) -> Path:
    """Resolve a relative path against PROJECT_ROOT safely, trying fallbacks."""
    # Primary: path as given
    resolved = (PROJECT_ROOT / path).resolve()
    if str(resolved).startswith(str(PROJECT_ROOT)) and resolved.exists():
        return resolved

    # Fallback 1: if path starts with "backend/" and we're in Docker, strip it
    if path.startswith("backend/") and not _LOCAL_MODE:
        alt = path[len("backend/"):]
        resolved2 = (BACKEND_ROOT / alt).resolve()
        if resolved2.exists():
            return resolved2

    # Fallback 2: if path starts with "app/" and we're local, prepend "backend/"
    if path.startswith("app/") and _LOCAL_MODE:
        alt = "backend/" + path
        resolved3 = (PROJECT_ROOT / alt).resolve()
        if resolved3.exists():
            return resolved3

    # Return original (even if not found — caller checks .exists())
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
            # Try from BACKEND_ROOT directly for short paths like "app/director"
            alt = (BACKEND_ROOT / directory).resolve()
            if alt.exists():
                resolved = alt
            else:
                return [f"[NOT FOUND] {directory} (tried {resolved} and {alt})"]
        matches = list(resolved.glob(pattern))
        # Return paths relative to PROJECT_ROOT when possible, else BACKEND_ROOT
        def _rel(p: Path) -> str:
            try:
                return str(p.relative_to(PROJECT_ROOT))
            except ValueError:
                try:
                    return str(p.relative_to(BACKEND_ROOT))
                except ValueError:
                    return str(p)
        return [_rel(m) for m in sorted(matches) if m.is_file()]
    except Exception as e:
        return [f"[ERROR] list_files({directory}): {e}"]


def search_codebase(query: str, file_pattern: str | None = None) -> list[dict]:
    """
    Search codebase with regex. Returns [{file, line, content}].
    Searches both PROJECT_ROOT (full monorepo locally) and BACKEND_ROOT.
    file_pattern: e.g. "*.py", "*.md"
    """
    try:
        results = []
        glob_pattern = f"**/{file_pattern}" if file_pattern else "**/*"
        _SKIP = ["node_modules", "__pycache__", ".git", "output/", "temp_uploads/", ".next/"]

        search_root = PROJECT_ROOT  # searches everything available

        for filepath in search_root.glob(glob_pattern):
            if not filepath.is_file():
                continue
            rel = str(filepath.relative_to(search_root))
            if _is_locked(rel):
                continue
            if any(skip in rel for skip in _SKIP):
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
                        if len(results) >= 150:
                            return results
            except Exception:
                continue
        return results
    except Exception as e:
        return [{"error": str(e)}]


def get_code_structure(scope: str = "all") -> dict:
    """
    Return a tree of all project source files Director can read.
    scope: "all" | "director" | "pipeline" | "api" | "frontend"
    Always works regardless of Docker vs local environment.
    """
    try:
        _SKIP = ["__pycache__", ".git", "node_modules", "output/", "temp_uploads/", ".next/", ".pyc"]

        def _tree(root: Path, suffix_filter: list[str] | None = None) -> list[str]:
            out = []
            for p in sorted(root.rglob("*")):
                if not p.is_file():
                    continue
                rel = str(p.relative_to(root))
                if any(s in rel for s in _SKIP):
                    continue
                if suffix_filter and not any(rel.endswith(s) for s in suffix_filter):
                    continue
                out.append(rel)
            return out

        # Director files — always available (same process)
        director_root = _THIS_FILE.parent.parent  # .../app/director
        backend_app_root = _THIS_FILE.parent.parent.parent  # .../app (or backend/app)

        result: dict = {
            "environment": "docker" if not _LOCAL_MODE else "local",
            "backend_root": str(BACKEND_ROOT),
            "project_root": str(PROJECT_ROOT),
        }

        if scope in ("all", "director"):
            result["director"] = _tree(director_root, [".py"])
            result["director_root_path"] = str(director_root)

        if scope in ("all", "pipeline"):
            pipeline_root = backend_app_root / "pipeline"
            if pipeline_root.exists():
                result["pipeline"] = _tree(pipeline_root, [".py"])

        if scope in ("all", "api"):
            api_root = backend_app_root / "api"
            if api_root.exists():
                result["api"] = _tree(api_root, [".py"])
            services_root = backend_app_root / "services"
            if services_root.exists():
                result["services"] = _tree(services_root, [".py"])

        if scope in ("all", "frontend"):
            # Frontend only in local mode (not in Docker)
            if _LOCAL_MODE:
                frontend_root = PROJECT_ROOT / "frontend" / "app"
                if frontend_root.exists():
                    result["frontend"] = _tree(frontend_root, [".tsx", ".ts"])
            else:
                result["frontend"] = ["[not available in Docker — frontend deploys to Vercel]"]

        if scope == "all":
            result["docs"] = _tree(PROJECT_ROOT / "docs", [".md"]) if (PROJECT_ROOT / "docs").exists() else []

        return result
    except Exception as e:
        return {"error": str(e)}


def read_own_file(module_path: str) -> str:
    """
    Read a Director/backend source file using the actual Python runtime path.
    Use this to read any file under backend/app/ (or app/ in Docker).
    module_path examples: "director/agent.py", "pipeline/orchestrator.py", "api/routes/feedback.py"
    """
    try:
        backend_app = _THIS_FILE.parent.parent.parent  # .../app or backend/app
        target = (backend_app / module_path).resolve()

        # Security: must stay inside backend_app
        if not str(target).startswith(str(backend_app.resolve())):
            return f"[BLOCKED] Path outside backend: {module_path}"

        if _is_locked(module_path):
            return f"[LOCKED] {module_path} is protected."

        if not target.exists():
            return f"[NOT FOUND] {module_path} (looked in {target})"

        content = target.read_text(encoding="utf-8", errors="replace")
        if len(content) > 60_000:
            content = content[:60_000] + f"\n\n[TRUNCATED — {len(content)} chars total, showing first 60000]"
        return content
    except Exception as e:
        return f"[ERROR] read_own_file({module_path}): {e}"


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
