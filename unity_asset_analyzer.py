from __future__ import annotations

"""
Read-only Unity / VRChat forensic analysis layer for AngelAI.

This module intentionally performs NO project mutation.  It builds on the
existing UnityInspector class and adds relationship analysis, diagnostics,
Animator/VRChat inspection, reference tracing, and AI-friendly summaries.

The implementation is deliberately YAML/serialization aware rather than
Unity-editor dependent, so it can analyse an extracted project without
opening Unity.
"""

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from unity_inspector import UnityInspector


class UnityAssetAnalyzer(UnityInspector):
    """Deep, read-only forensic analyser for Unity/VRChat projects."""

    # Unity object IDs useful to relationship analysis.
    OBJECT_TYPES = {
        **UnityInspector.UNITY_OBJECT_TYPES,
        1: "GameObject",
        4: "Transform",
        21: "Material",
        23: "MeshRenderer",
        33: "MeshFilter",
        43: "Mesh",
        74: "AnimationClip",
        95: "Animator",
        110: "AnimatorController",
        111: "AnimatorController",
        114: "MonoBehaviour",
        115: "MonoScript",
        213: "SpriteRenderer",
        224: "RectTransform",
        243: "AudioSource",
    }

    REFERENCE_PATTERN = re.compile(
        r"\{fileID:\s*(-?\d+)"
        r"(?:,\s*guid:\s*([0-9a-fA-F]{32}))?"
        r"(?:,\s*type:\s*(\d+))?\s*\}"
    )
    DOCUMENT_PATTERN = re.compile(
        r"^---\s+!u!(\d+)\s+&(-?\d+)\s*$"
        r"(.*?)(?=^---\s+!u!|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    META_GUID_PATTERN = re.compile(
        r"^\s*guid:\s*([0-9a-fA-F]{32})\s*$", re.MULTILINE
    )
    YAML_NAME_PATTERN = re.compile(
        r"^\s*m_Name:\s*(.*?)\s*$", re.MULTILINE
    )
    SCRIPT_PATTERN = re.compile(
        r"m_Script:\s*\{fileID:\s*(-?\d+),\s*guid:\s*([0-9a-fA-F]{32}),\s*type:\s*(\d+)\}"
    )
    PARAM_BLOCK_PATTERN = re.compile(
        r"-\s*name:\s*([^\n]+).*?\n\s*type:\s*(\d+)",
        re.DOTALL,
    )
    CONDITION_PATTERN = re.compile(
        r"m_ConditionEvent:\s*([^\n]+)"
    )
    CONDITION_MODE_PATTERN = re.compile(
        r"m_ConditionMode:\s*(\d+)"
    )
    MENU_CONTROL_NAME_PATTERN = re.compile(
        r"(?:name|m_Name):\s*([^\n]+)"
    )
    FILE_ID_PATTERN = re.compile(r"fileID:\s*(-?\d+)")
    GUID_LITERAL_PATTERN = re.compile(r"\b[0-9a-fA-F]{32}\b")

    # Common Animator parameter type IDs used by Unity's serialized format.
    PARAMETER_TYPES = {
        1: "Float",
        3: "Int",
        4: "Bool",
        5: "Trigger",
    }

    SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

    def __init__(self, project_path: str | Path):
        super().__init__(project_path)
        self._analysis_cache: dict[str, Any] = {}
        self._asset_cache: dict[str, dict[str, Any]] = {}
        self._guid_reverse_index: dict[str, list[str]] | None = None

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _safe_read(self, path: Path) -> str | None:
        """Read a supported text asset without ever modifying it."""
        if path.suffix.lower() not in self.TEXT_EXTENSIONS:
            return None
        try:
            if path.stat().st_size > self.MAX_TEXT_READ_BYTES:
                return None
            return path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeError):
            return None

    def _iter_text_assets(self) -> Iterable[tuple[Path, str]]:
        for path in self.iter_assets():
            text = self._safe_read(path)
            if text is not None:
                yield path, text

    def _guid_index_deep(self) -> dict[str, str]:
        """Return GUID -> project-relative asset path, including meta files."""
        if self._guid_index is not None:
            return self._guid_index

        index: dict[str, str] = {}
        duplicates: defaultdict[str, list[str]] = defaultdict(list)
        for path in self.iter_assets():
            if path.suffix.lower() != ".meta":
                continue
            text = self._safe_read(path)
            if text is None:
                continue
            match = self.META_GUID_PATTERN.search(text)
            if not match:
                continue
            guid = match.group(1).lower()
            asset_path = path.with_suffix("")
            rel = self.relative_path(asset_path)
            if guid in index:
                duplicates[guid].append(rel)
            else:
                index[guid] = rel

        self._guid_index = index
        self._guid_reverse_index = {
            guid: [index[guid], *paths]
            for guid, paths in duplicates.items()
        }
        return index

    def _asset_guid(self, path: Path) -> str | None:
        meta = Path(str(path) + ".meta")
        if not meta.is_file():
            return None
        text = self._safe_read(meta)
        if not text:
            return None
        match = self.META_GUID_PATTERN.search(text)
        return match.group(1).lower() if match else None

    def _documents(self, text: str) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        for match in self.DOCUMENT_PATTERN.finditer(text):
            class_id = int(match.group(1))
            file_id = int(match.group(2))
            body = match.group(3)
            name_match = self.YAML_NAME_PATTERN.search(body)
            documents.append(
                {
                    "class_id": class_id,
                    "type": self.OBJECT_TYPES.get(class_id, f"ClassID:{class_id}"),
                    "file_id": file_id,
                    "name": name_match.group(1).strip() if name_match else None,
                    "text": body,
                }
            )
        return documents

    def _references(self, text: str) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        for match in self.REFERENCE_PATTERN.finditer(text):
            file_id = int(match.group(1))
            guid = match.group(2).lower() if match.group(2) else None
            type_id = int(match.group(3)) if match.group(3) else None
            refs.append(
                {
                    "file_id": file_id,
                    "guid": guid,
                    "type": type_id,
                }
            )
        return refs

    def _finding(
        self,
        severity: str,
        code: str,
        message: str,
        path: str | None = None,
        evidence: Any = None,
        suggestion: str | None = None,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {
            "severity": severity,
            "code": code,
            "message": message,
        }
        if path:
            item["path"] = path
        if evidence is not None:
            item["evidence"] = evidence
        if suggestion:
            item["suggestion"] = suggestion
        return item

    # ------------------------------------------------------------------
    # Asset-level analysis
    # ------------------------------------------------------------------

    def analyze_asset(self, relative_path: str) -> dict[str, Any]:
        """Return a detailed, read-only analysis of one asset."""
        cache_key = relative_path.replace("\\", "/")
        if cache_key in self._asset_cache:
            return self._asset_cache[cache_key]

        try:
            path = self.resolve_project_path(relative_path)
        except PermissionError as exc:
            return {"success": False, "reason": str(exc)}

        if not path.is_file():
            return {"success": False, "reason": "File does not exist."}

        rel = self.relative_path(path)
        result: dict[str, Any] = {
            "success": True,
            "path": rel,
            "type": self.get_file_type(path),
            "extension": path.suffix.lower(),
            "size": path.stat().st_size,
            "guid": self._asset_guid(path),
            "documents": [],
            "references": [],
            "findings": [],
        }

        text = self._safe_read(path)
        if text is None:
            result["binary_or_unreadable"] = True
            self._asset_cache[cache_key] = result
            return result

        documents = self._documents(text)
        references = self._references(text)
        guid_index = self._guid_index_deep()

        result["documents"] = [
            {
                "class_id": d["class_id"],
                "type": d["type"],
                "file_id": d["file_id"],
                "name": d["name"],
            }
            for d in documents
        ]

        result["references"] = []
        seen_refs: set[tuple[int, str | None]] = set()
        for ref in references:
            key = (ref["file_id"], ref["guid"])
            if key in seen_refs:
                continue
            seen_refs.add(key)
            target = guid_index.get(ref["guid"]) if ref["guid"] else None
            result["references"].append(
                {
                    **ref,
                    "target": target,
                    "resolved": bool(target) if ref["guid"] else True,
                }
            )

            if ref["guid"] and not target:
                result["findings"].append(
                    self._finding(
                        "error",
                        "MISSING_GUID_REFERENCE",
                        f"Reference uses GUID {ref['guid']} but no matching asset/meta was found.",
                        rel,
                        {"guid": ref["guid"], "file_id": ref["file_id"]},
                        "Check whether the referenced asset was deleted, moved without its .meta file, or excluded from the project.",
                    )
                )

        # Missing MonoBehaviour scripts are a particularly useful Unity error.
        for match in self.SCRIPT_PATTERN.finditer(text):
            guid = match.group(2).lower()
            if guid not in guid_index:
                result["findings"].append(
                    self._finding(
                        "error",
                        "MISSING_SCRIPT",
                        f"MonoBehaviour references missing script GUID {guid}.",
                        rel,
                        {"guid": guid, "file_id": int(match.group(1))},
                        "Restore the script/meta pair or remove the broken component in Unity.",
                    )
                )

        # Animator controllers: expose parameters, layers and conditions.
        if path.suffix.lower() == ".controller":
            result["animator"] = self._analyze_controller_text(rel, text)

        # Animation clips: expose animated properties and likely paths.
        if path.suffix.lower() == ".anim":
            attrs = [x.strip() for x in self.ANIMATION_ATTRIBUTE_PATTERN.findall(text) if x.strip()]
            paths = [x.strip() for x in self.ANIMATION_PATH_PATTERN.findall(text) if x.strip()]
            result["animation"] = {
                "attributes": sorted(set(attrs)),
                "paths": sorted(set(paths)),
                "attribute_count": len(set(attrs)),
                "path_count": len(set(paths)),
            }

        # Prefab/scene component inventory.
        if path.suffix.lower() in {".prefab", ".unity"}:
            result["hierarchy"] = self._analyze_hierarchy_text(text)

        self._asset_cache[cache_key] = result
        return result

    def _analyze_hierarchy_text(self, text: str) -> dict[str, Any]:
        documents = self._documents(text)
        components = Counter(d["type"] for d in documents)
        names = [d["name"] for d in documents if d["type"] == "GameObject" and d["name"]]
        scripts = []
        for match in self.SCRIPT_PATTERN.finditer(text):
            scripts.append({"guid": match.group(2).lower(), "file_id": int(match.group(1))})
        return {
            "object_count": len(documents),
            "component_counts": dict(components),
            "game_objects": names,
            "script_references": scripts,
            "has_animator": any(d["type"] == "Animator" for d in documents),
        }

    # ------------------------------------------------------------------
    # Animator analysis
    # ------------------------------------------------------------------

    def _analyze_controller_text(self, path: str, text: str) -> dict[str, Any]:
        parameters: list[dict[str, Any]] = []
        for match in self.PARAM_BLOCK_PATTERN.finditer(text):
            name = match.group(1).strip()
            type_id = int(match.group(2))
            parameters.append(
                {
                    "name": name,
                    "type_id": type_id,
                    "type": self.PARAMETER_TYPES.get(type_id, f"Unknown:{type_id}"),
                }
            )

        # Unity controller YAML has state/transition blocks with conditions.
        conditions = [x.strip() for x in self.CONDITION_PATTERN.findall(text) if x.strip()]
        condition_modes = [int(x) for x in self.CONDITION_MODE_PATTERN.findall(text)]
        layers = []
        for block in re.split(r"(?=\n\s*-\s*m_Name:)", text):
            match = re.search(r"^\s*-\s*m_Name:\s*(.*?)\s*$", block, re.MULTILINE)
            if match:
                layers.append(match.group(1).strip())

        parameter_names = {p["name"] for p in parameters}
        condition_names = set(conditions)
        missing_conditions = sorted(condition_names - parameter_names)
        unused_parameters = sorted(parameter_names - condition_names)

        findings: list[dict[str, Any]] = []
        for name in missing_conditions:
            findings.append(
                self._finding(
                    "error",
                    "ANIMATOR_MISSING_PARAMETER",
                    f"Animator transition references parameter '{name}', but the controller does not declare it.",
                    path,
                    {"parameter": name},
                    "Create the parameter with the expected type, or update/remove the transition condition.",
                )
            )

        for name in unused_parameters:
            findings.append(
                self._finding(
                    "info",
                    "ANIMATOR_UNUSED_PARAMETER",
                    f"Animator parameter '{name}' is declared but no transition condition reference was detected.",
                    path,
                    {"parameter": name},
                    "Verify that the parameter is used by behaviours, drivers, or other runtime systems before removing it.",
                )
            )

        return {
            "parameters": parameters,
            "parameter_count": len(parameters),
            "layers": sorted(set(layers)),
            "layer_count": len(set(layers)),
            "transition_conditions": sorted(condition_names),
            "condition_count": len(condition_names),
            "condition_modes": condition_modes,
            "missing_condition_parameters": missing_conditions,
            "apparently_unused_parameters": unused_parameters,
            "findings": findings,
        }

    def analyze_animator(self, relative_path: str) -> dict[str, Any]:
        """Focused Animator Controller analysis."""
        result = self.analyze_asset(relative_path)
        if not result.get("success"):
            return result
        if result.get("type") != "animator_controller":
            return {
                "success": False,
                "reason": "The supplied asset is not an Animator Controller.",
                "path": relative_path,
            }
        return {
            "success": True,
            "path": relative_path,
            "animator": result.get("animator", {}),
            "findings": result.get("findings", []),
        }

    # ------------------------------------------------------------------
    # Global reference graph
    # ------------------------------------------------------------------

    def build_reference_graph(self, max_edges: int = 50000) -> dict[str, Any]:
        """Build a GUID-based read-only asset dependency graph."""
        max_edges = max(1, min(int(max_edges), 500000))
        guid_index = self._guid_index_deep()
        edges: list[dict[str, Any]] = []
        incoming: Counter[str] = Counter()
        outgoing: Counter[str] = Counter()
        unresolved: list[dict[str, Any]] = []

        for path, text in self._iter_text_assets():
            source = self.relative_path(path)
            source_guid = self._asset_guid(path)
            for ref in self._references(text):
                if not ref["guid"]:
                    continue
                target = guid_index.get(ref["guid"])
                if not target:
                    unresolved.append({
                        "source": source,
                        "guid": ref["guid"],
                        "file_id": ref["file_id"],
                    })
                    continue
                if len(edges) >= max_edges:
                    break
                edges.append({
                    "source": source,
                    "source_guid": source_guid,
                    "target": target,
                    "target_guid": ref["guid"],
                    "file_id": ref["file_id"],
                    "type": ref["type"],
                })
                outgoing[source] += 1
                incoming[target] += 1
            if len(edges) >= max_edges:
                break

        return {
            "success": True,
            "edge_count": len(edges),
            "truncated": len(edges) >= max_edges,
            "edges": edges,
            "unresolved_references": unresolved,
            "most_referenced": [
                {"path": path, "references": count}
                for path, count in incoming.most_common(100)
            ],
            "most_dependent": [
                {"path": path, "references": count}
                for path, count in outgoing.most_common(100)
            ],
        }

    def trace_references(self, relative_path: str, direction: str = "both") -> dict[str, Any]:
        """Trace direct incoming/outgoing asset relationships."""
        if direction not in {"in", "out", "both"}:
            return {"success": False, "reason": "direction must be 'in', 'out', or 'both'."}

        graph = self.build_reference_graph()
        target = relative_path.replace("\\", "/")
        incoming = []
        outgoing = []
        for edge in graph["edges"]:
            if edge["target"] == target:
                incoming.append(edge)
            if edge["source"] == target:
                outgoing.append(edge)

        return {
            "success": True,
            "path": target,
            "incoming": incoming if direction in {"in", "both"} else [],
            "outgoing": outgoing if direction in {"out", "both"} else [],
        }

    # ------------------------------------------------------------------
    # Project-wide diagnostics
    # ------------------------------------------------------------------

    def diagnose_project(self) -> dict[str, Any]:
        """Run broad read-only diagnostics across the Unity project."""
        cache_key = "diagnostics"
        if cache_key in self._analysis_cache:
            return self._analysis_cache[cache_key]

        validation = self.validate_project()
        if not validation["valid"]:
            result = {
                "success": False,
                "validation": validation,
                "findings": [
                    self._finding(
                        "error",
                        "INVALID_UNITY_PROJECT",
                        "The supplied directory is missing one or more core Unity project directories.",
                        suggestion="Point the inspector at the Unity project root containing Assets, Packages, and ProjectSettings.",
                    )
                ],
            }
            self._analysis_cache[cache_key] = result
            return result

        guid_index = self._guid_index_deep()
        findings: list[dict[str, Any]] = []
        missing_meta: list[str] = []
        empty_assets: list[str] = []
        script_errors: list[str] = []
        animator_paths: list[str] = []
        vrchat_paths: list[str] = []
        asset_counts = Counter()
        guid_seen: defaultdict[str, list[str]] = defaultdict(list)

        for path in self.iter_assets():
            rel = self.relative_path(path)
            asset_type = self.get_file_type(path)
            asset_counts[asset_type] += 1

            if path.suffix.lower() != ".meta":
                meta = Path(str(path) + ".meta")
                if not meta.is_file():
                    missing_meta.append(rel)
                    findings.append(
                        self._finding(
                            "warning",
                            "MISSING_META",
                            "Asset does not have a neighbouring .meta file.",
                            rel,
                            suggestion="Verify the asset is managed by Unity and that its .meta file was not lost during copying or version-control operations.",
                        )
                    )

                guid = self._asset_guid(path)
                if guid:
                    guid_seen[guid].append(rel)

            if asset_type == "animator_controller":
                animator_paths.append(rel)
            text = self._safe_read(path)
            if text:
                lowered = text.lower()
                if any(identifier in lowered for identifier in self.VRC_IDENTIFIERS):
                    vrchat_paths.append(rel)
                for match in self.SCRIPT_PATTERN.finditer(text):
                    if match.group(2).lower() not in guid_index:
                        script_errors.append(rel)

        duplicate_guids = {
            guid: paths for guid, paths in guid_seen.items() if len(paths) > 1
        }
        for guid, paths in duplicate_guids.items():
            findings.append(
                self._finding(
                    "error",
                    "DUPLICATE_GUID",
                    f"GUID {guid} appears to belong to multiple assets.",
                    evidence={"guid": guid, "paths": paths},
                    suggestion="Check copied assets and their .meta files. Duplicate GUIDs can cause Unity to resolve references to the wrong asset.",
                )
            )

        graph = self.build_reference_graph()
        for unresolved in graph["unresolved_references"]:
            findings.append(
                self._finding(
                    "error",
                    "UNRESOLVED_REFERENCE",
                    f"Asset references missing GUID {unresolved['guid']}.",
                    unresolved["source"],
                    unresolved,
                    "Find the missing asset/meta file or repair the serialized reference in Unity rather than editing YAML blindly.",
                )
            )

        # Flag assets with no incoming dependency edges as candidates for review.
        referenced = {edge["target"] for edge in graph["edges"]}
        orphan_candidates: list[str] = []
        for path in self.iter_assets():
            rel = self.relative_path(path)
            if path.suffix.lower() in {".meta", ".cs"}:
                continue
            if rel not in referenced and self.get_file_type(path) in {
                "prefab", "animation", "animator_controller", "material", "unity_asset"
            }:
                orphan_candidates.append(rel)

        for rel in orphan_candidates[:500]:
            findings.append(
                self._finding(
                    "info",
                    "ORPHAN_CANDIDATE",
                    "No incoming serialized asset reference was detected.",
                    rel,
                    suggestion="Review before deleting; assets can be referenced dynamically by scripts, packages, addressables, Resources, or VRChat tooling.",
                )
            )

        # Severity ordering gives the AI the important problems first.
        findings.sort(key=lambda item: (
            self.SEVERITY_ORDER.get(item["severity"], 99),
            item.get("path", ""),
            item["code"],
        ))

        result = {
            "success": True,
            "read_only": True,
            "project": self.project_path.name,
            "validation": validation,
            "asset_counts": dict(sorted(asset_counts.items())),
            "guid_count": len(guid_index),
            "duplicate_guids": duplicate_guids,
            "missing_meta_count": len(missing_meta),
            "missing_meta": missing_meta[:1000],
            "animator_controllers": sorted(animator_paths),
            "vrchat_candidate_assets": sorted(set(vrchat_paths)),
            "reference_graph": {
                "edge_count": graph["edge_count"],
                "unresolved_count": len(graph["unresolved_references"]),
                "truncated": graph["truncated"],
            },
            "orphan_candidate_count": len(orphan_candidates),
            "orphan_candidates": orphan_candidates[:1000],
            "findings": findings,
            "summary": self._diagnostic_summary(findings),
        }
        self._analysis_cache[cache_key] = result
        return result

    def _diagnostic_summary(self, findings: list[dict[str, Any]]) -> dict[str, Any]:
        counts = Counter(item["severity"] for item in findings)
        codes = Counter(item["code"] for item in findings)
        return {
            "errors": counts.get("error", 0),
            "warnings": counts.get("warning", 0),
            "info": counts.get("info", 0),
            "top_issue_codes": [
                {"code": code, "count": count}
                for code, count in codes.most_common(20)
            ],
        }

    # ------------------------------------------------------------------
    # VRChat-focused analysis
    # ------------------------------------------------------------------

    def analyze_vrchat(self) -> dict[str, Any]:
        """Find and correlate common VRChat avatar/menu/parameter assets."""
        candidates: list[dict[str, Any]] = []
        parameters: list[dict[str, Any]] = []
        menus: list[dict[str, Any]] = []
        controllers: list[dict[str, Any]] = []

        for path, text in self._iter_text_assets():
            rel = self.relative_path(path)
            lowered = text.lower()
            if not any(identifier in lowered for identifier in self.VRC_IDENTIFIERS):
                continue

            candidates.append({
                "path": rel,
                "type": self.get_file_type(path),
            })

            if "vrcExpressionParameters".lower() in lowered or "vrc_expressionparameters" in lowered:
                names = re.findall(r"name:\s*([^\n]+)", text, re.IGNORECASE)
                parameters.append({
                    "path": rel,
                    "parameter_names": sorted(set(x.strip() for x in names if x.strip())),
                })

            if "vrcExpressionsMenu".lower() in lowered or "vrc_expressionsmenu" in lowered:
                names = re.findall(r"name:\s*([^\n]+)", text, re.IGNORECASE)
                menus.append({
                    "path": rel,
                    "names": sorted(set(x.strip() for x in names if x.strip())),
                })

            if path.suffix.lower() == ".controller":
                controller = self._analyze_controller_text(rel, text)
                controllers.append({
                    "path": rel,
                    **controller,
                })

        findings: list[dict[str, Any]] = []
        menu_names = {
            name
            for menu in menus
            for name in menu.get("names", [])
        }
        controller_parameters = {
            p["name"]
            for controller in controllers
            for p in controller.get("parameters", [])
        }
        declared_parameters = {
            name
            for item in parameters
            for name in item.get("parameter_names", [])
        }

        # These are intentionally warnings: VRChat projects often use runtime
        # systems or generated assets that cannot be inferred from YAML alone.
        for name in sorted(declared_parameters - controller_parameters):
            findings.append(
                self._finding(
                    "warning",
                    "VRC_PARAMETER_NOT_SEEN_IN_CONTROLLER",
                    f"VRChat parameter '{name}' was found but no matching Animator parameter was detected.",
                    evidence={"parameter": name},
                    suggestion="Check whether the parameter is intentionally used by menus, drivers, contacts, or another controller.",
                )
            )

        return {
            "success": True,
            "read_only": True,
            "candidate_assets": candidates,
            "expression_parameters": parameters,
            "expression_menus": menus,
            "animator_controllers": controllers,
            "cross_asset_parameter_names": sorted(controller_parameters & declared_parameters),
            "menu_name_count": len(menu_names),
            "findings": findings,
        }

    # ------------------------------------------------------------------
    # AI-facing single-call interface
    # ------------------------------------------------------------------

    def full_analysis(self) -> dict[str, Any]:
        """Return a compact but comprehensive analysis payload for AngelAI."""
        diagnostics = self.diagnose_project()
        vrchat = self.analyze_vrchat()
        return {
            "success": diagnostics.get("success", False),
            "read_only": True,
            "project": self.project_path.name,
            "project_summary": self.get_project_summary(),
            "diagnostics": diagnostics,
            "vrchat": vrchat,
            "capabilities": [
                "asset_inventory",
                "asset_metadata",
                "serialized_yaml_analysis",
                "guid_resolution",
                "dependency_graph",
                "incoming_outgoing_reference_tracing",
                "missing_reference_detection",
                "missing_meta_detection",
                "duplicate_guid_detection",
                "missing_script_detection",
                "prefab_scene_component_analysis",
                "animation_clip_analysis",
                "animator_parameter_analysis",
                "animator_condition_analysis",
                "animator_unused_parameter_detection",
                "vrchat_parameter_menu_correlation",
                "orphan_candidate_detection",
            ],
            "limitations": [
                "Serialized analysis cannot prove runtime-generated references are unused.",
                "Animator and VRChat parsing is intentionally conservative and reports evidence rather than pretending to emulate Unity.",
                "Binary assets are inspected through metadata/references, not decoded into their full editor representation.",
                "No write, rename, move, delete, copy, import, reserialize, or repair operation is performed.",
            ],
        }


# Backwards-friendly alias for callers that want a more explicit name.
UnityForensics = UnityAssetAnalyzer
