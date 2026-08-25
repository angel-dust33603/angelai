from ollama import chat


def search_memory(query: str) -> str:
    return f"TEST TOOL RECEIVED QUERY: {query}"


response = chat(
    model="angel-ai",
    messages=[
        {
            "role": "user",
            "content": "Search my memory for the word hello."
        }
    ],
    tools=[search_memory]
)

print()
print("=== FULL RESPONSE ===")
print(response)

print()
print("=== MESSAGE ===")
print(response.message)

print()
print("=== CONTENT ===")
print(response.message.content)

print()
print("=== TOOL CALLS ===")
print(response.message.tool_calls)