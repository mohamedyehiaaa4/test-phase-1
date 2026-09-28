# Implementation plan

## Design in one picture

```
START → load ─► pick next step ─► [step sub-agent] ──submit──► review (PM) ──approve──► save ─► next
                    ▲                  │  ▲   │                   │ feedback ─► back to step
                    │                  │  │   └─ no_impact ─► save (same draft, re-linked)
                    │       not my job │  └─ note (unclear / not allowed)
                    │                  ▼
                    │           main agent (LLM, routes only) ─► guard (code) ─► owning step in change mode
                    │                                                        after save: check each later
                    └── idle (all approved): PM message ─► main agent        approved step, then resume
```

- Each step is a LangGraph **subgraph** with its own saved memory (`checkpointer=True`): its chat and its draft.
- A draft is plain JSON in the same shape the database saves and loads, so there is no mapping code.
- Every PM reply (answer, review, idle message) may carry a "change earlier work" request from the UI; it skips
  the main agent and goes straight to the guard.
- Approved results live in Supabase: one row per approval in `step_versions`, and the items in real tables linked
  to that version with foreign keys. A change makes a new version; old versions stay as history.
- Later steps get the **short summary** of each approved step, the full approved input of the step right before
  them, and a tool to read any earlier step.

## Phases

1. **Setup** — folder, `requirements.txt`, `.env.example`, install packages, Supabase MCP, skills, `CLAUDE.md`.
2. **Database** — `schema.sql`: drop the old objects, create the new tables, `save_step` / `load_step`
   functions, a `langgraph` schema for checkpoints; apply it through the MCP server; seed the project and PM
   with the ids already in `.env`.
3. **Steps** — `steps.py`: the item shapes (Pydantic) and the six step definitions (prompt, items, links,
   done check); `prompts/*.md`.
4. **Sub-agent** — `agent.py`: one builder that turns a step definition into a subgraph (model → tools loop,
   ask_pm pause, save/remove item tools, submit, not_my_job, no_impact, read_approved).
5. **Main graph** — `graph.py`: state, load/pick/review/save/idle nodes, the main agent (structured routing
   answer), the guard, the change flow, the Postgres checkpointer in Supabase.
6. **UI** — `app.py`: Streamlit chat, step status panel, "change earlier work" form, approve/feedback.
7. **First run** — run the app end to end with a real project idea and fix what breaks.
