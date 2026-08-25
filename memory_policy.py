from dataclasses import dataclass


@dataclass
class MemoryDecision:
    """
    Result of a memory policy evaluation.
    """

    allowed: bool
    category: str
    importance: int
    reason: str


class MemoryPolicy:
    """
    Controls what information is allowed to become
    persistent memory.

    This layer deliberately does NOT use an AI model.
    It provides deterministic rules that cannot be
    overridden by Qwen.
    """

    # ---------------------------------------------------------
    # Categories
    # ---------------------------------------------------------

    ALLOWED_CATEGORIES = {
        "preference",
        "project",
        "technical",
        "general",
    }

    # ---------------------------------------------------------
    # Sensitive information
    # ---------------------------------------------------------

    SENSITIVE_TERMS = {
        "password",
        "passcode",
        "security code",
        "api key",
        "api token",
        "access token",
        "private key",
        "secret key",
        "credit card",
        "bank account",
        "bank details",
        "social security",
        "national insurance",
        "passport number",
        "driver license",
        "drivers license",
    }

    # ---------------------------------------------------------
    # Temporary information
    # ---------------------------------------------------------

    TEMPORARY_PHRASES = {
        "right now",
        "currently",
        "at the moment",
        "today",
        "tonight",
        "this morning",
        "this afternoon",
        "this evening",
    }

    # ---------------------------------------------------------
    # Explicit memory phrases
    # ---------------------------------------------------------

    EXPLICIT_MEMORY_PHRASES = (
        "remember that",
        "remember this",
        "don't forget that",
        "dont forget that",
        "from now on",
        "going forward",
        "keep in mind",
    )

    # ---------------------------------------------------------
    # Evaluation
    # ---------------------------------------------------------

    def evaluate(
        self,
        text: str,
        category: str = "general",
        importance: int = 5,
        explicit: bool = False,
    ) -> MemoryDecision:

        text_lower = text.lower().strip()

        category = category.lower().strip()

        # -----------------------------------------------------
        # Category validation
        # -----------------------------------------------------

        if category not in self.ALLOWED_CATEGORIES:
            category = "general"

        # -----------------------------------------------------
        # Importance validation
        # -----------------------------------------------------

        try:
            importance = int(importance)
        except (TypeError, ValueError):
            importance = 5

        importance = max(
            1,
            min(
                importance,
                10
            )
        )

        # -----------------------------------------------------
        # Sensitive information
        # -----------------------------------------------------

        for term in self.SENSITIVE_TERMS:

            if term in text_lower:

                return MemoryDecision(
                    allowed=False,
                    category=category,
                    importance=importance,
                    reason=(
                        "Memory appears to contain "
                        f"sensitive information: '{term}'."
                    ),
                )

        # -----------------------------------------------------
        # Explicit user request
        # -----------------------------------------------------

        if explicit:

            return MemoryDecision(
                allowed=True,
                category=category,
                importance=importance,
                reason=(
                    "User explicitly requested "
                    "that this information be remembered."
                ),
            )

        # -----------------------------------------------------
        # Detect explicit phrases automatically
        # -----------------------------------------------------

        for phrase in self.EXPLICIT_MEMORY_PHRASES:

            if phrase in text_lower:

                return MemoryDecision(
                    allowed=True,
                    category=category,
                    importance=max(
                        importance,
                        7
                    ),
                    reason=(
                        "The message contains an "
                        "explicit request for persistent memory."
                    ),
                )

        # -----------------------------------------------------
        # Temporary information
        # -----------------------------------------------------

        temporary_matches = [
            phrase
            for phrase in self.TEMPORARY_PHRASES
            if phrase in text_lower
        ]

        if temporary_matches:

            return MemoryDecision(
                allowed=False,
                category=category,
                importance=importance,
                reason=(
                    "Information appears temporary "
                    "rather than useful as long-term memory."
                ),
            )

        # -----------------------------------------------------
        # Default behaviour
        # -----------------------------------------------------

        return MemoryDecision(
            allowed=False,
            category=category,
            importance=importance,
            reason=(
                "No explicit long-term memory request "
                "was detected."
            ),
        )


# =============================================================
# TEST INTERFACE
# =============================================================

def main():

    policy = MemoryPolicy()

    print()
    print("===================================")
    print("       AngelAI Memory Policy")
    print("===================================")
    print()

    examples = [
        (
            "Angel prefers complete replacement files.",
            "preference",
            8,
        ),
        (
            "Remember that Angel uses VSCodium.",
            "technical",
            7,
        ),
        (
            "Angel's API key is abc123.",
            "technical",
            10,
        ),
        (
            "Angel is currently testing Ollama.",
            "project",
            5,
        ),
        (
            "Angel works on the Discord bot.",
            "project",
            7,
        ),
    ]

    for text, category, importance in examples:

        decision = policy.evaluate(
            text=text,
            category=category,
            importance=importance,
        )

        print("Memory:")
        print(f"  {text}")
        print()

        print(
            f"Allowed: {decision.allowed}"
        )

        print(
            f"Category: {decision.category}"
        )

        print(
            f"Importance: {decision.importance}"
        )

        print(
            f"Reason: {decision.reason}"
        )

        print()
        print("-----------------------------------")
        print()


if __name__ == "__main__":
    main()