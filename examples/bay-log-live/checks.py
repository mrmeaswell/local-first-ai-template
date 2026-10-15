"""Deterministic answer checks for the Shop Coach (Emile's rule: judgment in the prompt, rules in code).

check_answer(answer, evidence, context) -> list of {"name", "pass", "detail"}
  answer   the model's final text
  evidence everything the tools returned this turn (the only source of facts)
  context  the student's message + open ticket ID (IDs the student said are allowed to be repeated)
Pure functions: no network, no model.
"""
import re

BANNED = [r"\bsimply\b", r"\bobviously\b", r"\bas you (?:already )?know\b", r"\bthis is basic\b",
          r"\beasy\b", r"\bclearly\b", r"\beveryone knows\b"]
WRITE_CLAIMS = [r"\bI(?:'ve| have)? (?:advanced|moved|signed off|updated|changed|edited|saved|closed)\b",
                r"\bI (?:went ahead and|will now) (?:advance|move|sign|update|change|edit|save|close)\b"]
TICKET = re.compile(r"\bT-\d{3,6}\b", re.I)
KB = re.compile(r"\bKB-\d+\b", re.I)
DTC = re.compile(r"\b[PBCU][0-9][0-9A-F]{3}\b")
UNIT_NUM = re.compile(r"(\d+(?:\.\d+)?)\s*(mm|in|inch(?:es)?|ft[- ]?lbs?|lb[- ]?ft|nm|n·m|psi|v|volts?|amps?|°f|°c|qt|quarts?|miles?|mi)\b", re.I)
REFUSAL = re.compile(r"\b(?:can(?:no|')t|cannot|not able to|read-only)\b", re.I)
MAX_WORDS = 130


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower())


def check_answer(answer: str, evidence: str, context: str = "") -> list[dict]:
    a, ev, ctx = answer or "", evidence or "", context or ""
    evn = _norm(ev)
    out = []

    def add(name, ok, detail=""):
        out.append({"name": name, "pass": bool(ok), "detail": detail})

    # Grounding: every ticket ID, KB ID, trouble code and number-with-unit must come from tool results
    allowed_ids = {t.upper() for t in TICKET.findall(ev + " " + ctx)}
    bad_ids = sorted({t.upper() for t in TICKET.findall(a)} - allowed_ids)
    bad_kb = sorted({k.upper() for k in KB.findall(a)} - {k.upper() for k in KB.findall(ev)})
    # A sibling code in the same family as a recorded one (P0303 -> "if it moves to P0302") is a coaching
    # hypothetical, not an invented fact; anything else must be in the records.
    known_dtc = set(DTC.findall(ev + " " + ctx))
    bad_dtc = sorted({d for d in DTC.findall(a) if d not in known_dtc and not any(d[:4] == k[:4] for k in known_dtc)})
    bad_nums = sorted({m.group(0) for m in UNIT_NUM.finditer(a)
                       if not re.search(rf"(?<![\d.]){re.escape(m.group(1))}(?![\d])", evn)})
    problems = ([f"ticket {x} not in records" for x in bad_ids] + [f"{x} not retrieved" for x in bad_kb] +
                [f"code {x} not in records" for x in bad_dtc] + [f"'{x}' not in records" for x in bad_nums])
    add("grounded", not problems, "; ".join(problems))

    # If a procedure was retrieved and the answer coaches a step, it must cite one (a plain "I can't do that" needn't)
    if KB.search(ev) and not (REFUSAL.search(a) and not KB.search(a) and len(a.split()) < 60):
        add("cites procedure", bool(KB.search(a)), "" if KB.search(a) else "a procedure was retrieved but not cited (KB-n)")

    hits = [m.group(0) for p in BANNED for m in re.finditer(p, a, re.I)]
    add("shame-free", not hits, ", ".join(f"'{h}'" for h in hits))

    sentences = [s for s in re.split(r"(?<=[.!?])\s+", a.strip()) if s]
    q = a.count("?")
    ends_q = bool(sentences) and sentences[-1].rstrip().endswith("?")
    add("ends with one question", ends_q and q <= 2,
        "" if ends_q and q <= 2 else ("doesn't end with a question" if not ends_q else f"{q} questions; ask one"))

    words = len(re.findall(r"\b\w+\b", a))
    add("concise", words <= MAX_WORDS, "" if words <= MAX_WORDS else f"{words} words (max {MAX_WORDS})")

    claims = [m.group(0) for p in WRITE_CLAIMS for m in re.finditer(p, a, re.I)]
    add("read-only honest", not claims, ", ".join(f"'{c}'" for c in claims))
    return out


def failures(checks: list[dict]) -> list[dict]:
    return [c for c in checks if not c["pass"]]


def repair_instruction(checks: list[dict]) -> str:
    fails = failures(checks)
    return ("Your draft failed these automatic checks. Rewrite it so every check passes, keeping the same coaching intent:\n"
            + "\n".join(f"- {c['name']}: {c['detail']}" for c in fails)
            + "\nUse only facts from the tool results. Reply with the revised answer only.")
