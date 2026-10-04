# Jira integration — the plan (NOT BUILT YET)

Replaces the earlier discussion notes. Labels: **DECIDED** = the user chose it; **PLAN** = how we build it.
Everything follows the project's rules: simplest code that works, agents decide, code writes, the PM approves.

---

## 1. The PM's journey (DECIDED)

```
New project ── name ── optional: connect Jira (log in once + pick the Jira project)
     │
Discovery → Requirements → Stories → Criteria → Sprint
     │
Assignments ── linked: shows the Jira project's people, asks only who is on the team and their roles
            └─ not linked: as today (the PM types the team)
     │
 ┌───┴──────────────────────────────┐
linked                          not linked
 │                                  │
Jira agent ("Push sprint 1 to Jira?")   plan complete (as today)
 │  preview → PM approves → code pushes through MCP
 │  answers Jira questions any time
 │
PM: "sprint 1 is finished"
 │  Jira agent reads Jira (what is done, what is not, new work), asks about unclear cases
 ▼
Sprint agent closes sprint 1 and plans sprint 2 → PM approves → assignments re-checks
 → Jira agent pushes sprint 2 → …
```

Decisions behind it:
- Jira is **optional**: a PM who never connects Jira gets the same app as today.
- **OAuth** login to Jira, **local** app (Atlassian accepts an `http://localhost` callback).
- **Only the PM** connects Jira and pushes; team members never need our app.
- **Atlassian's MCP server** for everything Jira (good for the presentation).
- **One Jira agent** for everything Jira the PM talks about: pushing, progress, questions.
- **The agent decides, code writes.** The agent asks and decides when; the actual writing to Jira is one code tool
  that calls the MCP tools in a fixed order (no AI in the writing).
- **Team from Jira:** if the project is linked when the assignments step starts, the agent takes the people from the
  Jira project and asks only for roles; otherwise the PM types the team (fallback, because some PMs do not use Jira).
- When Jira and our plan disagree after a sprint (for example the PM moved a task to the backlog in Jira), the
  **sprint agent** asks the PM which to follow.
- The chat will later run on the PM's **website**; until then Streamlit is the screen.

---

## 2. Architecture (PLAN)

```
          Streamlit (later: the website, through a small API)
                 │
            main graph ── planning agents (6) ── assignments ──► jira agent (linked projects only)
                 │                                                   │ read tools: MCP (search, sprint data, users)
                 │                                                   │ push_sprint: code ──► MCP write tools
                 │                                                   │ report_progress: ends its turn
              Supabase  ◄──────────────── jira.py (login, link, people, push, snapshot)
                                                     │
                                         Atlassian MCP server (https://mcp.atlassian.com/v2/mcp)
```

**One new code file, `jira.py`:** the MCP connection (OAuth login, token refresh), listing projects and people,
the push, and the progress snapshot. Everything that touches Jira goes through it.

**The Jira agent reuses `agent.py`:** it is built by the same builder as the six planning agents (same loop: model →
tools → model, pausing for the PM), with no draft items, its own prompt `prompts/jira.md`, and extra tools. It is not
part of the planning order: it runs after assignments, only for linked projects.

| Tool | Kind | What it does |
|---|---|---|
| MCP read tools (allow-list by name: JQL search, get issue, sprint data, assignable users, list projects) | read | look at Jira |
| `push_sprint` | **code** | shows the push preview with the normal Approve button; only after Approve, pushes through MCP |
| `report_progress` | ends its turn | the finished sprint's real progress, checked by code, handed to the sprint agent |
| `not_my_job` | ends its turn | anything about the plan itself goes to the router, as today |

**Database (2 new tables, 2 tables get columns; service role only, like every table):**

| What | Columns | Why |
|---|---|---|
| `jira_connections` (new) | pm_id (key), site_id, site_name, site_url, access_token (encrypted), refresh_token (encrypted), expires_at, login_state, login_verifier, login_started_at | one Jira login per PM; the login state survives the redirect back from Atlassian |
| `jira_issue_links` (new) | project_id + our key (key), jira_key, jira_id, content_hash, pushed_at | S1 → TEST-12: a second push updates instead of duplicating, and skips what did not change |
| `projects` (+ columns) | jira_project_key, jira_project_id, jira_board_id | which Jira project and Scrum board this project is linked to (empty = not linked) |
| `members` (+ column) | jira_account_id | the person's Jira id (empty = not from Jira) |

