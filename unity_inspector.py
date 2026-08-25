from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator


class UnityInspector:
    """
    Read-only inspector for extracted Unity projects.

    IMPORTANT:
        This class intentionally contains NO filesystem mutation
        functionality.

        It cannot:
            - create files
            - create directories
            - write files
            - delete files
            - move files
            - copy files
            - rename files

        It can only inspect files that already exist inside the
        configured Unity project.
    """

    UNITY_EXTENSIONS = {
        ".prefab": "prefab",
        ".unity": "scene",
        ".anim": "animation",
        ".controller": "animator_controller",
        ".mat": "material",
        ".asset": "unity_asset",
        ".meta": "meta",
        ".cs": "script",
        ".shader": "shader",
        ".cginc": "shader_include",
        ".hlsl": "shader_source",
        ".json": "json",
        ".asmdef": "assembly_definition",
        ".fbx": "model",
        ".obj": "model",
        ".blend": "model",
        ".png": "texture",
        ".jpg": "texture",
        ".jpeg": "texture",
        ".tga": "texture",
        ".psd": "texture_source",
        ".wav": "audio",
        ".mp3": "audio",
        ".ogg": "audio",
        ".mp4": "video",
        ".mov": "video",
    }

    REQUIRED_PROJECT_DIRECTORIES = {
        "Assets",
        "ProjectSettings",
        "Packages",
    }

    MAX_TEXT_READ_BYTES = 2 * 1024 * 1024

    TEXT_EXTENSIONS = {
        ".prefab",
        ".unity",
        ".anim",
        ".controller",
        ".mat",
        ".asset",
        ".meta",
        ".cs",
        ".shader",
        ".cginc",
        ".hlsl",
        ".json",
        ".asmdef",
        ".txt",
        ".md",
        ".yaml",
        ".yml",
    }

    GUID_PATTERN = re.compile(
        r"\bguid:\s*([0-9a-fA-F]{32})\b"
    )

    META_GUID_PATTERN = re.compile(
        r"^\s*guid:\s*([0-9a-fA-F]{32})\s*$",
        re.MULTILINE,
    )

    YAML_OBJECT_PATTERN = re.compile(
        r"^---\s+!u!(\d+)\s+&(-?\d+)",
        re.MULTILINE,
    )

    UNITY_OBJECT_TYPES = {
        1: "GameObject",
        4: "Transform",
        20: "Camera",
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
        128: "Font",
        129: "PlayerSettings",
        213: "SpriteRenderer",
        222: "CanvasRenderer",
        224: "RectTransform",
    }

    # Unity component class IDs that are particularly useful when
    # analysing prefabs/scenes.
    COMPONENT_OBJECT_TYPES = {
        1: "GameObject",
        4: "Transform",
        20: "Camera",
        23: "MeshRenderer",
        33: "MeshFilter",
        95: "Animator",
        114: "MonoBehaviour",
        213: "SpriteRenderer",
        222: "CanvasRenderer",
        224: "RectTransform",
    }

    # Common Unity serialized reference format:
    #
    # {fileID: 123, guid: abcdef..., type: 3}
    #
    # The GUID itself is already handled by GUID_PATTERN, but this
    # pattern lets us retain fileID/type information.
    OBJECT_REFERENCE_PATTERN = re.compile(
        r"\{fileID:\s*(-?\d+)"
        r"(?:,\s*guid:\s*([0-9a-fA-F]{32}))?"
        r"(?:,\s*type:\s*(\d+))?"
        r"\}"
    )

    # GameObject names.
    GAMEOBJECT_NAME_PATTERN = re.compile(
        r"^\s*m_Name:\s*(.*?)\s*$",
        re.MULTILINE,
    )

    # MonoBehaviour script references.
    SCRIPT_REFERENCE_PATTERN = re.compile(
        r"m_Script:\s*\{fileID:\s*(-?\d+),\s*guid:\s*([0-9a-fA-F]{32}),\s*type:\s*(\d+)\}"
    )

    # Generic Unity component block boundaries.
    YAML_DOCUMENT_PATTERN = re.compile(
        r"^---\s+!u!(\d+)\s+&(-?\d+)\s*$"
        r"(.*?)(?=^---\s+!u!|\Z)",
        re.MULTILINE | re.DOTALL,
    )

    # Animation property names.
    ANIMATION_ATTRIBUTE_PATTERN = re.compile(
        r"^\s*m_Attribute:\s*(.*?)\s*$",
        re.MULTILINE,
    )

    ANIMATION_PATH_PATTERN = re.compile(
        r"^\s*path:\s*(.*?)\s*$",
        re.MULTILINE,
    )

    # Animator parameters.
    PARAMETER_NAME_PATTERN = re.compile(
        r"^\s*-\s*name:\s*(.*?)\s*$",
        re.MULTILINE,
    )

    PARAMETER_TYPE_PATTERN = re.compile(
        r"^\s*type:\s*(\d+)\s*$",
        re.MULTILINE,
    )

    # Animator layers.
    LAYER_NAME_PATTERN = re.compile(
        r"^\s*m_Name:\s*(.*?)\s*$",
        re.MULTILINE,
    )

    # VRChat / VRCFury identifiers.
    VRC_IDENTIFIERS = {
        "vrchat",
        "vrc_",
        "vrcavatar",
        "vrcavatarparameterdriver",
        "vrcexpressionparameters",
        "vrcexpressionsmenu",
        "vrcfury",
        "vrcfurycomponents",
    }

    # =========================================================
    # INITIALISATION
    # =========================================================

    def __init__(
        self,
        project_path: str | Path,
    ):
        self.project_path = (
            Path(project_path)
            .expanduser()
            .resolve()
        )

        if not self.project_path.exists():
            raise FileNotFoundError(
                f"Unity project does not exist: "
                f"{self.project_path}"
            )

        if not self.project_path.is_dir():
            raise NotADirectoryError(
                f"Unity project path is not a directory: "
                f"{self.project_path}"
            )

        # Cached GUID index.

        self._guid_index: dict[str, str] | None = None

    # =========================================================
    # PROJECT VALIDATION
    # =========================================================

    def validate_project(
        self,
    ) -> dict[str, Any]:
        """
        Check whether the supplied directory resembles a complete
        Unity project.
        """

        existing = {
            directory
            for directory in self.REQUIRED_PROJECT_DIRECTORIES
            if (
                self.project_path / directory
            ).is_dir()
        }

        missing = sorted(
            self.REQUIRED_PROJECT_DIRECTORIES
            - existing
        )

        return {
            "valid": not missing,
            "path": str(self.project_path),
            "existing_directories": sorted(existing),
            "missing_directories": missing,
        }

    # =========================================================
    # PATH SAFETY
    # =========================================================

    def resolve_project_path(
        self,
        relative_path: str | Path,
    ) -> Path:
        """
        Resolve a path while preventing traversal outside the
        configured Unity project.
        """

        target = (
            self.project_path
            / relative_path
        ).resolve()

        try:
            target.relative_to(
                self.project_path
            )
        except ValueError:
            raise PermissionError(
                "Access denied: path is outside "
                "the Unity project."
            )

        return target

    def relative_path(
        self,
        path: Path,
    ) -> str:
        """
        Return a project-relative path.
        """

        try:
            return str(
                path.relative_to(
                    self.project_path
                )
            )
        except ValueError:
            return str(path)

    # =========================================================
    # ASSETS
    # =========================================================

    @property
    def assets_path(self) -> Path:
        return self.project_path / "Assets"

    def iter_assets(
        self,
    ) -> Iterator[Path]:
        """
        Yield files inside Assets/.

        This performs read-only directory traversal.
        """

        if not self.assets_path.is_dir():
            return

        for path in self.assets_path.rglob("*"):
            if path.is_file():
                yield path

    # =========================================================
    # FILE TYPE
    # =========================================================

    def get_file_type(
        self,
        path: Path,
    ) -> str:
        """
        Return a human-readable Unity asset category.
        """

        suffix = path.suffix.lower()

        return self.UNITY_EXTENSIONS.get(
            suffix,
            "other",
        )

    # =========================================================
    # INVENTORY
    # =========================================================

    def inventory(
        self,
    ) -> dict[str, Any]:
        """
        Scan Assets/ and produce an asset inventory.

        No files are modified.
        """

        validation = self.validate_project()

        if not validation["valid"]:
            return {
                "success": False,
                "reason": (
                    "Directory does not appear to be "
                    "a complete Unity project."
                ),
                "validation": validation,
            }

        counts: dict[str, int] = {}
        files: list[dict[str, str]] = []

        for path in self.iter_assets():

            file_type = self.get_file_type(
                path
            )

            counts[file_type] = (
                counts.get(file_type, 0)
                + 1
            )

            files.append(
                {
                    "path": self.relative_path(
                        path
                    ),
                    "type": file_type,
                }
            )

        files.sort(
            key=lambda item: (
                item["path"].lower()
            )
        )

        return {
            "success": True,
            "project": self.project_path.name,
            "path": str(self.project_path),
            "assets_path": str(self.assets_path),
            "counts": dict(
                sorted(counts.items())
            ),
            "total_files": len(files),
            "files": files,
        }

    # =========================================================
    # COMPACT PROJECT SUMMARY
    # =========================================================

    def get_project_summary(
        self,
    ) -> dict[str, Any]:
        """
        Return a compact summary intended for AngelAI.

        Unlike inventory(), this does not return every asset path.
        """

        validation = self.validate_project()

        if not validation["valid"]:
            return {
                "success": False,
                "reason": (
                    "Directory does not appear to be "
                    "a complete Unity project."
                ),
                "validation": validation,
            }

        counts: dict[str, int] = {}

        for path in self.iter_assets():

            file_type = self.get_file_type(
                path
            )

            counts[file_type] = (
                counts.get(file_type, 0)
                + 1
            )

        return {
            "success": True,
            "project": self.project_path.name,
            "path": str(self.project_path),
            "assets_path": str(self.assets_path),
            "counts": dict(
                sorted(counts.items())
            ),
            "total_assets": sum(
                counts.values()
            ),
        }

    # =========================================================
    # SEARCH
    # =========================================================

    def search_assets(
        self,
        query: str,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """
        Search asset filenames for a case-insensitive query.
        """

        query = query.strip().lower()

        if not query:
            return {
                "success": False,
                "reason": (
                    "Search query cannot be empty."
                ),
            }

        if not self.assets_path.is_dir():
            return {
                "success": False,
                "reason": (
                    "Assets directory does not exist."
                ),
            }

        max_results = max(
            1,
            min(
                int(max_results),
                1000,
            ),
        )

        results = []

        for path in self.iter_assets():

            if query not in path.name.lower():
                continue

            results.append(
                {
                    "path": self.relative_path(
                        path
                    ),
                    "type": self.get_file_type(
                        path
                    ),
                }
            )

            if len(results) >= max_results:
                break

        return {
            "success": True,
            "query": query,
            "results": results,
            "count": len(results),
            "limited": (
                len(results) >= max_results
            ),
        }

    # =========================================================
    # FILE INFORMATION
    # =========================================================

    def inspect_file(
        self,
        relative_path: str,
    ) -> dict[str, Any]:
        """
        Return metadata about one file.

        Does not read the file's contents.
        """

        try:
            target = self.resolve_project_path(
                relative_path
            )
        except PermissionError as error:
            return {
                "success": False,
                "reason": str(error),
            }

        if not target.exists():
            return {
                "success": False,
                "reason": "File does not exist.",
            }

        if not target.is_file():
            return {
                "success": False,
                "reason": "Path is not a file.",
            }

        stat = target.stat()

        return {
            "success": True,
            "path": self.relative_path(
                target
            ),
            "type": self.get_file_type(
                target
            ),
            "extension": target.suffix.lower(),
            "size": stat.st_size,
        }

    # =========================================================
    # TEXT READING
    # =========================================================

    def read_text_asset(
        self,
        relative_path: str,
        max_bytes: int | None = None,
    ) -> dict[str, Any]:
        """
        Read a text-based Unity asset.

        This is READ ONLY.

        Binary files are rejected.
        """

        try:
            target = self.resolve_project_path(
                relative_path
            )
        except PermissionError as error:
            return {
                "success": False,
                "reason": str(error),
            }

        if not target.exists():
            return {
                "success": False,
                "reason": "File does not exist.",
            }

        if not target.is_file():
            return {
                "success": False,
                "reason": "Path is not a file.",
            }

        extension = target.suffix.lower()

        if extension not in self.TEXT_EXTENSIONS:
            return {
                "success": False,
                "reason": (
                    f"'{extension}' is not a "
                    "supported text asset."
                ),
            }

        size = target.stat().st_size

        limit = (
            self.MAX_TEXT_READ_BYTES
            if max_bytes is None
            else max(
                1,
                min(
                    int(max_bytes),
                    self.MAX_TEXT_READ_BYTES,
                ),
            )
        )

        if size > limit:
            return {
                "success": False,
                "reason": (
                    "File is too large to read safely. "
                    f"Size: {size} bytes; "
                    f"limit: {limit} bytes."
                ),
                "size": size,
                "limit": limit,
            }

        try:
            content = target.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError as error:
            return {
                "success": False,
                "reason": str(error),
            }

        return {
            "success": True,
            "path": self.relative_path(
                target
            ),
            "type": self.get_file_type(
                target
            ),
            "size": size,
            "content": content,
        }

    # =========================================================
    # META / GUID
    # =========================================================

    def parse_meta(
        self,
        relative_path: str,
    ) -> dict[str, Any]:
        """
        Extract the GUID and importer information from a .meta file.
        """

        try:
            target = self.resolve_project_path(
                relative_path
            )
        except PermissionError as error:
            return {
                "success": False,
                "reason": str(error),
            }

        if target.suffix.lower() != ".meta":
            return {
                "success": False,
                "reason": (
                    "The supplied file is not a .meta file."
                ),
            }

        result = self.read_text_asset(
            relative_path
        )

        if not result["success"]:
            return result

        content = result["content"]

        match = self.META_GUID_PATTERN.search(
            content
        )

        guid = (
            match.group(1).lower()
            if match
            else None
        )

        return {
            "success": True,
            "path": relative_path,
            "guid": guid,
            "has_guid": guid is not None,
            "content_size": len(content),
        }

    # =========================================================
    # GUID INDEX
    # =========================================================

    def build_guid_index(
        self,
        max_assets: int | None = None,
        force_rebuild: bool = False,
    ) -> dict[str, Any]:
        """
        Build a GUID -> asset path index.

        Unity references assets primarily through GUIDs.

        The completed index is cached for later lookups.
        """

        if (
            self._guid_index is not None
            and not force_rebuild
            and max_assets is None
        ):
            return {
                "success": True,
                "project": self.project_path.name,
                "guid_count": len(
                    self._guid_index
                ),
                "scanned_meta_files": None,
                "errors": [],
                "cached": True,
                "index": dict(
                    sorted(
                        self._guid_index.items()
                    )
                ),
            }

        index: dict[str, str] = {}
        errors: list[dict[str, str]] = []
        scanned = 0

        for asset in self.iter_assets():

            if asset.suffix.lower() != ".meta":
                continue

            if (
                max_assets is not None
                and scanned >= max_assets
            ):
                break

            scanned += 1

            try:
                content = asset.read_text(
                    encoding="utf-8",
                    errors="replace",
                )

                match = (
                    self.META_GUID_PATTERN.search(
                        content
                    )
                )

                if not match:
                    continue

                guid = match.group(1).lower()

                source_asset = Path(
                    str(asset)[:-5]
                )

                if source_asset.exists():
                    index[guid] = (
                        self.relative_path(
                            source_asset
                        )
                    )

            except OSError as error:
                errors.append(
                    {
                        "path": self.relative_path(
                            asset
                        ),
                        "error": str(error),
                    }
                )

        if max_assets is None:
            self._guid_index = dict(index)

        return {
            "success": True,
            "project": self.project_path.name,
            "guid_count": len(index),
            "scanned_meta_files": scanned,
            "errors": errors,
            "cached": False,
            "index": dict(
                sorted(index.items())
            ),
        }

    # =========================================================
    # GUID LOOKUP
    # =========================================================

    def find_asset_by_guid(
        self,
        guid: str,
    ) -> dict[str, Any]:
        """
        Find the asset associated with a Unity GUID.
        """

        guid = guid.strip().lower()

        if not re.fullmatch(
            r"[0-9a-f]{32}",
            guid,
        ):
            return {
                "success": False,
                "reason": (
                    "Invalid Unity GUID."
                ),
            }

        if self._guid_index is None:
            self.build_guid_index()

        assert self._guid_index is not None

        path = self._guid_index.get(guid)

        if path is None:
            return {
                "success": False,
                "reason": (
                    "No asset with that GUID "
                    "was found."
                ),
                "guid": guid,
            }

        return {
            "success": True,
            "guid": guid,
            "path": path,
            "type": self.get_file_type(
                Path(path)
            ),
        }

    # =========================================================
    # GUID EXTRACTION FROM ASSET
    # =========================================================

    def extract_guids(
        self,
        relative_path: str,
    ) -> dict[str, Any]:
        """
        Extract all Unity GUID references from a text asset.
        """

        result = self.read_text_asset(
            relative_path
        )

        if not result["success"]:
            return result

        content = result["content"]

        guids = sorted(
            {
                guid.lower()
                for guid in self.GUID_PATTERN.findall(
                    content
                )
            }
        )

        return {
            "success": True,
            "path": relative_path,
            "guid_count": len(guids),
            "guids": guids,
        }

    # =========================================================
    # OBJECT REFERENCES
    # =========================================================

    def extract_object_references(
        self,
        relative_path: str,
    ) -> dict[str, Any]:
        """
        Extract serialized Unity object references.

        This provides more information than GUID extraction by
        retaining fileID and serialized reference type.
        """

        result = self.read_text_asset(
            relative_path
        )

        if not result["success"]:
            return result

        content = result["content"]

        references = []

        for match in self.OBJECT_REFERENCE_PATTERN.finditer(
            content
        ):
            file_id = match.group(1)
            guid = match.group(2)
            reference_type = match.group(3)

            references.append(
                {
                    "file_id": file_id,
                    "guid": (
                        guid.lower()
                        if guid
                        else None
                    ),
                    "type_id": (
                        int(reference_type)
                        if reference_type
                        else None
                    ),
                }
            )

        # Remove exact duplicates while preserving order.

        unique = []
        seen = set()

        for reference in references:
            key = (
                reference["file_id"],
                reference["guid"],
                reference["type_id"],
            )

            if key in seen:
                continue

            seen.add(key)
            unique.append(reference)

        return {
            "success": True,
            "path": relative_path,
            "count": len(unique),
            "references": unique,
        }

    # =========================================================
    # REFERENCE SEARCH
    # =========================================================

    def find_references(
        self,
        guid: str,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """
        Find Unity text assets that reference a GUID.

        This is the foundation for dependency tracing.
        """

        guid = guid.strip().lower()

        if not re.fullmatch(
            r"[0-9a-f]{32}",
            guid,
        ):
            return {
                "success": False,
                "reason": "Invalid Unity GUID.",
            }

        max_results = max(
            1,
            min(
                int(max_results),
                1000,
            ),
        )

        results = []

        for asset in self.iter_assets():

            if (
                asset.suffix.lower()
                not in self.TEXT_EXTENSIONS
            ):
                continue

            try:
                if (
                    asset.stat().st_size
                    > self.MAX_TEXT_READ_BYTES
                ):
                    continue

                content = asset.read_text(
                    encoding="utf-8",
                    errors="replace",
                )

            except OSError:
                continue

            if guid not in content.lower():
                continue

            results.append(
                {
                    "path": self.relative_path(
                        asset
                    ),
                    "type": self.get_file_type(
                        asset
                    ),
                }
            )

            if len(results) >= max_results:
                break

        return {
            "success": True,
            "guid": guid,
            "count": len(results),
            "limited": (
                len(results) >= max_results
            ),
            "references": results,
        }

    # =========================================================
    # CONTENT SEARCH
    # =========================================================

    def search_content(
        self,
        query: str,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """
        Search inside readable Unity text assets.

        Searches case-insensitively.
        """

        query = query.strip()

        if not query:
            return {
                "success": False,
                "reason": (
                    "Search query cannot be empty."
                ),
            }

        max_results = max(
            1,
            min(
                int(max_results),
                1000,
            ),
        )

        query_lower = query.lower()
        results = []

        for asset in self.iter_assets():

            if (
                asset.suffix.lower()
                not in self.TEXT_EXTENSIONS
            ):
                continue

            try:

                if (
                    asset.stat().st_size
                    > self.MAX_TEXT_READ_BYTES
                ):
                    continue

                content = asset.read_text(
                    encoding="utf-8",
                    errors="replace",
                )

            except OSError:
                continue

            content_lower = content.lower()

            if query_lower not in content_lower:
                continue

            line_matches = []

            for line_number, line in enumerate(
                content.splitlines(),
                start=1,
            ):

                if query_lower not in line.lower():
                    continue

                line_matches.append(
                    {
                        "line": line_number,
                        "text": line.strip()[:1000],
                    }
                )

                if len(line_matches) >= 20:
                    break

            results.append(
                {
                    "path": self.relative_path(
                        asset
                    ),
                    "type": self.get_file_type(
                        asset
                    ),
                    "matches": line_matches,
                }
            )

            if len(results) >= max_results:
                break

        return {
            "success": True,
            "query": query,
            "count": len(results),
            "limited": (
                len(results) >= max_results
            ),
            "results": results,
        }

    # =========================================================
    # ASSET INSPECTION
    # =========================================================

    def inspect_asset(
        self,
        relative_path: str,
    ) -> dict[str, Any]:
        """
        Perform a deeper read-only inspection of an asset.

        Includes:
            - metadata
            - GUID references
            - Unity YAML object types
            - basic size information
        """

        info = self.inspect_file(
            relative_path
        )

        if not info["success"]:
            return info

        result: dict[str, Any] = dict(info)

        extension = info["extension"]

        if extension == ".meta":

            meta = self.parse_meta(
                relative_path
            )

            result["meta"] = meta

            return result

        if extension not in self.TEXT_EXTENSIONS:

            result["readable_text"] = False

            return result

        text = self.read_text_asset(
            relative_path
        )

        if not text["success"]:

            result["readable_text"] = False
            result["read_error"] = text[
                "reason"
            ]

            return result

        content = text["content"]

        result["readable_text"] = True
        result["text_size"] = len(content)

        guids = sorted(
            {
                guid.lower()
                for guid in self.GUID_PATTERN.findall(
                    content
                )
            }
        )

        result["referenced_guids"] = guids
        result["referenced_guid_count"] = len(
            guids
        )

        objects = []

        for match in self.YAML_OBJECT_PATTERN.finditer(
            content
        ):

            type_id = int(
                match.group(1)
            )

            file_id = match.group(2)

            objects.append(
                {
                    "type_id": type_id,
                    "type": self.UNITY_OBJECT_TYPES.get(
                        type_id,
                        "UnityObject",
                    ),
                    "file_id": file_id,
                }
            )

        result["yaml_objects"] = objects

        return result

    # =========================================================
    # YAML OBJECT ANALYSIS
    # =========================================================

    def analyze_yaml_objects(
        self,
        relative_path: str,
    ) -> dict[str, Any]:
        """
        Parse Unity YAML documents into a generic object list.

        This is intentionally generic and does not assume that the
        asset is a particular VRChat package.
        """

        result = self.read_text_asset(
            relative_path
        )

        if not result["success"]:
            return result

        content = result["content"]

        objects = []

        for match in self.YAML_DOCUMENT_PATTERN.finditer(
            content
        ):
            type_id = int(
                match.group(1)
            )

            file_id = match.group(2)
            body = match.group(3)

            names = self.GAMEOBJECT_NAME_PATTERN.findall(
                body
            )

            object_name = (
                names[-1].strip()
                if names
                else None
            )

            script_guid = None

            script_match = (
                self.SCRIPT_REFERENCE_PATTERN.search(
                    body
                )
            )

            if script_match:
                script_guid = (
                    script_match.group(2).lower()
                )

            object_info = {
                "type_id": type_id,
                "type": self.UNITY_OBJECT_TYPES.get(
                    type_id,
                    "UnityObject",
                ),
                "file_id": file_id,
                "name": object_name,
                "script_guid": script_guid,
            }

            objects.append(object_info)

        return {
            "success": True,
            "path": relative_path,
            "object_count": len(objects),
            "objects": objects,
        }

    # =========================================================
    # PREFAB ANALYSIS
    # =========================================================

    def analyze_prefab(
        self,
        relative_path: str,
    ) -> dict[str, Any]:
        """
        Analyse a prefab without modifying it.

        Extracts:
            - Unity objects
            - GameObjects
            - components
            - script GUIDs
            - asset GUID references
        """

        info = self.inspect_file(
            relative_path
        )

        if not info["success"]:
            return info

        if info["extension"] != ".prefab":
            return {
                "success": False,
                "reason": (
                    "The supplied file is not "
                    "a prefab."
                ),
            }

        objects = self.analyze_yaml_objects(
            relative_path
        )

        if not objects["success"]:
            return objects

        references = self.extract_object_references(
            relative_path
        )

        if not references["success"]:
            return references

        gameobjects = []
        components = []

        for obj in objects["objects"]:

            if obj["type"] == "GameObject":
                gameobjects.append(obj)
            else:
                components.append(obj)

        script_guids = sorted(
            {
                obj["script_guid"]
                for obj in objects["objects"]
                if obj.get("script_guid")
            }
        )

        return {
            "success": True,
            "path": relative_path,
            "type": "prefab",
            "objects": objects["objects"],
            "object_count": len(
                objects["objects"]
            ),
            "gameobjects": gameobjects,
            "gameobject_count": len(
                gameobjects
            ),
            "components": components,
            "component_count": len(
                components
            ),
            "script_guids": script_guids,
            "object_references": references[
                "references"
            ],
            "object_reference_count": references[
                "count"
            ],
        }

    # =========================================================
    # SCENE ANALYSIS
    # =========================================================

    def analyze_scene(
        self,
        relative_path: str,
    ) -> dict[str, Any]:
        """
        Analyse a Unity scene using the same generic YAML parser
        used for prefabs.
        """

        info = self.inspect_file(
            relative_path
        )

        if not info["success"]:
            return info

        if info["extension"] != ".unity":
            return {
                "success": False,
                "reason": (
                    "The supplied file is not "
                    "a Unity scene."
                ),
            }

        objects = self.analyze_yaml_objects(
            relative_path
        )

        if not objects["success"]:
            return objects

        gameobjects = [
            obj
            for obj in objects["objects"]
            if obj["type"] == "GameObject"
        ]

        components = [
            obj
            for obj in objects["objects"]
            if obj["type"] != "GameObject"
        ]

        return {
            "success": True,
            "path": relative_path,
            "type": "scene",
            "objects": objects["objects"],
            "object_count": len(
                objects["objects"]
            ),
            "gameobjects": gameobjects,
            "gameobject_count": len(
                gameobjects
            ),
            "components": components,
            "component_count": len(
                components
            ),
        }

    # =========================================================
    # ANIMATION ANALYSIS
    # =========================================================

    def analyze_animation(
        self,
        relative_path: str,
    ) -> dict[str, Any]:
        """
        Analyse an AnimationClip.

        Extracts likely animated paths, properties, object bindings
        and GUID references.
        """

        info = self.inspect_file(
            relative_path
        )

        if not info["success"]:
            return info

        if info["extension"] != ".anim":
            return {
                "success": False,
                "reason": (
                    "The supplied file is not "
                    "an animation clip."
                ),
            }

        result = self.read_text_asset(
            relative_path
        )

        if not result["success"]:
            return result

        content = result["content"]

        paths = sorted(
            {
                value.strip()
                for value in self.ANIMATION_PATH_PATTERN.findall(
                    content
                )
                if value.strip()
            }
        )

        attributes = sorted(
            {
                value.strip()
                for value in self.ANIMATION_ATTRIBUTE_PATTERN.findall(
                    content
                )
                if value.strip()
            }
        )

        guids = sorted(
            {
                guid.lower()
                for guid in self.GUID_PATTERN.findall(
                    content
                )
            }
        )

        return {
            "success": True,
            "path": relative_path,
            "type": "animation",
            "size": len(content),
            "animated_paths": paths,
            "animated_path_count": len(paths),
            "animated_properties": attributes,
            "animated_property_count": len(
                attributes
            ),
            "referenced_guids": guids,
            "referenced_guid_count": len(
                guids
            ),
        }

    # =========================================================
    # ANIMATOR CONTROLLER
    # =========================================================

    def inspect_animator_controller(
        self,
        relative_path: str,
    ) -> dict[str, Any]:
        """
        Inspect a Unity Animator Controller.

        Extracts useful structural information from serialized YAML.
        """

        info = self.inspect_file(
            relative_path
        )

        if not info["success"]:
            return info

        if info["extension"] != ".controller":
            return {
                "success": False,
                "reason": (
                    "The supplied file is not "
                    "an Animator Controller."
                ),
            }

        result = self.read_text_asset(
            relative_path
        )

        if not result["success"]:
            return result

        content = result["content"]

        states = []

        state_matches = re.finditer(
            r"^\s*m_Name:\s*(.+?)\s*$",
            content,
            re.MULTILINE,
        )

        for match in state_matches:

            name = match.group(1).strip()

            if name:
                states.append(name)

        parameters = []

        parameter_pattern = re.compile(
            r"^\s*-\s*name:\s*(.+?)\s*$",
            re.MULTILINE,
        )

        for match in parameter_pattern.finditer(
            content
        ):

            name = match.group(1).strip()

            if name:
                parameters.append(name)

        guids = sorted(
            {
                guid.lower()
                for guid in self.GUID_PATTERN.findall(
                    content
                )
            }
        )

        return {
            "success": True,
            "path": relative_path,
            "type": "animator_controller",
            "size": len(content),
            "possible_state_names": sorted(
                set(states),
                key=str.lower,
            ),
            "possible_parameters": sorted(
                set(parameters),
                key=str.lower,
            ),
            "referenced_guids": guids,
            "referenced_guid_count": len(
                guids
            ),
        }

    # =========================================================
    # VRCHAT EXPRESSION PARAMETERS
    # =========================================================

    def inspect_vrchat_parameters(
        self,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """
        Find likely VRChat Expression Parameters assets.
        """

        results = []

        for asset in self.iter_assets():

            if asset.suffix.lower() != ".asset":
                continue

            try:

                if (
                    asset.stat().st_size
                    > self.MAX_TEXT_READ_BYTES
                ):
                    continue

                content = asset.read_text(
                    encoding="utf-8",
                    errors="replace",
                )

            except OSError:
                continue

            lowered = content.lower()

            if (
                "vrc_expressionparameters"
                not in lowered
                and "vrcexpressionparameters"
                not in lowered
            ):
                continue

            results.append(
                {
                    "path": self.relative_path(
                        asset
                    ),
                    "type": "vrchat_expression_parameters",
                    "size": asset.stat().st_size,
                }
            )

            if len(results) >= max_results:
                break

        return {
            "success": True,
            "count": len(results),
            "results": results,
        }

    # =========================================================
    # VRCHAT EXPRESSION MENUS
    # =========================================================

    def inspect_vrchat_menus(
        self,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """
        Find likely VRChat Expressions Menu assets.
        """

        results = []

        for asset in self.iter_assets():

            if asset.suffix.lower() != ".asset":
                continue

            try:

                if (
                    asset.stat().st_size
                    > self.MAX_TEXT_READ_BYTES
                ):
                    continue

                content = asset.read_text(
                    encoding="utf-8",
                    errors="replace",
                )

            except OSError:
                continue

            lowered = content.lower()

            if (
                "vrcexpressionsmenu"
                not in lowered
                and "vrc_expressionmenu"
                not in lowered
            ):
                continue

            results.append(
                {
                    "path": self.relative_path(
                        asset
                    ),
                    "type": "vrchat_expression_menu",
                    "size": asset.stat().st_size,
                }
            )

            if len(results) >= max_results:
                break

        return {
            "success": True,
            "count": len(results),
            "results": results,
        }

    # =========================================================
    # GENERIC VRCHAT / VRCFURY DETECTION
    # =========================================================

    def detect_vrchat_features(
        self,
        relative_path: str,
    ) -> dict[str, Any]:
        """
        Detect VRChat/VRCFury-related serialized content.

        This deliberately does not target one specific asset.
        """

        result = self.read_text_asset(
            relative_path
        )

        if not result["success"]:
            return result

        content = result["content"]
        lowered = content.lower()

        matches = []

        for identifier in sorted(
            self.VRC_IDENTIFIERS
        ):
            if identifier in lowered:
                matches.append(identifier)

        return {
            "success": True,
            "path": relative_path,
            "is_vrchat_related": bool(matches),
            "detected_identifiers": matches,
        }

    # =========================================================
    # DEPENDENCY ANALYSIS
    # =========================================================

    def analyze_dependencies(
        self,
        relative_path: str,
        max_dependencies: int = 200,
    ) -> dict[str, Any]:
        """
        Resolve GUID references from an asset into actual project
        assets.

        This is read-only and forms the basis of the generic
        dependency graph.
        """

        guid_result = self.extract_guids(
            relative_path
        )

        if not guid_result["success"]:
            return guid_result

        guids = guid_result["guids"]

        max_dependencies = max(
            1,
            min(
                int(max_dependencies),
                1000,
            ),
        )

        dependencies = []
        unresolved = []

        for guid in guids:

            resolved = self.find_asset_by_guid(
                guid
            )

            if resolved["success"]:
                dependencies.append(
                    {
                        "guid": guid,
                        "path": resolved["path"],
                        "type": resolved["type"],
                    }
                )
            else:
                unresolved.append(guid)

            if (
                len(dependencies)
                + len(unresolved)
                >= max_dependencies
            ):
                break

        return {
            "success": True,
            "path": relative_path,
            "guid_count": len(guids),
            "dependency_count": len(
                dependencies
            ),
            "dependencies": dependencies,
            "unresolved_guids": unresolved,
            "unresolved_count": len(
                unresolved
            ),
            "limited": (
                len(guids)
                > max_dependencies
            ),
        }

    # =========================================================
    # DEPENDENTS
    # =========================================================

    def find_dependents(
        self,
        relative_path: str,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """
        Find project assets that reference the supplied asset.

        This performs the reverse side of dependency analysis.
        """

        max_results = max(
            1,
            min(
                int(max_results),
                1000,
            ),
        )

        try:
            target = self.resolve_project_path(
                relative_path
            )
        except PermissionError as error:
            return {
                "success": False,
                "reason": str(error),
            }

        if not target.exists():
            return {
                "success": False,
                "reason": "Asset does not exist.",
            }

        meta = Path(
            str(target) + ".meta"
        )

        if not meta.is_file():
            return {
                "success": False,
                "reason": (
                    "Asset does not have a "
                    "corresponding .meta file."
                ),
            }

        meta_result = self.parse_meta(
            self.relative_path(meta)
        )

        if not meta_result["success"]:
            return meta_result

        guid = meta_result.get("guid")

        if not guid:
            return {
                "success": False,
                "reason": (
                    "Asset .meta file does not "
                    "contain a GUID."
                ),
            }

        references = self.find_references(
            guid,
            max_results=max_results,
        )

        if not references["success"]:
            return references

        return {
            "success": True,
            "path": relative_path,
            "guid": guid,
            "dependents": references[
                "references"
            ],
            "count": references[
                "count"
            ],
            "limited": references[
                "limited"
            ],
        }

    # =========================================================
    # RECURSIVE DEPENDENCY TREE
    # =========================================================

    def build_dependency_tree(
        self,
        relative_path: str,
        max_depth: int = 3,
        max_nodes: int = 250,
    ) -> dict[str, Any]:
        """
        Build a bounded recursive dependency tree.

        Limits are intentionally enforced so a large Unity project
        cannot cause an uncontrolled recursive scan.
        """

        max_depth = max(
            0,
            min(
                int(max_depth),
                10,
            ),
        )

        max_nodes = max(
            1,
            min(
                int(max_nodes),
                5000,
            ),
        )

        visited: set[str] = set()
        node_counter = 0

        def walk(
            path: str,
            depth: int,
        ) -> dict[str, Any]:

            nonlocal node_counter

            normalized = path.replace(
                "\\",
                "/",
            ).lower()

            if normalized in visited:
                return {
                    "path": path,
                    "cycle": True,
                }

            if node_counter >= max_nodes:
                return {
                    "path": path,
                    "truncated": True,
                }

            visited.add(normalized)
            node_counter += 1

            info = self.inspect_file(
                path
            )

            node: dict[str, Any] = {
                "path": path,
            }

            if not info["success"]:
                node["error"] = info["reason"]
                return node

            node["type"] = info["type"]

            if depth >= max_depth:
                node["depth_limit"] = True
                return node

            dependencies = self.analyze_dependencies(
                path,
                max_dependencies=100,
            )

            if not dependencies["success"]:
                return node

            children = []

            for dependency in dependencies[
                "dependencies"
            ]:

                child = walk(
                    dependency["path"],
                    depth + 1,
                )

                child["guid"] = dependency[
                    "guid"
                ]

                children.append(child)

                if node_counter >= max_nodes:
                    break

            node["dependencies"] = children

            if node_counter >= max_nodes:
                node["truncated"] = True

            return node

        tree = walk(
            relative_path,
            0,
        )

        return {
            "success": True,
            "root": relative_path,
            "max_depth": max_depth,
            "max_nodes": max_nodes,
            "nodes_scanned": node_counter,
            "tree": tree,
        }

    # =========================================================
    # GENERIC ASSET ANALYSIS
    # =========================================================

    def analyze_asset(
        self,
        relative_path: str,
        include_dependencies: bool = True,
        include_dependents: bool = False,
        dependency_depth: int = 2,
        max_nodes: int = 150,
    ) -> dict[str, Any]:
        """
        Perform a generic high-level analysis of any supported
        Unity asset.

        The method automatically selects specialised analysis
        based on the asset type while retaining generic information.

        No filesystem mutation occurs.
        """

        info = self.inspect_file(
            relative_path
        )

        if not info["success"]:
            return info

        extension = info["extension"]

        result: dict[str, Any] = {
            "success": True,
            "path": relative_path,
            "type": info["type"],
            "extension": extension,
            "size": info["size"],
        }

        # -----------------------------------------------------
        # Generic inspection
        # -----------------------------------------------------

        if extension in self.TEXT_EXTENSIONS:

            inspected = self.inspect_asset(
                relative_path
            )

            if inspected["success"]:

                result["referenced_guids"] = (
                    inspected.get(
                        "referenced_guids",
                        [],
                    )
                )

                result["referenced_guid_count"] = (
                    inspected.get(
                        "referenced_guid_count",
                        0,
                    )
                )

                result["yaml_objects"] = (
                    inspected.get(
                        "yaml_objects",
                        [],
                    )
                )

        # -----------------------------------------------------
        # Specialised analysis
        # -----------------------------------------------------

        if extension == ".prefab":

            result["prefab_analysis"] = (
                self.analyze_prefab(
                    relative_path
                )
            )

        elif extension == ".unity":

            result["scene_analysis"] = (
                self.analyze_scene(
                    relative_path
                )
            )

        elif extension == ".anim":

            result["animation_analysis"] = (
                self.analyze_animation(
                    relative_path
                )
            )

        elif extension == ".controller":

            result["animator_analysis"] = (
                self.inspect_animator_controller(
                    relative_path
                )
            )

        # -----------------------------------------------------
        # VRChat/VRCFury detection
        # -----------------------------------------------------

        if extension in self.TEXT_EXTENSIONS:

            result["vrchat_analysis"] = (
                self.detect_vrchat_features(
                    relative_path
                )
            )

        # -----------------------------------------------------
        # Dependencies
        # -----------------------------------------------------

        if include_dependencies:

            result["dependency_analysis"] = (
                self.analyze_dependencies(
                    relative_path
                )
            )

            result["dependency_tree"] = (
                self.build_dependency_tree(
                    relative_path,
                    max_depth=dependency_depth,
                    max_nodes=max_nodes,
                )
            )

        # -----------------------------------------------------
        # Reverse dependencies
        # -----------------------------------------------------

        if include_dependents:

            result["dependent_analysis"] = (
                self.find_dependents(
                    relative_path
                )
            )

        return result

    # =========================================================
    # FULL PROJECT SEARCH
    # =========================================================

    def find_asset(
        self,
        query: str,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """
        Search both filenames and readable content.

        This is intended as a convenient high-level search
        function for AngelAI.
        """

        filename_results = self.search_assets(
            query,
            max_results=max_results,
        )

        content_results = self.search_content(
            query,
            max_results=max_results,
        )

        return {
            "success": True,
            "query": query,
            "filename_matches": (
                filename_results.get(
                    "results",
                    [],
                )
            ),
            "content_matches": (
                content_results.get(
                    "results",
                    [],
                )
            ),
        }