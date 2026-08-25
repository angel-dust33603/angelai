from ollama import chat


response = chat(
    model="angel-ai",
    messages=[
        {
            "role": "user",
            "content": "Say hello in one short sentence."
        }
    ]
)

print()
print(response.message.content)