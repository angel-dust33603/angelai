from pathlib import Path

from filesystem.file_policy import FilePolicy


class FileBridge:
    """
    Controlled interface between AngelAI and the filesystem.

    Every filesystem operation must pass through FilePolicy and
    therefore requires a valid, unexpired capability token.
    """

    def __init__(self):

        self.policy = FilePolicy()

    # =========================================================
    # ACCESS
    # =========================================================

    def grant_access(
        self,
        path: str,
        permissions: set[str]
    ):

        return self.policy.grant_access(
            path,
            permissions
        )

    def revoke_token(
        self,
        token: str
    ):

        return {
            "revoked": self.policy.revoke_token(
                token
            )
        }

    # =========================================================
    # READ
    # =========================================================

    def read_file(
        self,
        token: str,
        path: str
    ):

        allowed, reason = self.policy.validate_token(
            token,
            path,
            FilePolicy.READ
        )

        if not allowed:

            return {
                "success": False,
                "reason": reason,
            }

        target = self.policy.resolve_path(path)

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

        try:

            content = target.read_text(
                encoding="utf-8"
            )

        except UnicodeDecodeError:

            return {
                "success": False,
                "reason": (
                    "File is not a UTF-8 text file."
                ),
            }

        except OSError as error:

            return {
                "success": False,
                "reason": str(error),
            }

        return {
            "success": True,
            "path": str(target),
            "content": content,
        }

    # =========================================================
    # LIST DIRECTORY
    # =========================================================

    def list_directory(
        self,
        token: str,
        path: str
    ):

        allowed, reason = self.policy.validate_token(
            token,
            path,
            FilePolicy.READ
        )

        if not allowed:

            return {
                "success": False,
                "reason": reason,
            }

        target = self.policy.resolve_path(path)

        if not target.exists():

            return {
                "success": False,
                "reason": "Directory does not exist.",
            }

        if not target.is_dir():

            return {
                "success": False,
                "reason": "Path is not a directory.",
            }

        try:

            entries = []

            for entry in target.iterdir():

                entries.append(
                    {
                        "name": entry.name,
                        "type": (
                            "directory"
                            if entry.is_dir()
                            else "file"
                        ),
                    }
                )

        except OSError as error:

            return {
                "success": False,
                "reason": str(error),
            }

        entries.sort(
            key=lambda item: (
                item["type"],
                item["name"].lower()
            )
        )

        return {
            "success": True,
            "path": str(target),
            "entries": entries,
        }

    # =========================================================
    # CREATE DIRECTORY
    # =========================================================

    def create_directory(
        self,
        token: str,
        path: str
    ):

        allowed, reason = self.policy.validate_token(
            token,
            path,
            FilePolicy.CREATE
        )

        if not allowed:

            return {
                "success": False,
                "reason": reason,
            }

        target = self.policy.resolve_path(path)

        if target.exists():

            return {
                "success": False,
                "reason": "Path already exists.",
            }

        try:

            target.mkdir(
                parents=True,
                exist_ok=False
            )

        except OSError as error:

            return {
                "success": False,
                "reason": str(error),
            }

        return {
            "success": True,
            "path": str(target),
        }

    # =========================================================
    # WRITE FILE
    # =========================================================

    def write_file(
        self,
        token: str,
        path: str,
        content: str
    ):

        target = self.policy.resolve_path(path)

        operation = (
            FilePolicy.WRITE
            if target.exists()
            else FilePolicy.CREATE
        )

        allowed, reason = self.policy.validate_token(
            token,
            target,
            operation
        )

        if not allowed:

            return {
                "success": False,
                "reason": reason,
            }

        if target.exists() and not target.is_file():

            return {
                "success": False,
                "reason": "Path is not a file.",
            }

        try:

            target.write_text(
                content,
                encoding="utf-8"
            )

        except OSError as error:

            return {
                "success": False,
                "reason": str(error),
            }

        return {
            "success": True,
            "path": str(target),
        }

    # =========================================================
    # DELETE FILE
    # =========================================================

    def delete_file(
        self,
        token: str,
        path: str
    ):

        allowed, reason = self.policy.validate_token(
            token,
            path,
            FilePolicy.DELETE
        )

        if not allowed:

            return {
                "success": False,
                "reason": reason,
            }

        target = self.policy.resolve_path(path)

        if not target.exists():

            return {
                "success": False,
                "reason": "Path does not exist.",
            }

        if target.is_dir():

            return {
                "success": False,
                "reason": (
                    "Directory deletion is not "
                    "supported."
                ),
            }

        try:

            target.unlink()

        except OSError as error:

            return {
                "success": False,
                "reason": str(error),
            }

        return {
            "success": True,
            "path": str(target),
        }

    # =========================================================
    # STATUS
    # =========================================================

    def show_permissions(self):

        return self.policy.get_active_grants()
