# Runbook
- Start: `python api/app.py` (add `--seed` to reset the data)
- Health: `curl /zone`
- Evals: `python evals/run_evals.py`
- Rollback AI change: (Phase 2) `control-mcp.rollback`
