"""The agent's chat: what the PM sees of it, and what the model is sent."""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def chat_of(messages):
    """What the PM sees: the agent's plain replies and the PM's own messages. Named messages (notes, review
    feedback, handed-over requests) and tool traffic are hidden: the main chat shows those once, elsewhere."""
    return [{"role": "assistant" if isinstance(m, AIMessage) else "user", "text": m.content}
            for m in messages
            if (isinstance(m, AIMessage) and not m.tool_calls and m.content)
            or (isinstance(m, HumanMessage) and not m.name)]


def without_old_tool_traffic(messages):
    """What the model is sent: every message between PM and agent, plus tool calls and results of the current turn
    only (since the last PM message or note). Older calls go out together with their results; the draft shown every
    turn already holds what they did. The saved chat itself stays complete."""
    turn = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=-1)
    out = []
    for i, m in enumerate(messages):
        if i > turn or isinstance(m, HumanMessage):
            out.append(m)
        elif isinstance(m, AIMessage) and m.content and not (m.tool_calls or m.invalid_tool_calls):
            out.append(m)
        elif isinstance(m, AIMessage) and m.content:
            out.append(AIMessage(m.content))  # keep its words, drop its old tool calls
    return out


def answer_broken(messages):
    """Every tool call needs an answer or the API rejects the whole chat. A call with broken arguments (for example
    cut off at the output limit) sits in invalid_tool_calls, which no tool runs, so answer it here."""
    out = []
    for m in messages:
        out.append(m)
        if isinstance(m, AIMessage):
            out += [ToolMessage("Not done: the arguments of this call were broken. Send it again.", tool_call_id=c["id"])
                    for c in m.invalid_tool_calls if c.get("id")]
    return out
