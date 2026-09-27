"""Assistant orchestrator: an MCP client that lets a local Ollama model call zone-mcp tools.

Write approval happens HERE, on stdin, outside the model: when a tool result contains a plan_id,
the human is asked Approve? [y/N]. Only on 'y' does this program read the confirm token from the
side channel and call /plans/{id}/confirm. The token never enters the model's context."""
import asyncio, getpass, json, os, pathlib, sys, httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = pathlib.Path(__file__).resolve().parent
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("MODEL", "qwen2.5:7b")
API = os.environ.get("ZONE_API", "http://127.0.0.1:8080")
PENDING = pathlib.Path(os.environ.get("ZONE_PENDING_DIR", HERE / ".pending"))
SYSTEM = (HERE / "prompts/system.md").read_text()


def human_decides(plan, token, ask=input):
    """Show the plan, ask the human, and confirm via the API only on 'y'. Returns the text the model sees."""
    pid = int(plan["plan_id"]); f = PENDING / str(pid)
    print(f"\n  !! Plan #{pid}: {plan['summary']}")
    approved = ask("  Approve? [y/N] ").strip().lower() == "y"
    try:
        if not approved: return f"Plan #{pid} was NOT approved by the user. Do not retry unless they ask."
        r = httpx.post(f"{API}/plans/{pid}/confirm", json={"confirm_token": f.read_text()},
                       headers={"Authorization": f"Bearer {token}"})
        return f"Plan #{pid} approved by the user. Result: {r.status_code} {r.json()}"
    finally:
        f.unlink(missing_ok=True)


async def main():
    token = os.environ.get("ZONE_TOKEN") or getpass.getpass("sign-in token> ").strip()
    env = {**os.environ, "ZONE_TOKEN": token, "ZONE_PENDING_DIR": str(PENDING)}
    params = StdioServerParameters(command=sys.executable, args=[str(HERE / "mcp/zone-mcp/server.py")], env=env)
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        tools = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.inputSchema}}
                 for t in (await s.list_tools()).tools]
        msgs = [{"role": "system", "content": SYSTEM}]
        print(f"Assistant ready ({MODEL}, tools: {', '.join(t['function']['name'] for t in tools)}). Ctrl-C to quit.")
        while True:
            msgs.append({"role": "user", "content": input("\nyou> ")})
            for _ in range(5):
                res = httpx.post(f"{OLLAMA}/api/chat", json={"model": MODEL, "messages": msgs, "tools": tools, "stream": False,
                                  "options": {"temperature": 0.2}}, timeout=300).json()["message"]
                msgs.append(res)
                if not res.get("tool_calls"): print("ai>", res["content"]); break
                for call in res["tool_calls"]:
                    f = call["function"]; print(f"  [tool] {f['name']}({f['arguments']})")
                    out = await s.call_tool(f["name"], f["arguments"])
                    text = "".join(getattr(c, "text", "") for c in out.content)
                    try: data = json.loads(text)
                    except ValueError: data = None
                    if isinstance(data, dict) and "plan_id" in data:
                        text = human_decides(data, token)
                    msgs.append({"role": "tool", "content": text})

if __name__ == "__main__":
    try: asyncio.run(main())
    except (KeyboardInterrupt, EOFError): pass
