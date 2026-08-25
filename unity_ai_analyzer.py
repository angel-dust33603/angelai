from __future__ import annotations

"""
Read-only Unity/VRChat analysis facade for AngelAI.

This module deliberately performs no mutation. It is intended to be the
safe analysis layer that can later be exposed to the model as tools without
mixing Unity parsing with filesystem write/delete functionality.
"""

from pathlib import Path
from typing import Any

from unity_inspector import UnityInspector


class UnityAIAnalyzer:
    """High-level, read-only Unity project analysis."""

    def __init__(self, project_path: str | Path):
        self.inspector = UnityInspector(project_path)

    @property
    def project_path(self) -> Path:
        return self.inspector.project_path

    def validate(self) -> dict[str, Any]:
        return self.inspector.validate_project()

    def summary(self) -> dict[str, Any]:
        return self.inspector.get_project_summary()

    def inventory(self) -> dict[str, Any]:
        return self.inspector.inventory()

    def search(self, query: str, max_results: int = 100) -> dict[str, Any]:
        return self.inspector.search_assets(query, max_results=max_results)

    def inspect_asset(self, relative_path: str) -> dict[str, Any]:
        """Return the most detailed read-only inspection available."""
        path = self.inspector.resolve_project_path(relative_path)

        if not path.exists():
            return {"success": False, "reason": f"Asset does not exist: {relative_path}"}

        if not path.is_file():
            return {"success": False, "reason": f"Not a file: {relative_path}"}

        result: dict[str, Any] = {
            "success": True,
            "path": self.inspector.relative_path(path),
            "type": self.inspector.get_file_type(path),
            "size_bytes": path.stat().st_size,
        }

        # Use inspector capabilities when present. Keeping this defensive
        # means the facade remains compatible as the inspector grows.
        for method_name in (
            "inspect_file",
            "inspect_asset",
            "analyze_asset",
            "analyze_file",
        ):
            method = getattr(self.inspector, method_name, None)
            if callable(method):
                try:
                    inspected = method(relative_path)
                except TypeError:
                    inspected = method(path)
                if isinstance(inspected, dict):
                    result.update(inspected)
                break

        return result

    def analyze(self, relative_path: str | None = None) -> dict[str, Any]:
        """Analyze one asset or the whole project without modifying anything."""
        if relative_path:
            return self.inspect_asset(relative_path)
        return self.summary()

    def capabilities(self) -> dict[str, Any]:
        """Describe the currently available read-only analysis surface."""
        return {
            "read_only": True,
            "project_validation": True,
            "project_summary": True,
            "asset_inventory": True,
            "asset_filename_search": True,
            "single_asset_inspection": True,
            "inspector_methods": sorted(
                name
                for name in dir(self.inspector)
                if not name.startswith("_") and callable(getattr(self.inspector, name, None))
            ),
            "mutation_operations": [],
        }


__all__ = ["UnityAIAnalyzer"]
