# UI shell
Calls the Core API directly and never calls MCP. Try it with `curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/records`. Human UI writes use the direct routes (`/records/{id}/notes`, `/records/{id}/advance`) with the same checks; the AI uses plans. The UI stack is an open decision (React or vanilla).
