from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import secrets


class FilePolicy:
    """
    Deterministic security policy for AngelAI filesystem access.

    The AI model never decides whether a filesystem operation is
    permitted. This class independently enforces filesystem access.

    Access is granted through short-lived capability tokens.

    A token:
        - is cryptographically random
        - is tied to a specific path
        - contains explicitly approved permissions
        - expires automatically
        - cannot override protected paths
    """

    READ = "read"
    WRITE = "write"
    CREATE = "create"
    DELETE = "delete"

    ALLOWED_OPERATIONS = {
        READ,
        WRITE,
        CREATE,
        DELETE,
    }

    TOKEN_LIFETIME = timedelta(minutes=30)

    @dataclass
    class AccessGrant:
        token: str
        path: Path
        permissions: set[str]
        expires_at: datetime

    def __init__(self):

        self.angelai_directory = (
            Path(__file__).resolve().parent.parent
        )

        self.protected_directories = [
            Path(r"C:\Windows"),
            Path(r"C:\Program Files"),
            Path(r"C:\Program Files (x86)"),
            Path(r"C:\ProgramData"),
            self.angelai_directory,
        ]

        self.protected_files = {
            "angel_ai.py",
            "Modelfile",
            "memory.db",
        }

        self.active_grants = {}

    # =========================================================
    # PATH NORMALISATION
    # =========================================================

    def resolve_path(
        self,
        path: str | Path
    ) -> Path:

        return Path(path).expanduser().resolve()

    # =========================================================
    # PROTECTION
    # =========================================================

    def is_inside(
        self,
        path: Path,
        parent: Path
    ) -> bool:

        try:

            path.relative_to(parent)

            return True

        except ValueError:

            return False

    def is_protected(
        self,
        path: str | Path
    ) -> bool:

        path = self.resolve_path(path)

        for protected in self.protected_directories:

            protected = self.resolve_path(protected)

            if (
                path == protected
                or self.is_inside(
                    path,
                    protected
                )
            ):

                return True

        if path.name.lower() in {
            name.lower()
            for name in self.protected_files
        }:

            if self.is_inside(
                path,
                self.angelai_directory
            ):

                return True

        return False

    # =========================================================
    # TOKEN GENERATION
    # =========================================================

    def generate_token(self) -> str:

        return secrets.token_urlsafe(32)

    # =========================================================
    # CLEAN EXPIRED TOKENS
    # =========================================================

    def cleanup_expired(self):

        now = datetime.now(timezone.utc)

        expired = [
            token
            for token, grant in self.active_grants.items()
            if grant.expires_at <= now
        ]

        for token in expired:

            del self.active_grants[token]

    # =========================================================
    # GRANT ACCESS
    # =========================================================

    def grant_access(
        self,
        path: str | Path,
        permissions: set[str]
    ):

        self.cleanup_expired()

        path = self.resolve_path(path)

        permissions = {
            permission.lower().strip()
            for permission in permissions
        }

        invalid = (
            permissions
            - self.ALLOWED_OPERATIONS
        )

        if invalid:

            raise ValueError(
                "Invalid permissions: "
                + ", ".join(sorted(invalid))
            )

        if not permissions:

            raise ValueError(
                "At least one permission must be granted."
            )

        if self.is_protected(path):

            raise PermissionError(
                "That path is permanently protected."
            )

        token = self.generate_token()

        expires_at = (
            datetime.now(timezone.utc)
            + self.TOKEN_LIFETIME
        )

        self.active_grants[token] = (
            self.AccessGrant(
                token=token,
                path=path,
                permissions=permissions,
                expires_at=expires_at,
            )
        )

        return {
            "token": token,
            "path": str(path),
            "permissions": sorted(permissions),
            "expires_at": expires_at.isoformat(),
        }

    # =========================================================
    # REVOKE TOKEN
    # =========================================================

    def revoke_token(
        self,
        token: str
    ) -> bool:

        return (
            self.active_grants.pop(
                token,
                None
            )
            is not None
        )

    # =========================================================
    # TOKEN VALIDATION
    # =========================================================

    def validate_token(
        self,
        token: str,
        path: str | Path,
        operation: str
    ):

        self.cleanup_expired()

        operation = (
            operation.lower().strip()
        )

        if operation not in self.ALLOWED_OPERATIONS:

            return False, (
                f"Unknown filesystem operation: "
                f"{operation}"
            )

        grant = self.active_grants.get(token)

        if grant is None:

            return False, (
                "Access denied: invalid or expired "
                "filesystem access token."
            )

        target = self.resolve_path(path)

        if self.is_protected(target):

            return False, (
                "Access denied: this path is "
                "permanently protected."
            )

        if not (
            target == grant.path
            or self.is_inside(
                target,
                grant.path
            )
        ):

            return False, (
                "Access denied: the requested path "
                "is outside the approved access scope."
            )

        if operation not in grant.permissions:

            return False, (
                f"Access denied: '{operation}' permission "
                "was not granted for this access token."
            )

        return True, "Allowed."

    # =========================================================
    # TOKEN STATUS
    # =========================================================

    def get_grant(
        self,
        token: str
    ):

        self.cleanup_expired()

        grant = self.active_grants.get(token)

        if grant is None:

            return None

        return {
            "path": str(grant.path),
            "permissions": sorted(
                grant.permissions
            ),
            "expires_at": (
                grant.expires_at.isoformat()
            ),
        }

    # =========================================================
    # DISPLAY ACTIVE GRANTS
    # =========================================================

    def get_active_grants(self):

        self.cleanup_expired()

        results = []

        for grant in self.active_grants.values():

            results.append(
                {
                    "path": str(grant.path),
                    "permissions": sorted(
                        grant.permissions
                    ),
                    "expires_at": (
                        grant.expires_at.isoformat()
                    ),
                }
            )

        return results

