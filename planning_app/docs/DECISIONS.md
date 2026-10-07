# Next phase — what we decided (not built yet)

Decisions made with the user for the next phase of the project: adding the design phase after planning. No plan or
code yet; this file only records what was decided and why.

## 1. Each phase answers one question

```
Planning (WHAT)              Design (SHAPE + TOOLS)
discovery → requirements  →  architecture → technology
→ stories → criteria
```

- Stories and acceptance criteria stay in planning: they describe what users get and do not depend on technology.

## 2. Separate apps, linked only by the database

- Each phase is its **own app**: its own files, its own graph, its own chat and its own saved progress.
- The apps never call each other. Each reads only the approved work it needs from earlier phases (read-only, from
  the database) and saves its own approved work.
- Each phase is built its own way; they share no code beyond what the web platform gives every phase (login,
  settings, the database connection).
- In Streamlit: one page per app.

## 3. Order and changes between apps

- The design app opens only after **every** planning step is approved.
- Earlier work is changed **only in its own app**. If the PM asks the design chat to change planning work, the agent
  tells them to go back to the planning chat.
- Changes still flow down: each approval remembers which versions of earlier work it was built on. When an app opens
  and the database holds newer earlier work, its affected steps re-check themselves and the PM approves any update.

## 4. Design app

- **Architecture agent** starts the design chat. It does not open with a menu of options: it learns from the PM what
  it needs to know, proposes a suitable architecture with reasons, and discusses it until the PM agrees.
- **Technology agent** starts after the architecture is approved, in the same chat. It makes the technology choices
  itself from the requirements and the architecture (it does not ask about the team's skills); the PM can disagree
  before approving.
