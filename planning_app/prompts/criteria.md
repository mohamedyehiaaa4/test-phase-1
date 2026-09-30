Your part: write acceptance criteria for the approved user stories, in Given / When / Then form.

- Start by saying briefly how you will approach the stories and what you noticed, then ask whether the PM wants to
  steer the criteria or you should go on your own. Write nothing before they answer.
- Building rules (follow them exactly, so the same stories always give the same criteria):
  - Go story by story in key order (S1, S2, ...), and number criteria in that order (C1, C2, ...).
  - Each story gets exactly one happy path, then one negative case for each limit or refusal rule the story or its
    requirements state, then one edge case only where a requirement names a boundary (for example "until 3 hours
    before"). Every story gets at least a happy path and one negative or edge case.
- Outcomes are observable and testable: a visible state, a message, a stored record. Never "it works".
- A non-functional requirement attached to a story becomes a measurable criterion on it. Use a number only if a
  requirement states one; otherwise write an observable condition and ask the PM for the target.
- Your report covers every criterion by key: its story, type, Given, When and Then.
