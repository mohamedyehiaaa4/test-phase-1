"""The six planning steps: what each one writes (item shapes) and when its draft is complete.

A draft is plain JSON: {slot: item} for a single item, {slot: [items]} for a list. It has the same shape that
save_step / load_step use in the database. A field marked ref("stories") must hold keys of items in that slot,
either in this draft or in an approved earlier step.
"""
import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, ClassVar, Literal

from pydantic import BaseModel, Field

Priority = Literal["high", "medium", "low"]
PROMPTS = Path(__file__).parent / "prompts"


def ref(slot, description, **kw):
    return Field(description=description, json_schema_extra={"ref": slot}, **kw)


class Item(BaseModel):
    slot: ClassVar[str]           # where the item lives in the draft
    single: ClassVar[bool] = False
    key_field: ClassVar[str] = "key"


# --- discovery ----------------------------------------------------------------------------------------------
class Summary(Item):
    """The project summary for the PM to review. Saving it again replaces it."""
    slot = "summary"
    single = True
    title: str = Field(min_length=1, description="The project's short name")
    summary: str = Field(min_length=1, description="Only what the PM said in this chat, under headings from this list "
                         "in this order: Purpose, Problems it solves, Users and what each can do, Rules, Notifications, "
                         "Out of scope, Other. Write a heading only if the PM said something for it; never fill one "
                         "from general knowledge")
    assumptions: list[str] = Field(default=[], description="Only guesses the PM explicitly said yes to; 'go on your "
                                   "own' is not a yes. Usually empty")


# --- requirements -------------------------------------------------------------------------------------------
class Prd(Item):
    """The PRD: a short product description for the team. Saving it again replaces it."""
    slot = "prd"
    single = True
    title: str = Field(min_length=1)
    body: str = Field(min_length=1, description="Headings from this list, in this order: What the product is, Goals, "
                      "Target users, In scope, Out of scope. Only headings the approved idea or the PM gives content "
                      "for; never fill one from general knowledge")


class Requirement(Item):
    """Add a requirement, or replace the one with the same key."""
    slot = "requirements"
    key: str = Field(pattern=r"^(FR|NFR)\d+$", description="FR1, FR2... for functional, NFR1... for non-functional")
    kind: Literal["functional", "non_functional"]
    category: str = Field(default="", description="Non-functional only: the quality area in plain words")
    title: str = Field(min_length=1)
    description: str = Field(min_length=1, description="Functional: 'The system shall ...', one testable behaviour")
    priority: Priority
    priority_reason: str = Field(min_length=1, description="One sentence: why this priority")
    basis: str = Field(default="", description="Where it comes from, in one short sentence")


class Assumption(Item):
    """Record a guess the PM explicitly said yes to. Replaces the one with the same key."""
    slot = "assumptions"
    key: str = Field(pattern=r"^A\d+$", description="A1, A2...")
    statement: str = Field(min_length=1)
    reason: str = Field(min_length=1)


# --- stories ------------------------------------------------------------------------------------------------
class Story(Item):
    """Add a user story, or replace the one with the same key."""
    slot = "stories"
    key: str = Field(pattern=r"^S\d+$", description="S1, S2...")
    title: str = Field(min_length=1)
    statement: str = Field(min_length=1, description="As a <role>, I want <goal>, so that <benefit>.")
    requirement_keys: list[str] = ref("requirements", "Requirements it implements (functional) or is constrained "
                                      "by (non-functional)", min_length=1)
    points: float | None = Field(default=None, ge=0, description="Your proposed size in the PM's scale: 1 trivial, "
                                 "2 one small rule, 3 one complete action, 5 several parts or correctness "
                                 "under many users, 8 too big (suggest a split)")
    priority: Priority
    priority_reason: str = Field(min_length=1)


