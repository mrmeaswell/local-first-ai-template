# Emile, local

The Emile curriculum collaborator as a standalone web app for instructors, running on your own server.

Emile's public repo ([mrmeaswell/emile-public](https://github.com/mrmeaswell/emile-public)) is *a music library plus a tuner*: the system prompt, course context, the MSCB story bible, the quiz spec, and deterministic validators. It has no screen and never calls a model. This app adds **the musician and the stage**:

```
Browser ──► app.py ──► at the door:   gate.student_data()  student names, IDs, emails, grades → stopped, nothing sent
                   ──► the musician:  Claude (API) ──── on any failure ───► on-prem model (Ollama)
                   │                     ⇄ Emile's MCP server (stdio): course context, MSCB, quiz spec, validators
                   ──► on the way out: gate.check()  = Emile's own validators.py + 2 rules from its prompt
                   │                     → one revision round if anything fails
                   ──► the instructor sees the deliverable and every check
```

**Judgment in the prompt, rules in code.** The prompt is Emile's own `data/emile-system.md`, loaded from the Emile repo at runtime (one source of truth), plus a short app addendum (`prompts/app-addendum.md`). The rules are Emile's own `validators.py`, the same code its MCP server exposes:

| Check | Source | What it enforces |
|---|---|---|
| no student data (inbound) | `gate.py` | Emails, 9-digit IDs, phone numbers, grades, "student Name", roster rows are stopped **before any model sees them** (FERPA) |
| shame-free | Emile `lint_language` | No "simply", "obviously", "as you know", "this is basic". Quoting the instructor's own draft to critique it is allowed |
| cognitive load | Emile `check_load` | ≤5 new terms per section. Emile bolds each new term on first use; code counts them |
| no pass-rate framing | Emile prompt, Layer 3 | No pass-rate headlines or goals |
| quiz spec | Emile `validate_quiz` | Objective mapped, answer shape, no all/none of the above, double negatives; full packages also get the 35-item and 30/45/25 mix rules |
| no student data (outbound) | `gate.py` | The same detector, on what Emile wrote |

**The musician is replaceable.** With an API key, Claude plays Emile. If the API fails mid-answer, the on-prem model takes over and the page says so. The **On-prem only** switch sends a conversation only to the local model. Without a key, everything is local. The tuner doesn't care who played.

**Instructor-facing only.** Emile drafts; a person publishes. Nothing writes to Canvas. In Claude mode, what you type goes to Anthropic's API, which is why the student-data gate runs first.

## Setup (inside the box that runs Ollama, as root)

```bash
git clone -b emile-local https://github.com/mrmeaswell/local-first-ai-template /opt/lfat-emile
cd /opt/lfat-emile/examples/emile-local && ./setup.sh
./setup.sh key        # optional: Claude plays Emile (key typed hidden, stored root-only)
```

Open `http://<box-ip>:8091`.

| Command | What it does |
|---|---|
| `./setup.sh` | Clone or update Emile, install, start `emile-local.service`, warm the local model |
| `./setup.sh key` | Store an Anthropic API key in `/opt/emile-local/secrets.env` (mode 600); offers to reuse the Bay Log demo's key. `--remove` = local only |
| `./setup.sh status` | Emile's files, Claude, the local model |
| `./setup.sh stop` | Stop the service |

Env overrides: `PORT` (8091), `CLAUDE_MODEL` (claude-sonnet-5), `MODEL` (qwen2.5:7b), `OLLAMA_URL`, `DEMO_DIR`, `EMILE_REPO`.

## Tests

```bash
EMILE_DIR=/opt/emile-local/emile EMILE_PYTHON=/opt/emile-local/emile-venv/bin/python \
  /opt/emile-local/venv/bin/python -u evals/run_evals.py          # add --local for an on-prem end-to-end run
```

`gate` (no model): the door stops student data and lets course content through; the outbound checks catch what they should. `emile` (no model): Emile's server starts and serves its tools. `answer` (end to end): a student-data message is stopped before any model is called, and a module intro, sample quiz items, and a draft review each pass every check.

## Files

| File | Role |
|---|---|
| `app.py` | The web app: door gate, Claude → on-prem fallback, Emile tool loop, outbound checks, one revision |
| `gate.py` | The rules: the student-data detector, plus wrappers around Emile's validators |
| `prompts/app-addendum.md` | How Emile works inside this app (tools, conventions the checks rely on) |
| `static/index.html` | The page: course picker, on-prem switch, starters, rendered deliverables, quiz cards, check chips, Download .md |
| `evals/run_evals.py` | `gate`, `emile`, `answer` suites |
| `DEMO-SCRIPT.md` | A 5-minute presentation run-through |
