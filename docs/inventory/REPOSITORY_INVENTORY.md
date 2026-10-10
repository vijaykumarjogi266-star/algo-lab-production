# Repository Inventory

1. `/home/ubuntu/algolab`
   - Purpose: Main active OMS integration repository.
   - Components: `oms_project/`, comprehensive test suite.
   - Status: Active development root.

2. `/home/ubuntu/algolab-from-github`
   - Purpose: Original structured clone or legacy base repository.
   - Contains: `apps`, `quant`, `research`, `services`, `docker-compose.yml`, `alembic.ini`.
   - Disposition: Reference / Potential source for modules.

3. `/home/ubuntu/algolab-sandbox`
   - Purpose: Experimentation and test runner execution output.
   - Contains: `runs/` with historical job outputs, `disposable_sandbox/`.
   - Disposition: Archive / Log storage.

4. `/home/ubuntu/algolab-builder`
   - Purpose: Docker image definition and composition.
   - Contains: `Dockerfile`, `docker-compose.yml`.
   - Disposition: Reusable module for deployment.

5. `/home/ubuntu/algolab-control`
   - Purpose: Orchestrator / factory tasks.
   - Contains: `factory/`, `tasks/`, `pending/`.
   - Disposition: Reusable module.

6. `/home/ubuntu/algo-backups`
   - Purpose: Cold storage data backups.
   - Contains: `.tar.gz` data lab backups.
   - Disposition: Archive.

7. `/home/ubuntu/termux-ai-sandbox`
   - Purpose: Mobile/Termux automated execution experiments.
   - Disposition: Evaluate for reusable sub-components.

8. `/home/ubuntu/quant-research-lab`
   - Purpose: Research notebooks or strategy exploration.
   - Disposition: Independent research repository.
