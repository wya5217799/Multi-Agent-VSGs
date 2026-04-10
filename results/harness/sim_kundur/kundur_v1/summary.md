Run status: `failed`

Completed tasks: scenario_status, train_smoke_start

Key findings:
- scenario_status: Unsupported scenario_id. Expected one of: kundur, ne39
- train_smoke_start: train_smoke requires scenario_status ok, no failed modeling tasks, and model_report run_status ok/warning

Next actions:
- Fix failed modeling tasks before train_smoke
