r"""One builder that turns a step into a sub-agent: a small LangGraph subgraph with its own saved memory.

    START -> model --tool calls--> tools --(ended its turn)--> END
               ^  \--plain text--> pm (wait for the PM) --> model
               \-------------------------------------------/

The agent talks to the PM with plain text and changes its draft only through tools. It ends its run with one
outcome for the main graph: submit (draft ready for review), handoff (the PM asked for something that is not its
job), or no_impact (a change to earlier work does not affect it).
"""
import copy
import json
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt
from pydantic import BaseModel, Field, ValidationError

from .messages import answer_broken, chat_of, without_old_tool_traffic
from .steps import STEPS, bad_refs, earlier, keys_in


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]  # this agent's own conversation
    draft: dict                                # this agent's own draft (reset to the approved one for a change)
    mode: str                                  # build | change | check
    approved: dict                             # approved drafts by step (input from the main graph)
    summaries: dict                            # short summary of each approved step (input from the main graph)
    outcome: dict | None
    submitted: dict | None                     # the last work sent for review: {report, summary, draft}


class Submit(BaseModel):
    """Send your complete draft to the PM for review."""
    report: str = Field(min_length=1, description="The full review text for the PM")
    summary: str = Field(min_length=1, description="A short summary (a few sentences) of your own work only, for "
                         "later work to build on. Never repeat facts, numbers or names that belong to earlier parts")


class NotMyJob(BaseModel):
    """The PM asked for something that belongs to another part of the plan. This ends your turn."""
    quote: str = Field(min_length=1, description="The PM's request, complete enough to understand on its own: their "
                       "words plus what earlier messages made clear")


class NoImpact(BaseModel):
    """Only while checking a change to earlier work: your approved work is not affected. Changes nothing."""
    reason: str = Field(min_length=8, description="Why the change does not affect your work")


class Answered(BaseModel):
    """Only after the PM answered your review with a message: it was only a question, you answered it, and your work
    is unchanged. The same work goes back to them for approval. This ends your turn."""


class ReadApproved(BaseModel):
    """Read the full approved work of an earlier part of the plan (read-only)."""
    step: str


class Remove(BaseModel):
    key: str


MODE_NOTES = {
    "build": "",
    "change": "# Now\nYour work was approved before. The PM now asks for a change (their last message). Make only the "
              "edits it needs, keep everything else as it is, then submit so the PM can approve the new version. If "
              "the request is not about your part, use not_my_job. If the PM only asked a question, or in the end "
              "wants nothing changed, answer them and then call no_impact.",
    "check": "# Now\nEarlier work you build on was changed (see the last note). Compare your approved draft with the "
             "updated approved work above. If something is affected, fix only that and submit. If nothing is "
             "affected, call no_impact and change nothing.",
}


def tool(name, model, description=None):
    return {"type": "function", "function": {
        "name": name, "description": description or model.__doc__, "parameters": model.model_json_schema()}}


def context_for(step, approved, summaries):
    """Earlier approved work: short summaries of all of it, and the steps this one builds on in full."""
    before = [s for s in earlier(step) if s in approved]
    if not before:
        return ""
    lines = ["# Approved earlier work (short summaries; read_approved gives the full text)"]
    lines += [f"- {STEPS[s].title}: {summaries.get(s, '')}" for s in before]
    for s in STEPS[step].builds_on:
        if s in approved:
            lines += [f"\n# Approved {STEPS[s].title} (full, the input you build on)",
                      json.dumps(approved[s], ensure_ascii=False)]
    return "\n".join(lines)


