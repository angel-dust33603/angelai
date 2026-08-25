import re
import sys
from pathlib import Path

import ollama


# =============================================================
# PATHS
# =============================================================

ANGELAI_DIRECTORY = Path(__file__).resolve().parent
MEMORY_DIRECTORY = ANGELAI_DIRECTORY / "memory"

if str(ANGELAI_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(ANGELAI_DIRECTORY))

if str(MEMORY_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(MEMORY_DIRECTORY))


from memory.memory_bridge import MemoryBridge
from filesystem.file_bridge import FileBridge


# =============================================================
# CONFIGURATION
# =============================================================

MODEL_NAME = "angel-ai"

MAX_HISTORY_MESSAGES = 20
MAX_TOOL_ROUNDS = 8


# =============================================================
# MEMORY DETECTION
# =============================================================

MEMORY_QUERY_PATTERNS = [
    r"\bwhat do you remember\b",
    r"\bwhat do you know about me\b",
    r"\bwhat do you know about angel\b",
    r"\bdo you remember\b",
    r"\bremember about\b",
    r"\bmemory\b",
    r"\bmemories\b",
    r"\blist memories\b",
    r"\blist your memories\b",
]


def looks_like_memory_query(text: str) -> bool:

    text_lower = text.lower().strip()

    return any(
        re.search(
            pattern,
            text_lower
        )
        for pattern in MEMORY_QUERY_PATTERNS
    )


# =============================================================
# MEMORY DISPLAY
# =============================================================

def build_memory_context(
    bridge: MemoryBridge,
    query: str
) -> str:

    memories = bridge.search(
        query=query,
        limit=10
    )

    if not memories:
        return "No relevant memories were found."

    return bridge.format_memories(
        memories
    )


# =============================================================
# SYSTEM PROMPT
# =============================================================

SYSTEM_PROMPT = """
You are Angel's local AI assistant.

You are running locally through Ollama on Angel's computer.

PERSONALITY AND COMMUNICATION

- Be casual, conversational, and natural.
- Swearing is acceptable when it fits the conversation.
- Do not be unnecessarily formal or robotic.
- Match Angel's casual style without forcing it.
- Use humour when appropriate.
- Explain technical concepts clearly without talking down to Angel.
- If Angel is confused, slow down and explain the situation plainly.
- Do not overwhelm Angel with unnecessary information or steps.
- When troubleshooting, work through one step at a time when practical.

STYLE

- Angel may use emoticons such as :3 and UwU.
- Treat :3 as punctuation when appropriate.
- Do not unnecessarily add a period after :3.
- You may naturally understand and occasionally use casual emoticons when they fit.

CODING PREFERENCES

- Angel prefers complete replacement files when making code changes rather than isolated snippets.
- Before changing another existing file, tell Angel that the additional file needs to be changed.
- Do not make unrelated changes to working code.
- Explain what caused a bug when fixing one.
- Preserve existing functionality unless Angel specifically asks for it to be changed.
- When providing code changes, clearly identify which file is being changed.

LOCAL OPERATION

- You are a locally running AI model through Ollama.
- You can generate responses without an internet connection.
- Do not claim that internet access is required for normal conversation or coding.
- You do not have unrestricted access to Angel's computer.
- Never claim to have read, modified, deleted, executed, or inspected something unless the application actually provided the relevant information.
- Never pretend that an external action was performed when it was not.

MEMORY

- Persistent memories are supplied to you by the application when relevant.
- Treat supplied memory information as factual context about Angel.
- Do not claim to remember something that was not supplied in the conversation or memory context.
- If no relevant memory was supplied, say that you do not have a relevant memory.
- Angel may sometimes refer to himself in third person.
- Do not interpret third-person references to "Angel" as necessarily referring to another person.

FILESYSTEM SECURITY

- Filesystem access is controlled by the application.
- You have filesystem tools available when Angel has explicitly granted filesystem access.
- The application keeps the actual filesystem access token private.
- Never ask Angel for a filesystem token.
- Never invent or fabricate a filesystem token.
- Never claim a filesystem operation succeeded unless the tool reports success.
- Never claim to have access to a path merely because Angel mentioned it.
- Use filesystem tools when they are appropriate for the user's request.
- Protected system directories and AngelAI's own files cannot be accessed.
- Filesystem permissions expire automatically.
- Never attempt to bypass filesystem security.
- If a filesystem operation is denied, explain the denial instead of attempting another route around it.
"""