**Security (never cut):** tokens are encrypted by the database (`pgcrypto`, key `JIRA_TOKEN_KEY` in `.env`) and never
appear in the chat, the graph state or logs; the login uses a one-time `state` and PKCE; the Jira agent has **no
write tools** (only `push_sprint`, which writes only after the PM's Approve), so text written in Jira cannot make it
change anything; Jira text is data, never instructions.

**What goes where in Jira:**

| Ours | Jira |
|---|---|
| Epic E1 | Epic |
| Story S1 (every approved story: sprint and backlog) | Story, parent = its epic; description = the story sentence + its acceptance criteria (Given / When / Then); priority; story points |
| Task T1 (tasks of the active sprint) | Sub-task of its story; assignee = main owner; work type as a label |
| `depends_on` | "blocks" link |
| Active sprint SP1 | Jira sprint "Sprint 1" with its goal, created **not started** (the PM starts and completes sprints in Jira); its stories added |

---

## 3. Phases

Each phase works on its own and ends with a manual check (tests stay out of scope). After each phase: update
`PLAN.md`, this file and `CHANGES.md`.

### Phase 0 — Prove the MCP connection (experiment, ~1 day)
Prepare: a free Jira Cloud site and a test project (company-managed **Scrum**), 2–3 invited test users.
A throwaway script (not in the project) logs in to the MCP server from localhost, reads (projects, assignable users,
sprints), writes in the test project (epic, story with points, sub-task with assignee, a link, a sprint with the
story) and deletes it, and runs one read-only agent question through the MCP tools.
Answers, written into this file:
1. Can our Python app log in to the MCP server with OAuth from localhost (package `mcp`)?
2. Do the MCP write tools cover story points, epic parent, sub-tasks and adding to a sprint? Anything missing goes
   through Jira's normal web API (REST) as a backup.
3. Can assignment emails be turned off (the free plan allows 100 emails a day)?
4. Which tools use Rovo credits, and how many does a push / a progress read cost?
5. How fast can we call (rate limits) for the ~100 calls of a push?
**Done when:** all 5 are answered and the plan still holds (or is adjusted here).

### Phase 1 — Projects: create and switch (~1 day)
- **PM sees:** "My projects" (name, date) and **New project** (a name, required). After creating: the project's
  empty chat; the first message is the idea, as today. Switching keeps each project's own chat and plan. The open
  project is in the page address (`?project=…`), so a refresh keeps it.
- **Database:** the name must be 1–80 characters (a check constraint). No new table.
- **Code:** `app.py`: the list, the form, opening a project; the graph's `thread_id` = the open project's id (each
  project's agents and chats are already stored per project); a project id in the address must belong to the PM.
  `PROJECT_ID` leaves `.env`. The existing project shows up in the list.
- **Not now:** deleting and renaming projects; login (one PM from `.env`).
- **Check:** two projects keep separate chats; refresh keeps the project; empty name and unknown ids are refused.

### Phase 2 — Connect Jira and link a project (~2–3 days)
- **PM sees:** on the New project form an optional **Jira project** field: "Connect Jira" if not logged in, else a
  dropdown of the PM's Jira projects that have a Scrum board (others greyed out: "no Scrum board, so no sprints").
  The same field in a small **Project settings** view (link, change, unlink; a link to the board). A sidebar line:
  Jira site name, or "Connect Jira"; "Disconnect".
- **Login (OAuth, PKCE):** "Connect Jira" saves a one-time `state` and verifier on the PM's `jira_connections` row,
  opens Atlassian's consent page; Atlassian returns to `http://localhost:<port>/?code=…&state=…`; the app checks the
  state, trades the code for tokens, saves them encrypted, and cleans the address. A PM on several Jira sites picks
  one.
- **Code (`jira.py`):** `connect_url`, `finish_connect`, `session` (gives a working MCP connection; refreshes the
  token when it expires within 2 minutes and saves the new refresh token at once, because Atlassian replaces it on
  every use; on failure the PM is shown "Reconnect Jira"), `disconnect`, `list_projects`, `link`.
- **Rules:** changing or unlinking after a push asks to confirm ("pushed issues stay in the old Jira project");
  confirming clears this project's `jira_issue_links`.
- **Check:** connect, restart the app, still connected; an expired token refreshes; a revoked one asks to reconnect;
  cancel at Atlassian saves nothing; projects without a Scrum board are greyed out.

### Phase 3 — Team from Jira in the assignments step (~2 days)
- **PM sees (linked):** "Your Jira project has Sara Ahmed, Omar Ali and Ahmed Hassan. Which of them are on this team,
  and what is each one's role?" — then assignments as today. **Not linked:** exactly as today.
- **Database:** `members.jira_account_id`; `save_step` / `load_step` save and load it.
- **Code:** `steps.py`: optional `Member.jira_account_id`. `graph.py`: when the assignments agent runs and the project
  is linked, code fetches the Jira people and passes them in (like the computed numbers: always there, not a tool);
  if Jira cannot be reached, a note says so and the agent works as without Jira (nothing blocks). `agent.py`: the
  prompt section "People in the linked Jira project"; a code check: a saved `jira_account_id` must be in that list.
  The computed team load adds "No longer in the Jira project: M3 Omar" when someone left (the list is fetched fresh
  every time, so team changes show up at the next sprint). `prompts/assignments.md`: take the team only from the list
  when it is shown, one question for who is on the team and their roles.
- **Linked late** (after the team was set): no extra screen. Before pushing, the Jira agent sees members without a
  Jira id and code starts a change to assignments ("pick the team from the Jira project"); the assignments agent
  redoes only the team, the PM approves, as any change.
- **Check:** linked → Jira names and ids saved; not linked → as today; a made-up id is refused; a removed Jira user
  is flagged; linking late leads to the team change.

### Phase 4 — The Jira agent and the push (~3–4 days)
- **PM sees:** after assignments is approved (linked projects), the Jira agent: "Push sprint 1 to Jira?". On yes, the
  **preview** with the normal **Approve** button: "Will create 3 epics, 7 stories (4 in the sprint, 3 in the backlog),
  15 sub-tasks, 4 links, the sprint 'Sprint 1', 15 assignments" (+ an email warning on the free plan, if phase 0 says
  so). After Approve: "Pushed: 29 created, 0 failed" with a link to the board. The PM can ask Jira questions any time
  ("what's blocked?").
- **Graph:** a new node `jira` (the Jira agent). After the last planning step is approved, `load` goes to `jira`
  instead of `idle` when the project is linked (not linked: `idle`, as today). Its `not_my_job` goes to the router as
  today; the router can send a Jira question back to `jira` (the guard allows it only for linked projects).
- **`push_sprint` (code, `jira.py`), in a fixed order:** read the approved plan and the link table; look up the
  Jira names once (issue types, story points field); epics → stories → sub-tasks → links → the sprint and its stories.
  Each item: linked and unchanged (same `content_hash`, standard library `hashlib`) → skip; linked and changed →
  update; new → create and **save its link at once** (a push stopped halfway continues without duplicates). One call
  at a time; on "too many requests" wait as Jira asks and retry (up to 5). A failing item does not stop the rest: the
  result lists it with its reason ("T7: Sara can't be assigned"), and the agent explains and offers to push again.
  Items removed from our plan after a push are **not deleted in Jira**; the result lists them.
- **Prompt `prompts/jira.md`:** offer the push after planning; push only when the PM agrees; explain results and
  failures in plain words; answer Jira questions from the read tools; anything about the plan itself is not its job.
- **Check:** first push builds the right board; a second push skips everything; a changed story is updated alone;
  stopping halfway then pushing again makes no duplicates; an unassignable member is reported and the rest pushed.

### Phase 5 — Sprint finished: progress and the next sprint (~2–3 days)
- **PM sees:** "sprint 1 is finished" (to the Jira agent, or anywhere: the router sends it to `jira` for linked
  projects). The Jira agent: "8 of 11 tasks are done. T9 is still In Review — count it as not done?" (one question at
  a time). Then the sprint agent closes sprint 1 and plans sprint 2; the PM approves; assignments re-checks; the Jira
  agent offers to push sprint 2.
- **Snapshot (code, always first):** every issue of the Jira sprint with its status, sorted by code into done, not
  done, new work (in the sprint but not in our link table), moved out (in our link table, no longer in the sprint).
  Given to the agent as input, so the facts are always there.
- **`report_progress`:** ends the agent's turn with done / not done / new work / moved / notes; code checks every key
  exists, then starts a sprint change with a note — "Sprint 1 finished. From Jira: done T1–T8; not done T9 (In
  Review), T11; new work in Jira: 'Fix login crash' (TEST-31); moved to the backlog in Jira: T10." — the same change
  flow as "sprint 1 is finished" today.
