from __future__ import annotations

"""
Read-only Unity/VRChat analysis layer for AngelAI.

This module deliberately performs NO filesystem mutation.  It sits above
UnityInspector and adds analysis-oriented operations for Unity YAML assets,
Animator controllers, animations, prefabs/scenes, VRChat/VRCFury data and
cross-asset references.

It is safe to expose to an AI as a tool layer because every operation is
read-only and every requested path is resolved through UnityInspector's
project-bound path safety checks.
"""

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from unity_inspector import UnityInspector


class UnityAIAnalyzer:
    """High-level, read-only Unity and VRChat project analysis."""

    TEXT_EXTENSIONS = {
        ".prefab", ".unity", ".anim", ".controller", ".mat", ".asset",
        ".meta", ".cs", ".shader", ".cginc", ".hlsl", ".json",
        ".asmdef", ".txt", ".md", ".yaml", ".yml",
    }

    GUID_RE = re.compile(r"\bguid:\s*([0-9a-fA-F]{32})\b")
    OBJECT_RE = re.compile(
        r"\{fileID:\s*(-?\d+)(?:,\s*guid:\s*([0-9a-fA-F]{32}))?"
        r"(?:,\s*type:\s*(\d+))?\}"
    )
    YAML_OBJECT_RE = re.compile(
        r"^---\s+!u!(\d+)\s+&(-?\d+)\s*$",
        re.MULTILINE,
    )
    NAME_RE = re.compile(r"^\s*m_Name:\s*(.*?)\s*$", re.MULTILINE)
    SCRIPT_RE = re.compile(
        r"m_Script:\s*\{fileID:\s*(-?\d+),\s*guid:\s*([0-9a-fA-F]{32}),\s*type:\s*(\d+)\}"
    )
    PARAM_RE = re.compile(
        r"(?:^|\n)\s*-\s*name:\s*([^\n]+)\s*\n\s*type:\s*(\d+)",
        re.MULTILINE,
    )
    ANIM_PATH_RE = re.compile(r"^\s*path:\s*(.*?)\s*$", re.MULTILINE)
    ANIM_ATTR_RE = re.compile(r"^\s*m_Attribute:\s*(.*?)\s*$", re.MULTILINE)
    STATE_NAME_RE = re.compile(r"^\s*m_Name:\s*(.*?)\s*$", re.MULTILINE)
    TRANSITION_DEST_RE = re.compile(r"m_DstState:\s*\{fileID:\s*(-?\d+)\}")
    CONDITION_MODE_RE = re.compile(r"mode:\s*(\d+)")
    CONDITION_PARAM_RE = re.compile(r"m_ConditionEvent:\s*([^\n]+)")

    UNITY_TYPES = {
        1: "GameObject", 4: "Transform", 20: "Camera", 21: "Material",
        23: "MeshRenderer", 33: "MeshFilter", 43: "Mesh", 74: "AnimationClip",
        95: "Animator", 110: "AnimatorController", 111: "AnimatorController",
        114: "MonoBehaviour", 115: "MonoScript", 128: "Font",
        129: "PlayerSettings", 213: "SpriteRenderer", 222: "CanvasRenderer",
        224: "RectTransform",
    }

    PARAMETER_TYPES = {
        1: "Float",
        3: "Int",
        4: "Bool",
        9: "Trigger",
    }

    VRCHAT_TERMS = (
        "vrchat", "vrc_", "vrcavatar", "vrcfury", "vrcfurycomponent",
        "vrcavatarparameterdriver", "vrcexpressionparameters", "vrcexpressionsmenu",
    )

    def __init__(self, project_path: str | Path):
        self.inspector = UnityInspector(project_path)
        self._guid_index: dict[str, str] | None = None

    @property
    def project_path(self) -> Path:
        return self.inspector.project_path

    # ------------------------------------------------------------------
    # Basic project operations
    # ------------------------------------------------------------------

    def validate(self) -> dict[str, Any]:
        return self.inspector.validate_project()

    def summary(self) -> dict[str, Any]:
        return self.inspector.get_project_summary()

    def inventory(self) -> dict[str, Any]:
        return self.inspector.inventory()

    def search(self, query: str, max_results: int = 100) -> dict[str, Any]:
        return self.inspector.search_assets(query, max_results=max_results)

    def _resolve(self, relative_path: str | Path) -> Path:
        return self.inspector.resolve_project_path(relative_path)

    def _read_text(self, path: Path, max_bytes: int = 4 * 1024 * 1024) -> str:
        if path.stat().st_size > max_bytes:
            raise ValueError(
                f"File is too large for safe text analysis ({path.stat().st_size} bytes)."
            )
        if path.suffix.lower() not in self.TEXT_EXTENSIONS:
            raise ValueError(f"Unsupported text asset type: {path.suffix or '<none>'}")
        return path.read_text(encoding="utf-8", errors="replace")

    def _asset_path(self, path: Path) -> str:
        return self.inspector.relative_path(path)

    # ------------------------------------------------------------------
    # GUID / reference graph
    # ------------------------------------------------------------------

    def build_guid_index(self, force: bool = False) -> dict[str, Any]:
        """Build a GUID -> project-relative asset path index, read-only."""
        if self._guid_index is not None and not force:
            return {"success": True, "cached": True, "count": len(self._guid_index), "index": dict(self._guid_index)}

        index: dict[str, str] = {}
        duplicates: dict[str, list[str]] = defaultdict(list)

        for asset in self.inspector.iter_assets():
            if asset.suffix.lower() != ".meta":
                continue
            try:
                text = asset.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            match = re.search(r"^\s*guid:\s*([0-9a-fA-F]{32})\s*$", text, re.MULTILINE)
            if not match:
                continue
            guid = match.group(1).lower()
            target = asset.with_suffix("")
            if target.exists():
                rel = self._asset_path(target)
                if guid in index:
                    duplicates[guid].append(rel)
                else:
                    index[guid] = rel

        self._guid_index = index
        return {
            "success": True,
            "cached": False,
            "count": len(index),
            "duplicates": dict(duplicates),
            "index": dict(index),
        }

    def resolve_guid(self, guid: str) -> dict[str, Any]:
        guid = guid.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{32}", guid):
            return {"success": False, "reason": "Invalid Unity GUID."}
        index = self.build_guid_index()["index"]
        path = index.get(guid)
        return {
            "success": True,
            "guid": guid,
            "found": path is not None,
            "path": path,
        }

    def extract_references(self, relative_path: str) -> dict[str, Any]:
        """Extract serialized GUID/fileID references from one text asset."""
        path = self._resolve(relative_path)
        if not path.is_file():
            return {"success": False, "reason": "Not a file."}
        try:
            text = self._read_text(path)
        except (OSError, ValueError) as error:
            return {"success": False, "reason": str(error)}

        references = []
        index = self.build_guid_index()["index"]
        for match in self.OBJECT_RE.finditer(text):
            file_id, guid, ref_type = match.groups()
            if not guid:
                continue
            guid = guid.lower()
            references.append({
                "file_id": int(file_id),
                "guid": guid,
                "reference_type": int(ref_type) if ref_type else None,
                "resolved_path": index.get(guid),
                "missing": guid not in index,
            })

        unique = {}
        for ref in references:
            key = (ref["file_id"], ref["guid"], ref["reference_type"])
            unique[key] = ref
        references = list(unique.values())
        missing = [r for r in references if r["missing"]]

        return {
            "success": True,
            "path": self._asset_path(path),
            "reference_count": len(references),
            "missing_reference_count": len(missing),
            "references": references,
        }

    # ------------------------------------------------------------------
    # Generic asset diagnostics
    # ------------------------------------------------------------------

    def inspect_asset(self, relative_path: str) -> dict[str, Any]:
        path = self._resolve(relative_path)
        if not path.exists():
            return {"success": False, "reason": f"Asset does not exist: {relative_path}"}
        if not path.is_file():
            return {"success": False, "reason": f"Not a file: {relative_path}"}

        result: dict[str, Any] = {
            "success": True,
            "path": self._asset_path(path),
            "type": self.inspector.get_file_type(path),
            "extension": path.suffix.lower(),
            "size_bytes": path.stat().st_size,
        }

        if path.suffix.lower() in self.TEXT_EXTENSIONS:
            try:
                text = self._read_text(path)
                result.update(self._analyze_text_asset(path, text))
            except (OSError, ValueError) as error:
                result["read_error"] = str(error)

        if path.suffix.lower() not in {".meta", ".cs", ".json"}:
            result["references"] = self.extract_references(relative_path)

        return result

    def _analyze_text_asset(self, path: Path, text: str) -> dict[str, Any]:
        objects = []
        for class_id, file_id in self.YAML_OBJECT_RE.findall(text):
            cid = int(class_id)
            objects.append({
                "class_id": cid,
                "type": self.UNITY_TYPES.get(cid, f"Unknown({cid})"),
                "file_id": int(file_id),
            })

        names = [n.strip().strip('"') for n in self.NAME_RE.findall(text) if n.strip()]
        guids = sorted(set(g.lower() for g in self.GUID_RE.findall(text)))
        scripts = [
            {"file_id": int(fid), "guid": guid.lower(), "type": int(kind)}
            for fid, guid, kind in self.SCRIPT_RE.findall(text)
        ]

        return {
            "line_count": text.count("\n") + 1,
            "unity_yaml_objects": objects,
            "object_type_counts": dict(Counter(o["type"] for o in objects)),
            "names": names[:200],
            "guid_count": len(guids),
            "guids": guids[:500],
            "script_references": scripts,
            "vrchat_related": self._looks_vrchat_related(path, text),
        }

    def _looks_vrchat_related(self, path: Path, text: str) -> bool:
        haystack = f"{path.name}\n{text}".lower()
        return any(term in haystack for term in self.VRCHAT_TERMS)

    # ------------------------------------------------------------------
    # Prefab / scene analysis
    # ------------------------------------------------------------------

    def analyze_hierarchy_asset(self, relative_path: str) -> dict[str, Any]:
        """Analyse GameObjects, components and script references in a prefab/scene."""
        path = self._resolve(relative_path)
        if path.suffix.lower() not in {".prefab", ".unity"}:
            return {"success": False, "reason": "Expected a .prefab or .unity asset."}
        try:
            text = self._read_text(path)
        except (OSError, ValueError) as error:
            return {"success": False, "reason": str(error)}

        blocks = re.split(r"(?=^---\s+!u!\d+\s+&-?\d+)", text, flags=re.MULTILINE)
        gameobjects = []
        components = Counter()
        scripts = []

        for block in blocks:
            header = re.search(r"^---\s+!u!(\d+)\s+&(-?\d+)", block, re.MULTILINE)
            if not header:
                continue
            cid, file_id = int(header.group(1)), int(header.group(2))
            type_name = self.UNITY_TYPES.get(cid, f"Unknown({cid})")
            components[type_name] += 1
            name_match = self.NAME_RE.search(block)
            name = name_match.group(1).strip().strip('"') if name_match else None
            if cid == 1:
                gameobjects.append({"file_id": file_id, "name": name})
            for sfid, guid, kind in self.SCRIPT_RE.findall(block):
                scripts.append({"file_id": int(sfid), "guid": guid.lower(), "type": int(kind), "gameobject": name})

        return {
            "success": True,
            "path": self._asset_path(path),
            "asset_kind": "scene" if path.suffix.lower() == ".unity" else "prefab",
            "gameobject_count": len(gameobjects),
            "gameobjects": gameobjects[:1000],
            "component_counts": dict(components),
            "script_references": scripts,
            "reference_analysis": self.extract_references(relative_path),
        }

    # ------------------------------------------------------------------
    # Animator / animation analysis
    # ------------------------------------------------------------------

    def analyze_animator(self, relative_path: str) -> dict[str, Any]:
        """Extract Animator parameters, layers, state names and transition references."""
        path = self._resolve(relative_path)
        if path.suffix.lower() != ".controller":
            return {"success": False, "reason": "Expected a .controller asset."}
        try:
            text = self._read_text(path)
        except (OSError, ValueError) as error:
            return {"success": False, "reason": str(error)}

        parameters = []
        for name, type_code in self.PARAM_RE.findall(text):
            clean_name = name.strip().strip('"')
            code = int(type_code)
            parameters.append({"name": clean_name, "type_code": code, "type": self.PARAMETER_TYPES.get(code, f"Unknown({code})")})

        # Animator YAML is nested, so this is intentionally conservative:
        # collect distinct serialized state/layer names rather than pretending
        # regex can reconstruct every Unity object relationship perfectly.
        names = [n.strip().strip('"') for n in self.STATE_NAME_RE.findall(text) if n.strip()]
        transitions = [int(fid) for fid in self.TRANSITION_DEST_RE.findall(text)]
        condition_parameters = [p.strip().strip('"') for p in self.CONDITION_PARAM_RE.findall(text)]
        animation_guids = sorted(set(g.lower() for g in self.GUID_RE.findall(text)))

        return {
            "success": True,
            "path": self._asset_path(path),
            "parameters": parameters,
            "parameter_count": len(parameters),
            "state_and_layer_names": names,
            "state_name_count": len(names),
            "transition_destination_file_ids": transitions,
            "transition_count": len(transitions),
            "condition_parameters": sorted(set(condition_parameters)),
            "condition_parameter_count": len(set(condition_parameters)),
            "referenced_guids": animation_guids,
            "references": self.extract_references(relative_path),
        }

    def analyze_animation(self, relative_path: str) -> dict[str, Any]:
        path = self._resolve(relative_path)
        if path.suffix.lower() != ".anim":
            return {"success": False, "reason": "Expected an .anim asset."}
        try:
            text = self._read_text(path)
        except (OSError, ValueError) as error:
            return {"success": False, "reason": str(error)}

        paths = sorted(set(p.strip() for p in self.ANIM_PATH_RE.findall(text) if p.strip()))
        attributes = sorted(set(a.strip() for a in self.ANIM_ATTR_RE.findall(text) if a.strip()))
        return {
            "success": True,
            "path": self._asset_path(path),
            "binding_path_count": len(paths),
            "binding_paths": paths[:2000],
            "attribute_count": len(attributes),
            "attributes": attributes[:1000],
            "frame_curve_count": text.count("m_Curve:"),
            "event_count": text.count("m_Events:"),
            "references": self.extract_references(relative_path),
        }

    # ------------------------------------------------------------------
    # VRChat / VRCFury analysis
    # ------------------------------------------------------------------

    def analyze_vrchat_asset(self, relative_path: str) -> dict[str, Any]:
        path = self._resolve(relative_path)
        if not path.is_file():
            return {"success": False, "reason": "Not a file."}
        try:
            text = self._read_text(path)
        except (OSError, ValueError) as error:
            return {"success": False, "reason": str(error)}

        lowered = text.lower()
        hits = sorted({term for term in self.VRCHAT_TERMS if term in lowered})
        parameter_names = sorted(set(p.strip().strip('"') for p in self.PARAM_RE.findall(text)))
        return {
            "success": True,
            "path": self._asset_path(path),
            "vrchat_related": bool(hits),
            "identified_terms": hits,
            "parameter_like_names": parameter_names,
            "vrcfury_mentions": lowered.count("vrcfury"),
            "expression_menu_mentions": lowered.count("expressionsmenu"),
            "expression_parameter_mentions": lowered.count("expressionparameters"),
            "references": self.extract_references(relative_path),
        }

    def scan_vrchat_assets(self, max_results: int = 1000) -> dict[str, Any]:
        results = []
        for path in self.inspector.iter_assets():
            if path.suffix.lower() not in self.TEXT_EXTENSIONS:
                continue
            try:
                text = self._read_text(path, max_bytes=2 * 1024 * 1024)
            except (OSError, ValueError):
                continue
            if self._looks_vrchat_related(path, text):
                results.append({
                    "path": self._asset_path(path),
                    "type": self.inspector.get_file_type(path),
                })
                if len(results) >= max(1, min(int(max_results), 5000)):
                    break
        return {"success": True, "count": len(results), "results": results}

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def diagnose_asset(self, relative_path: str) -> dict[str, Any]:
        """Produce deterministic read-only diagnostics for one asset."""
        result = self.inspect_asset(relative_path)
        if not result.get("success"):
            return result

        issues: list[dict[str, Any]] = []
        path = self._resolve(relative_path)

        if path.suffix.lower() in self.TEXT_EXTENSIONS:
            refs = result.get("references", {})
            for ref in refs.get("references", []):
                if ref.get("missing"):
                    issues.append({
                        "severity": "error",
                        "code": "MISSING_GUID_REFERENCE",
                        "message": f"Reference to GUID {ref['guid']} could not be resolved.",
                        "guid": ref["guid"],
                        "file_id": ref["file_id"],
                    })

        if path.suffix.lower() == ".controller":
            animator = self.analyze_animator(relative_path)
            for parameter in animator.get("condition_parameters", []):
                if parameter and parameter not in {p["name"] for p in animator.get("parameters", [])}:
                    issues.append({
                        "severity": "warning",
                        "code": "ANIMATOR_PARAMETER_NOT_DECLARED",
                        "message": f"Animator condition references undeclared parameter '{parameter}'.",
                        "parameter": parameter,
                    })

        return {
            "success": True,
            "path": self._asset_path(path),
            "issue_count": len(issues),
            "issues": issues,
            "analysis": result,
        }

    def diagnose_project(self, max_asset_diagnostics: int = 250) -> dict[str, Any]:
        """Run a bounded project-wide read-only diagnostic pass."""
        validation = self.validate()
        if not validation.get("valid"):
            return {"success": False, "validation": validation, "issues": []}

        issues: list[dict[str, Any]] = []
        scanned = 0
        for path in self.inspector.iter_assets():
            if path.suffix.lower() not in self.TEXT_EXTENSIONS:
                continue
            if scanned >= max(1, min(int(max_asset_diagnostics), 2000)):
                break
            scanned += 1
            result = self.diagnose_asset(self._asset_path(path))
            for issue in result.get("issues", []):
                issue["asset"] = self._asset_path(path)
                issues.append(issue)

        counts = Counter(issue["severity"] for issue in issues)
        return {
            "success": True,
            "assets_scanned": scanned,
            "issue_count": len(issues),
            "severity_counts": dict(counts),
            "issues": issues,
        }

    # ------------------------------------------------------------------
    # Full analysis / capabilities
    # ------------------------------------------------------------------

    def analyze(self, relative_path: str | None = None) -> dict[str, Any]:
        """Analyze one asset or return a compact whole-project analysis."""
        if relative_path:
            return self.inspect_asset(relative_path)
        return self.full_project_analysis()

    def full_project_analysis(self) -> dict[str, Any]:
        """Collect a broad but bounded read-only project overview."""
        summary = self.summary()
        validation = self.validate()
        vrchat = self.scan_vrchat_assets()
        guid = self.build_guid_index()
        return {
            "success": bool(validation.get("valid")),
            "read_only": True,
            "validation": validation,
            "summary": summary,
            "guid_index_count": guid.get("count", 0),
            "vrchat": vrchat,
            "capabilities": self.capabilities()["analysis_operations"],
        }

    def capabilities(self) -> dict[str, Any]:
        return {
            "read_only": True,
            "mutation_operations": [],
            "analysis_operations": [
                "validate",
                "summary",
                "inventory",
                "search",
                "inspect_asset",
                "build_guid_index",
                "resolve_guid",
                "extract_references",
                "analyze_hierarchy_asset",
                "analyze_animator",
                "analyze_animation",
                "analyze_vrchat_asset",
                "scan_vrchat_assets",
                "diagnose_asset",
                "diagnose_project",
                "full_project_analysis",
            ],
            "asset_categories": [
                "prefab", "scene", "animation", "animator_controller",
                "material", "shader", "script", "model", "texture", "audio",
                "Unity YAML assets", "VRChat/VRCFury serialized data",
            ],
            "safety": {
                "writes_files": False,
                "deletes_files": False,
                "renames_files": False,
                "moves_files": False,
                "creates_directories": False,
                "executes_project_scripts": False,
                "path_traversal_blocked": True,
            },
        }


__all__ = ["UnityAIAnalyzer"]
