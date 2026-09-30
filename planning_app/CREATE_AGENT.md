# Switching the sub-agents to LangChain's `create_agent` — PROPOSED, NOT APPROVED YET

Nothing here is built. This records the discussion about replacing our hand-written ReAct loop in `agent.py` with
LangChain's prebuilt `create_agent` (the successor of LangGraph's deprecated `create_react_agent`).

## Background
- All 6 sub-agents are already ReAct agents (reason -> call a tool -> observe -> repeat), built by hand as a small
  LangGraph subgraph in `agent.py` (nodes `model`, `tools`, `pm`).
- `create_react_agent` is deprecated in our LangGraph version (v1). The replacement is `create_agent` in the
  `langchain` package (not installed yet).
- `create_agent` now supports **middleware**: plug-ins that hook into each model call and tool call. With them, the
  reasons first given against switching are mostly easy to solve.

## The first objections, re-checked
| Objection | Real difficulty | How to solve it |
|---|---|---|
| Needs the `langchain` package | Easy | One `pip install`. |
| A plain reply ends the agent (ours means "ask the PM") | Easy | Let it end; the main graph pauses for the PM and runs the same agent again with the answer (its memory is saved). Or an `ask_pm` tool that calls `interrupt()`. |
| Tools run in parallel on one shared draft | Easy to medium | Turn off parallel tool calls when binding the model (confirm DeepSeek supports it), or have tools return small draft updates. |
| Different tools per mode (`no_impact` only in change/check) | Easy | A small custom middleware that hides `no_impact` in build mode: one agent per step, not three. |
| Our own fixes must be rebuilt | Medium | Draft each turn = dynamic prompt middleware; outcome tools = "return directly" tools; broken tool calls = tool error handling plus a small check. |
| Risk of breaking what was tested live | Manageable | Rerun the same live test script after switching. |

## Built-in middleware that solves open problems
- **Summarization** — summarizes old messages near a size limit -> solves LATER.md #7 (long chats).
- **Model call limit / Tool call limit** — stops an agent after too many calls -> solves LATER.md #8 (no smarter
  stop for repeated refused calls).
- **Model retry / Model fallback** — retry failed DeepSeek calls, or fall back to another model.
- **Tool error** — turns tool errors into messages (like our "Not done: ...").
- **Human-in-the-loop** — pauses for approval of tool calls.

## What stays exactly the same
- The main graph: router, guard, review, save, load, idle, the change flow.
- `steps.py` (items, done checks, links), the prompts, the database, the UI and the one chat.
- The rule: agents decide, code checks.

## What changes inside `agent.py`
| Part | Ours now | With `create_agent` |
|---|---|---|
| The loop | Written by us: `model`, `tools`, `pm` nodes and edges | Built by LangChain: `create_agent(model, tools, middleware=[...])` |
| Tools | Dict tool specs + one `run_tool` with `if name == ...` branches | One small `@tool` function per tool that reads the state and returns the draft update |
| Talking to the PM | Plain reply -> our `pm` node pauses and continues | Plain reply ends the turn; the main graph pauses and re-runs the agent with the answer |
| Draft shown every turn | Built into our `model` node | Dynamic prompt middleware |
| Tools per mode | Three tool lists bound to the model | Middleware hides `no_impact` in build mode |
| Ending with an outcome | Our `tools` node sets `outcome` | submit / not_my_job / no_impact end the run directly and write the outcome |
| Tools one at a time | Our loop runs them in order | Parallel tool calls turned off (confirm with DeepSeek) |
| Broken tool calls | Our `answer_broken` helper | LangChain tool error handling + a small check |
| Long chats | Nothing (grows forever) | Summarization middleware |
| Repeated refused calls | Stops only at the graph step limit | Model / tool call limit middleware |
| Failed model calls | Only the client's own retries | Model retry (+ optional fallback) middleware |

## What changes elsewhere (small)
- `graph.py`: the step node gets a small loop — if the agent ended with a question to the PM, pause, then run it
  again with the answer (replaces our `pm` node).
- `requirements.txt`: add `langchain`.

## Net effect
- Code size: about the same (our loop goes away; small tool functions and middleware settings come in).
- Behavior for the PM: the same chat, questions, reviews and changes.
- Gains: long chats summarized, runaway loops stopped cleanly, failed calls retried, a standard well-known agent to
  name in the presentation.
- Cost: about a day of work plus rerunning the live test.

## To confirm before switching
1. DeepSeek accepts turning off parallel tool calls.
2. `create_agent` works as a subgraph with its own saved memory (like our `checkpointer=True` subgraph today).
3. Broken tool calls (cut off at the output limit) are answered, so DeepSeek never rejects the chat.

Sources:
- https://docs.langchain.com/oss/python/langchain/middleware/built-in
- https://reference.langchain.com/python/langchain/agents/middleware/summarization/SummarizationMiddleware
- https://blog.langchain.com/how-middleware-lets-you-customize-your-agent-harness/
