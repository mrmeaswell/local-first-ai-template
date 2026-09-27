# Local-First AI Tool Template

A template for building **on-premises, offline-capable tools with a local AI assistant**. It is designed so faculty can run real-world demonstrations and guide students through building their own "blend zone" projects.

- **Architecture:** [`docs/reference-architecture.md`](docs/reference-architecture.md) (the operating standard)
- **Runnable starter:** [`zone-template/`](zone-template/) has a core API, a read-only `zone-mcp`, and an Ollama assistant
- **Worked example:** [`examples/bay-log/`](examples/bay-log/), an automotive bay work-order tracker (reference instance #1)
- **For faculty:** [`faculty/`](faculty/) has demo scripts, a phased student project path, and rubrics

## Quick start (about 5 minutes)

Requirements: Python 3.10+. [Ollama](https://ollama.com) is optional and only needed for the assistant.

```bash
cd zone-template
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python api/app.py --seed ../examples/bay-log/seed.sql   # Core API on :8080
# in a second terminal:
python evals/run_evals.py                             # API rule checks (own temp DB)
python evals/test_confirmation_gate.py                # human-approval gate checks
ollama pull qwen2.5:7b && python assistant.py         # sign in with student-demo-token
```

## How it fits together

```
UI / curl ──REST──► Core API (api/app.py) ◄──REST── zone-mcp (mcp/zone-mcp/server.py)
                         │                                  ▲ MCP (stdio)
                    SQLite + audit                   assistant.py ── Ollama (local)
```

The UI never calls MCP, and the AI never bypasses the API (Section 3), so business rules live in one place.

## Security model (starter)
- **Identity:** writes require `Authorization: Bearer <token>` mapped to a role in `users`. Claimed role headers are ignored. The seed tokens are demo-only; use hashed PINs or SSO for real deployments.
- **Writes:** off by default. When enabled, the assistant program asks the human `Approve? [y/N]` before any write tool runs. The model has no way to approve its own writes.
- **Evals:** they run against a throwaway, freshly seeded database.
- **Not yet covered:** the evals check the API's rules, not whether the model picks the right tool. Model tool-selection evals (the Section 13 promotion gate) are a Phase 1 student deliverable.

## Status
Draft v0.2 (September 2026). The starter covers Phase 0 and Phase 1 of the roadmap. `control-mcp` and `host-mcp` are stubbed with their contracts, and faculty can use them as later student phases.

## License
All rights reserved. See [LICENSE](LICENSE).
