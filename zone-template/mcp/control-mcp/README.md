# control-mcp (standard, do not fork). Phase 2 stub.
Adjusts the AI layer: roles, prompts, and adapters. Admin only. Every change auto-snapshots to `config_versions`.
Planned tools: `list_roles`, `draft_prompt`, `run_evals`, `promote`, `rollback`. Flow: draft → eval → promote, with rollback.
