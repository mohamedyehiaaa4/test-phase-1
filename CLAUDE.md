# Planning App — rules for Claude

Graduation project: six planning agents (discovery → requirements → stories → criteria → sprint → assignments)
under one routing main agent, built with LangGraph, DeepSeek, Supabase and Streamlit. Local only.

- New code lives in `planning_app/`. The plan is `planning_app/PLAN.md`: follow its phases in order.
- `planning_app/LATER.md` lists ideas already discussed with the user but not built yet. Read it before changing
  the checks, the review screen or the sprint logic.
- `planning_app/JIRA.md` holds the discussed (not approved) Jira integration design. Read it before any Jira work.
- `planning_app/CREATE_AGENT.md` holds the proposal to switch the sub-agents to LangChain's `create_agent`. Read it
  before changing how `agent.py` builds the agents.
- Out of scope for now: tests, tooling (lint/CI/pre-commit), hosting, login.
- Replies to the user: very simple, everyday words. End every change with a list of what changed.

## Code style (ponytail)

Simplest code that works. Stop at the first rung that holds:
1. Does it need to exist? If not, skip it and say so in one line.
2. Standard library does it? Use it.
3. Platform/DB feature covers it (a constraint, a foreign key, a LangGraph feature)? Use it.
4. An installed package solves it? Use it. No new dependency for a few lines of code.
5. Only then: the minimum code.

No interface with one implementation, no factory for one product, no config for a value that never changes,
no scaffolding "for later", fewest files. Never cut: input checks at trust boundaries, error handling that
prevents data loss, security. Mark a deliberate shortcut with `# ponytail: <limit>, <when to upgrade>`.
Agents make the decisions and write the content; code only stores data, checks that references are real, and runs
the graph.

## Which skill to use when

| Task | Skill |
|---|---|
| Anything touching Supabase: MCP server, applying SQL, supabase-py calls, RLS, keys, logs | `supabase` |
| Before writing or changing SQL: tables, columns, constraints, indexes, functions, RLS policies | `supabase-postgres-best-practices` (read the matching `references/*.md` rule) |
| A task needs know-how no listed skill covers (e.g. Streamlit patterns, LangGraph) | `find-skills` — search skills.sh first, review a skill before installing it |
| Checking the model provider or LLM-call questions (DeepSeek here, so usually skip) | `claude-api` only if Claude models are involved |

Supabase work goes through the `supabase` MCP server (project `ymvgcctuekolpvszrgav`). Never print or log keys from `.env`.
