r"""The main planning graph: four sub-agents, a routing main agent, review, save, and the change flow.

    START -> load --(next step)--> <step> --submit----> review --approve--> save --> load
               \                    |  \--no_impact-----------------------/  \--save failed--> <step>
                \--(all approved)-> idle     \--handoff--> router (LLM) --> guard --> <step> in change mode
                                     \--PM message--------/                      \--> refused: back to the sender

Moves are conditional edges. The main agent (router) only decides which step owns a request; the guard (code)
only checks that the move is allowed. After a change is approved, every later approved step checks itself, then
the paused step continues. Everything the PM sees is one chat: `log` collects it across all agents.
"""
import json
import operator
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import START, StateGraph
from langgraph.types import interrupt
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field

from .agent import build_agent
from .messages import chat_of
from .steps import ORDER, PROMPTS, STEPS, what_changed

# ---- state ------------------------------------------------------------------------------------------------------


class State(TypedDict, total=False):
    project_id: str
    pm_id: str
    idea: str
    step: str | None      # the sub-agent that runs next
    mode: str             # build | change | check
    fresh: bool           # a change or check starts now: the agent's draft restarts from the approved version
    note: HumanMessage | None  # message handed to that sub-agent on its next run
    outcome: dict | None  # how the sub-agent ended its run
    reviewing: dict | None  # submitted work the PM answered with a message: shown again if that was only a question
    seen: dict            # step -> the draft the PM last reviewed without approving it (to show what changed since)
    approved: dict        # step -> {version, summary, draft}: the current approved versions (from the DB)
    change: dict | None   # {origin, request, to_check: [steps], back_to: step | None}
    handoff: dict | None  # {from: step | None, quote, target: step | None}
    notice: str | None    # message for the PM while idle
    resume: dict | None   # {step, note}: after a change, the paused part that continues once the PM says so
    log: Annotated[list, operator.add]  # the one chat the PM sees: {step, role, text}
    logged: dict          # step -> how much of that agent's own chat is already in `log`


class Route(BaseModel):
    kind: Literal["change", "question", "unclear", "continue"] = Field(
        description="change: something must be different; question: the PM only asks; unclear: you cannot tell; "
                    "continue: after a finished change, the PM has nothing more to change or ask")
    target: Literal[tuple(ORDER)] | None = Field(default=None, description="For a change: the part that owns it")
    answer: str = Field(default="", description="For a question: the reply to the PM, short and plain. When unclear: "
                        "one short question that uses the recent conversation to name what they most likely mean")
    reason: str = Field(description="One short sentence")


def note(text):
    return HumanMessage(text, name="note")


def changed_so_far(change):
    """The PM's request plus what really changed in each part so far (computed by code when each part was saved)."""
    lines = [f'Earlier work was changed at the PM\'s request: "{change["request"]}".']
    if change.get("diffs"):
        lines.append("What changed so far:")
        lines += [f"- {STEPS[d['step']].title}: " + "; ".join(d["lines"]) for d in change["diffs"]]
    return "\n".join(lines)


# ---- graph ------------------------------------------------------------------------------------------------------


