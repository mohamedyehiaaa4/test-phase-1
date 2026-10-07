# Ideas for later (discussed, not built yet)

Ordered by importance: the first one matters most. Everything already built or decided is in `CHANGES.md`.

## 1. Start from existing work (skip steps) — future product feature
Today the forward order is fixed by code (idea -> requirements -> stories -> criteria): the
right default (each step needs the one before it, runs stay consistent, no step skipped by mistake). Moving back is
already flexible: the main agent routes change requests to any approved part.
- Idea: a PM who already has the work ("I already have a requirements document, import it") skips the earlier steps.
- How: the main agent (LLM, exists) recognises the request; the owning agent (already able) reads the pasted document
  and builds its items with its existing tools; the PM reviews and approves as usual. Two small code changes: the guard
  must allow a later part when the PM brings existing work for it (today: "not written yet"), and `load` must accept
  that an earlier step was skipped on purpose (today it always starts at the first unapproved step).
- Works partly today: pasting the document at the start makes discovery use it as the PM's input; steps go faster.
- Rejected alternatives: an LLM supervisor choosing the next step every time; running steps in parallel.

## 2. Suggestions on request, and web search for feature ideas
Found in the PM's car-wash test: with the plan complete, "can you suggest me more FRs" got "I can't invent
requirements", and "search relevant websites for features" got "I can't search websites".
- **Suggestions (small fix, no new service).** Our rules already allow suggestions that are clearly marked and enter
  the plan only on the PM's yes; the router's "never invent anything" is read too strictly. A request for suggestions
  should go to the requirements agent as work: it proposes a short list of features with reasons, the PM picks, and the
  chosen ones go through the normal review ("What changed", Approve).
- **Web search (new feature).** Give the requirements agent one `search_web` tool. Flow: the PM asks to search → the
  router sends it to requirements → the agent searches comparable products, proposes suggested features each with its
  source link → the PM picks → normal review.
- **Service:** Tavily (free 1,000 searches a month, built for AI agents, standard LangChain choice); about ten lines with
  the already installed `httpx`, no new package; key `TAVILY_API_KEY` in `.env`. Alternatives: Exa (free credits,
  meaning-based search), Brave (paid only). DeepSeek's own web search is not available through the API we use.
- **Security (never cut):** web pages can carry hidden instructions (indirect prompt injection, OWASP LLM01). Only this
  one tool reads the web; its text is data, never instructions; the agent can only propose, nothing enters the plan
  without the PM's review and Approve; sources are always shown.

## 3. Findings from the user-style test run (home cleaning company)
A full run as an ordinary user (idea, requirements, stories, criteria, a change half-way, a final overview). The flow
itself worked well; these are the problems a user would notice, most important first.
- **A wrong requirement slipped in.** NFR2 said "never let the same slot be booked by more than one customer", but with
  6 cleaners up to 6 customers share a time. Caught only because the PM knew the business; a user trusts what is written.
- **Gaps and risks are not raised.** The agents ask about details but not about risks: the owner's admin page and the
  cleaners' phone view have no login anywhere in the plan (security); "a cleaning always takes 3 hours" clashes with
  "price per room"; "ask for the same cleaner" has no rule for when that cleaner is booked. Idea: before submitting,
  requirements checks its own work against the idea for contradictions, private screens without access control and
  clashing rules, and asks the PM about each (principles only, no examples in the prompt). Together with the first point.
- **"None stated" under empty headings** (idea: Notifications, Out of scope; PRD: Out of scope), against the heading
  rule; "Problems it solves" stretched from the PM's words again (parked problem 3, quote check). Idea: a small code
  check that refuses a heading with nothing real under it.
- **Jargon for a non-technical PM:** "non-functional requirements", FR/NFR, "baseline", "PRD", "points",
  "Given/When/Then", "edge case". Fine for project managers; for business owners it needs plain words or a short
  explanation. Depends on who the platform is for.
- **Long walls of text at every review.** A short summary first (counts and what matters), details folded, like the final
  overview, which was the best part of the run.
- **Small things:** after explaining points it asked "Shall I go ahead and build the stories?" although they were built;
  the check-in said "your change to the requirements" when stories changed too; "What changed" shows only the title of a
  new item ("added FR12: …"), not its text.
