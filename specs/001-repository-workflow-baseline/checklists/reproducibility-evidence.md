# Reproducibility Evidence

**Feature**: `specs/001-repository-workflow-baseline/`  
**Date**: 2026-07-14

## Method

Ten consecutive runs of the same four root workflow targets on the same commit:

```bash
make fmt-check
make type-check
make lint
make test
make build
```

Between rounds no source file was edited and no dependency was changed. Git
diff was sampled after each round.

## Results

| Round | fmt-check | type-check | lint | test | build | Time (s) | Git diff lines |
|-------|-----------|------------|------|------|-------|----------|----------------|
| 1     | 0         | 0          | 0    | 0    | 0     | 14       | 206            |
| 2     | 0         | 0          | 0    | 0    | 0     | 13       | 206            |
| 3     | 0         | 0          | 0    | 0    | 0     | 13       | 206            |
| 4     | 0         | 0          | 0    | 0    | 0     | 13       | 206            |
| 5     | 0         | 0          | 0    | 0    | 0     | 13       | 206            |
| 6     | 0         | 0          | 0    | 0    | 0     | 13       | 206            |
| 7     | 0         | 0          | 0    | 0    | 0     | 13       | 206            |
| 8     | 0         | 0          | 0    | 0    | 0     | 13       | 206            |
| 9     | 0         | 0          | 0    | 0    | 0     | 13       | 206            |
| 10    | 0         | 0          | 0    | 0    | 0     | 12       | 206            |

All exit codes are zero. The 206 diff lines are confined to
`specs/001-repository-workflow-baseline/tasks.md` checkbox updates performed as
part of implementation tracking; no unexpected worktree drift was introduced by
the workflow itself.

## Asset determinism

- `shared/dist/shared-assets.tar.gz`, `infra/dist/infra-assets.tar.gz` and
  `ops/dist/ops-assets.tar.gz` are produced by deterministic archive builders.
- Image tags are derived from component version (`0.1.0`), not git state.

## Conclusion

From round 2 onward the workflow produced zero new tracked differences and
identical pass/fail results, confirming the repository workflow is reproducible.
