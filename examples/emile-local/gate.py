"""Rules in code for Emile, local.

Two gates around the model:
  inbound   student_data(text)  runs on what the instructor typed BEFORE anything is sent to any model.
                                 Emile is instructor-facing only (FERPA): names+grades, emails, student IDs stop here.
  outbound  check(answer)       runs on every draft BEFORE the instructor sees it, using Emile's own
                                 validators.py (the same code its MCP server exposes) plus two rules from
                                 the system prompt that have a right answer.

Pure functions: no network, no model. `validators` is imported from the Emile repo (EMILE_DIR).
"""
import json
import os
import re
import sys
from pathlib import Path

EMILE_DIR = Path(os.environ.get("EMILE_DIR", Path(__file__).resolve().parent / "emile")).resolve()
sys.path.insert(0, str(EMILE_DIR))
import validators  # noqa: E402  (Emile's own deterministic checks)

# ---------------------------------------------------------------- inbound: the data boundary
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
STUDENT_ID = re.compile(r"(?<![\d-])\d{9}(?![\d-])")  # ctcLink-style 9-digit ID
PHONE = re.compile(r"(?<!\d)(?:\(\d{3}\)\s?|\d{3}[-.\s])\d{3}[-.\s]\d{4}(?!\d)")
GRADE = re.compile(r"\b(?:grade[sd]?|scored?|got|earned|failed|gpa)\b[^.\n]{0,25}?\b\d{1,3}(?:\.\d+)?\s*(?:%|/\s*\d+|points?\b)", re.I)
NAMED = re.compile(r"\b(?i:student|learner)\s*(?:name)?\s*[:\-]?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b")
ROSTER = re.compile(r"^\s*[A-Z][a-z]+,?\s+[A-Z][a-z]+\s*[,\t|]\s*\d", re.M)  # "Doe, Jane, 87" rows
# Placeholder students from the MSCB scenario, and generic roles, are fine.
OK_NAMES = {"Student A", "Student B", "Student C"}


def student_data(text: str) -> list[str]:
    """What looks like student-identifying data. Empty list = OK to send to a model."""
    t = text or ""
    found = []
    if EMAIL.search(t): found.append("an email address")
    if STUDENT_ID.search(t): found.append("a 9-digit student ID")
    if PHONE.search(t): found.append("a phone number")
    if GRADE.search(t): found.append("a grade or score")
    named = [m.group(0) for m in NAMED.finditer(t) if not any(ok in m.group(0) for ok in OK_NAMES)]
    if named: found.append("a student's name")
    if ROSTER.search(t): found.append("roster-style rows")
    return found


# ---------------------------------------------------------------- outbound: checks on every draft
PASS_RATE = re.compile(r"\bpass(?:ing)?[- ]rates?\b|\b\d{1,3}\s*%\s+(?:of\s+(?:students|learners)\s+)?pass(?:ed|ing)?\b", re.I)
ALL_NONE = re.compile(r"\b(?:all|none) of the above\b", re.I)
BOLD = re.compile(r"\*\*([^*\n]{2,60}?)\*\*")
JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)
QUIZ_TOTAL = sum(validators.TYPES.values())


def new_terms(answer: str) -> list[str]:
    """Emile bolds each new technical term the first time it appears (prompt convention)."""
    terms = []
    for t in BOLD.findall(answer or ""):
        t = t.strip().rstrip(":.")
        if t and len(t.split()) <= 5 and not t.endswith("?") and t.lower() not in {x.lower() for x in terms}:
            terms.append(t)
    return terms


def _quiz(answer: str):
    for block in JSON_BLOCK.findall(answer or ""):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("questions"), list):
            return block, len(data["questions"])
    return None, 0


QUOTED = re.compile(r'"([^"\n]{1,200})"|\u201c([^\u201d\n]{1,200})\u201d')


def _unquote_instructor(answer: str, source: str) -> str:
    """Blank out quoted phrases that come from the instructor's own message, so Emile can quote a draft
    to critique it ("'Simply' tells a stuck learner...") without failing the lint. Quotes of anything
    else stay checked."""
    src = re.sub(r"\s+", " ", (source or "").lower())
    def blank(m):
        q = (m.group(1) or m.group(2) or "").strip().lower()
        return " " if q and re.sub(r"\s+", " ", q).strip(".,!? ") in src else m.group(0)
    return QUOTED.sub(blank, answer) if src else answer


HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.M)


def check(answer: str, source: str = "", required: list[str] | None = None, mode_name: str = "") -> list[dict]:
    """source: the instructor's message this answers (quotes from it are exempt from the language lint).
    required: section headings an add-on mode demands (checked only when the answer is a deliverable,
    i.e. has headings; a short clarifying reply is left alone)."""
    a = answer or ""
    out = []

    def add(name, ok, detail=""):
        out.append({"name": name, "pass": bool(ok), "detail": detail})

    lint = validators.lint_language(_unquote_instructor(a, source))
    add("shame-free", lint["pass"], ", ".join(f"'{h['phrase']}' (line {h['line']})" for h in lint["hits"]))

    terms = new_terms(a)
    load = validators.check_load(a, terms)
    over = [f"'{s['heading']}' introduces {s['count']} new terms ({', '.join(s['terms'])})" for s in load["segments"] if s["over"]]
    add("cognitive load", load["pass"], "; ".join(over) + (f"; split it or defer some (max {load['max']} per section)" if over else ""))

    hits = PASS_RATE.findall(a)
    add("no pass-rate framing", not hits, ", ".join(f"'{h}'" for h in hits))

    block, n = _quiz(a)
    if block:
        res = validators.validate_quiz(block)
        issues = res["issues"]
        partial = n < QUIZ_TOTAL
        if partial:  # a sample set: item rules still apply, package counts and mix don't
            issues = [i for i in issues if re.match(r"Q\d+:", i)]
        add("quiz spec" + (f" ({n} sample items)" if partial else ""), not issues, "; ".join(issues[:6]))
    elif ALL_NONE.search(a):
        add("quiz spec", False, "uses all/none of the above")

    leaked = student_data(a)
    add("no student data", not leaked, ", ".join(leaked))

    heads = [h.lower() for h in HEADING.findall(a)]
    if required and heads:
        missing = [r for r in required if not any(r.lower() in h for h in heads)]
        add(f"{mode_name or 'package'} complete", not missing, ("missing sections: " + ", ".join(missing)) if missing else "")
    return out


def failures(checks: list[dict]) -> list[dict]:
    return [c for c in checks if not c["pass"]]


def repair_instruction(checks: list[dict]) -> str:
    return ("Your draft failed these automatic checks (Emile's validators). Revise it so every check passes, "
            "keeping the same pedagogical intent and structure:\n"
            + "\n".join(f"- {c['name']}: {c['detail']}" for c in failures(checks))
            + "\nReply with the full revised deliverable only.")
