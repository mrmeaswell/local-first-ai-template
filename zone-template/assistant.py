"""Assistant orchestrator: an MCP client that lets a local Ollama model call zone-mcp tools."""
import asyncio, json, os, sys, httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("MODEL", "qwen2.5:7b")
WRITE_TOOLS = {"add_note", "advance_stage"}  # must match zone-mcp
SYSTEM = open(os.path.join(os.path.dirname(__file__), "prompts/system.md")).read()

def human_approves(name, args):
    """Human-in-the-loop gate. Runs in the client, outside the model's control."""
    print(f"\n  !! The assistant wants to run WRITE tool {name} with {json.dumps(args)}")
    return input("  Approve? [y/N] ").strip().lower() == "y"

async def main():
    token = os.environ.get("ZONE_TOKEN") or input("sign-in token> ").strip()
    os.environ["ZONE_TOKEN"] = token  # the assistant acts as the signed-in user, never a fixed role
    params = StdioServerParameters(command=sys.executable, args=[os.path.join(os.path.dirname(__file__), "mcp/zone-mcp/server.py")], env=dict(os.environ))
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        tools = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.inputSchema}}
                 for t in (await s.list_tools()).tools]
        msgs = [{"role": "system", "content": SYSTEM}]
        print(f"Assistant ready ({MODEL}, {len(tools)} tools). Ctrl-C to quit.")
        while True:
            msgs.append({"role": "user", "content": input("\nyou> ")})
            for _ in range(5):
                res = httpx.post(f"{OLLAMA}/api/chat", json={"model": MODEL, "messages": msgs, "tools": tools, "stream": False,
                                  "options": {"temperature": 0.2}}, timeout=300).json()["message"]
                msgs.append(res)
                if not res.get("tool_calls"): print("ai>", res["content"]); break
                for call in res["tool_calls"]:
                    f = call["function"]; print(f"  [tool] {f['name']}({f['arguments']})")
                    if f["name"] in WRITE_TOOLS and not human_approves(f["name"], f["arguments"]):
                        msgs.append({"role": "tool", "content": "DENIED: the user did not approve this write. Do not retry it unless the user asks."})
                        continue
                    out = await s.call_tool(f["name"], f["arguments"])
                    msgs.append({"role": "tool", "content": "".join(getattr(c, "text", "") for c in out.content)})

if __name__ == "__main__":
    try: asyncio.run(main())
    except (KeyboardInterrupt, EOFError): pass
