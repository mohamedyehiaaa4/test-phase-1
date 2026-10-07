"""When a step's draft is complete: (draft, approved drafts of earlier steps) -> problems."""


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
