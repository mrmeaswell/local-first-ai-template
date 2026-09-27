# Runbook
- Reset data: `python api/app.py --seed ../examples/bay-log/seed.sql`
- Add a user: `python api/app.py --add-user NAME ROLE` (token printed once). Service users: `--add-user NAME service --owner HUMAN`
- Start: `python api/app.py`
- Health: `curl -H "Authorization: Bearer $TOKEN" localhost:8080/whoami`
- Evals: `python evals/run_evals.py` (isolated; never touches zone.db)
- Pending plans: `curl -H "Authorization: Bearer $TOKEN" localhost:8080/plans/<id>`
- Rollback AI change: (Phase 2) `control-mcp.rollback`
