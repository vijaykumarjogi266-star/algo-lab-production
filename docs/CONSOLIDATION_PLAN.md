# Consolidation Plan

**Stage 0**: Create backup and Git tag of all current states.
**Stage 1**: Establish `/home/ubuntu/algolab` as canonical root.
**Stage 2**: Import exact duplicates only as references if absolutely necessary.
**Stage 3**: Review reusable modules one at a time (e.g., `algolab-builder` for Docker).
**Stage 4**: Migrate tests before implementation for any external components.
**Stage 5**: Migrate source code in small commits.
**Stage 6**: Run full regression suite after each module.
**Stage 7**: Archive (do not delete) old locations.

## Rollback Instructions
If a migrated module breaks the OMS test suite (e.g., reintroduces risk exhaustion failures or idempotency leaks), revert the specific Git commit in `/home/ubuntu/algolab` and restore from the Stage 0 backup tag.