def build_agent(name, llm):
    step = STEPS[name]
    saves = {f"save_{m.__name__.lower()}": m for m in step.items}
    removes = {f"remove_{m.__name__.lower()}": m for m in step.items if not m.single}
    tools = [tool(n, m) for n, m in saves.items()]
    tools += [tool(n, Remove, f"Remove a {m.__name__.lower()} by its key.") for n, m in removes.items()]
    tools += [tool("submit", Submit), tool("not_my_job", NotMyJob), tool("answered", Answered)]
    if earlier(name):
        tools.append(tool("read_approved", ReadApproved))
    with_tools = {"build": llm.bind_tools(tools), "change": llm.bind_tools(tools + [tool("no_impact", NoImpact)]),
                  "check": llm.bind_tools(tools + [tool("no_impact", NoImpact)])}
    others = "\n".join(f"- {s.title}: {s.owns}" for s in STEPS.values() if s.name != name)

    def known_keys(state, draft):
        known = {}
        for d in [*(v for k, v in state["approved"].items() if k != name), draft]:
            for slot, keys in keys_in(d).items():
                known.setdefault(slot, set()).update(keys)
        return known

    def dangling(state, draft):
        known, bad = known_keys(state, draft), []
        for m in step.items:
            value = draft.get(m.slot)
            for x in ([value] if m.single else value) if value else []:
                bad += bad_refs(m.model_validate(x), known)
        return sorted(set(bad))

    def run_tool(call, draft, state):
        """Apply one tool call to the draft. Returns (text for the agent, outcome or None)."""
        n, args = call["name"], call["args"]
        if n in saves:
            m = saves[n]
            item = m.model_validate(args)
            if m.single:
                draft[m.slot] = item.model_dump()
                return "Saved.", None
            key, new = getattr(item, m.key_field), item.model_dump()
            before = draft.get(m.slot, [])
            rows = [new if x[m.key_field] == key else x for x in before]
            if not any(x[m.key_field] == key for x in before):
                rows.append(new)
            if bad := bad_refs(item, known_keys(state, {**draft, m.slot: rows})):
                raise ValueError(f"these keys do not exist: {', '.join(bad)}")
            draft[m.slot] = rows
            return f"Saved {key}.", None
        if n in removes:
            m, key = removes[n], Remove.model_validate(args).key
            if not any(x[m.key_field] == key for x in draft.get(m.slot, [])):
                raise ValueError(f"there is no {key}")
            draft[m.slot] = [x for x in draft[m.slot] if x[m.key_field] != key]
            return f"Removed {key}.", None
        if n == "read_approved":
            wanted = ReadApproved.model_validate(args).step.strip().lower()
            if wanted not in earlier(name) or wanted not in state["approved"]:
                raise ValueError(f"step must be one of the approved earlier parts: "
                                 f"{[s for s in earlier(name) if s in state['approved']]}")
            return json.dumps(state["approved"][wanted], ensure_ascii=False), None
        if n == "submit":
            a = Submit.model_validate(args)
            problems = step.check(draft, state["approved"])
            if bad := dangling(state, draft):
                problems.append(f"these keys no longer exist: {', '.join(bad)}")
            if problems:
                raise ValueError("; ".join(problems))
            return "Sent for review.", {"kind": "submit", "report": a.report, "summary": a.summary}
        if n == "not_my_job":
            return "Handed over.", {"kind": "handoff", "quote": NotMyJob.model_validate(args).quote}
        if n == "answered":
            last = next((m for m in reversed(state["messages"]) if isinstance(m, HumanMessage) and m.name != "note"), None)
            sent = state.get("submitted")
            if not (last is not None and last.name == "review" and sent and draft == sent["draft"]):
                raise ValueError("only right after the PM answered your review, when your work is unchanged")
            return "The same work goes back to the PM.", {k: sent[k] for k in ("kind", "report", "summary")}
        if n == "no_impact" and state["mode"] in ("change", "check"):
            NoImpact.model_validate(args)
            if draft != state["approved"].get(name):
                raise ValueError("you already edited your draft, so it is affected: submit it for review instead")
            if bad := dangling(state, draft):
                raise ValueError(f"your work points at keys that no longer exist: {', '.join(bad)}; fix and submit")
            if problems := step.check(draft, state["approved"]):  # the new input can make a complete draft incomplete
                raise ValueError("your work is affected: " + "; ".join(problems))
            return "Recorded: nothing to change.", {"kind": "no_impact"}
        raise ValueError(f"unknown tool {n}")

    async def model(state):
        system = "\n\n".join(filter(None, [
            step.prompt, f"# Other parts of the plan (not yours)\n{others}",
            context_for(name, state["approved"], state.get("summaries") or {}),
            MODE_NOTES[state["mode"]],
            "# Your current draft\n" + json.dumps(state.get("draft") or {}, ensure_ascii=False, indent=1)]))
        sent = answer_broken(without_old_tool_traffic(state["messages"]))
        reply = await with_tools[state["mode"]].ainvoke([SystemMessage(system), *sent])
        return {"messages": [reply]}

    def tools_node(state):
        draft, replies, outcome = copy.deepcopy(state.get("draft") or {}), [], None
        for call in state["messages"][-1].tool_calls:
            if outcome:
                text = "Skipped: your turn already ended."
            else:
                try:
                    text, outcome = run_tool(call, draft, state)
                except (ValidationError, ValueError) as e:
                    text = f"Not done: {e}"
            replies.append(ToolMessage(text, tool_call_id=call["id"]))
        update = {"draft": draft, "messages": replies, "outcome": outcome}
        if outcome and outcome["kind"] == "submit":
            update["submitted"] = {**outcome, "draft": copy.deepcopy(draft)}
        return update

    def pm(state):
        text = state["messages"][-1].content
        if not text.strip():
            return {"messages": [HumanMessage("Reply to the PM in plain text or call a tool.", name="note")]}
        # A plain reply to review feedback or to a change request never leaves the PM without the Approve button, and
        # never hides an unhandled request. Review feedback with the work unchanged: the agent must name what it did
        # with an action (answered, or not_my_job), because its words alone may claim a hand-over it never made.
        # Whenever the work changed (since that review, or since the approved version): the agent must send it now.
        last = next((m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), None)
        sent = state.get("submitted")
        if last is not None and last.name in ("review", "handoff"):
            if last.name == "review" and sent and state.get("draft") == sent["draft"]:  # decided by an action, not words
                return {"messages": [HumanMessage(
                    "The PM's last message is still open. If it asks for anything outside your own work, call "
                    "not_my_job now: saying it is passed on does not pass it on. If it was only a question and you "
                    "answered it, call answered.", name="note")]}
            base = sent["draft"] if last.name == "review" and sent else state["approved"].get(name)
            if state.get("draft") != base:
                return {"messages": [HumanMessage("Your work changed: send it for review now with submit. Do not ask "
                                                  "the PM first.", name="note")]}
        # Finished work reaches the PM only as a review: the agent saved work this turn that is now complete and not yet
        # sent, then wrote it into the chat instead of submitting. Read from the state, never from the reply's words.
        since = max((i for i, m in enumerate(state["messages"]) if isinstance(m, HumanMessage)), default=-1)
        saved_now = any(c["name"].startswith(("save_", "remove_"))
                        for m in state["messages"][since + 1:] for c in getattr(m, "tool_calls", None) or [])
        draft = state.get("draft") or {}
        if saved_now and draft != (sent["draft"] if sent else state["approved"].get(name)) \
                and not step.check(draft, state["approved"]) and not dangling(state, draft):
            return {"messages": [HumanMessage("Your work is complete: send it for review now with submit instead of "
                                              "writing it into the chat.", name="note")]}
        answer = interrupt({"type": "question", "step": name, "chat": chat_of(state["messages"])})
        return {"messages": [HumanMessage(answer)]}

    g = StateGraph(AgentState)
    g.add_node("model", model)
    g.add_node("tools", tools_node)
    g.add_node("pm", pm)
    g.add_edge(START, "model")
    g.add_conditional_edges("model", lambda s: "tools" if s["messages"][-1].tool_calls
                            or s["messages"][-1].invalid_tool_calls else "pm", ["tools", "pm"])
    g.add_conditional_edges("tools", lambda s: END if s.get("outcome") else "model", ["model", END])
    g.add_conditional_edges("pm", lambda s: END if s.get("outcome") else "model", ["model", END])
    return g.compile(checkpointer=True)  # the agent keeps its conversation and draft between runs
