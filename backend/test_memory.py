"""Quick test for SupabaseMemoryClient"""
import os
from dotenv import load_dotenv

# Load env vars
load_dotenv()

print(f"SUPABASE_URL: {os.getenv('SUPABASE_URL', 'NOT SET')[:50]}...")
print(f"SUPABASE_ANON_KEY present: {bool(os.getenv('SUPABASE_ANON_KEY'))}")

# Test the memory client
from app.memory.chat_memory import get_memory_client, get_chat_memory

client = get_memory_client()
print(f"\nMemoryClient is_available: {client.is_available}")

if client.is_available:
    # Try to insert a test message
    result = client.insert("chat_messages", {
        "thread_id": "test-thread-123",
        "user_id": "test-user",
        "role": "user",
        "content": "Test message from script",
        "metadata": {"test": True}
    })
    print(f"Insert result: {result}")

    # Try to select
    rows = client.select("chat_messages", {"thread_id": "eq.test-thread-123"}, limit=5)
    print(f"Select result: {len(rows)} rows")
    for row in rows:
        print(f"  - {row.get('content')}")
else:
    print("MemoryClient is NOT available - check env vars")
