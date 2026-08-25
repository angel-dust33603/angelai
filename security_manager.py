import getpass
import hashlib
import hmac
import json
import secrets
from pathlib import Path


SECURITY_DIRECTORY = Path.home() / "AngelAI" / "security"
SECURITY_FILE = SECURITY_DIRECTORY / "security.json"

PBKDF2_ITERATIONS = 600_000


class SecurityManager:

    def __init__(self):

        SECURITY_DIRECTORY.mkdir(
            parents=True,
            exist_ok=True
        )

        self.security_file = SECURITY_FILE

    # ---------------------------------------------------------
    # SECURITY FILE
    # ---------------------------------------------------------

    def _load_security_data(self):

        if not self.security_file.exists():
            return None

        with self.security_file.open(
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    def _save_security_data(self, data):

        with self.security_file.open(
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                indent=4
            )

    # ---------------------------------------------------------
    # HASHING
    # ---------------------------------------------------------

    def _hash_code(
        self,
        code: str,
        salt: bytes
    ):

        return hashlib.pbkdf2_hmac(
            "sha256",
            code.encode("utf-8"),
            salt,
            PBKDF2_ITERATIONS
        )

    # ---------------------------------------------------------
    # INITIAL SETUP
    # ---------------------------------------------------------

    def is_configured(self):

        return self.security_file.exists()

    def setup_code(self):

        if self.is_configured():

            print(
                "A security code is already configured."
            )

            return False

        print()
        print("=== AngelAI Security Setup ===")
        print()

        while True:

            code = getpass.getpass(
                "Create security code: "
            )

            if not code:

                print(
                    "Security code cannot be empty."
                )

                continue

            confirmation = getpass.getpass(
                "Confirm security code: "
            )

            if code != confirmation:

                print(
                    "Codes do not match."
                )

                continue

            break

        salt = secrets.token_bytes(32)

        password_hash = self._hash_code(
            code,
            salt
        )

        data = {
            "algorithm": "PBKDF2-HMAC-SHA256",
            "iterations": PBKDF2_ITERATIONS,
            "salt": salt.hex(),
            "hash": password_hash.hex()
        }

        self._save_security_data(
            data
        )

        print()
        print(
            "Security code configured successfully."
        )

        return True

    # ---------------------------------------------------------
    # VERIFY CODE
    # ---------------------------------------------------------

    def verify_code(self, code: str):

        data = self._load_security_data()

        if data is None:

            return False

        salt = bytes.fromhex(
            data["salt"]
        )

        expected_hash = bytes.fromhex(
            data["hash"]
        )

        actual_hash = self._hash_code(
            code,
            salt
        )

        return hmac.compare_digest(
            actual_hash,
            expected_hash
        )

    # ---------------------------------------------------------
    # INTERACTIVE VERIFICATION
    # ---------------------------------------------------------

    def request_authorization(
        self,
        action: str
    ):

        if not self.is_configured():

            print()
            print(
                "No security code has been configured."
            )

            print(
                "Run security setup first."
            )

            return False

        print()
        print(
            f"Security authorization required "
            f"for: {action}"
        )

        code = getpass.getpass(
            "Security code: "
        )

        if self.verify_code(code):

            print(
                "Authorization successful."
            )

            return True

        print(
            "Authorization failed."
        )

        return False


# =============================================================
# TEST INTERFACE
# =============================================================

def main():

    security = SecurityManager()

    print()
    print("===================================")
    print("       AngelAI Security Manager")
    print("===================================")
    print()

    if not security.is_configured():

        print(
            "No security code configured."
        )

        print()

        choice = input(
            "Create one now? [y/N]: "
        ).strip().lower()

        if choice == "y":

            security.setup_code()

        else:

            print(
                "Security setup cancelled."
            )

        return

    print(
        "Security code is already configured."
    )

    print()

    choice = input(
        "Test authorization? [y/N]: "
    ).strip().lower()

    if choice == "y":

        security.request_authorization(
            "security test"
        )


if __name__ == "__main__":
    main()