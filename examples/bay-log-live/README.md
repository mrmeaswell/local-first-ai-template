# Bay Log + Shop Coach (live demo)

A read-only AI coach inside the real Bay Log app, built on Emile's architecture: **judgment in the prompt, rules in code.**

```
Browser ──► helper.py :8090 ──┬─ /helper/chat ──► Claude (API) ─┐   ⇄ baylog_mcp.py ──► Bay Log API
                              │                    └ on failure ─► Ollama (local model)
                              │                  ──► checks.py (every answer, before the student sees it)
                              └─ everything else ──► Bay Log :8080 (unchanged; panel <script> injected)
```

- **Judgment in the prompt.** `prompts/shop-coach.md` is a Pocket Pedagogy prompt for adult learners: why before how, bridges from what they already know, shame-free, and dialogue over deposit. Every answer follows Hook → Core (the next unfinished step, citing the procedure) → Landing (one question).
- **Rules in code.** `checks.py` tests every draft against what the tools actually returned: ticket IDs, procedure IDs, trouble codes and specs must be in the records; a retrieved procedure must be cited; no shaming words; ends with one question; ≤130 words; never claims to have changed a record. A failed check gets one revision round. The student sees the answer with its checks.
- **Claude for the voice, on-prem as backup.** With an API key, Claude coaches. If the API fails mid-answer, the local model takes over automatically and the panel says so. Without a key, it runs fully local.
- **Read-only by design.** `baylog_mcp.py` has four tools: `get_ticket`, `search_tickets`, `get_board`, `search_kb`. None can write. Sign-offs and stage changes stay with people.
- **Bay Log is not modified.** `helper.py` sits in front of it and injects the panel.
- **Sample data only.** In Claude mode, ticket text is sent to Anthropic's API, so use Bay Log's seed data (three vehicles, fake people). Never point it at production or real student records.

## Setup (inside the box that runs Ollama, as root)

```bash
git clone -b bay-log-helper-demo https://github.com/mrmeaswell/local-first-ai-template /opt/lfat
cd /opt/lfat/examples/bay-log-live && chmod +x setup.sh && ./setup.sh
./setup.sh key        # optional: Claude as the coaching voice (key typed hidden, stored root-only)
```

Then open `http://<box-ip>:8090` and tap **Shop Coach** (bottom right).

| Command | What it does |
|---|---|
| `./setup.sh` | Install or update, start both services, warm the local model |
| `./setup.sh key` | Store an Anthropic API key in `/opt/baylog-demo/secrets.env` (mode 600). `--remove` returns to local only |
| `./setup.sh reset` | Put Bay Log back to its sample data (do this right before presenting) |
| `./setup.sh status` | Health of Bay Log, Claude, the local model, and the coach |
| `./setup.sh stop` | Stop both services |
| `/opt/baylog-demo/venv/bin/python -u evals/run_evals.py` | Rules, tools, tool selection, and end-to-end answers (every check must pass) |

Env overrides: `CLAUDE_MODEL` (claude-sonnet-5), `MODEL` (qwen2.5:7b), `OLLAMA_URL`, `PORT`, `DEMO_DIR`.

## Reaching it from another network

Add a public hostname in the Cloudflare Tunnel dashboard pointing at `http://<box-ip>:8090`, and protect it with a Cloudflare Access policy. Bay Log and the coach share one hostname.

## Files

| File | Role |
|---|---|
| `helper.py` | Reverse proxy, `/helper/chat` (Claude → local fallback, tool loop, checks, one revision), health |
| `checks.py` | The rules: grounded, cites procedure, shame-free, one question, concise, read-only honest |
| `prompts/shop-coach.md` | The judgment: Pocket Pedagogy for adult learners, Hook → Core → Landing |
| `baylog_mcp.py` | Read-only MCP tools over Bay Log's API |
| `static/shop-helper.js` | The panel: open ticket, live lookups, KB pills, check chips, which model answered |
| `evals/run_evals.py` | `rules` (no model), `tools` (no model), `select` (local model), `answer` (end to end, all checks) |
| `DEMO-SCRIPT.md` | A 5-minute presentation run-through with fallbacks |