def build(llm, db, checkpointer):
    agents = {name: build_agent(name, llm) for name in ORDER}
    router_llm = llm.with_structured_output(Route, method="function_calling")

    async def load(s):
        approved = (await db.rpc("load_project", {"p_project": s["project_id"]}).execute()).data or {}
        base = {"approved": approved, "outcome": None, "handoff": None}
        change = s.get("change")
        if change and change["to_check"]:
            nxt, *rest = change["to_check"]
            return {**base, "change": {**change, "to_check": rest}, "step": nxt, "mode": "check", "fresh": True,
                    "note": note(changed_so_far(change))}
        if change and change["back_to"]:  # the change is done: check in with the PM before the paused part goes on
            back = change["back_to"]
            return {**base, "change": None, "step": None,
                    "resume": {"step": back, "note": changed_so_far(change) + "\nYour input above is updated. Keep your "
                               "draft and adjust only what the change affects. Open your next message to the PM with one "
                               "short line on what the change means for your work, then continue (if your work was "
                               "complete, submit it again)."},
                    "notice": f"Done: your change to the {STEPS[change['origin']].title.lower()} is approved. Anything "
                              f"else you'd like to change or ask before we go back to the {STEPS[back].title.lower()}?"}
        nxt = next((x for x in ORDER if x not in approved), None)
        first = HumanMessage(s["idea"]) if nxt == "discovery" else note(
            "Begin your part now with your first message to the PM. The approved work above is your input.")
        return {**base, "change": None, "step": nxt, "mode": "build", "note": first if nxt else None}

    def step_node(name):
        async def run(s):
            own = s["approved"].get(name)
            inp = {"mode": s["mode"], "outcome": None,
                   "approved": {k: v["draft"] for k, v in s["approved"].items()},
                   "summaries": {k: v["summary"] for k, v in s["approved"].items()}}
            if s.get("fresh") and own:
                inp["draft"] = own["draft"]  # only when a change or check starts; later rounds keep the agent's edits
            if s.get("note"):
                inp["messages"] = [s["note"]]
            out = await agents[name].ainvoke(inp)
            o, chat = out["outcome"], chat_of(out["messages"])
            seen = (s.get("logged") or {}).get(name, 0)
            update = {"note": None, "fresh": False, "outcome": {**o, "draft": out.get("draft") or {}},
                      "log": [{"step": name, **m} for m in chat[seen:]],
                      "logged": {**(s.get("logged") or {}), name: len(chat)}}
            if o["kind"] == "handoff":
                update["handoff"] = {"from": name, "quote": o["quote"], "target": None}
            r = s.get("reviewing")
            if not (o["kind"] == "handoff" and r and r["draft"] == update["outcome"]["draft"]):
                update["reviewing"] = None  # the agent worked on its draft: that review is out of date
            return update
        return run

    def review(s):
        o, step, seen = s["outcome"], s["step"], s.get("seen") or {}
        # Compared with what the PM saw last: their last unapproved review of this step, else the approved version
        # when this is a change. None on a first review: the full report is shown as it is.
        before = seen[step] if step in seen else s["approved"][step]["draft"] if s["mode"] != "build" else None
        changes = None if before is None else what_changed(step, before, o["draft"], values=True)
        answer = interrupt({"type": "review", "step": step, "text": o["report"], "changes": changes})
        said = [{"step": step, "role": "assistant", "text": o["report"], "changes": changes},
                {"step": step, "role": "user", "text": "Approved." if answer is True else answer}]
        if answer is True:
            return {"outcome": {**o, "approved": True}, "reviewing": None, "log": said,
                    "seen": {k: v for k, v in seen.items() if k != step}}
        return {"outcome": None, "reviewing": o, "note": HumanMessage(answer, name="review"), "log": said,
                "seen": {**seen, step: o["draft"]}}

    async def save(s):
        o, step = s["outcome"], s["step"]
        summary = (s["approved"][step] if o["kind"] == "no_impact" else o)["summary"]  # no change: keep the summary
        try:
            await db.rpc("save_step", {"p_project": s["project_id"], "p_step": step, "p_by": s["pm_id"],
                                       "p_summary": summary, "p_draft": o["draft"]}).execute()
        except APIError as e:  # the draft stays in the agent's memory; it fixes it and submits again
            return {"outcome": None, "note": note(f"Saving failed: {e.message}. Fix your draft and submit again.")}
        if s["mode"] == "build":
            return {"outcome": None}
        change = s["change"]  # change or check mode: record what really changed, for the parts after this one
        if diff := what_changed(step, (s["approved"].get(step) or {}).get("draft"), o["draft"]):
            change = {**change, "diffs": [*change.get("diffs", []), {"step": step, "lines": diff}]}
        if s["mode"] == "check":
            return {"outcome": None, "change": change}
        later = [x for x in ORDER[ORDER.index(step) + 1:] if x in s["approved"]]
        return {"outcome": None, "change": {**change, "to_check": later}}

    async def router(s):
        h = s["handoff"]
        parts = "\n".join(f"- {name}: {STEPS[name].owns}" for name in ORDER)
        done = "\n\n".join(f"## {name}\n{json.dumps(s['approved'][name]['draft'], ensure_ascii=False)}"
                           for name in ORDER if name in s["approved"]) or "(nothing yet)"
        resume = s.get("resume")
        waiting = (f"nobody: a change was just finished and the {STEPS[resume['step']].title.lower()} waits to "
                   "continue (kind continue if the PM has nothing more to change or ask)" if resume
                   else "nobody (every part is approved)")
        recent = "\n".join(f"{'PM' if m['role'] == 'user' else 'You'}: {m['text'][:600]}"
                           for m in (s.get("log") or [])[-6:]) or "(none)"
        r = await router_llm.ainvoke([
            SystemMessage((PROMPTS / "router.md").read_text(encoding="utf-8") + f"\n\n# Parts\n{parts}\n\n"
                          f"# Approved content of each part, in order\n{done}\n\n# Recent conversation\n{recent}"),
            HumanMessage(f"Handed over by: {h['from'] or waiting}\nPM's request: {h['quote']}")])
        return {"handoff": {**h, "kind": r.kind, "target": r.target, "answer": r.answer}}

    def guard(s):
        h, approved, change, resume = s["handoff"], s["approved"], s.get("change"), s.get("resume")
        src, target, quote = h["from"], h.get("target"), h["quote"]
        again = (f"\n\nAnything else you'd like to change or ask before we go back to the "
                 f"{STEPS[resume['step']].title.lower()}?" if resume and not src else "")
        if resume and not src and (h.get("kind") == "continue" or target == resume["step"]):  # go on with the paused part
            wish = f'\nThe PM also said: "{quote}". Take it into account.' if h.get("kind") != "continue" else ""
            return {"handoff": None, "resume": None, "step": resume["step"], "mode": "build",
                    "note": note(resume["note"] + wish)}
        if h.get("kind") == "continue":  # nothing paused: nothing to continue
            return {"handoff": None, "step": None, "notice": None}
        if h.get("kind") == "question" and h.get("answer"):  # answered: nothing is changed, reviewed or saved
            if src:
                back = {"handoff": None, "step": src, "log": [{"step": src, "role": "assistant", "text": h["answer"]}]}
                if s.get("reviewing"):  # asked during a review and nothing changed: show the same review again
                    return {**back, "outcome": s["reviewing"], "reviewing": None}
                return {**back, "note": note(f'The PM asked: "{quote}". It was already answered for them: '
                                             f'"{h["answer"]}". Do not comment on it, thank them or repeat it: '
                                             "continue your part where you left off, as if the conversation had not "
                                             "paused.")}
            return {"handoff": None, "step": None, "notice": h["answer"] + again}
        back_to = src if src and src not in approved else (resume["step"] if resume and not src else None)
        if change and s.get("mode") == "change" and src == change["origin"]:  # the change was misrouted: send it on
            change, back_to = None, change["back_to"]

        def refuse(for_agent, for_pm="", ask_again=True):
            if src:
                return {"handoff": None, "step": src, "note": note(f'The PM wrote: "{quote}". {for_agent}')}
            return {"handoff": None, "step": None, "notice": for_pm + (again if ask_again else "")}

        if target is None or h.get("kind") != "change":
            return refuse("It is not clear which part of the plan this is about: ask the PM one short question.",
                          h.get("answer") or "I'm not sure what you'd like to change. Could you say it in other words?",
                          ask_again=False)
        if target == src:
            return refuse("This is for your part after all: handle it.")  # target == src implies src is an agent
        if target not in approved:
            return refuse(f"That is about the {STEPS[target].title.lower()}, which you and the PM have not reached yet, so "
                          "it cannot be changed now. Tell them so plainly, about their project.",
                          f"We haven't written the {STEPS[target].title.lower()} yet, so there is nothing there to change.")
        if change:
            return refuse("Another change is still being applied. Tell the PM to ask again when it is done.",
                          "I'm still working on your previous change. Please ask again once it's done.")
        return {"handoff": None, "reviewing": None, "resume": None, "step": target, "mode": "change", "fresh": True,
                "note": HumanMessage(quote, name="handoff"),
                "change": {"origin": target, "request": quote, "to_check": [], "back_to": back_to}}

    def idle(s):
        text = s.get("notice") or ("Your plan is complete: the project idea, requirements, user stories and acceptance "
                                   "criteria are all agreed. Tell me anything you'd like to change.")
        answer = interrupt({"type": "idle", "text": text})
        return {"notice": None, "handoff": {"from": None, "quote": answer, "target": None},
                "log": [{"step": None, "role": "assistant", "text": text}, {"step": None, "role": "user", "text": answer}]}

    g = StateGraph(State)
    for name, fn in [("load", load), ("review", review), ("save", save), ("router", router), ("guard", guard),
                     ("idle", idle), *((name, step_node(name)) for name in ORDER)]:
        g.add_node(name, fn)
    to_step = lambda s: s["step"] or "idle"  # noqa: E731
    g.add_edge(START, "load")
    g.add_conditional_edges("load", to_step, [*ORDER, "idle"])
    for name in ORDER:
        g.add_conditional_edges(name, lambda s: {  # no_impact in change mode: nothing changed, nothing to save
            "submit": "review", "no_impact": "save" if s["mode"] == "check" else "load", "handoff": "router"}[
            s["outcome"]["kind"]], ["review", "save", "load", "router"])
    g.add_conditional_edges("review", lambda s: "save" if s.get("outcome") else s["step"], ["save", *ORDER])
    g.add_conditional_edges("save", lambda s: s["step"] if s.get("note") else "load", ["load", *ORDER])
    g.add_edge("router", "guard")
    back_to_review = lambda s: "review" if (s.get("outcome") or {}).get("kind") == "submit" else to_step(s)  # noqa: E731
    g.add_conditional_edges("guard", back_to_review, ["review", *ORDER, "idle"])
    g.add_edge("idle", "router")
    return g.compile(checkpointer=checkpointer)
