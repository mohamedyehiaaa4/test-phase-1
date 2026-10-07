"""The shape of every item the planning steps write (summary, requirement, story, criterion).

A draft is plain JSON: {slot: item} for a single item, {slot: [items]} for a list. It has the same shape that
save_step / load_step use in the database. A field marked ref("stories") must hold keys of items in that slot,
either in this draft or in an approved earlier step.
"""
from typing import ClassVar, Literal

from pydantic import BaseModel, Field

Priority = Literal["high", "medium", "low"]


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
    body: str = Field(min_length=1, description="Under the headings from your instructions")


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
    points: float | None = Field(default=None, ge=0, description="Your proposed size")
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
