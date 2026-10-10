# File Duplicate & Conflict Report

Checksum analysis across `algolab`, `algolab-from-github`, and `termux-ai-sandbox` indicates widespread duplication of core abstractions (`contracts.py`, `portfolio.py`, `overview.md`), especially within historical `runs/` output archives.

- **Exact Duplicates**: Found in `/home/ubuntu/algolab-sandbox/runs/`. Recommended Disposition: ARCHIVE_ONLY (Do not merge).
- **Conflicting Files**: The `algolab-from-github` repository contains structural divergences from the active `algolab` OMS. (e.g., `services/` layout differences). Recommended Disposition: Treat `algolab-from-github` as OLDER_REFERENCE.
- **OMS Project**: The `oms_project/` folder is unique and most advanced in `/home/ubuntu/algolab`, establishing it as the CANONICAL version.
