/* Shop Helper panel for Bay Log.
   Injected by helper.py's proxy; Bay Log's own code is untouched.
   Reads the open ticket from Bay Log's detail panel (.d-id), streams answers from /helper/chat. */
(() => {
  if (window.__shopHelper) return;
  window.__shopHelper = true;

  const css = `
  .sh-fab{position:fixed;right:20px;bottom:20px;z-index:9000;height:56px;padding:0 20px 0 16px;border-radius:28px;
    border:0;background:var(--yellow,#ffac00);color:#151515;font:600 15px/1 system-ui,-apple-system,sans-serif;
    display:flex;align-items:center;gap:10px;cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,.45)}
  .sh-fab:hover{background:#ffbe33}.sh-fab svg{width:22px;height:22px}
  .sh-fab[hidden]{display:none}
  .sh-panel{position:fixed;right:20px;bottom:20px;z-index:9001;width:400px;max-width:calc(100vw - 32px);
    height:min(640px,calc(100vh - 40px));display:flex;flex-direction:column;background:var(--ink-1,#151515);
    color:var(--txt-0,#fff);border:1px solid var(--ink-5,#494949);border-radius:var(--r-macro,20px);
    box-shadow:0 18px 48px rgba(0,0,0,.6);font:14px/1.45 system-ui,-apple-system,sans-serif;overflow:hidden}
  .sh-panel[hidden]{display:none}
  .sh-head{display:flex;align-items:flex-start;gap:12px;padding:16px 16px 12px;border-bottom:1px solid var(--ink-4,#2e2e2e)}
  .sh-title{font-weight:700;font-size:16px}.sh-sub{color:var(--txt-2,#808080);font-size:12px;margin-top:2px}
  .sh-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--txt-3,#616161);margin-right:6px;vertical-align:1px}
  .sh-dot.ok{background:var(--sage,#629b5c)}.sh-dot.warn{background:var(--yellow,#ffac00)}.sh-dot.bad{background:var(--ember,#e84826)}
  .sh-x{margin-left:auto;width:40px;height:40px;border-radius:12px;border:0;background:var(--ink-3,#232323);color:var(--txt-1,#cbcbcb);font-size:20px;cursor:pointer}
  .sh-ctx{margin:12px 16px 0;padding:8px 12px;border-radius:12px;background:var(--ink-3,#232323);color:var(--txt-1,#cbcbcb);font-size:13px}
  .sh-ctx b{color:var(--yellow,#ffac00);font-family:ui-monospace,Menlo,monospace;font-weight:600}
  .sh-log{flex:1;overflow-y:auto;padding:12px 16px;display:flex;flex-direction:column;gap:12px}
  .sh-msg{max-width:92%;padding:10px 12px;border-radius:14px;white-space:pre-wrap;word-wrap:break-word}
  .sh-user{align-self:flex-end;background:var(--ink-4,#2e2e2e)}
  .sh-bot{align-self:flex-start;background:var(--ink-2,#1c1c1c);border:1px solid var(--ink-4,#2e2e2e)}
  .sh-steps{list-style:none;margin:0 0 8px;padding:0;font:12px/1.6 ui-monospace,Menlo,monospace;color:var(--sky,#77afd8)}
  .sh-steps li::before{content:"→ ";color:var(--txt-3,#616161)}
  .sh-status{color:var(--txt-2,#808080);font-size:12px}
  .sh-kb{display:inline-block;padding:0 6px;margin:0 1px;border-radius:6px;background:rgba(255,172,0,.15);color:var(--yellow,#ffac00);font:600 12px/1.6 ui-monospace,Menlo,monospace}
  .sh-meta{margin-top:6px;color:var(--txt-3,#616161);font-size:11px}
  .sh-err{color:var(--ember,#e84826)}
  .sh-chips[hidden]{display:none}.sh-chips{display:flex;flex-wrap:wrap;gap:8px;padding:0 16px 10px}
  .sh-chip{min-height:36px;padding:6px 12px;border-radius:18px;border:1px solid var(--ink-5,#494949);background:transparent;color:var(--txt-1,#cbcbcb);font:13px system-ui,sans-serif;cursor:pointer}
  .sh-chip:hover{border-color:var(--yellow,#ffac00);color:var(--txt-0,#fff)}
  .sh-form{display:flex;gap:8px;padding:12px 16px 16px;border-top:1px solid var(--ink-4,#2e2e2e)}
  .sh-in{flex:1;min-height:48px;max-height:120px;resize:none;padding:12px;border-radius:12px;border:1px solid var(--ink-5,#494949);
    background:var(--ink-3,#232323);color:var(--txt-0,#fff);font:14px/1.4 system-ui,sans-serif}
  .sh-in:focus{outline:2px solid var(--yellow,#ffac00);outline-offset:-1px}
  .sh-send{width:48px;height:48px;border-radius:12px;border:0;background:var(--yellow,#ffac00);color:#151515;font-size:20px;cursor:pointer}
  .sh-send:disabled{opacity:.4;cursor:default}
  .sh-foot{padding:0 16px 10px;color:var(--txt-3,#616161);font-size:11px}
  .sh-shift{right:calc(var(--panel,400px) + 20px)}
  @media (max-width:560px){.sh-panel{right:0;bottom:0;width:100vw;max-width:100vw;height:100vh;border-radius:0}}`;
  const style = document.createElement("style"); style.textContent = css; document.head.appendChild(style);

  const h = (tag, props = {}, kids = []) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "text") e.textContent = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (v !== null && v !== undefined) e.setAttribute(k, v);
    }
    for (const c of [].concat(kids)) if (c) e.append(c);
    return e;
  };
  const icon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z"/></svg>';

  const fab = h("button", { class: "sh-fab", type: "button", "aria-label": "Open Shop Helper" });
  fab.innerHTML = icon + "<span>Shop Helper</span>";
  const sub = h("div", { class: "sh-sub" }, [h("span", { class: "sh-dot" }), document.createTextNode("Checking…")]);
  const ctx = h("div", { class: "sh-ctx" });
  const log = h("div", { class: "sh-log", "aria-live": "polite" });
  const chips = h("div", { class: "sh-chips" });
  const input = h("textarea", { class: "sh-in", rows: "1", placeholder: "Ask about this repair order…", "aria-label": "Message" });
  const send = h("button", { class: "sh-send", type: "submit", "aria-label": "Send", text: "↑" });
  const panel = h("section", { class: "sh-panel", hidden: "", role: "dialog", "aria-label": "Shop Helper" }, [
    h("div", { class: "sh-head" }, [
      h("div", {}, [h("div", { class: "sh-title", text: "Shop Helper" }), sub]),
      h("button", { class: "sh-x", type: "button", "aria-label": "Close", text: "×", onclick: () => toggle(false) })
    ]),
    ctx, log, chips,
    h("form", { class: "sh-form", onsubmit: e => { e.preventDefault(); ask(input.value); } }, [input, send]),
    h("div", { class: "sh-foot", text: "Read-only: it can look things up but can't change tickets. Runs on the shop's own server." })
  ]);
  document.body.append(fab, panel);

  const history = [];
  let busy = false, lastTicket;

  const openTicket = () => {
    const el = document.querySelector(".d-id");
    const t = el && el.textContent.trim();
    return /^T-\d+$/i.test(t || "") ? t.toUpperCase() : null;
  };

  function dock() {
    // Sit beside Bay Log's ticket panel on wide screens, so the ticket stays visible next to the answer.
    const shift = !!document.querySelector(".detail.open") && window.innerWidth >= 1100;
    panel.classList.toggle("sh-shift", shift); fab.classList.toggle("sh-shift", shift);
  }

  function renderContext() {
    dock();
    chips.hidden = log.childElementCount > 0;
    const t = openTicket();
    if (t === lastTicket && chips.childElementCount) return;
    lastTicket = t;
    ctx.replaceChildren(...(t ? [document.createTextNode("Looking at "), h("b", { text: t })]
                              : [document.createTextNode("No repair order open. Pick one on the board, or ask a general question.")]));
    const list = t ? ["What should I check next?", "What's blocking the next stage?", "Explain the trouble code on this ticket"]
                   : ["What's waiting on QC?", "Find the work order for the F-150", "How do I diagnose a no-crank?"];
    chips.replaceChildren(...list.map(q => h("button", { class: "sh-chip", type: "button", text: q, onclick: () => ask(q) })));
  }

  async function health() {
    try {
      const r = await (await fetch("/helper/health")).json();
      const ok = r.baylog === "ok" && r.ollama === "ok";
      const dot = h("span", { class: "sh-dot " + (ok ? (r.model_loaded ? "ok" : "warn") : "bad") });
      const txt = ok ? `${r.model} · on-prem · ${r.model_loaded ? "ready" : "warming up"}`
                     : (r.ollama !== "ok" ? `Model offline (${r.ollama})` : "Bay Log not reachable");
      sub.replaceChildren(dot, document.createTextNode(txt));
    } catch { sub.replaceChildren(h("span", { class: "sh-dot bad" }), document.createTextNode("Helper offline")); }
  }

  function withKB(text) {
    const frag = document.createDocumentFragment();
    text.split(/(KB-\d+)/g).forEach(part =>
      frag.append(/^KB-\d+$/.test(part) ? h("span", { class: "sh-kb", text: part }) : document.createTextNode(part)));
    return frag;
  }

  async function ask(q) {
    q = (q || "").trim();
    if (!q || busy) return;
    busy = true; send.disabled = true; input.value = "";
    log.append(h("div", { class: "sh-msg sh-user", text: q })); chips.hidden = true;
    const steps = h("ul", { class: "sh-steps" });
    const status = h("div", { class: "sh-status", text: "Thinking…" });
    const bot = h("div", { class: "sh-msg sh-bot" }, [steps, status]);
    log.append(bot); log.scrollTop = log.scrollHeight;
    const t0 = Date.now(); let statusText = "Thinking…";
    const timer = setInterval(() => { status.textContent = `${statusText} ${Math.round((Date.now() - t0) / 1000)}s`; }, 1000);
    let answer = "";
    try {
      const res = await fetch("/helper/chat", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: q, ticket_id: openTicket(), history }) });
      if (!res.ok || !res.body) throw new Error("HTTP " + res.status);
      const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
          if (!line) continue;
          const ev = JSON.parse(line);
          if (ev.type === "step") steps.append(h("li", { text: ev.label }));
          else if (ev.type === "status") statusText = ev.text;
          else if (ev.type === "answer") {
            answer = ev.text || "(no answer)";
            status.replaceWith(h("div", {}, [withKB(answer)]));
            bot.append(h("div", { class: "sh-meta", text: `${ev.model} · ${ev.seconds}s · ${steps.childElementCount} lookup${steps.childElementCount === 1 ? "" : "s"}` }));
          } else if (ev.type === "error") status.replaceWith(h("div", { class: "sh-err", text: ev.text }));
          log.scrollTop = log.scrollHeight;
        }
      }
      if (!steps.childElementCount) steps.remove();
      if (answer) history.push({ role: "user", content: q }, { role: "assistant", content: answer });
    } catch (e) {
      status.replaceWith(h("div", { class: "sh-err", text: "Couldn't reach the helper: " + e.message }));
    } finally {
      clearInterval(timer); busy = false; send.disabled = false; input.focus();
    }
  }

  function toggle(open) {
    panel.hidden = !open; fab.hidden = open;
    if (open) { renderContext(); health(); input.focus(); }
  }
  fab.addEventListener("click", () => toggle(true));
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(input.value); }
    if (e.key === "Escape") { e.stopPropagation(); toggle(false); }
  });
  panel.addEventListener("keydown", e => e.stopPropagation());
  window.addEventListener("resize", dock);
  new MutationObserver(() => { dock(); if (!panel.hidden) renderContext(); })
    .observe(document.body, { childList: true, subtree: true });
})();
