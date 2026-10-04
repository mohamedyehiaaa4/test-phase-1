# Your part: the requirements
Turn the approved project idea into a requirements baseline: a PRD, functional and non-functional requirements, and
assumptions. Cover everything the idea says, and only what it or the PM supports.

# Building rules (follow them exactly, so the same idea always gives the same baseline)
- Functional requirements: "The system shall ...", one per behaviour in the idea. Each is one complete behaviour
  together with all its rules, limits, refusals and immediate results, wherever the idea mentions them: a rule never
  becomes a requirement of its own when it belongs to a behaviour. When first written, number them in the order the
  idea mentions the behaviours.
- Non-functional requirements: only from these categories, only when the idea implies them, at most one per
  category: security/access, reliability/correctness, performance, availability, usability, notification delivery.
  A likely need without a target is written without a number, and you ask for the target.
- Priority: high = needed for the core purpose or a stated problem; medium = a rule around an edge case; low = nice
  to have. Give a one-sentence reason and a short basis.
- The PRD is short, with headings from this list, in this order: What the product is, Goals, Target users, In scope,
  Out of scope. Write a heading only if the idea or the PM gives content for it; a missing heading is correct, a
  filled-in guess is wrong.

# Report
The whole PRD, every requirement with its priority and reason, and every assumption.
