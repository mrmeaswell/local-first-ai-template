# Local-First AI Tool Template

A template for building **on-premises, offline-capable tools with a local AI assistant**. It is designed so faculty can run real-world demonstrations and guide students through building their own "blend zone" projects.

- **Architecture:** [`docs/reference-architecture.md`](docs/reference-architecture.md) (the operating standard)
- **Runnable starter:** [`zone-template/`](zone-template/) has a core API, a read-only `zone-mcp`, and an Ollama assistant
- **Worked example:** [`examples/bay-log/`](examples/bay-log/), an automotive bay work-order tracker (reference instance #1)
- **For faculty:** [`faculty/`](faculty/) has demo scripts, a phased student project path, and rubrics

## Quick start (about 5 minutes)

Requirements: Python 3.10+. [Ollama](https://ollama.com) is optional and only needed for the assistant and the tool-selection evals.

```bash
cd zone-template
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python api/app.py --seed ../examples/bay-log/seed.sql --add-user "Student A" student   # prints a token once
python api/app.py                                     # Core API on :8080
# in a second terminal:
python evals/run_evals.py                             # all suites (own temp DB, never touches zone.db)
ollama pull qwen2.5:7b
ZONE_TOKEN=<token> python assistant.py                # read-only assistant
ZONE_TOKEN=<token> ZONE_MCP_WRITES=1 python assistant.py   # can request plans; you approve at the prompt
```

## Tests
`python evals/run_evals.py` runs every suite and prints one line per test, then `N passed, N failed, N skipped`.

| Suite | What it proves | Needs |
|---|---|---|
| golden | Reads return real data | nothing extra |
| negative | No/invalid/forged identity, role gates, QC gate, bad JSON | nothing extra |
| plans | Confirm tokens: same user only, 5-minute expiry, single use | nothing extra |
| mcp | `request_plan` never returns the token; no confirm tool; token file is 0600 | `mcp` package |
| gate | The human's y/N decides; the model's text never contains the token | nothing extra |
| helper | Undeclared actions, raw commands, and shell metacharacters are rejected | nothing extra |
| tools | The model picks the right tool for 6 prompts | **Ollama** with `MODEL` (default `qwen2.5:7b`); otherwise `SKIPPED` |

A skipped suite is not a pass. Tool-selection evals are the Section 13 promotion gate, so run them against your model before promoting any AI change.

## How it fits together

```
UI / curl ──REST+token──► Core API (api/app.py) ◄──REST── zone-mcp (mcp/zone-mcp/server.py)
                         │                                  ▲ MCP (stdio)
                    SQLite + audit                   assistant.py ── Ollama (local)
```

The UI never calls MCP, and the AI never bypasses the API (Section 3), so business rules live in one place.

## Security model (starter)
- **Identity:** every request needs `Authorization: Bearer <token>`. Tokens are created with `--add-user`, shown once, and stored only as SHA-256 hashes. There are no role headers. Non-human clients use the `service` role and must name a human `--owner`.
- **AI writes:** the model can only call `request_plan`. The API issues a one-time confirm token (5 minutes, same user, single use). `zone-mcp` strips it and hands it to `assistant.py` through `.pending/` (mode 0600). The human answers `Approve? [y/N]`, and only then does the orchestrator confirm. There is no confirm tool.
- **Host actions:** typed kinds in `helper/kinds/` with fixed argument lists and `shell=False`. Anything not declared in `host-actions.yaml` doesn't exist.
- **Limits:** the side channel protects against the model, not against someone with a shell on the box as the same Unix user. For production, run the orchestrator and helper as separate users.

## Status
Draft v0.2 (September 2026). The starter covers Phase 0 and Phase 1 of the roadmap. `control-mcp` and `host-mcp` are stubbed with their contracts, and faculty can use them as later student phases.

## License
All rights reserved. See [LICENSE](LICENSE).