# =============================================================
# OLLAMA TOOLS
# =============================================================

FILESYSTEM_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read a UTF-8 text file using the currently "
                "granted filesystem access."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "The file path to read."
                        ),
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": (
                "List the contents of a directory using the "
                "currently granted filesystem access."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "The directory path to list."
                        ),
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_directory",
            "description": (
                "Create a directory using the currently "
                "granted filesystem access."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "The directory path to create."
                        ),
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Create or overwrite a UTF-8 text file using "
                "the currently granted filesystem access."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "The file path to write."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "The complete text content to write."
                        ),
                    },
                },
                "required": [
                    "path",
                    "content",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": (
                "Delete a file using the currently granted "
                "filesystem access."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "The file path to delete."
                        ),
                    },
                },
                "required": ["path"],
            },
        },
    },
]


# =============================================================
# ANGEL AI
# =============================================================

class AngelAI:

    def __init__(self):

        self.bridge = MemoryBridge()
        self.files = FileBridge()

        # The token is deliberately kept outside the model.
        self.active_filesystem_token = None

        self.messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.strip(),
            }
        ]

    # =========================================================
    # HISTORY
    # =========================================================

    def add_message(
        self,
        role: str,
        content: str,
    ):

        self.messages.append(
            {
                "role": role,
                "content": content,
            }
        )

        self.trim_history()

    def trim_history(self):

        system_message = self.messages[0]

        conversation = self.messages[1:]

        if len(conversation) > MAX_HISTORY_MESSAGES:

            conversation = conversation[
                -MAX_HISTORY_MESSAGES:
            ]

        self.messages = [
            system_message,
            *conversation,
        ]

    # =========================================================
    # MEMORY REQUESTS
    # =========================================================

    def handle_memory_request(
        self,
        text: str,
    ):

        request = self.bridge.detect_memory_request(
            text
        )

        if not request:
            return None

        if request["action"] == "remember":

            result = self.bridge.remember(
                request["text"],
                explicit=True,
            )

            if result["saved"]:

                return (
                    f"Memory saved as "
                    f"#{result['id']}."
                )

            return (
                "I couldn't save that memory: "
                f"{result['reason']}"
            )

        if request["action"] == "update":

            result = self.bridge.update(
                request["id"],
                request["text"],
            )

            if result["updated"]:

                return (
                    f"Memory #{result['id']} updated.\n"
                    f"Old: {result['old_memory']}\n"
                    f"New: {result['new_memory']}"
                )

            return result["reason"]

        if request["action"] == "forget_id":

            result = self.bridge.forget(
                request["id"]
            )

            if result["deleted"]:

                return (
                    f"Memory #{result['id']} deleted."
                )

            return result["reason"]

        if request["action"] == "forget_text":

            matches = self.bridge.search(
                request["text"],
                limit=10,
            )

            if not matches:

                return (
                    "I couldn't find a matching memory."
                )

            lines = [
                "I found these matching memories:"
            ]

            for memory in matches:

                lines.append(
                    f"#{memory['id']} "
                    f"[{memory['category']}] "
                    f"{memory['memory']} "
                    f"(importance "
                    f"{memory['importance']})"
                )

            lines.append(
                "Use 'forget memory <ID>' "
                "to delete one."
            )

            return "\n".join(lines)

        return None

    # =========================================================
    # MEMORY SEARCH
    # =========================================================

    def handle_memory_query(
        self,
        text: str,
    ):

        if not looks_like_memory_query(text):
            return None

        return build_memory_context(
            self.bridge,
            text,
        )

    # =========================================================
    # FILESYSTEM COMMANDS
    # =========================================================

    def handle_filesystem_command(
        self,
        text: str,
    ):

        stripped = text.strip()

        # -----------------------------------------------------
        # GRANT
        # -----------------------------------------------------

        match = re.match(
            r'^/fs\s+grant\s+"([^"]+)"\s+(.+)$',
            stripped,
            re.IGNORECASE,
        )

        if match:

            path = match.group(1)

            permissions = {
                permission.strip().lower()
                for permission in match.group(2).split(",")
                if permission.strip()
            }

            try:

                result = self.files.grant_access(
                    path,
                    permissions,
                )

            except (
                PermissionError,
                ValueError,
            ) as error:

                return (
                    f"Filesystem access denied: "
                    f"{error}"
                )

            self.active_filesystem_token = (
                result["token"]
            )

            return (
                "Filesystem access granted.\n"
                f"Path: {result['path']}\n"
                f"Permissions: "
                f"{', '.join(result['permissions'])}\n"
                f"Expires: {result['expires_at']}"
            )

        # -----------------------------------------------------
        # REVOKE
        # -----------------------------------------------------

        if re.match(
            r'^/fs\s+revoke$',
            stripped,
            re.IGNORECASE,
        ):

            if not self.active_filesystem_token:

                return (
                    "There is no active filesystem "
                    "access token."
                )

            revoked = self.files.revoke_token(
                self.active_filesystem_token
            )

            self.active_filesystem_token = None

            if revoked["revoked"]:

                return (
                    "Filesystem access token revoked."
                )

            return (
                "The filesystem access token "
                "was already invalid or expired."
            )

        # -----------------------------------------------------
        # STATUS
        # -----------------------------------------------------

        if re.match(
            r'^/fs\s+status$',
            stripped,
            re.IGNORECASE,
        ):

            grants = self.files.show_permissions()

            if not grants:

                return (
                    "No active filesystem access grants."
                )

            lines = [
                "Active filesystem access:"
            ]

            for grant in grants:

                lines.append(
                    f"- {grant['path']} "
                    f"[{', '.join(grant['permissions'])}] "
                    f"expires {grant['expires_at']}"
                )

            return "\n".join(lines)

        return None

    # =========================================================
    # TOOL EXECUTION
    # =========================================================

    def execute_tool(
        self,
        tool_name: str,
        arguments: dict,
    ):

        if not self.active_filesystem_token:

            return {
                "success": False,
                "reason": (
                    "No filesystem access has been "
                    "explicitly granted."
                ),
            }

        token = self.active_filesystem_token

        # -----------------------------------------------------
        # READ FILE
        # -----------------------------------------------------

        if tool_name == "read_file":

            return self.files.read_file(
                token,
                arguments["path"],
            )

        # -----------------------------------------------------
        # LIST DIRECTORY
        # -----------------------------------------------------

        if tool_name == "list_directory":

            return self.files.list_directory(
                token,
                arguments["path"],
            )

        # -----------------------------------------------------
        # CREATE DIRECTORY
        # -----------------------------------------------------

        if tool_name == "create_directory":

            return self.files.create_directory(
                token,
                arguments["path"],
            )

        # -----------------------------------------------------
        # WRITE FILE
        # -----------------------------------------------------

        if tool_name == "write_file":

            return self.files.write_file(
                token,
                arguments["path"],
                arguments["content"],
            )

        # -----------------------------------------------------
        # DELETE FILE
        # -----------------------------------------------------

        if tool_name == "delete_file":

            return self.files.delete_file(
                token,
                arguments["path"],
            )

        return {
            "success": False,
            "reason": (
                f"Unknown filesystem tool: "
                f"{tool_name}"
            ),
        }

    # =========================================================
    # OLLAMA
    # =========================================================

    def ask_model(
        self,
        user_text: str,
        memory_context: str | None = None,
    ):

        messages = list(
            self.messages
        )

        if memory_context is not None:

            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Relevant persistent memory "
                        "retrieved for this message:\n\n"
                        f"{memory_context}\n\n"
                        "Use this information when "
                        "answering the user's message."
                    ),
                }
            )

        # -----------------------------------------------------
        # Tell the model about the currently available scope.
        #
        # The actual token is NEVER included.
        # -----------------------------------------------------

        if self.active_filesystem_token:

            grants = self.files.show_permissions()

            if grants:

                filesystem_context = (
                    "Filesystem access is currently "
                    "available through your filesystem tools.\n\n"
                    "The application will independently "
                    "enforce the granted permissions.\n\n"
                    "Current granted access:\n"
                )

                for grant in grants:

                    filesystem_context += (
                        f"- {grant['path']} "
                        f"[{', '.join(grant['permissions'])}] "
                        f"expires {grant['expires_at']}\n"
                    )

                messages.append(
                    {
                        "role": "system",
                        "content": filesystem_context,
                    }
                )

        messages.append(
            {
                "role": "user",
                "content": user_text,
            }
        )

        # -----------------------------------------------------
        # TOOL-CALLING LOOP
        # -----------------------------------------------------

        for _ in range(MAX_TOOL_ROUNDS):

            response = ollama.chat(
                model=MODEL_NAME,
                messages=messages,
                tools=FILESYSTEM_TOOLS,
            )

            message = response["message"]

            tool_calls = message.get(
                "tool_calls"
            )

            # -------------------------------------------------
            # Normal model response
            # -------------------------------------------------

            if not tool_calls:

                return message.get(
                    "content",
                    "",
                )

            # -------------------------------------------------
            # Add assistant tool-call message
            # -------------------------------------------------

            messages.append(
                message
            )

            # -------------------------------------------------
            # Execute requested tools
            # -------------------------------------------------

            for tool_call in tool_calls:

                function = tool_call["function"]

                tool_name = function["name"]

                arguments = function.get(
                    "arguments",
                    {},
                )

                if not isinstance(
                    arguments,
                    dict,
                ):

                    arguments = {}

                result = self.execute_tool(
                    tool_name,
                    arguments,
                )

                messages.append(
                    {
                        "role": "tool",
                        "content": str(result),
                    }
                )

        return (
            "I reached the maximum number of filesystem "
            "operations allowed for this request."
        )

    # =========================================================
    # MAIN MESSAGE HANDLER
    # =========================================================

    def respond(
        self,
        text: str,
    ):

        # -----------------------------------------------------
        # Direct filesystem commands
        # -----------------------------------------------------

        filesystem_result = (
            self.handle_filesystem_command(
                text
            )
        )

        if filesystem_result is not None:

            self.add_message(
                "user",
                text,
            )

            self.add_message(
                "assistant",
                filesystem_result,
            )

            return filesystem_result

        # -----------------------------------------------------
        # Memory requests
        # -----------------------------------------------------

        memory_result = (
            self.handle_memory_request(
                text
            )
        )

        if memory_result is not None:

            self.add_message(
                "user",
                text,
            )

            self.add_message(
                "assistant",
                memory_result,
            )

            return memory_result

        # -----------------------------------------------------
        # Memory query
        # -----------------------------------------------------

        memory_context = (
            self.handle_memory_query(
                text
            )
        )

        # -----------------------------------------------------
        # Ask model
        # -----------------------------------------------------

        response = self.ask_model(
            text,
            memory_context,
        )

        self.add_message(
            "user",
            text,
        )

        self.add_message(
            "assistant",
            response,
        )

        return response

    # =========================================================
    # CLOSE
    # =========================================================

    def close(self):

        if self.active_filesystem_token:

            self.files.revoke_token(
                self.active_filesystem_token
            )

            self.active_filesystem_token = None

        self.bridge.close()


