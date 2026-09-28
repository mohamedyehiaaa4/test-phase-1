r"""The main planning graph: six sub-agents, a routing main agent, review, save, and the change flow.

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
import os
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import START, StateGraph
from langgraph.types import interrupt
from postgrest.exceptions import APIError
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field
from supabase import acreate_client

from agent import build_agent, chat_of
from steps import ORDER, PROMPTS, STEPS

# ---- state ------------------------------------------------------------------------------------------------------


class State(TypedDict, total=False):
    project_id: str
    pm_id: str
    idea: str
    step: str | None      # the sub-agent that runs next
    mode: str             # build | change | check
    note: HumanMessage | None  # message handed to that sub-agent on its next run
    outcome: dict | None  # how the sub-agent ended its run
    approved: dict        # step -> {version, summary, report, draft}: the current approved versions (from the DB)
    change: dict | None   # {origin, request, to_check: [steps], back_to: step | None}
    handoff: dict | None  # {from: step | None, quote, target: step | None}
    notice: str | None    # message for the PM while idle
    log: Annotated[list, operator.add]  # the one chat the PM sees: {step, role, text}
    logged: dict          # step -> how much of that agent's own chat is already in `log`


class Route(BaseModel):
    target: Literal[tuple(ORDER)] | None = Field(description="The part that owns the request; null if unclear")
    reason: str = Field(description="One short sentence")


def note(text):
    return HumanMessage(text, name="note")


def context_for(step, approved):
    before = [s for s in ORDER[:ORDER.index(step)] if s in approved]
    if not before:
        return ""
    lines = ["# Approved earlier work (short summaries; read_approved gives the full text)"]
    lines += [f"- {STEPS[s].title}: {approved[s]['summary']}" for s in before]
    last = before[-1]
    lines += [f"\n# Approved {STEPS[last].title} (full, the input you build on)", json.dumps(approved[last]["draft"], ensure_ascii=False)]
    return "\n".join(lines)


# ---- graph ------------------------------------------------------------------------------------------------------


def build(llm, db, checkpointer):
    agents = {name: build_agent(name, llm) for name in ORDER}
    router_llm = llm.with_structured_output(Route, method="function_calling")

    async def load(s):
        rows = (await db.table("current_steps").select("step, version, summary, report")
                .eq("project_id", s["project_id"]).execute()).data
        approved = {}
        for r in rows:
            draft = (await db.rpc("load_step", {"p_project": s["project_id"], "p_step": r["step"]}).execute()).data
            approved[r["step"]] = {**r, "draft": draft}
        base = {"approved": approved, "outcome": None, "handoff": None}
        change = s.get("change")
        if change and change["to_check"]:
            nxt, *rest = change["to_check"]
            return {**base, "change": {**change, "to_check": rest}, "step": nxt, "mode": "check",
                    "note": note(f'Earlier work was changed at the PM\'s request: "{change["request"]}".')}
        if change and change["back_to"]:
            return {**base, "change": None, "step": change["back_to"], "mode": "build",
                    "note": note("Earlier work you build on was changed at the PM's request and your input above is "
                                 "updated. Keep your draft, adjust only what the change affects, then continue.")}
        nxt = next((x for x in ORDER if x not in approved), None)
        first = HumanMessage(s["idea"]) if nxt == "discovery" else note("Begin your part now.")
        return {**base, "change": None, "step": nxt, "mode": "build", "note": first if nxt else None}

    def step_node(name):
        async def run(s):
            own = s["approved"].get(name)
            inp = {"mode": s["mode"], "outcome": None, "context": context_for(name, s["approved"]),
                   "approved": {k: v["draft"] for k, v in s["approved"].items()}}
            if s["mode"] != "build" and own:
                inp["draft"] = own["draft"]  # changes start from exactly what is approved
            if s.get("note"):
                inp["messages"] = [s["note"]]
            out = await agents[name].ainvoke(inp)
            o, chat = out["outcome"], chat_of(out["messages"])
            seen = (s.get("logged") or {}).get(name, 0)
            update = {"note": None, "outcome": {**o, "draft": out.get("draft") or {}},
                      "log": [{"step": name, **m} for m in chat[seen:]],
                      "logged": {**(s.get("logged") or {}), name: len(chat)}}
            if o["kind"] == "handoff":
                update["handoff"] = {"from": name, "quote": o["quote"], "target": None}
            return update
        return run

    def review(s):
        o, step = s["outcome"], s["step"]
        answer = interrupt({"type": "review", "step": step, "text": o["report"]})
        said = [{"step": step, "role": "assistant", "text": o["report"]},
                {"step": step, "role": "user", "text": "Approved." if answer is True else answer}]
        if answer is True:
            return {"outcome": {**o, "approved": True}, "log": said}
        return {"outcome": None, "note": HumanMessage(answer, name="review"), "log": said}

    async def save(s):
        o, step = s["outcome"], s["step"]
        text = s["approved"][step] if o["kind"] == "no_impact" else o  # no change: keep the approved report
        try:
            await db.rpc("save_step", {"p_project": s["project_id"], "p_step": step, "p_by": s["pm_id"],
                                       "p_summary": text["summary"], "p_report": text["report"],
                                       "p_draft": o["draft"]}).execute()
        except APIError as e:  # the draft stays in the agent's memory; it fixes it and submits again
            return {"outcome": None, "note": note(f"Saving failed: {e.message}. Fix your draft and submit again.")}
        if s["mode"] != "change":
            return {"outcome": None}
        change = s["change"]
        later = [x for x in ORDER[ORDER.index(step) + 1:] if x in s["approved"]]
        return {"outcome": None, "change": {**change, "to_check": later}}

    async def router(s):
        h = s["handoff"]
        parts = "\n".join(f"- {name}: {STEPS[name].owns}" for name in ORDER)
        done = "\n".join(f"- {name}: {v['summary']}" for name, v in s["approved"].items()) or "(nothing yet)"
        r = await router_llm.ainvoke([
            SystemMessage((PROMPTS / "router.md").read_text(encoding="utf-8") + f"\n\n# Parts\n{parts}\n\n"
                          f"# Approved so far\n{done}"),
            HumanMessage(f"Handed over by: {h['from'] or 'nobody (every part is approved)'}\n"
                         f"PM's words: {h['quote']}")])
        return {"handoff": {**h, "target": r.target}}

    def guard(s):
        h, approved, change = s["handoff"], s["approved"], s.get("change")
        src, target, quote = h["from"], h.get("target"), h["quote"]
        back_to = src if src and src not in approved else None
        if change and s.get("mode") == "change" and src == change["origin"]:  # the change was misrouted: send it on
            change, back_to = None, change["back_to"]

        def refuse(for_agent, for_pm):
            if src:
                return {"handoff": None, "step": src, "note": note(f'The PM wrote: "{quote}". {for_agent}')}
            return {"handoff": None, "step": None, "notice": for_pm}

        if target is None:
            return refuse("It is not clear which part of the plan this is about: ask the PM one short question.",
                          "I could not tell which part of the plan that is about. Which part should change?")
        if target == src:
            return refuse("This is for your part after all: handle it.", "")
        if target not in approved:
            return refuse(f"That belongs to {STEPS[target].title}, which is not written yet, so it cannot be changed "
                          "now. Tell the PM plainly.", f"{STEPS[target].title} is not written yet.")
        if change:
            return refuse("Another change is still being applied. Tell the PM to ask again when it is done.",
                          "Another change is still being applied. Ask again when it is done.")
        return {"handoff": None, "step": target, "mode": "change", "note": HumanMessage(quote, name="handoff"),
                "change": {"origin": target, "request": quote, "to_check": [], "back_to": back_to}}

    def idle(s):
        text = s.get("notice") or ("Every part of the plan is approved. Tell me what should change, or what "
                                   "happened (for example: sprint 1 is finished).")
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
        g.add_conditional_edges(name, lambda s: {"submit": "review", "no_impact": "save", "handoff": "router"}[
            s["outcome"]["kind"]], ["review", "save", "router"])
    g.add_conditional_edges("review", lambda s: "save" if s.get("outcome") else s["step"], ["save", *ORDER])
    g.add_conditional_edges("save", lambda s: s["step"] if s.get("note") else "load", ["load", *ORDER])
    g.add_edge("router", "guard")
    g.add_conditional_edges("guard", to_step, [*ORDER, "idle"])
    g.add_edge("idle", "router")
    return g.compile(checkpointer=checkpointer)


async def open_graph():
    """Connect to DeepSeek and Supabase and build the graph. Its progress is saved in Supabase (schema langgraph)."""
    llm = ChatDeepSeek(model=os.environ.get("PLANNING_MODEL", "deepseek-chat"), api_key=os.environ["DEEPSEEK_API_KEY"],
                       temperature=0.3, max_tokens=8192, timeout=180, max_retries=3)
    db = await acreate_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

    async def use_langgraph_schema(conn):
        await conn.execute("set search_path to langgraph")

    pool = AsyncConnectionPool(os.environ["SUPABASE_DB_URL"], open=False, configure=use_langgraph_schema,
                               kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row})
    await pool.open()
    saver = AsyncPostgresSaver(pool)
    await saver.setup()
    return build(llm, db, saver)
