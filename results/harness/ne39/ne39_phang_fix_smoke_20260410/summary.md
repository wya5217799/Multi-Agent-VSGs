Run status: `failed`

Completed tasks: model_inspect, scenario_status, train_smoke_start

Key findings:
- train_smoke_start: train_smoke requires scenario_status ok, no failed modeling tasks, and model_report run_status ok/warning

Recommended followups:
- Fix failed modeling tasks before train_smoke
