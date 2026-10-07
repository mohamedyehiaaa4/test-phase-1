"""The four planning steps: which items each one writes, when its draft is complete, and what changed between
two versions of it."""
import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .checks import check_criteria, check_discovery, check_requirements, check_stories
from .items import Assumption, Criterion, Item, Prd, Requirement, Story, Summary

PROMPTS = Path(__file__).parent / "prompts"


def what_changed(step, old, new, cap=30, values=False):
    """What differs between two versions of a step's draft, as short facts for the parts that check themselves.
    With values=True a changed item also shows the new text of each changed field (for the PM's review)."""
    old, new, lines = old or {}, new or {}, []

    def label(x):
        return next((str(x[f]) for f in ("title", "scenario", "statement") if x.get(f)), "")

    def fields(a, b):
        changed = [f for f in b if a.get(f) != b.get(f)]
        if not values:
            return ", ".join(changed)
        show = lambda v: (", ".join(map(str, v)) if isinstance(v, list) else "(empty)" if v in (None, "")  # noqa: E731
                          else f"{v:g}" if isinstance(v, float) else str(v))
        return "; ".join(f"{f.replace('_', ' ')} is now: {show(b.get(f))}" for f in changed)

    for m in STEPS[step].items:
        a, b = old.get(m.slot), new.get(m.slot)
        if m.single:
            a, b = a or {}, b or {}
            for f in m.model_fields:
                x, y = a.get(f), b.get(f)
                if x == y:
                    continue
                if values and isinstance(y, str) and "\n" not in (x or "") + y:  # a one-line text: its new value
                    lines.append(f"{f.replace('_', ' ')} is now: {y or '(empty)'}")
                elif isinstance(x, str) and isinstance(y, str):  # text: line by line
                    lines += [f"{'removed' if d[0] == '-' else 'added'} line in {f}: {d[2:].strip()}"
                              for d in difflib.ndiff(x.splitlines(), y.splitlines())
                              if d[:2] in ("- ", "+ ") and d[2:].strip()]
                else:
                    lines.append(f"{f} changed: {x!r} -> {y!r}")
        else:  # list items: by key
            ka, kb = {x[m.key_field]: x for x in a or []}, {x[m.key_field]: x for x in b or []}
            lines += [f"added {k}: {label(kb[k])}" for k in kb if k not in ka]
            lines += [f"removed {k}: {label(ka[k])}" for k in ka if k not in kb]
            lines += [f"changed {k} ({label(kb[k])}): {fields(ka[k], kb[k])}" for k in kb if k in ka and ka[k] != kb[k]]
    return lines[:cap] + ([f"...and {len(lines) - cap} more"] if len(lines) > cap else [])


@dataclass(frozen=True)
class Step:
    name: str
    title: str
    items: tuple[type[Item], ...]
    check: Callable[[dict, dict], list[str]]
    owns: str  # what this step owns, for the main agent's routing
    builds_on: tuple[str, ...] = ()  # earlier steps shown to the agent in full

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
