# Demo 2: Reads are free, and writes are gated (15 min)
1. Run `curl -X POST -H 'X-Role: student' localhost:8080/records/2/advance`. It returns **403** because Diagnosis → Approval requires a lead.
2. Repeat with `-H 'X-Role: lead'`. It returns 200, and the move appears in `curl localhost:8080/events`.
3. Restart the assistant with `ZONE_MCP_WRITES=1`. Ask it to add a note, and show that it asks for confirmation first.
4. Run `python evals/run_evals.py` (reseed first). Explain why the negative suite must be 100% before a change can be promoted.