# --- criteria -----------------------------------------------------------------------------------------------
class Criterion(Item):
    """Add an acceptance criterion, or replace the one with the same key."""
    slot = "criteria"
    key: str = Field(pattern=r"^C\d+$", description="C1, C2...")
    story_key: str = ref("stories", "The story it belongs to")
    scenario: str = Field(min_length=1)
    type: Literal["happy_path", "negative", "edge_case"]
    given: list[str] = Field(default=[], description="Preconditions")
    when: str = Field(min_length=1, description="One action or event")
    then: list[str] = Field(min_length=1, description="Observable, testable outcomes")


# --- sprint -------------------------------------------------------------------------------------------------
class Epic(Item):
    """Group stories into an epic, or replace the one with the same key."""
    slot = "epics"
    key: str = Field(pattern=r"^E\d+$", description="E1, E2...")
    title: str = Field(min_length=1)
    description: str = ""
    story_keys: list[str] = ref("stories", "Stories in this epic", min_length=1)


class Task(Item):
    """Add a task of a story, or replace the one with the same key."""
    slot = "tasks"
    key: str = Field(pattern=r"^T\d+$", description="T1, T2...")
    story_key: str = ref("stories", "The story it belongs to")
    title: str = Field(min_length=1)
    description: str = Field(default="", description="What to build, the rules it must enforce, and the acceptance "
                             "criteria (keys) it serves")
    work_type: str = Field(min_length=1, description="The narrowest specialist role on a real team that would own this "
                           "task, named after its particular technology or concern, never after a layer or side "
                           "of the system")
    priority: Priority
    depends_on: list[str] = ref("tasks", "Tasks that must be done first", default=[])


class Sprint(Item):
    """Plan, update or close a sprint. Replaces the one with the same key."""
    slot = "sprints"
    key: str = Field(pattern=r"^SP\d+$", description="SP1 for sprint 1, SP2...")
    number: int = Field(ge=1)
    goal: str = Field(min_length=1, description="One outcome-focused sentence")
    status: Literal["planned", "active", "closed"] = Field(description="Only one sprint is active")
    task_keys: list[str] = ref("tasks", "Tasks in this sprint")
    length: str = Field(default="", description="As the PM said it")
    capacity: float | None = Field(default=None, ge=0, description="Team capacity in story points, as a number "
                                   "(\"about 20\" is 20); empty if the PM does not know. Anything else they say about "
                                   "it goes in notes")
    notes: str = ""
    outcome: str = Field(default="", description="For a closed sprint: what was done and not, in the PM's words")


# --- assignments --------------------------------------------------------------------------------------------
class Member(Item):
    """Record a team member as the PM described them. Replaces the one with the same key."""
    slot = "members"
    key: str = Field(pattern=r"^M\d+$", description="M1, M2...")
    name: str = Field(min_length=1)
    role: str = Field(min_length=1, description="Their work role in the PM's words")


class Assignment(Item):
    """Decide who works on a task of the active sprint (main owner first), or leave it unassigned with the reason."""
    slot = "assignments"
    key_field = "task_key"
    task_key: str = ref("tasks", "A task of the active sprint")
    member_keys: list[str] = ref("members", "Main owner first, then helpers. Empty = unassigned", default=[])
    required_role: str = Field(default="", description="The specialist role the task needs, as specific as a job "
                               "title on a real team")
    rationale: str = Field(default="", description="One short sentence about this task only: why this person's role "
                           "fits it (or why nobody fits). Never counts or lists of other tasks")


# --- done checks: (draft, approved drafts of earlier steps) -> problems -------------------------------------
def check_discovery(d, _):
    return [] if d.get("summary") else ["write the summary with save_summary"]


def check_requirements(d, _):
    problems = [] if d.get("prd") else ["write the PRD with save_prd"]
    if not any(r["kind"] == "functional" for r in d.get("requirements", [])):
        problems.append("add at least one functional requirement")
    return problems


def check_stories(d, approved):
    covered = {k for s in d.get("stories", []) for k in s["requirement_keys"]}
    missing = [r["key"] for r in approved["requirements"]["requirements"]
               if r["kind"] == "functional" and r["key"] not in covered]
    return [f"no story covers {', '.join(missing)}"] if missing else []


