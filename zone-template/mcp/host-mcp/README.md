# host-mcp (standard, do not fork). Phase 4 stub.
Makes fenced host and equipment changes through typed kinds declared in `helper/host-actions.yaml` only, using plan → apply → verify, with rollback semantics declared per kind (`helper/kinds/`). Admin only; never runs on a student's behalf.
