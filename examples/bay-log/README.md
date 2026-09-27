# Bay Log (reference instance #1)
| Slot | Value |
|---|---|
| Stages | Intake → Diagnosis → Approval → Repair → QC → Pickup |
| Tools | `get_record`, `search_records`, `search_kb`, plus `request_plan` for `add_note` and `advance_stage` (human approves) |
| Gates | Approval, QC, and Pickup require a lead |

Load it from `zone-template/` with `python api/app.py --seed ../examples/bay-log/seed.sql --add-user "Student A" student`.
