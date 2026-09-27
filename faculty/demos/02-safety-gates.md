# Demo 2: Reads are free, and writes are gated (15 min)
1. **Faked roles don't work.** Run `curl -X POST -H 'X-Role: admin' localhost:8080/records/2/advance`. It returns **401** because the API ignores claimed roles and only trusts sign-in tokens.
2. **Real roles are enforced.** Run `curl -X POST -H 'Authorization: Bearer student-demo-token' localhost:8080/records/2/advance`. It returns **403** because Approval requires a lead.
3. Repeat step 2 with `lead-demo-token`. It returns 200, and the move appears in `curl localhost:8080/events` under the lead's name.
4. **The AI can't approve itself.** Start `ZONE_MCP_WRITES=1 python assistant.py`, sign in with the student token, and ask it to add a note. The assistant program (not the model) stops and asks `Approve? [y/N]`. Answer `n` and show that nothing changed.
5. Run `python evals/run_evals.py` and `python evals/test_confirmation_gate.py`. The evals use their own throwaway database, so they never touch the class data.

Discussion: why is a `confirmed=true` flag that the model fills in no protection against prompt injection?
