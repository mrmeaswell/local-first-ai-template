# Local-First AI Tool Template — Reference Architecture
**Scope:** A reusable template for on-premises, AI-assisted tools (blend zones). **Bay Log is reference instance #1.**
**Owner:** Ren Tarvin · Blended Knowledge / RTC CNT
**Status:** Draft v0.2 — September 2026 (supersedes v0.1 "Standardized LLM Reference Architecture")
**Hardware baseline:** any Linux host or hypervisor; an optional GPU node running Ollama (e.g. a 16–24 GB card with ROCm or CUDA); optional Cloudflare Tunnel + Access

---

## 0. What this template is

This is a template for building a **tool that runs on premises, works without the internet, has a local AI assistant, and can make controlled adjustments** at three levels:

| Level | What gets adjusted | Example (Bay Log) |
|---|---|---|
| **A. AI layer** | Models, fine-tuned adapters, prompts, settings | Swap to the new `extract` adapter; roll back if QC evals drop |
| **B. Records** | Business data, edited offline, synced later | Advance a work order to QC while the Wi-Fi is down |
| **C. Host / equipment** | The machine it runs on, or connected devices | Restart a service, set a kiosk display, read a scan tool |

> **Analogy:** The template is a franchise kit. Every shop (blend zone) gets the same building, electrical, point-of-sale system, and safety code. Each shop brings its own menu (workflow, schema, tools, prompts). Bay Log is the flagship store that proves the kit works.

The handbook's 15 pages remain the **glossary** (see Section 12). This doc is the **operating standard**.

---

## 1. Design principles

1. **Local-first.** Everything works on the LAN with the internet unplugged. Cloud is an optional add-on, never a dependency.
2. **Config over code.** A new blend zone is mostly a `zone.yaml` plus a schema, not a fork.
3. **The UI talks to an API, and the AI talks through MCP.** Humans don't queue at the parts counter; the visiting specialist does (Section 3).
4. **Tools over training.** Facts live in the database and the retrieval index. Weights only shape behavior.
5. **Reads are free, writes are gated, and host changes are fenced.** Three escalating trust levels, one for each adjustment level.
6. **Every change is versioned and reversible.** Models, prompts, config, records, and host actions all go through plan → apply → verify → rollback.
7. **Deterministic checks first, LLM judgment second** (the LEON eval philosophy).
8. **Student and customer data never leaves the box by default.**

---

## 2. Template architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  UI SHELL  (mobile-first, POS-style — from blend-zones template)  │
│   Workflow screens · Assistant panel · Admin Control Panel         │
└──────┬───────────────────────────┬──────────────────────────────┘
       │ REST/JSON                 │ assistant chat
┌──────▼───────────────┐   ┌───────▼──────────────────────────────┐
│  CORE API            │   │  ASSISTANT ORCHESTRATOR (MCP client)  │
│  auth · workflow     │   │  role-based model calls via gateway   │
│  engine · sync ·     │   └──┬──────────────┬──────────────┬─────┘
│  audit               │      │ MCP          │ MCP          │ MCP
└──────┬───────────────┘ ┌────▼─────┐  ┌─────▼─────┐  ┌─────▼──────┐
       │                 │ <zone>-  │  │ control-  │  │ host-mcp   │
       │                 │ mcp      │  │ mcp       │  │ (fenced)   │
       │                 │ records  │  │ AI layer  │  │ allowlist  │
       │                 └────┬─────┘  └─────┬─────┘  └─────┬──────┘
┌──────▼──────────────────────▼──────┐ ┌─────▼──────┐ ┌─────▼──────┐
│ DATA: SQLite (default) | Postgres  │ │ MODEL      │ │ PRIVILEGED │
│ event log/outbox · retrieval index │ │ RUNTIME    │ │ HELPER     │
│ file store (photos)                │ │ Ollama +   │ │ (root svc, │
└────────────────────────────────────┘ │ gateway    │ │ tiny API)  │
                                       └────────────┘ └────────────┘
            ── OBSERVABILITY: traces · audit · eval runner ──
