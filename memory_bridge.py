import re
import sys
from pathlib import Path

from memory_manager import MemoryManager
from memory_policy import MemoryPolicy


ANGELAI_DIRECTORY = Path(__file__).resolve().parent.parent

if str(ANGELAI_DIRECTORY) not in sys.path:
    sys.path.insert(
        0,
        str(ANGELAI_DIRECTORY)
    )

from security.security_manager import SecurityManager


class MemoryBridge:

    def __init__(self):

        self.memory = MemoryManager()
        self.policy = MemoryPolicy()
        self.security = SecurityManager()

    # ---------------------------------------------------------
    # MEMORY COMMANDS
    # ---------------------------------------------------------

    def remember(
        self,
        text: str,
        category: str = "general",
        importance: int = 5,
        explicit: bool = False
    ):

        decision = self.policy.evaluate(
            text=text,
            category=category,
            importance=importance,
            explicit=explicit
        )

        if not decision.allowed:

            return {
                "saved": False,
                "reason": decision.reason
            }

        memory_id = self.memory.remember(
            memory=text,
            category=decision.category,
            importance=decision.importance
        )

        return {
            "saved": True,
            "id": memory_id,
            "reason": decision.reason
        }

    # ---------------------------------------------------------
    # SEARCH
    # ---------------------------------------------------------

    def search(
        self,
        query: str,
        limit: int = 10
    ):

        return self.memory.search(
            query=query,
            limit=limit
        )

    # ---------------------------------------------------------
    # SECURED UPDATE
    # ---------------------------------------------------------

    def update(
        self,
        memory_id: int,
        new_memory: str
    ):

        existing = self.memory.get(
            memory_id
        )

        if existing is None:

            return {
                "updated": False,
                "reason": (
                    f"Memory #{memory_id} "
                    "does not exist."
                )
            }

        authorized = self.security.request_authorization(
            f"change memory #{memory_id}"
        )

        if not authorized:

            return {
                "updated": False,
                "reason": (
                    "Security authorization failed."
                )
            }

        decision = self.policy.evaluate(
            text=new_memory,
            category=existing["category"],
            importance=existing["importance"],
            explicit=True
        )

        if not decision.allowed:

            return {
                "updated": False,
                "reason": decision.reason
            }

        updated = self.memory.update(
            memory_id=memory_id,
            memory=new_memory,
            category=decision.category,
            importance=decision.importance
        )

        if not updated:

            return {
                "updated": False,
                "reason": (
                    "The memory could not be updated."
                )
            }

        return {
            "updated": True,
            "id": memory_id,
            "old_memory": existing["memory"],
            "new_memory": new_memory,
            "old_importance": existing["importance"],
            "new_importance": decision.importance
        }

    # ---------------------------------------------------------
    # SECURED FORGET
    # ---------------------------------------------------------

    def forget(
        self,
        memory_id: int
    ):

        existing = self.memory.get(
            memory_id
        )

        if existing is None:

            return {
                "deleted": False,
                "reason": (
                    f"Memory #{memory_id} "
                    "does not exist."
                )
            }

        authorized = self.security.request_authorization(
            f"delete memory #{memory_id}"
        )

        if not authorized:

            return {
                "deleted": False,
                "reason": (
                    "Security authorization failed."
                )
            }

        deleted = self.memory.forget(
            memory_id
        )

        return {
            "deleted": deleted,
            "id": memory_id
        }

    # ---------------------------------------------------------
    # FORMAT MEMORIES
    # ---------------------------------------------------------

    def format_memories(
        self,
        memories
    ):

        if not memories:

            return "No relevant memories found."

        lines = []

        for memory in memories:

            lines.append(
                f"- #{memory['id']} "
                f"[{memory['category']}] "
                f"{memory['memory']}"
            )

        return "\n".join(lines)

    def get_context(
        self,
        query: str
    ):

        memories = self.search(
            query
        )

        return self.format_memories(
            memories
        )

    # ---------------------------------------------------------
    # MEMORY REQUEST DETECTION
    # ---------------------------------------------------------

    def detect_memory_request(
        self,
        text: str
    ):

        text = text.strip()

        if not text:
            return None

        # -----------------------------------------------------
        # UPDATE
        #
        # Update commands remain deliberately structured.
        # -----------------------------------------------------

        update_patterns = [
            r"^change memory (\d+) to (.+)$",
            r"^update memory (\d+) to (.+)$",
            r"^replace memory (\d+) with (.+)$",
            r"^change memory (\d+) so that (.+)$",
            r"^update memory (\d+) so that (.+)$",
        ]

        for pattern in update_patterns:

            match = re.match(
                pattern,
                text,
                re.IGNORECASE
            )

            if match:

                return {
                    "action": "update",
                    "id": int(match.group(1)),
                    "text": match.group(2).strip()
                }

        # -----------------------------------------------------
        # REMEMBER
        #
        # Explicit memory phrases are now wildcards.
        #
        # Example:
        #
        # "hey please remember that Angel likes Python"
        #
        # becomes:
        #
        # "Angel likes Python"
        # -----------------------------------------------------

        remember_phrases = [
            "remember that",
            "remember this",
            "don't forget that",
            "dont forget that",
            "from now on",
            "going forward",
            "keep in mind that",
            "keep in mind",
        ]

        text_lower = text.lower()

        remember_match = None
        matched_phrase = None

        for phrase in remember_phrases:

            index = text_lower.find(
                phrase
            )

            if index == -1:
                continue

            # Keep the earliest matching trigger.
            if (
                remember_match is None
                or index < remember_match
            ):

                remember_match = index
                matched_phrase = phrase

        if matched_phrase is not None:

            memory_text = text[
                remember_match + len(matched_phrase):
            ].strip()

            # Remove common punctuation immediately after
            # the trigger.
            memory_text = memory_text.lstrip(
                " :,-;."
            ).strip()

            # Do not create an empty memory.
            if memory_text:

                return {
                    "action": "remember",
                    "text": memory_text
                }

        # -----------------------------------------------------
        # FORGET
        #
        # These remain structured so normal conversation
        # containing words like "forget" does not accidentally
        # delete anything.
        # -----------------------------------------------------

        forget_patterns = [
            r"^forget memory (\d+)$",
            r"^delete memory (\d+)$",
            r"^remove memory (\d+)$",
            r"^forget that (.+)$",
            r"^forget (.+)$",
            r"^don't remember that (.+)$",
            r"^dont remember that (.+)$",
        ]

        for pattern in forget_patterns:

            match = re.match(
                pattern,
                text,
                re.IGNORECASE
            )

            if not match:

                continue

            if match.group(1).isdigit():

                return {
                    "action": "forget_id",
                    "id": int(match.group(1))
                }

            return {
                "action": "forget_text",
                "text": match.group(1).strip()
            }

        return None

    # ---------------------------------------------------------
    # DISPLAY MEMORIES
    # ---------------------------------------------------------

    def show_all(self):

        memories = self.memory.get_all()

        if not memories:

            print(
                "No memories stored."
            )

            return

        print()
        print("=== Stored Memories ===")
        print()

        for memory in memories:

            print(
                f"#{memory['id']} "
                f"[{memory['category']}] "
                f"{memory['memory']} "
                f"(importance "
                f"{memory['importance']})"
            )

        print()

    # ---------------------------------------------------------
    # CLOSE
    # ---------------------------------------------------------

    def close(self):

        self.memory.close()


