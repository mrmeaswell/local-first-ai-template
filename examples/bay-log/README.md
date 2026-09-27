# Bay Log (reference instance #1)
| Slot | Value |
|---|---|
| Stages | Intake → Diagnosis → Approval → Repair → QC → Pickup |
| Tools | `get_record`, `search_records`, `search_kb`, plus gated `add_note` and `advance_stage` |
| Gates | Approval and Pickup require a lead |

Load it with `python api/app.py --seed ../examples/bay-log/seed.sql` from `zone-template/`.
