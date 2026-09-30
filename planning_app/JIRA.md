# Jira integration — DISCUSSED, NOT APPROVED YET

Nothing here is built. This records everything we discussed about connecting the app to the PM's Jira: pushing the
approved plan, reading progress back, and planning the next sprint from that progress.

- **Part 1** — the options from the first discussion.
- **Part 2** — the new options from the latest discussion (ReAct agents, closing a sprint from Jira progress, and
  what happens when Jira and our plan disagree).
- **Part 3** — how Part 2 changes Part 1, and the combined picture.

Status labels: **USER DECIDED** = the user chose it; **PROPOSED** = recommended, not approved yet.

---

# Part 1 — Options from the first discussion

## 1.1 Decisions from the user (USER DECIDED)
- **Jira Cloud** (`<site>.atlassian.net`).
- **What to push:** the active sprint (with its tasks and assignees) and the backlog stories (not in the sprint,
  just saved in the PM's Jira for later).
- **Two-way wanted:** mainly to learn what was finished in sprint N and what was not, so unfinished work goes into
  the next sprint.
- **Must be a visible feature** of the site, not something the PM has to guess to type.
- The PM may not know whether the project is company-managed or team-managed; the code must handle both.

## 1.2 Mapping: our data -> Jira (PROPOSED)
| Ours | Jira |
|---|---|
| Epic (E1...) | Epic |
| Story (S1...) | Story, parent = its epic |
| Story points | Story points field (name differs per project type; look up the field id on the site) |
| Priority high/medium/low | Priority High/Medium/Low |
| Acceptance criteria | Given/When/Then list in the story description |
| Task (T1...) | Sub-task of its story ("Sub-task" or "Subtask": read allowed issue types first) |
| `depends_on` | Issue link "blocks" |
| Active sprint | Sprint on the project's Scrum board; its stories and sub-tasks moved into it |
| Backlog stories | Stories in the Jira backlog, no sprint, no tasks |
| Assignment main owner | Assignee (Jira account id) |
| Requirements / PRD | Optional: link or text on the epic |

Company-managed vs team-managed: the code detects the project type and adapts (story points field name, sub-task
type name). Epics and sprints work the same in both on Jira Cloud; team-managed needs the sprint feature on.

## 1.3 Pushing the plan: who does it (PROPOSED)
| Option | Verdict |
|---|---|
| **A. Code node `publish`** — fixed mapping, safe to run twice, exact report | **Recommended** |
| B. An agent pushing issue by issue with Atlassian's MCP tools | Not recommended |
| C. CSV export the PM imports by hand | Simplest, demo only (no sprints/updates/links) |

Why not B: pushing has no decisions in it; the same plan must give the same result every time; pushing twice must
update, not duplicate (an agent must remember the mapping itself, one slip duplicates issues in the PM's Jira);
50+ issues = 50+ tool calls (slow, costly, a half-done push may be reported as done); Jira text read back into an
agent with write tools can carry prompt injection.

How A works: the main agent (or the card) triggers `publish`; the guard checks sprint and assignments are approved;
code creates or updates epics, stories, sub-tasks, links and the sprint. A Supabase table remembers our key -> Jira
key (e.g. S1 -> PROJ-12), so pushing again updates instead of duplicating. The result is written in the chat.

## 1.4 Team accounts (PROPOSED)
| Option | Verdict |
|---|---|
| **A. Read the team from the Jira project** (assignable users: name + account id) | **Recommended** |
| B. Ask the PM each person's Jira email in the chat | Slow; Jira often hides emails, so matching can fail |

How A works: the assignments agent gets the Jira team list automatically (not a tool) and only asks the PM each
person's role. The assignee is just the chosen account id: no matching step. A team change in Jira shows up in the
next sprint.

## 1.5 Reading progress back (PROPOSED — extended in Part 2)
- Full two-way sync of content is **not** recommended: edits made in Jira flowing straight back would skip the
  PM-approval rule and cause conflicts. Code can list the differences; the agent tells the PM; only the PM's approval
  changes our data.
- What we need back is **progress**: each issue's status and whether the Jira sprint was completed.
- Local app, no hosting, so no webhooks: the app reads Jira when needed (sprint finished, or the PM asks).

## 1.6 UI (PROPOSED)
- **Settings panel (outside the chat):** Connect Jira — site, email, API token, project. Credentials must never be
  typed in the chat (the chat history is saved and sent to the model on every turn).
- **Sidebar Jira section:** "Connect Jira" before setup; then project name, board link, last push time.
- **Chat card when the plan is ready** (sprint + assignments approved): "Your plan is ready: 4 epics, 15 stories,
  sprint 1 with 32 tasks. [Push to Jira]". After the push: the result and a link to the board.
- **Chat card when a sprint is finished:** [Get progress from Jira].
- Typing ("push it to Jira") still works too.

## 1.7 Creating a Jira project for the PM (PROPOSED)
| Option | Verdict |
|---|---|
| **A. Use an existing project** (pick from a list) | Always available |
| **B. Create a new project** from the app | Available when the PM is a Jira admin |

B: form pre-filled from our plan — name from the approved discovery title, a suggested key (e.g. LIB, editable),
lead = the PM, team = people from their Jira site (+ emails to invite, if admin). The PM confirms, then code
creates it. Conditions: the PM must be a Jira admin (usually true on a free site they created); create
**company-managed Scrum** projects only (team-managed creation through the API is not reliable; company-managed
gives one known story points field and a Scrum board automatically); the key must be unique, 2-10 capital letters;
hard to undo (a deleted project stays in the trash 60 days), so the PM must confirm clearly.

## 1.8 Optional read-only Jira agent (PROPOSED — merged in Part 3)
A small agent for free questions ("what's blocked?", "what is Sara doing?"), routed by the main agent, read-only
tools, never writes to Jira.

## 1.9 Limits and costs (checked September 2026)
- **The API is free.** No new model cost for the push: it is code, not an agent.
- **Jira Free plan:** free for up to 10 users, unlimited projects, backlog/boards/sprints. An 11th user needs a paid
  plan (per user) — the PM's cost, not ours.
- **Free plan: 100 email notifications a day.** Assigning many tasks in one push can use them up; design the push to
  avoid flooding notifications.
- **Rate limits:** API-token traffic has burst limits and per-issue write limits; over the limit Jira returns 429
  with Retry-After. The push must slow down and retry. (The points-based limits from March 2026 apply to apps;
  API-token traffic is not affected.)
- **API tokens expire after at most 1 year.** Show a clear "your Jira token expired" message.
- **Use a scoped API token** with only the Jira permissions we need.
- Creating a project needs Jira admin rights. Free plan storage is 2 GB (irrelevant: we push text).

Sources:
- https://www.atlassian.com/software/jira/pricing
- https://www.usecarly.com/blog/jira-pricing/
- https://developer.atlassian.com/cloud/jira/platform/rate-limiting/
- https://community.developer.atlassian.com/t/action-required-update-your-apps-to-comply-with-jira-cloud-burst-api-rate-limits/97202
- https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/

---

# Part 2 — New options (latest discussion)

## 2.1 Using ReAct agents with Jira (PROPOSED)
Our sub-agents are already ReAct-style (reason -> act with a tool -> observe -> repeat). For Jira it depends on the
tools the agent gets:

| Shape | Verdict |
|---|---|
| ReAct agent with **small write tools** (`create_issue`, `add_to_sprint`, `link_issues`) pushing issue by issue | **No** — slow, costly, may skip or duplicate, not repeatable |
| ReAct agent with **big, safe tools written in code** (`push_plan()`, `read_progress()`, `list_jira_team()`) plus **read-only** search | **Yes** — the agent decides when and what to do when something goes wrong; code does the exact writing |

Where the ReAct loop helps:
1. Errors that need judgment — push returns "Sara has no Jira account" -> the agent asks "Invite her, or give her
   tasks to someone else?" -> acts on the answer -> pushes again.
2. Matching people — the team says "Omar", Jira has "Omar Hassan" and "Omar Ali" -> the agent asks which.
3. Expired token or missing permission — explains in plain words what to fix.
4. Progress with nuance — "T9 is 'In Review', not Done. Count it as unfinished?"
5. Free questions — "what's blocked?", "how far is sprint 2?"

## 2.2 Closing a sprint from Jira progress (PROPOSED — the main use of ReAct)
Use the **existing sprint agent** (closing a sprint and planning the next is already its job), not a new agent,
with Jira read-only tools.

Flow:
1. **Trigger:** the PM clicks "Sprint 1 finished -> get progress from Jira" (or types it).
2. **Automatic snapshot (code, not a tool):** the status of every task of the sprint (Done / In Progress / To Do /
   In Review ...), so the basic facts are always there even if the agent forgets to look.
3. **ReAct investigation (read-only Jira tools):** the sprint agent looks deeper and asks the PM where needed:
   - "In Review" / almost-done tasks: "T9 is in review, not done. Carry it over, or count it as done?"
   - New work created directly in Jira (not in our plan): "The team added 'Fix login crash' in Jira. A task under
     S1, or a new story?" (A new story is not the sprint agent's job: it hands it off to the stories part.)
   - Tasks moved or removed in Jira: notices and asks.
   - Comments and blockers on unfinished tasks, to decide what to carry over.
4. **Closes sprint N** with the real outcome, then **plans sprint N+1**: unfinished work first, then the most
   important backlog stories, using code-computed point totals (see LATER.md point 3).
5. **The PM approves** -> assignments checks itself -> **[Push to Jira]** creates the next sprint.

Why ReAct fits here (and not for pushing): pushing is a fixed mapping with nothing to decide; closing a sprint is
full of "it depends" (half-done tasks, surprise work, blockers, moved items).

Safety rules:
- The sprint agent's Jira tools are **read-only**. Writing to Jira only happens through the code push, after the PM
  approves.
- The **automatic snapshot** always comes first, so checking progress cannot be skipped.
- Text from Jira (comments, titles) is **data, never instructions** (prompt injection).

## 2.3 When Jira and our plan disagree about unfinished work (USER DECIDED: option C)
In Jira, "Complete sprint" asks the PM where unfinished issues go (backlog or next sprint). Our sprint agent also
decides this. Example: in Jira the PM moves T9 and T10 to the backlog, but our sprint agent plans sprint 2 with T9
and T10 in it.

| Option | Pros | Cons |
|---|---|---|
| A. Jira wins: our app copies the PM's Jira choice | The PM decides once, in Jira | Our agent cannot plan well (no pulling in high-priority backlog stories, no capacity check) |
| B. Our app wins: the next push changes Jira to match the approved plan | One source of truth, well-planned sprint | Overwrites what the PM did in Jira by hand |
| **C. Mixed — CHOSEN** | Nothing done in Jira is ignored; the PM still decides in one place | One extra question when Jira and the plan disagree |

How C works: the sprint agent reads what the PM chose in Jira and uses it as a strong hint ("In Jira you moved T9
and T10 to the backlog. Leave them out of sprint 2, or bring them in?"), then plans. The PM approves, and the push
updates Jira to match the approved plan. This keeps the rule "nothing changes without the PM's approval".

---

# Part 3 — How Part 2 changes Part 1

| Part 1 item | Change |
|---|---|
| 1.3 Push by code | Unchanged. Code still does all writing. It can also be called by an agent as the `push_plan()` tool. |
| 1.5 Reading progress | Extended: the automatic snapshot stays, and the sprint agent gets read-only Jira tools to investigate (2.2). |
| 1.6 UI | The "Get progress from Jira" card starts the sprint-closing flow of 2.2. |
| 1.8 Read-only Jira agent | Can be merged into the sprint agent's read-only tools; a separate agent is only needed for general Jira questions outside sprint closing. |

Combined loop: **plan -> approve -> [Push to Jira] (code) -> the team works in Jira -> [Get progress from Jira]
(snapshot by code + sprint agent investigates with read-only tools, option C for disagreements) -> close sprint and
plan the next -> approve -> push again.**

## Open questions
- How to avoid the 100-emails-a-day limit on big pushes.
- Policy for items removed in our app after a push: close them in Jira, or leave them.
- Whether general Jira questions ("what's blocked?") get their own read-only agent or go to the sprint agent.
