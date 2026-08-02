# End-to-end release audit

BookBuddy's release audit is non-destructive. EPUBs are read from the configured
library, while evidence, graphs, caches, logs, and reader state are created in
temporary directories. Only reports are copied to the requested output folder.

```powershell
.\venv\Scripts\python.exe backend\audit_pipeline.py baseline --output artifacts\audit-results\baseline
.\venv\Scripts\python.exe backend\audit_pipeline.py offline --chapters 200 --output artifacts\audit-results\offline
.\venv\Scripts\python.exe backend\audit_pipeline.py stress --output artifacts\audit-results\stress
```

The live provider is never called by the offline or stress profiles. A bounded
five-chapter canary requires an explicit flag and has a hard ten-attempt budget:

```powershell
.\venv\Scripts\python.exe backend\audit_pipeline.py live-canary --chapters 200 --live-ai --output artifacts\audit-results\live
```

Gemini Vision requires the additional `--vision` flag. The live report records
token usage, retries, latency, pricing date, and estimated cost.

`audit-report.json` is the authoritative `bookbuddy_audit_v1` record. Its
Markdown companion is the review view. `checksums.sha256` covers every emitted
artifact. A run remains `pending` until the evidence review packet is approved;
machine failures make it `blocked`.

The stress profile deliberately performs a 2,000-chapter evidence replay with
at least 10,000 entities, 20,000 aliases, and 20,000 relationship observations.
Schedule it separately from interactive development because it can be lengthy.