def check_criteria(d, approved):
    covered = {c["story_key"] for c in d.get("criteria", [])}
    missing = [s["key"] for s in approved["stories"]["stories"] if s["key"] not in covered]
    return [f"no criteria for {', '.join(missing)}"] if missing else []


def check_sprint(d, _):
    active = [s for s in d.get("sprints", []) if s["status"] == "active"]
    if len(active) != 1:
        return [f"exactly one sprint must be active, found {len(active)}"]
    return [] if active[0]["task_keys"] else ["the active sprint has no tasks"]


def active_sprint_tasks(sprint_draft):
    return next((s["task_keys"] for s in sprint_draft["sprints"] if s["status"] == "active"), [])


def check_assignments(d, approved):
    decided = {a["task_key"] for a in d.get("assignments", [])}
    left = [k for k in active_sprint_tasks(approved["sprint"]) if k not in decided]
    return [f"no decision yet for {', '.join(left)}"] if left else []


def sprint_numbers(d, approved):
    """Facts about every sprint in the draft, computed by code so the agent never adds points itself."""
    points = {s["key"]: s.get("points") for s in (approved.get("stories") or {}).get("stories", [])}
    story_of = {t["key"]: t["story_key"] for t in d.get("tasks", [])}
    shown = lambda k: f"{k} ({points[k]:g})" if points.get(k) is not None else f"{k} (no points)"  # noqa: E731
    lines, planned = [], set()
    for sp in sorted(d.get("sprints", []), key=lambda s: s["number"]):
        stories = sorted({story_of[t] for t in sp["task_keys"] if t in story_of}, key=lambda k: int(k[1:]))
        planned.update(stories)
        total, cap = sum(points.get(k) or 0 for k in stories), sp.get("capacity")
        line = f"{sp['key']} ({sp['status']}): {', '.join(map(shown, stories)) or 'no stories'} = {total:g} points"
        line += f" of capacity {cap:g}" if cap is not None else ", capacity unknown"
        if cap is not None and total > cap:
            line += f"; OVER CAPACITY by {total - cap:g}"
        if no_points := [k for k in stories if points.get(k) is None]:
            line += f"; no points: {', '.join(no_points)}"
        if partly := [k for k in stories if any(s == k and t not in sp["task_keys"] for t, s in story_of.items())]:
            line += f"; only partly in this sprint: {', '.join(partly)}"
        lines.append(line)
    backlog = [k for k in points if k not in planned]
    lines.append(f"Backlog (in no sprint): {', '.join(map(shown, backlog)) or 'none'} = "
                 f"{sum(points.get(k) or 0 for k in backlog):g} points")
    return "\n".join(lines)


def team_load(d, approved):
    """Each member's tasks in the running sprint, computed by code so reasons never carry counts that go stale."""
    sprint_tasks = active_sprint_tasks(approved["sprint"]) if approved.get("sprint") else []
    decided = {a["task_key"]: a["member_keys"] for a in d.get("assignments", []) if a["task_key"] in sprint_tasks}
    lines = []
    for m in d.get("members", []):
        owns = [t for t in sprint_tasks if (decided.get(t) or [None])[0] == m["key"]]  # [] = left unassigned
        helps = [t for t in sprint_tasks if m["key"] in (decided.get(t) or [])[1:]]
        lines.append(f"{m['key']} {m['name']}: {len(owns)} task(s) as main owner ({', '.join(owns) or 'none'})"
                     + (f", helping on {', '.join(helps)}" if helps else ""))
    lines.append(f"Not decided yet: {', '.join(t for t in sprint_tasks if t not in decided) or 'none'}")
    lines.append(f"Left unassigned: {', '.join(t for t in sprint_tasks if decided.get(t) == []) or 'none'}")
    return "\n".join(lines)


