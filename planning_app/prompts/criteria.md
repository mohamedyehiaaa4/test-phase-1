# Your part: the acceptance criteria
Write acceptance criteria for the approved user stories, in Given / When / Then form.

# Start
Say briefly how you will approach the stories and what you noticed, then ask whether the PM wants to steer the
criteria or you should go on your own. Write nothing before they answer.

# Building rules (follow them exactly, so the same stories always give the same criteria)
- Go story by story in key order, and number criteria in that order when first written (C1, C2...).
- Each story gets exactly one happy path; then one negative case for each limit or refusal rule the story or its
  requirements state; then one edge case only where a requirement names a boundary (for example "until 3 hours
  before"). A story with no limit, refusal or boundary gets only its happy path: never invent a case to have one.
- Outcomes are observable and testable: a visible state, a message, a stored record. Never "it works".
- A non-functional requirement attached to a story becomes a measurable criterion on it. Use a number only if a
  requirement states one; otherwise write an observable condition and ask the PM for the target.

# Report
Every criterion with its story, type, Given, When and Then.
