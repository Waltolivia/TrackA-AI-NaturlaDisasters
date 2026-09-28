# Legacy collectors

This directory preserves earlier ground-truth collector implementations for
project history, reproducibility, and compatibility tests. They are not part of
the current production pipeline.

## Contents

- `disaster_monitor-v2/` is the previous structured collector. The pipeline
  worker still understands its flat-outbox trigger format for backward
  compatibility.
- `emergency_alert_collector/` is the original prototype.

Use `../disaster_monitor-v5/` for all current collection, deployment, and
Wednesday demonstration work. Do not run a legacy collector alongside v5
unless a deliberately isolated compatibility test requires it.

Legacy source is retained rather than deleted so earlier project decisions and
data formats remain auditable.
