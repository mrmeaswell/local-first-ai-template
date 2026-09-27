# Demo 1: The UI talks to an API, and the AI talks through MCP (15 min)
1. Seed the data and create a user: `python api/app.py --seed ../examples/bay-log/seed.sql --add-user "Student A" student`. Copy the token, then start the API with `python api/app.py`.
2. Run `curl -H "Authorization: Bearer $STUDENT" localhost:8080/records/1`. Point out that no model is involved.
3. Run `ZONE_TOKEN=$STUDENT python assistant.py` and ask "What's the status of the Civic, and what procedure applies?" Show the `[tool]` lines and the KB-001 citation.
4. Ask the class why the AI calls the same API instead of querying SQL directly. (Answer: rules live in one place, and access is audited.)
5. Show the audit trail with a lead token: `curl -H "Authorization: Bearer $LEAD" localhost:8080/events`.
