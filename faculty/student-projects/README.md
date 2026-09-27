# Student Project Path: build your own zone
Teams pick a real workflow (a campus help desk, lab equipment checkout, a food bank intake, a garden plot log...).

| Phase | Student deliverable | Gate (evidence) |
|---|---|---|
| 0 | `zone.yaml` + `schema/002_zone.sql` + seed data | API runs; `curl /records` returns their data |
| 1 | Read-only `zone-mcp` tools with clear descriptions | 5+ golden evals pass; assistant cites real IDs |
| 2 | Prompt and role config, with a written rationale | Before/after eval comparison |
| 3 | Write tools with confirmation and role gates | Negative suite 100% |
| 4 | (Advanced) one allowlisted host action with rollback | Lockout test: the helper reverts |
| 5 | Retrieval upgrade (embeddings) | Grounding evals: no invented IDs |
| Final | `MODEL_CARD.md` + `RUNBOOK.md` + a 5-min demo | Rubric |

Weekly check-in prompts: What did you verify live? What is still an assumption? What would break if the internet went down?