- **`prompts/sprint.md`:** when the Jira note shows something the plan disagrees with, ask the PM which to follow.
- **Sprint 2 push:** creates "Sprint 2", moves carried-over issues into it (their links already exist: no
  duplicates), creates only what is new. The PM completes sprint 1 in Jira (the normal Jira way); we only read it.
- **Not linked:** "sprint 1 is finished" goes straight to the sprint agent, as today.
- **Check:** two full loops (plan → push → work in Jira → progress → sprint 2 → push) with no duplicates; an In
  Review task is asked about; an issue added in Jira is reported as new work; a moved task makes the sprint agent ask.

### Phase 6 (later) — The website
A small API in front of the same functions when the website's UI is ready (Streamlit stays as a test screen):
projects (list, create), chat (send, approve, get the chat and what is waiting), Jira (connect start + callback,
disconnect, list and link projects). The push and progress need no endpoint of their own: they happen in the chat.

---

## 4. Totals
- **New:** `jira.py`, `prompts/jira.md`; tables `jira_connections`, `jira_issue_links`; columns on `projects` and
  `members`; packages `mcp` (+ a LangGraph adapter for MCP tools, if phase 0 uses it); `.env` `JIRA_TOKEN_KEY` (+ the
  OAuth app id/secret if phase 0 shows they are needed); `PROJECT_ID` leaves `.env`.
