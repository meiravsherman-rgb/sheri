"""LLM agent — handles a single incoming message and returns a reply."""

import anthropic

from config import ANTHROPIC_API_KEY, LLM_MODEL, MAX_HISTORY
from database import append, tail
from prompt import build_system_prompt
from tools import TOOL_REGISTRY

# Tools whose chat_id must be overridden from the webhook context
FRAMEWORK_INJECTED_CHAT_ID = {
    "schedule_reminder",
    "list_reminders",
    "cancel_reminder",
    "request_human_handoff",
}

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

MAX_TOOL_ITERATIONS = 5


def _build_tools_list() -> list[dict]:
    """Convert TOOL_REGISTRY to Anthropic tool format."""
    return [
        {
            "name": name,
            "description": td["schema"].get("description", ""),
            "input_schema": td["schema"]["input_schema"],
        }
        for name, td in TOOL_REGISTRY.items()
    ]


def _run_tool(tool_use, chat_id: str) -> str:
    """Execute a tool call, injecting framework-controlled parameters."""
    name = tool_use.name
    if name not in TOOL_REGISTRY:
        return f"Unknown tool: {name}"

    tool_input = dict(tool_use.input or {})

    # Framework owns chat_id for these tools
    if name in FRAMEWORK_INJECTED_CHAT_ID:
        tool_input["chat_id"] = chat_id

    try:
        result = TOOL_REGISTRY[name]["fn"](**tool_input)
        return str(result)
    except Exception as e:
        return f"Tool error ({name}): {e}"


def handle_message(chat_id: str, sender_name: str, message_text: str) -> str:
    """Process an incoming message and return the bot's reply.

    Args:
        chat_id: Sender phone number (e.g. '972501234567')
        sender_name: Display name of the sender
        message_text: The message text
    Returns:
        The bot's reply text
    """
    # Load conversation history
    history = tail(chat_id, MAX_HISTORY)

    # Add current message
    append(chat_id, "user", message_text)

    # Build messages for Claude
    system_prompt = build_system_prompt(TOOL_REGISTRY)
    messages = history + [{"role": "user", "content": message_text}]

    # Prepare tools
    tools = _build_tools_list()

    # Tool-calling loop
    for _ in range(MAX_TOOL_ITERATIONS):
        kwargs = {
            "model": LLM_MODEL,
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = _client.messages.create(**kwargs)

        # Check if the response contains tool use
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_use_blocks:
            # No tool calls — extract text reply
            text_blocks = [b.text for b in response.content if b.type == "text"]
            reply = "\n".join(text_blocks) if text_blocks else "🌸"
            append(chat_id, "assistant", reply)
            return reply

        # Process tool calls
        # Add assistant message with all content blocks
        messages.append({"role": "assistant", "content": response.content})

        # Execute each tool and collect results
        tool_results = []
        for tool_block in tool_use_blocks:
            result = _run_tool(tool_block, chat_id)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_block.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    # If we hit the iteration cap, force a text reply
    reply = "אני מטפלת בבקשה שלך. אם את צריכה עזרה נוספת, אשמח לעזור 🌸"
    append(chat_id, "assistant", reply)
    return reply
