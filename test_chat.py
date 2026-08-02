"""Direct chat test — bypasses the server, talks to the agent directly."""

import sys
import io
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Must set up before importing agent
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from database import init_db
init_db()

# Import tools to populate registry
import tools.human_handoff  # noqa: F401
import tools.reminders  # noqa: F401
from tools.reminders import start_scheduler
start_scheduler()

from agent import handle_message


def test_conversation(phone: str, name: str, messages: list[str]):
    """Run a test conversation and print results."""
    print(f"\n{'='*60}")
    print(f"  Conversation with: {name} ({phone})")
    print(f"{'='*60}")

    for msg in messages:
        print(f"\n[{name}]: {msg}")
        print("  (thinking...)")
        reply = handle_message(phone, name, msg)
        print(f"\n[Sheri]: {reply}")
        print(f"\n{'-'*60}")


if __name__ == "__main__":
    import sqlite3
    from config import DATABASE_PATH

    # Clear test data
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("DELETE FROM conversations WHERE chat_id LIKE '972999%'")
    conn.commit()
    conn.close()

    # Test 1: New user says hi
    test_conversation("972999000001", "Tali", ["hi"])

    # Test 2: Someone asking about courses
    test_conversation("972999000002", "Noa", ["I heard about your method, what courses do you have?"])

    # Test 3: Pain empathy
    test_conversation("972999000003", "Maya", ["I have terrible period pain every month"])

    print("\n\nAll tests completed!")
