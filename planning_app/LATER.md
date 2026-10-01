# Ideas for later (discussed, not built yet)

Ordered by importance: the first one matters most. Everything already built or decided is in `CHANGES.md`.

## 1. Stories miss the groundwork, so the plan cannot really be built — HIGH, not approved
- Found in the PM's run (advising agent for students): S1-S7 cover only what users see, and no story or task builds
  the agent itself (model, main instructions, web search tool). True for any project: the stories step writes exactly
  one story per functional requirement, so shared groundwork (an agent, a database, a payment connection, login,
  server setup) gets no story, the sprint never schedules it and nobody is assigned to it.
- Related: AI work is labeled "backend" (T3 "Work out the missing skills", T7 "Build the roadmap") even though the
  sprint rule lists AI/ML as a kind of work, so it can go to the wrong person.
- Proposal (groundwork stories, also called technical or enabler stories; prompts only, no code or database change):
  - `prompts/stories.md`: after the one-story-per-requirement list, add a story for each shared piece that two or
    more stories need and no story builds, written from the team's side ("S8: As the development team, we need the
    advising agent set up (model, main instructions, web search tool), so that S2 to S7 can work"). It links to the
    requirements it serves, gets points and a priority like any story, and the report names it so the PM can remove
    or change it. Only for groundwork the requirements clearly need; never new features (the "never invent" rule stays).
  - `prompts/sprint.md`: a groundwork story counts as a dependency of the stories it serves, so the existing
    dependencies-first rule puts it in the first sprint. Also: work done by an AI model is AI work, not backend.
  - Criteria and assignments need no change: groundwork stories use normal S keys and get criteria and owners.
- Fits point 3 (no NFR-only story): a groundwork story still links to functional requirements.

## 2. Slow turns look frozen — MEDIUM
Rewriting 45 criteria took several minutes; the app only shows "Working...", so a user may think it froze. Long turns
are the agent's bulk work in one go (dozens of save calls). Dropping old tool traffic (CHANGES.md) made later turns
smaller but not the first long one. Ideas: show progress (stream the agent's steps, e.g. "saved C12 of 45"), or a
clearer waiting message.

## 3. No story built only from non-functional requirements — MEDIUM-LOW, not approved
- It slipped through once (S15 built only on NFR4) before the stricter stories prompt; since that prompt ("exactly one
  story per functional requirement") no NFR-only story appeared in the test runs, but nothing in code guarantees it.
- A story is something a user does (from a functional requirement); a non-functional requirement is a constraint on
  how things work, so this is a rule about how data is linked, which fits code.
- Proposals: `check_stories` refuses submit when a story links to no functional requirement ("S15 links to no
  functional requirement"); and every non-functional requirement must be attached to at least one story ("NFR3 is
  attached to no story"). About 4 lines; facts about links, not text.
- Options: A both checks (recommended); B only the first; C prompt only.

## 4. A partly done story counts its full points — MEDIUM-LOW
A story carried over with only some of its tasks unfinished counts its full points again in the next sprint (S4 in the
first test; S4 and S10 in the full test). `sprint_numbers` now marks it "only partly in this sprint" but still counts
full points, so sprint totals look bigger than the remaining work.

## 5. Consistency checker — LOW, optional, on demand
A read-only agent that finds contradictions between parts (e.g. the idea says 7 days, the requirements 14) and reports
them; fixes go through the normal change flow. Costs extra calls, so run it when the PM asks or once before pushing to
Jira, not after every change. The change comparison (CHANGES.md, full test problem 2) already removes the main source of contradictions.

## 6. Start from existing work (skip steps) — future product feature
Today the forward order is fixed by code (idea -> requirements -> stories -> criteria -> sprint -> assignments): the
right default (each step needs the one before it, runs stay consistent, no step skipped by mistake). Moving back is
already flexible: the main agent routes change requests to any approved part.
- Idea: a PM who already has the work ("I already have a requirements document, import it") skips the earlier steps.
- How: the main agent (LLM, exists) recognises the request; the owning agent (already able) reads the pasted document
  and builds its items with its existing tools; the PM reviews and approves as usual. Two small code changes: the guard
  must allow a later part when the PM brings existing work for it (today: "not written yet"), and `load` must accept
  that an earlier step was skipped on purpose (today it always starts at the first unapproved step).
- Works partly today: pasting the document at the start makes discovery use it as the PM's input; steps go faster.
- Rejected alternatives: an LLM supervisor choosing the next step every time; running steps in parallel.

## 7. Real velocity and workload — later, with Jira
The sprint agent reads real velocity from past sprints to suggest a capacity; the assignments agent reads each
person's current load in Jira. Only useful once there is real sprint history (see JIRA.md).
