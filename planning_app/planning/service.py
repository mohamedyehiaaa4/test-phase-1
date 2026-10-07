"""Drive the planning graph: start it, answer it, approve, and read where it stands. No screen code here: the
Streamlit app calls these now, the web platform's routes will call the same functions later."""
import os

from langgraph.types import Command

from .steps import ORDER, STEPS


def _config():
    return {"configurable": {"thread_id": os.environ["PROJECT_ID"]}, "recursion_limit": 200}


async def _run(graph, value, on_step):
    """Run the graph until it waits for the PM again. on_step(text) is told each change an agent starts writing."""
    async for ns, (chunk, _) in graph.astream(value, _config(), stream_mode="messages", subgraphs=True):
        for call in getattr(chunk, "tool_call_chunks", None) or []:
            if call.get("name") and ns and on_step:  # a sub-agent starts a tool call (the first chunk carries its name)
                on_step(f"{STEPS[ns[0].split(':')[0]].title}: {call['name'].replace('_', ' ')}")


def start(graph, idea, on_step=None):
    return _run(graph, {"project_id": os.environ["PROJECT_ID"], "pm_id": os.environ["PM_USER_ID"], "idea": idea},
                on_step)


def answer(graph, text, on_step=None):
    return _run(graph, Command(resume=text), on_step)


def approve(graph, on_step=None):
    return _run(graph, Command(resume=True), on_step)


def retry(graph, on_step=None):
    """Run the last step again after an error; the saved progress is kept."""
    return _run(graph, None, on_step)


async def status(graph):
    """Where the plan stands, as plain data: the parts, the whole chat, and what the graph waits for."""
    snapshot = await graph.aget_state(_config())
    values = snapshot.values
    waiting = snapshot.interrupts[0].value if snapshot.interrupts else None
    approved = values.get("approved", {})

    chat = list(values.get("log", []))
    if waiting and waiting["type"] == "question":  # the running agent's messages that are not in the log yet
        seen = values.get("logged", {}).get(waiting["step"], 0)
        chat += [{"step": waiting["step"], **m} for m in waiting["chat"][seen:]]

    paused = ((values.get("change") or {}).get("back_to")  # the part that waits while an earlier one is changed
              or (values.get("resume") or {}).get("step"))
    parts = [{"step": name, "title": STEPS[name].title,
              "status": "working" if values.get("step") == name and waiting
              else f"approved v{approved[name]['version']}" if name in approved
              else "paused" if name == paused else "not started"}
             for name in ORDER]
    error = next((t.error for t in snapshot.tasks if t.error), None)
    return {"started": bool(values), "parts": parts, "chat": chat, "waiting": waiting,
            "changing": STEPS[values["change"]["origin"]].title if values.get("change") else None,
            "error": str(error) if error else None}