```

**Three MCP servers, three trust levels.** Every zone gets the same `control-mcp` and `host-mcp`; only `<zone>-mcp` is custom.

| Server | Adjusts | Trust | Who can invoke |
|---|---|---|---|
| `<zone>-mcp` | B. Records | Reads open; writes need confirmation | Assistant on behalf of a signed-in user |
| `control-mcp` | A. AI layer | Admin role; every change auto-snapshots | Admin, from the Control Panel or assistant |
| `host-mcp` | C. Host/equipment | Allowlist only, plan/apply, rollback declared per action kind | Admin only; never on a student's behalf |

---

## 3. UI ↔ API ↔ MCP

- **The UI never calls MCP.** It calls the Core API directly. That's faster, easier to debug, and needs no model in the loop.
- **The assistant panel is an MCP client.** When a user asks "what's left on this ticket?", the orchestrator calls `<zone>-mcp` tools, and those tools call the *same* Core API. Business rules live in one place, and the AI can't bypass them.
- **Pitfall to avoid:** duplicating workflow rules inside MCP tools. Tools should be thin wrappers over the API, or the AI path and the UI path drift apart.

> **Analogy:** The Core API is the shop's rulebook. The front desk (UI) and the phone-in specialist (assistant) both follow the same rulebook. You don't write a second rulebook for phone calls.

---

## 4. Level A — AI layer adjustments (`control-mcp` + Control Panel)

**What admins can adjust locally**
- Model per **role** (`extract`, `tutor`, `summarize`, `embed`) from the local model list
- Fine-tuned adapter per role (load, A/B test, promote, roll back)
- Prompt templates and tool descriptions (versioned)
- Sampling: temperature, max tokens, stop sequences (handbook p.9)
- Retrieval: top-k, reranker on/off, chunk index rebuild

**How changes are made safe**
1. All AI config lives in versioned files: `config/ai/roles.yaml` and `prompts/*.md`, committed to a local git repo on the box.
2. Every change goes **draft → eval → promote**. The Control Panel runs the zone's golden set against the draft before the Promote button unlocks.
3. Promotion creates a snapshot tag, and rollback is one click back to the previous tag.
4. Pinned identifiers only. Never `latest`.

> **Analogy:** This works like a switch's running-config vs. startup-config. You edit the candidate, test it, then commit, and you always keep the last known good.

---

## 5. Level B — Records, offline edits, and sync

**Default (Profile A — single on-prem node):** one SQLite database in WAL mode, a single writer (the Core API), and every device on the LAN hits that one API. This is simple and correct.

**Offline devices (Profile B — multiple workstations/tablets that may lose the LAN):**
- Each device keeps a local copy plus an **outbox**, an append-only event log such as `stage_advanced`, `note_added`, `photo_attached`.
- On reconnect, the hub replays events in order. Record state is derived from events, not overwritten.
- **Conflict policy, set per field in `zone.yaml`:**
  - Workflow stage transitions are **hub-authoritative**. If two devices advance the same ticket, the first valid transition wins and the second becomes a flagged conflict for a human.
  - Notes and photos are **append-only**, so they never conflict.
  - Simple fields (mileage, customer phone) are **last-writer-wins with audit**.
- At this profile the hub moves to **Postgres**. SQLite is not a multi-writer database.

> **Analogy:** The outbox works like carbon-copy work order slips. Each bay writes on its own pad. At end of shift the slips go to the front office in time order, and the office manager resolves any two slips that disagree. Nobody erases anyone else's slip.

---

## 6. Level C — Host and equipment adjustments (`host-mcp`)

This is the highest-risk layer, so it is fenced hard.

**Architecture**
- `host-mcp` runs **unprivileged**. It forwards requests to a separate **privileged helper**, a tiny root-level service with a fixed set of actions and no shell passthrough.
- Actions are **declared in `host-actions.yaml`**, and anything not declared does not exist:
  ```yaml
  - id: restart_app_service
    kind: systemd_restart
    target: baylog-api.service
    risk: low
  - id: set_kiosk_brightness
    kind: script
    script: scripts/kiosk_brightness.sh
    params: { level: { type: integer, min: 10, max: 100 } }
    risk: low
  - id: rotate_logs
    kind: script
    script: scripts/rotate.sh
    risk: low
  - id: read_scan_tool_dtc
    kind: device_read
    device: obd_adapter
    risk: medium   # read-only
  ```
- **Plan → apply → verify, and rollback semantics are declared per action kind.** Every action shows a plan, which is a dry run with the exact change. Apply is followed by a health check. Each kind in `helper/kinds/` declares a `rollback_mode`:
  - `auto_revert`: if verification fails or the admin doesn't confirm within N minutes, the helper reverts the change (e.g. `systemd_restart`).
  - `ttl_flag`: **create** actions get an expiry flag for a human to review. They are never auto-destroyed.
  - `none`: only for read-only or trivially safe actions.
- **Destroy actions are not allowed in v1.**
- Actions are typed: `host-actions.yaml` names a `kind`, never a raw command. Kinds run fixed argument lists with `shell=False`.

> **Analogy:** This is Junos `commit confirmed`, or Cisco's `reload in 10` before a risky ACL change. If you lock yourself out, the box undoes it for you. You're learning Terraform, and it's the same plan/apply discipline.

**Hard rules**
- No arbitrary shell commands, package installs, firewall rules, or user management through the AI. Those go through Ansible or Terraform, run by a human.
- **Equipment writes are off in the template.** Anything that writes to a vehicle or connected device (clearing codes, module programming) requires a zone-specific safety review and is never AI-initiated.
- The assistant can **propose** a host action, but only an admin can approve it, in the UI.
- Every host action is audited: who, what, plan, result, and rollback status.

---

## 7. Local model runtime & gateway

- **Runtime:** Ollama on the local box. On a virtualization cluster, a dedicated GPU node can serve models for every zone. A standalone shop mini-PC runs its own small model.
- **Gateway:** a thin OpenAI-compatible proxy inside the stack that maps roles to pinned models and adapters, enforces timeouts (lesson from a past deployment: explicit abort, never hang the UI), and emits traces.
- **Offline default:** no frontier-model calls. An optional `remote` role can be enabled per zone when policy allows and the internet is up, and the tool must degrade gracefully without it.
- **Hardware tiers** (the template states minimums; each zone picks one):

| Tier | Box | Realistic local roles |
|---|---|---|
| T1 | CPU-only mini-PC | Embeddings plus a small 1–4B model for extract/classify |
| T2 | 16–24 GB GPU (e.g., a dedicated GPU node) | 7–14B models, QLoRA training on the same box |
| T3 | Cluster-served | Multiple zones share one GPU node through the gateway |

---

## 8. Retrieval standard

1. Chunk by **procedure or document unit**, not character count, and attach metadata.
2. **Hybrid search.** Keyword plus vector, because codes and part numbers break pure vector search.
3. **Rerank**, then pass the top ~5 chunks to the model.
4. **Cite chunk IDs** in every answer, and have the UI show the source.
5. **Negative-control chunks** that must never be retrieved (LEON `cl05` pattern), tested in evals.

The storage backend is SQLite with a vector extension in Profile A, and Postgres with pgvector in Profile B.

---

## 9. Fine-tuning standard (per zone, optional)

> **Analogy:** RAG is the service manual on the bench. Fine-tuning is the apprenticeship. Train habits, never torque specs.

**Decision ladder** (climb in order): prompt → few-shot → retrieval → tool redesign → **fine-tune**. Fine-tune only for *behavioral* failures:
- Local model won't reliably emit valid tool calls or JSON (LEON's compliance issue)
- High-volume narrow classification (Bay Log: symptom → subsystem → procedure ID)
- Domain vocabulary the base model mangles

**Method:** QLoRA on a T2 box. 7–8B is comfortable on 24 GB and 14B is tight. Validate the ROCm training stack with a toy run first. Export the adapter to GGUF, load it with Ollama's `ADAPTER` directive, and register it as a draft in `control-mcp` so it goes through the same draft → eval → promote flow.

**Data:** records the zone already verifies. For Bay Log, that's QC-verified closed tickets. De-identify them, version datasets with the LEON naming convention, and hold out 15–20% for evals. Start with 300–500 high-quality pairs.

**Promotion checklist**
- [ ] Beats base model plus best prompt on the holdout
- [ ] No regression on safety negatives or general behavior
- [ ] MODEL_CARD updated (base, dataset version, hyperparameters, results)
- [ ] Previous adapter kept as the rollback tag

**Governance:** resolve the IP question (Blended Knowledge vs. RTC) before training on institution-generated data.

---

## 10. Identity & security (local-first)

| Context | Identity source | Notes |
|---|---|---|
| On the LAN | Local accounts: badge/PIN for floor staff, password + TOTP for admins | Must work offline |
| Remote | Cloudflare Access JWT (Bay Log's `access-identity` branch) mapped to the same local roles | Optional profile |
| Canvas | LTI 1.3 launch mapped to the same roles | Optional profile |

- Roles: `viewer`, `operator` (student/tech), `lead` (instructor), and `admin` (CNT).
- The AI acts **as the signed-in user**, with no elevated service identity for records.
- Retrieved text, notes, and photo captions are **untrusted**. They can never trigger a write or host action without human confirmation (prompt-injection defense).
- Secrets live in a local env/secret file with root-only permissions, never in prompts, the repo, or tool descriptions.

---

## 11. Template repo layout (extends `blend-zones`)

```
blend-zone-template/
  zone.yaml                 # name, workflow stages, roles, conflict policy, profile
  schema/                   # SQL migrations (zone-specific tables + standard core tables)
  ui/                       # app shell (React or vanilla), assistant panel, control panel
  api/                      # core API: auth, workflow engine, sync, audit
  mcp/
    zone-mcp/               # zone tools (thin wrappers over api/)
    control-mcp/            # standard — do not fork
    host-mcp/               # standard — do not fork
  helper/                   # privileged helper + host-actions.yaml
    kinds/                  # typed action kinds: plan/apply/status/rollback + rollback_mode
  config/ai/roles.yaml      # role → pinned model/adapter
  prompts/                  # versioned templates, tool descriptions
  retrieval/                # chunker config, index build scripts
  evals/
    golden.jsonl
    negative.jsonl
  finetune/                 # dataset builders, training configs (optional)
  deploy/
    profile-a-single/       # LXC/compose for one on-prem node
    profile-b-multi/        # hub + Postgres + device sync
    profile-c-remote/       # Cloudflare Tunnel/Access add-on
  MODEL_CARD.md
  RUNBOOK.md
```

**Standard core tables (every zone):** `users` (hashed bearer tokens; `owner` for service users), `roles`, `events` (outbox and audit), `attachments`, `config_versions`, `host_action_log`, `plans` (AI-requested changes awaiting a human confirm token).

**Standard roles:** each zone lists its own, plus the standard **`service`** role for non-human clients (kiosks, Shortcuts, scripts). A service user must have a human `owner`, and audit lines record both.

**Write path for the AI:** the model calls `request_plan` → the API stores the plan and issues a one-time confirm token (SHA-256 stored, 5-minute expiry, same actor only) → `zone-mcp` strips the token and hands it to the orchestrator through a side channel → the human approves at the prompt → the orchestrator confirms. There is no confirm tool in MCP.

**Creating a new zone:** copy the template → edit `zone.yaml` and `schema/` → write `zone-mcp` tools → seed the retrieval corpus → write the golden set → deploy a profile.

### Bay Log as reference instance
| Template slot | Bay Log value |
|---|---|
| `zone.yaml` stages | Intake → Diagnosis → Approval → Repair → QC → Pickup |
| Zone tables | work_orders, vehicles, parts_catalog, repair_kb |
| `zone-mcp` tools | `get_work_order`, `search_work_orders`, `search_repair_kb`, `lookup_part`, `add_note`, `advance_stage` (confirmation required) |
| Host actions | Restart app service, kiosk display, log rotation, read-only scan tool |
| Fine-tune candidate | `extract`: symptom → subsystem → procedure ID |
| Profile | A now (single node); B if bay tablets need offline edits |

---

## 12. Handbook → template mapping

| Pages | Used in | Notes |
|---|---|---|
| 1–2 | Glossary | Model and context-limit tables are stale; ignore the numbers |
| 3, 14 | Section 8 (retrieval) | Vendor tables are stale; the concepts still hold |
| 4–6 | Background | p.4 diagrams conflict (post- vs. pre-norm); GQA and MoE are missing |
| 7 | Context budgeting | "Llama 3: 70K tokens" is wrong (70B is the parameter count) |
| 9 | Section 4 sampling controls | Low temperature for `extract` |
| 11 | Section 13 evals | Keep the dimensions; drop BLEU/ROUGE for this use |
| 12 | Prompts and tool descriptions | Useful |
| 13 | Section 9 | Core fine-tuning reference |
| 15 | Pitfalls checklist | Useful |

---

## 13. Evaluation & observability

| Check | Method | Gate |
|---|---|---|
| Tool selection and arguments | Deterministic match plus schema validation | Required to promote any AI change |
| Grounding (cites real chunks, no invented IDs) | Lookup against the DB | Required |
| Safety negatives (no write/host action without confirmation) | Negative set | Required, must be 100% |
| Quality (e.g., Socratic tone) | LLM-as-judge plus a lead's spot check | Advisory |
| Ops (p95 latency, tokens, rollback count) | Local traces | Dashboard in the Control Panel |

The eval runner is built into the Control Panel, so a non-developer lead can run it before promoting.

---

## 14. Roadmap

| Phase | Deliverable | Gate |
|---|---|---|
| 0 | Extract the template from Bay Log: core API, standard tables, `zone.yaml` | Bay Log runs unchanged on the template |
| 1 | Assistant panel plus read-only `baylog-mcp`; local Ollama via gateway | Tool-selection evals pass |
| 2 | `control-mcp` plus Control Panel (roles, prompts, draft → eval → promote, rollback) | Rollback tested |
| 3 | Write tools with confirmation; audit | Negative suite 100% |
| 4 | `host-mcp` plus privileged helper with 3–4 low-risk typed actions and declared rollback modes | Lockout test passes (the helper reverts) |
| 5 | Profile B offline sync (if needed) | Conflict drill passes |
| 6 | Fine-tuned `extract` adapter through the promote flow | Section 9 checklist |
| 7 | Second zone built from the template | Built without editing the standard components |

---

## 15. Open decisions

1. **Profile:** one on-prem node per zone (A), or multiple offline-capable devices (B)?
2. **UI stack for the template:** React, vanilla, or both (Bay Log has both today)?
3. **Scan-tool integration:** in scope for v1 (read-only), or deferred?
4. **Minimum hardware tier** a zone must have to adopt the template.
5. **Licensing and IP** for the template and trained adapters (the `blend-zones` repo is currently all rights reserved).
