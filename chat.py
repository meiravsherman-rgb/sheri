"""Interactive chat simulator — talk to Sheri as a test user."""

import sys
import io
import json
import httpx

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")

SERVER = "http://localhost:8090"
PHONE_NUMBER_ID = "1277616142095171"
WABA_ID = "2193110644820323"

_msg_counter = 0


def send_message(phone: str, name: str, text: str) -> None:
    global _msg_counter
    _msg_counter += 1
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": WABA_ID,
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": PHONE_NUMBER_ID},
                    "contacts": [{"profile": {"name": name}, "wa_id": phone}],
                    "messages": [{
                        "from": phone,
                        "id": f"chat_sim_{phone}_{_msg_counter}",
                        "timestamp": "1722470400",
                        "type": "text",
                        "text": {"body": text}
                    }]
                },
                "field": "messages"
            }]
        }]
    }
    try:
        resp = httpx.post(f"{SERVER}/webhook", json=payload, timeout=60)
        if resp.status_code != 200:
            print(f"  [ERROR] Server returned {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"  [ERROR] {e}")


def get_last_reply(phone: str) -> str:
    """Read the last assistant reply from the database."""
    import database
    rows = database.tail(phone, 2)
    for r in reversed(rows):
        if r["role"] == "assistant":
            return r["content"]
    return "(no reply)"


def main():
    import database
    database.init_db()

    print("=" * 50)
    print("  Chat Simulator - Sheri Bot")
    print("=" * 50)
    print()

    # Choose user
    name = input("Enter sender name (e.g. Tali): ").strip() or "Tali"
    phone = input("Enter phone (e.g. 972501234567): ").strip() or "972501234567"
    new_user = input("New user? (y/n, default y): ").strip().lower()

    if new_user != "n":
        # Clear history for this phone
        import sqlite3
        from config import DATABASE_PATH
        conn = sqlite3.connect(DATABASE_PATH)
        conn.execute("DELETE FROM conversations WHERE chat_id = ?", (phone,))
        conn.execute("DELETE FROM seen_messages WHERE message_id LIKE ?", (f"chat_sim_{phone}%",))
        conn.commit()
        conn.close()
        print(f"\n  History cleared for {phone}")

    print(f"\n  Chatting as: {name} ({phone})")
    print(f"  Type 'quit' to exit, 'switch' to change user")
    print("-" * 50)

    while True:
        try:
            msg = input(f"\n[{name}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not msg:
            continue
        if msg.lower() == "quit":
            break
        if msg.lower() == "switch":
            name = input("New name: ").strip() or "Tali"
            phone = input("New phone: ").strip() or "972509999999"
            new = input("New user? (y/n): ").strip().lower()
            if new != "n":
                import sqlite3
                from config import DATABASE_PATH
                conn = sqlite3.connect(DATABASE_PATH)
                conn.execute("DELETE FROM conversations WHERE chat_id = ?", (phone,))
                conn.commit()
                conn.close()
                print(f"  History cleared for {phone}")
            print(f"  Now chatting as: {name} ({phone})")
            continue

        # Send and wait for reply
        send_message(phone, name, msg)

        import time
        print("  (waiting for Sheri...)")
        time.sleep(8)  # Wait for Claude to respond

        reply = get_last_reply(phone)
        print(f"\n[Sheri]: {reply}")


if __name__ == "__main__":
    main()
