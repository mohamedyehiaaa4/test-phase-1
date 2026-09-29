# Jira integration — DISCUSSED, NOT APPROVED YET

Nothing here is built. This records what we discussed about pushing the approved plan to the PM's Jira and reading
progress back.

## Decisions from the user
- **Jira Cloud** (`<site>.atlassian.net`).
- **What to push:** the active sprint (with its tasks and assignees) and the backlog stories (not in the sprint,
  just saved in the PM's Jira for later).
- **Two-way wanted:** mainly to learn what was finished in sprint N and what was not, so unfinished work goes into
  the next sprint.
- **Must be a visible feature** of the site, not something the PM has to guess to type.
- The PM may not know whether the project is company-managed or team-managed; the code must handle both.

## Mapping: our data -> Jira
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

## Recommended approach
No new agent at first. Moving data is code (exact, repeatable, safe to run twice, cheap); decisions stay with agents.

1. **Push = a code node `publish`.** Guard checks sprint and assignments are approved. Creates or updates epics,
   stories, sub-tasks, links, the sprint. A Supabase table remembers our key -> Jira key (e.g. S1 -> PROJ-12), so
   pushing again updates instead of duplicating. The result is written in the chat.
2. **Team accounts come from Jira, not from the chat.** The code reads the project's assignable users (name +
   account id). The assignments agent gets that list automatically (not a tool) and only asks the PM each person's
   role. No emails to ask for, no matching errors. A team change in Jira shows up in the next sprint.
3. **Reading progress = automatic input for the sprint agent.** When the PM says a sprint is finished, code first
   reads issue statuses from Jira; the sprint agent sees facts like "Done: T1, T2. Not done: T3, T4", closes the
   sprint with that outcome and plans the next one with unfinished work first. PM approves, then push again.
4. **No full two-way sync of content.** Edits made in Jira (e.g. a renamed story) are not copied back
   automatically — that would skip the PM-approval rule and cause conflicts. Code can list the differences; the
   agent tells the PM; only the PM's approval changes our data.
5. Local app, no hosting, so no webhooks: the app reads Jira when needed (sprint finished, or the PM asks).
6. **Optional later:** a small read-only Jira agent for free questions ("what's blocked?", "what is Sara doing?"),
   routed by the main agent, using read-only tools. Never writes to Jira.

### Why not a Jira agent with Atlassian's MCP for the push
- Pushing has no decisions in it; it is a fixed mapping.
- The same plan must give the same result every time; an agent varies.
- Pushing twice must update, not duplicate; an agent must remember the mapping itself, and one slip duplicates
  issues in the PM's Jira.
- 50+ issues = 50+ tool calls: slow, costly, and a half-done push may be reported as done.
- Safety: Jira text read back into an agent that has write tools can carry prompt injection.
- Middle way if an agent is wanted: an agent whose tools are ours in code (`push_plan()`, `read_progress()`) plus
  read-only MCP tools; the agent decides when and explains, code does the writing.

## UI (visible feature)
- **Settings panel (outside the chat):** Connect Jira — site, email, API token, project. Credentials must never be
  typed in the chat (the chat history is saved and sent to the model on every turn).
- **Sidebar Jira section:** "Connect Jira" before setup; then project name, board link, last push time.
- **Chat card when the plan is ready** (sprint + assignments approved): "Your plan is ready: 4 epics, 15 stories,
  sprint 1 with 32 tasks. [Push to Jira]". After the push: the result and a link to the board.
- **Chat card when a sprint is finished:** [Get progress from Jira].
- Typing ("push it to Jira") still works too.

## Create a Jira project for the PM (option)
- In the Jira panel: **Use an existing project** (pick from a list) or **Create a new project**.
- Create form pre-filled from our plan: name from the approved discovery title, a suggested key (e.g. LIB, the PM
  can edit), lead = the PM, team = people from their Jira site (+ emails to invite, if admin). PM confirms, then
  code creates it.
- Conditions: the PM must be a Jira admin (usually true on a free site they created); create **company-managed
  Scrum** projects only (team-managed creation through the API is not reliable; company-managed also gives one
  known story points field and a Scrum board automatically); key must be unique, 2-10 capital letters; hard to
  undo (a deleted project stays in the trash 60 days), so the PM must confirm clearly.

## Limits and costs (checked September 2026)
- **The API is free.** No new model cost either: the push is code, not an agent.
- **Jira Free plan:** free for up to 10 users, unlimited projects, backlog/boards/sprints. An 11th user needs a paid
  plan (per user) — the PM's cost, not ours.
- **Free plan: 100 email notifications a day.** Assigning many tasks in one push can use them up; design the push
  to avoid flooding notifications.
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

## Open questions
- Company-managed or team-managed (only matters when using an existing project; the code can detect it).
- How to avoid the 100-emails-a-day limit on big pushes.
- Policy for items removed in our app after a push: close them in Jira, or leave them.