# =============================================================
# TEST INTERFACE
# =============================================================

def main():

    bridge = MemoryBridge()

    print()
    print("===================================")
    print("       AngelAI Memory Bridge")
    print("===================================")
    print()

    try:

        while True:

            text = input(
                "You: "
            ).strip()

            if not text:

                continue

            if text.lower() in {
                "exit",
                "quit",
                "/exit",
                "/quit"
            }:

                break

            # -------------------------------------------------
            # SHOW MEMORIES
            # -------------------------------------------------

            if text.lower() in {
                "show memories",
                "list memories",
                "/memories"
            }:

                bridge.show_all()

                continue

            # -------------------------------------------------
            # SEARCH
            # -------------------------------------------------

            search_match = re.match(
                r"^(?:search|find) memories?(?: for)? (.+)$",
                text,
                re.IGNORECASE
            )

            if search_match:

                query = search_match.group(1).strip()

                context = bridge.get_context(
                    query
                )

                print()
                print("Relevant memory:")
                print(context)
                print()

                continue

            # -------------------------------------------------
            # MEMORY COMMANDS
            # -------------------------------------------------

            request = bridge.detect_memory_request(
                text
            )

            if request:

                # ---------------------------------------------
                # REMEMBER
                # ---------------------------------------------

                if request["action"] == "remember":

                    result = bridge.remember(
                        request["text"],
                        explicit=True
                    )

                    if result["saved"]:

                        print(
                            f"Memory saved as #{result['id']}"
                        )

                    else:

                        print(
                            "Memory was blocked:"
                        )

                        print(
                            result["reason"]
                        )

                # ---------------------------------------------
                # UPDATE
                # ---------------------------------------------

                elif request["action"] == "update":

                    result = bridge.update(
                        request["id"],
                        request["text"]
                    )

                    if result["updated"]:

                        print(
                            f"Memory #{result['id']} "
                            "updated."
                        )

                        print(
                            f"Old: "
                            f"{result['old_memory']}"
                        )

                        print(
                            f"New: "
                            f"{result['new_memory']}"
                        )

                    else:

                        print(
                            result["reason"]
                        )

                # ---------------------------------------------
                # FORGET BY ID
                # ---------------------------------------------

                elif request["action"] == "forget_id":

                    result = bridge.forget(
                        request["id"]
                    )

                    if result["deleted"]:

                        print(
                            f"Memory #{result['id']} "
                            "deleted."
                        )

                    else:

                        print(
                            result["reason"]
                        )

                # ---------------------------------------------
                # FORGET BY TEXT
                # ---------------------------------------------

                elif request["action"] == "forget_text":

                    matches = bridge.search(
                        request["text"]
                    )

                    if not matches:

                        print(
                            "I couldn't find a matching memory."
                        )

                    else:

                        print()
                        print(
                            "Matching memories:"
                        )
                        print()

                        for memory in matches:

                            print(
                                f"#{memory['id']} "
                                f"[{memory['category']}] "
                                f"{memory['memory']}"
                            )

                        print()
                        print(
                            "Use 'forget memory <ID>' "
                            "to delete one."
                        )

                continue

            # -------------------------------------------------
            # NORMAL SEARCH
            # -------------------------------------------------

            context = bridge.get_context(
                text
            )

            print()
            print("Relevant memory:")
            print(context)
            print()

    except KeyboardInterrupt:

        print()
        print(
            "Stopping memory bridge..."
        )

    finally:

        bridge.close()


if __name__ == "__main__":
    main()