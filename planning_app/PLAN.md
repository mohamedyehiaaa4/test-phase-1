# Implementation plan

All phases below are built. Ideas for later are in `LATER.md`; the Jira design is in `JIRA.md`.

## Design in one picture

```
START → load ─► pick next step ─► [step sub-agent] ──submit──► review (PM) ──approve──► save ─► load
                    ▲                  │  ▲   │                   │ feedback ─► back to step
                    │                  │  │   └─ no_impact ─► save (check mode: same draft, re-linked)
                    │                  │  │                 └► load (change mode: nothing changed, nothing saved)
                    │       not my job │  └─ note (unclear / not allowed)
                    │                  ▼
                    │           main agent (LLM, routes only) ─► guard (code) ─► owning step in change mode
                    │                                                        after save: check each later
                    └── idle (all approved): PM message ─► main agent        approved step, then resume
```

- Each step is a LangGraph **subgraph** with its own saved memory (`checkpointer=True`): its chat and its draft.
  It is a ReAct-style loop: model → tools → model; a plain-text reply pauses for the PM.
- A draft is plain JSON in the same shape the database saves and loads, so there is no mapping code.
- The PM does everything in **one chat**: answers, review feedback, and change requests to earlier work. A change
  request is handed off by the current agent (`not_my_job`) to the main agent, which routes it; the guard checks it.
- Approved results live in Supabase: one row per approval in `step_versions`, and the items in real tables linked
  to that version with foreign keys. A change makes a new version; old versions stay as history. `load_project`
  returns every current step in one call.
- Later steps get the **short summary** of each approved step, the full approved input of the step right before
  them, and a tool to read any earlier step.
- The graph's progress (chats, where each step stands) is saved in Supabase Postgres (schema `langgraph`).

## Phases (done)

1. **Setup** — folder, `requirements.txt`, `.env.example`, install packages, Supabase MCP, skills, `CLAUDE.md`.
2. **Database** — `schema.sql`: the tables, `save_step` / `load_step` / `load_project` functions, a `langgraph`
   schema for checkpoints, access rules; seed the project and PM with the ids in `.env`.
3. **Steps** — `steps.py`: the item shapes (Pydantic) and the six step definitions (prompt, items, links,
   done check); `prompts/*.md`.
4. **Sub-agent** — `agent.py`: one builder that turns a step definition into a subgraph (model → tools loop,
   PM pause on plain text, save/remove item tools, submit, not_my_job, no_impact, read_approved).
5. **Main graph** — `graph.py`: state, load/review/save/router/guard/idle nodes, the change flow, the one-chat
   log, the Postgres checkpointer in Supabase.
6. **UI** — `app.py`: Streamlit, one chat for every agent, Approve inside the report, read-only status sidebar,
   "Try again" when a step fails.
7. **First run and live test** — run end to end with real DeepSeek and Supabase; bugs found were fixed (see
   `LATER.md` for open findings).