# =============================================================
# MAIN
# =============================================================

def main():

    ai = AngelAI()

    print()
    print("===================================")
    print("             AngelAI")
    print("===================================")
    print()
    print(f"Model: {MODEL_NAME}")
    print("Persistent memory: enabled")
    print("Memory handling: application")
    print("Filesystem access: protected")
    print("Filesystem tokens: 30 minutes")
    print("Filesystem tools: enabled")
    print()
    print("Type /exit to quit.")
    print()
    print(
        "Filesystem grant example:"
    )
    print(
        '/fs grant "C:\\Users\\colep\\Desktop\\Test" '
        'create,write,read'
    )
    print()

    try:

        while True:

            try:

                text = input(
                    "You: "
                ).strip()

            except EOFError:

                break

            if not text:

                continue

            if text.lower() in {
                "/exit",
                "/quit",
                "exit",
                "quit",
            }:

                break

            try:

                response = ai.respond(
                    text
                )

                print()
                print(
                    f"AngelAI: {response}"
                )
                print()

            except KeyboardInterrupt:

                print()
                print(
                    "Interrupted."
                )
                print()

            except Exception as error:

                print()
                print(
                    "AngelAI error:"
                )
                print(
                    f"{type(error).__name__}: "
                    f"{error}"
                )
                print()

    except KeyboardInterrupt:

        print()
        print(
            "\nStopping AngelAI..."
        )

    finally:

        ai.close()


if __name__ == "__main__":
    main()