- **Changed:** `app.py` (projects, Jira field, settings), `graph.py` (node `jira`, Jira people for assignments, the
  progress note), `agent.py` (extra tools option, Jira people section and check), `steps.py` (`Member` field),
  prompts (assignments, sprint, router), `schema.sql` (+ live database).
- **Estimate:** about 2.5–3 weeks plus testing time in Jira.

## 5. Open decisions (default in brackets)
- Close issues in Jira that were removed from our plan? [no: only list them in the push result]
- Turn off assignment emails if possible? [decide after phase 0]
- Fill sprint start and end dates from the sprint length? [no: the PM starts the sprint in Jira]
- Create a Jira project from our app (needs Jira admin rights)? [later, optional; for now pick an existing one]

## 6. Decided against (and why)
- **The agent writing to Jira call by call** — ~100 model steps per push, can skip or duplicate, and Jira text
  could trick an agent with write tools. The agent decides; code writes.
- **A separate push button and a matching screen** — the Jira agent's preview + the normal Approve card does the
  push; the assignments change flow does late matching. Fewer screens, one way to do each thing.
- **Jira's web API (REST) for everything** — needs its own login and hand-written calls; kept only as a backup for
  anything MCP cannot do (phase 0).
- **Asking members' emails in the chat** — Jira usually hides emails, so matching fails.
- **A separate table for login attempts or push history** — the login state fits on the connection row; the link
  table already knows what was pushed and when.
- **A second agent loop for the Jira agent** — it reuses the builder in `agent.py`.

## 7. Facts checked (October 2026)
- Atlassian Rovo MCP v2 is generally available since September 8, 2026, remote at `https://mcp.atlassian.com/v2/mcp`,
  OAuth 2.1 or API token; Jira tools include create/edit/get issue, sub-task conversion, issue links,
  `manageJiraSprint` (create, fill, start, close), board sprints and sprint data, assignable users, account id
  lookup, JQL search, list projects. Search-type Rovo tools can use Rovo credits.
- Atlassian OAuth callbacks must be HTTPS except `http://localhost`.
- Jira Free: up to 10 users, sprints and boards included, 100 notification emails a day. API rate limits answer 429
  with Retry-After.

Sources:
- https://developer.atlassian.com/cloud/rovo-mcp/
- https://developer.atlassian.com/cloud/rovo-mcp/guides/supported-tools/
- https://developer.atlassian.com/cloud/oauth/getting-started/implementing-oauth-3lo/
- https://community.developer.atlassian.com/t/oauth-2-0-callback-url-using-http-not-https/58722
- https://www.atlassian.com/software/jira/pricing
- https://developer.atlassian.com/cloud/jira/platform/rate-limiting/
