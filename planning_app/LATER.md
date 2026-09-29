# Ideas for later (discussed, not built yet)

Review of the code checks: which ones code should do, and which ones belong to the agent or the PM.

## 1. Criteria check: coverage only — DECIDED (option 2), not built
- Today `check_criteria` (steps.py) forces every story to have a happy path AND a negative/edge case.
- That is a quality judgment, and it pushes the agent to invent weak scenarios to pass.
- Change: code only checks that every approved story has at least one criterion. The prompt says: a happy path,
  plus negative or edge cases where they make sense; never invent one just to have it.

```python
def check_criteria(d, approved):
    covered = {c["story_key"] for c in d.get("criteria", [])}
    missing = [s["key"] for s in approved["stories"]["stories"] if s["key"] not in covered]
    return [f"no criteria for {', '.join(missing)}"] if missing else []
```

## 2. Review shows the real draft, not a written report — PROPOSED (option 2), maybe later
- Today the agent writes a full report and code only checks that every key appears in it (`missing_from`).
  That does not prove the report is true, is easy to trick, and long reports caused the cut-off bug.
- Idea: code renders the draft itself for review (tables/lists, one small generic renderer for all item types);
  the agent writes only a short message on top. Remove the key search from submit.
- Trade-off: less natural prose; layout fixed by code instead of formats the PM asks for.
- Other options discussed: keep as is; a second LLM checks the report against the draft (extra cost per submit).

## 3. Sprint arithmetic in code — DECIDED, not built
The agent still decides what goes in the sprint (stories, tasks, goal); the PM approves. Code only makes sure the
agent has the right data and the right numbers.

- **A. The sprint agent always sees the stories with their points.** Today it sees only criteria in full (the step
  right before) and must remember to call `read_approved` for stories. Fix: each step declares which earlier steps it
  builds on (`builds_on` in steps.py), and `context_for` (graph.py) shows all of them in full: sprint = stories +
  criteria; assignments = sprint + stories; others unchanged.
- **B. Capacity as a number.** New `capacity_points` field on `Sprint` (number, or empty if the PM does not know);
  `notes` keeps anything else. schema.sql: `sprints.capacity` text -> `capacity_points` numeric, and update
  `save_step` / `load_step`.
- **C. Code computes the sprint numbers every turn** — a helper (not a tool: numbers must always be right and must
  not depend on the agent remembering to call something). Per sprint: stories in it (from its tasks), total points
  vs capacity, stories with no points, stories only partly in the sprint (counted with full points, marked
  "partly"), and a clear warning when over capacity (never blocks). Shown automatically under the draft each turn
  and in the review. ~10 lines in steps.py + one line in the agent's `model` node for the sprint step.
- **D. Sprint prompt.** Remove "do the arithmetic yourself". Add: "Use the computed sprint numbers shown to you;
  never add points yourself. If the sprint is over capacity or a story has no points, say so plainly."

## 4. No story built only from non-functional requirements — DISCUSSED, NOT APPROVED YET
- It slipped through once (S15 built only on NFR4); the prompt rule alone did not hold.
- A story is something a user does (from a functional requirement); a non-functional requirement is a constraint on
  how things work. So this is a rule about how data is linked, which fits code.
- Proposal: `check_stories` refuses submit when a story links to no functional requirement (~2 lines).
- Related proposal: every non-functional requirement must be attached to at least one story, so criteria can test
  it (~1 line). Global NFRs get attached to many stories.
- Options discussed: prompt only (already failed once); block at submit (proposed); warn only (weaker, no good
  exceptions to this rule).

## 5. Check messages state facts only, never advice — DISCUSSED, NOT APPROVED YET
- A check must say what failed, or the agent cannot fix it; a fixed message stating a fact about the data is fine.
- But a message must not tell the agent what to do (that is a decision for the agent; the prompt explains the rules).
- Example: "Not done: S15 links only to non-functional requirements (NFR4)." — not "...Attach NFR4 to the stories
  it constrains, or ask the PM to...".
- Apply to all check messages: review the current ones and cut any advice (e.g. "write the summary with
  save_summary", "fix and submit", "submit it for review instead").

## Other discussion: same inputs, same results (the doctor's question) — not planned
- Same inputs word for word: temperature 0 helps but is not a guarantee; a response cache (same request -> saved
  reply) guarantees identical runs.
- Same idea in different words: needs structured facts from discovery, fixed rules per agent, topic plans.
