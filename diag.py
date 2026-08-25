import time
import sys
from pathlib import Path

print("[1] Starting", flush=True)

ANGELAI_DIRECTORY = Path(__file__).resolve().parent
MEMORY_DIRECTORY = ANGELAI_DIRECTORY / "memory"

sys.path.insert(0, str(ANGELAI_DIRECTORY))
sys.path.insert(0, str(MEMORY_DIRECTORY))

print("[2] Paths configured", flush=True)

print("[3] Importing ollama...", flush=True)
import ollama
print("[4] ollama imported", flush=True)

print("[5] Importing MemoryBridge...", flush=True)
from memory.memory_bridge import MemoryBridge
print("[6] MemoryBridge imported", flush=True)

print("[7] Creating MemoryBridge...", flush=True)
bridge = MemoryBridge()
print("[8] MemoryBridge created", flush=True)

print("[9] Testing memory database...", flush=True)
print(bridge.memory.get_all(), flush=True)
print("[10] Memory database works", flush=True)

print("[11] Testing Ollama connection...", flush=True)

start = time.perf_counter()

response = ollama.chat(
    model="angel-ai",
    messages=[
        {
            "role": "user",
            "content": "Reply with exactly: hello"
        }
    ]
)

elapsed = time.perf_counter() - start

print(
    f"[12] Ollama responded after {elapsed:.2f} seconds",
    flush=True
)

print("[13] Response:", flush=True)
print(response["message"]["content"], flush=True)

bridge.close()

print("[14] Finished", flush=True)