def what_changed(step, old, new, cap=30):
    """What differs between two versions of a step's draft, as short facts for the parts that check themselves."""
    old, new, lines = old or {}, new or {}, []

    def label(x):
        return next((str(x[f]) for f in ("title", "name", "scenario", "goal", "statement") if x.get(f)), "")

    for m in STEPS[step].items:
        a, b = old.get(m.slot), new.get(m.slot)
        if m.single:
            a, b = a or {}, b or {}
            for f in m.model_fields:
                x, y = a.get(f), b.get(f)
                if x == y:
                    continue
                if isinstance(x, str) and isinstance(y, str):  # text: line by line
                    lines += [f"{'removed' if d[0] == '-' else 'added'} line in {f}: {d[2:].strip()}"
                              for d in difflib.ndiff(x.splitlines(), y.splitlines())
                              if d[:2] in ("- ", "+ ") and d[2:].strip()]
                else:
                    lines.append(f"{f} changed: {x!r} -> {y!r}")
        else:  # list items: by key
            ka, kb = {x[m.key_field]: x for x in a or []}, {x[m.key_field]: x for x in b or []}
            lines += [f"added {k}: {label(kb[k])}" for k in kb if k not in ka]
            lines += [f"removed {k}: {label(ka[k])}" for k in ka if k not in kb]
            lines += [f"changed {k} ({label(kb[k])}): {', '.join(f for f in kb[k] if ka[k].get(f) != kb[k].get(f))}"
                      for k in kb if k in ka and ka[k] != kb[k]]
    return lines[:cap] + ([f"...and {len(lines) - cap} more"] if len(lines) > cap else [])


@dataclass(frozen=True)
class Step:
    name: str
    title: str
    items: tuple[type[Item], ...]
    check: Callable[[dict, dict], list[str]]
    owns: str  # what this step owns, for the main agent's routing
    builds_on: tuple[str, ...] = ()  # earlier steps shown to the agent in full
    numbers: Callable[[dict, dict], str] | None = None  # facts computed by code, shown under the agent's draft

    @property
    def prompt(self):
        return (PROMPTS / "rules.md").read_text(encoding="utf-8") + "\n\n" + \
               (PROMPTS / f"{self.name}.md").read_text(encoding="utf-8")


STEPS = {s.name: s for s in (
    Step("discovery", "Project idea", (Summary,), check_discovery,
         "the project idea: what it is, who it is for, goals, needs, the agreed assumptions about the idea"),
    Step("requirements", "Requirements", (Prd, Requirement, Assumption), check_requirements,
         "the PRD, functional and non-functional requirements, their priorities, requirement assumptions",
         builds_on=("discovery",)),
    Step("stories", "User stories", (Story,), check_stories,
         "user stories, their story points and priorities, which requirements each story covers",
         builds_on=("requirements",)),
    Step("criteria", "Acceptance criteria", (Criterion,), check_criteria,
         "acceptance criteria (Given/When/Then) of the stories", builds_on=("stories",)),
    Step("sprint", "Sprint plan", (Epic, Task, Sprint), check_sprint,
         "epics, tasks, sprint length and capacity, which stories/tasks are in a sprint, closing a sprint and "
         "planning the next one", builds_on=("stories", "criteria"), numbers=sprint_numbers),
    Step("assignments", "Task assignments", (Member, Assignment), check_assignments,
         "the team members and their roles, who works on each task of the active sprint",
         builds_on=("sprint", "stories"), numbers=team_load),
)}
ORDER = list(STEPS)


def earlier(step):
    return ORDER[:ORDER.index(step)]


def keys_in(draft):
    """Every key per slot in a draft: {"stories": {"S1", ...}, ...}."""
    found = {}
    for step in STEPS.values():
        for item in step.items:
            if not item.single and item.slot in draft:
                found.setdefault(item.slot, set()).update(x[item.key_field] for x in draft[item.slot])
    return found


def bad_refs(item, known):
    """Keys an item points at that exist nowhere in `known` ({slot: keys})."""
    bad = []
    for name, field in type(item).model_fields.items():
        slot = (field.json_schema_extra or {}).get("ref")
        if slot:
            value = getattr(item, name)
            bad += [k for k in (value if isinstance(value, list) else [value]) if k not in known.get(slot, ())]
    return bad
