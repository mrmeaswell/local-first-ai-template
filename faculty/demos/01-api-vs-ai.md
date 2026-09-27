# Demo 1: The UI talks to an API, and the AI talks through MCP (15 min)
1. Start the API with the Bay Log seed. Run `curl localhost:8080/records/1`. Point out that no model is involved.
2. Run `python assistant.py` and ask "What's the status of the Civic, and what procedure applies?" Show the `[tool]` lines and the KB-001 citation.
3. Ask the class why the AI calls the same API and doesn't query SQL directly. (Answer: rules live in one place, and access is audited.)
4. Show `curl localhost:8080/events` to reveal the audit trail.
