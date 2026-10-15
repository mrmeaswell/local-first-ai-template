# Bay Log + Shop Helper (live demo)

A read-only AI helper inside the real Bay Log app, running entirely on the shop's own server: no cloud, no GPU required.

```
Browser ──► helper.py :8090 ──┬─ /helper/chat ──► Ollama (local model) ⇄ baylog_mcp.py ──► Bay Log API
                              └─ everything else ──► Bay Log :8080 (unchanged; panel <script> injected)
```

- **Bay Log is not modified.** `helper.py` sits in front of it, serves Bay Log as-is, and adds the Shop Helper panel.
- **Read-only by design.** `baylog_mcp.py` has four tools: `get_ticket`, `search_tickets`, `get_board`, `search_kb`. None of them can write. Advancing stages and sign-offs stay with people on the Bay Log screen.
- **Grounded.** Every fact comes from Bay Log's API. Answers cite knowledge-base procedures (`KB-1`).
- **Coach, not answer key.** The prompt (`prompts/shop-helper.md`) points to the next diagnostic step and ends with a question.
- **Sample data only.** Uses Bay Log's seed data (three vehicles, fake people). Never point it at production.

## Setup (inside the box that runs Ollama, as root)

```bash
git clone -b bay-log-helper-demo https://github.com/mrmeaswell/local-first-ai-template /opt/lfat
cd /opt/lfat/examples/bay-log-live && chmod +x setup.sh && ./setup.sh
```

Then open `http://<box-ip>:8090` and tap **Shop Helper** (bottom right).

| Command | What it does |
|---|---|
| `./setup.sh` | Install or update, start both services, warm the model |
| `./setup.sh reset` | Put Bay Log back to its sample data (do this right before presenting) |
| `./setup.sh status` | Health of Bay Log, the model, and the helper |
| `./setup.sh stop` | Stop both services |
| `/opt/baylog-demo/venv/bin/python -u evals/run_evals.py` | Tool, tool-selection, and end-to-end answer tests |

Env overrides: `MODEL`, `OLLAMA_URL`, `PORT`, `DEMO_DIR`.

## Reaching it from another network

Add a public hostname in the Cloudflare Tunnel dashboard pointing at `http://<box-ip>:8090`, and protect it with a Cloudflare Access policy for your own email. Bay Log and the helper share one hostname, so nothing else is needed.

## Files

| File | Role |
|---|---|
| `helper.py` | Reverse proxy + `/helper/chat` (streams each tool call as it happens) + model warm-up |
| `baylog_mcp.py` | Read-only MCP tools over Bay Log's API |
| `prompts/shop-helper.md` | Behavior: tools for every fact, cite KB, end with a question, read-only |
| `static/shop-helper.js` | The panel: reads the open ticket, suggested questions, live lookups, KB pills |
| `evals/run_evals.py` | `tools` (no model), `select` (model picks the right tool), `answer` (end to end) |
| `DEMO-SCRIPT.md` | A 5-minute presentation run-through with fallbacks |
