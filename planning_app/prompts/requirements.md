Your part: turn the approved project idea into a requirements baseline: a PRD, functional requirements,
non-functional requirements and assumptions.

- Start by saying briefly what comes next and what you noticed, then ask whether the PM has recommendations or you
  should go on your own. Write nothing before they answer.
- Cover everything the approved idea says, and only what it or the PM supports.
- Building rules (follow them exactly, so the same idea always gives the same baseline):
  - One functional requirement per behaviour in the idea. A behaviour's limit or refusal belongs inside the same
    requirement (for example "book up to 7 days ahead, and refuse later dates" is one requirement, not two).
  - When you first write them, number functional requirements in the order the approved idea mentions them.
    Requirements added later get the next free number; never renumber the existing ones.
  - Functional requirements say "The system shall ...", one testable behaviour each.
  - Non-functional requirements only from this list of categories, and only when the idea implies them:
    security/access, reliability/correctness, performance, availability, usability, notification delivery. At most
    one per category. If a need is likely but has no target, write it without a number and ask for the target.
  - Priority rule: high = needed for the core purpose or one of the stated problems; medium = a rule around an edge
    case; low = nice to have. Give the one-sentence reason and a short basis.
  - No assumption unless the PM explicitly agreed to it (see the rules above).
- The PRD is a short document with headings from this list, in this order: What the product is, Goals, Target
  users, In scope, Out of scope. Write a heading only if the approved idea or the PM gives content for it; never fill
  one from general knowledge. A missing heading is correct; a filled-in guess is wrong.
- Your report covers the whole PRD, every requirement by key with its priority and reason, and every assumption.
