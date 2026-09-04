---
name: resolving-merge-conflicts
description: >
  Use when you need to resolve an in-progress git merge or rebase conflict
  (conflict markers, MERGE_HEAD, rebase-merge, "fix conflicts and then commit",
  解决冲突, 合并冲突, git mergetool). Do not use for silent loss after a
  completed merge — that is merge-reconciler. Slash: /resolving-merge-conflicts
---

# Resolving merge conflicts

Source: [mattpocock/skills resolving-merge-conflicts](https://github.com/mattpocock/skills/tree/main/skills/engineering/resolving-merge-conflicts). Adapted for TokenMarket.

**Announce:** "I'm using the resolving-merge-conflicts skill."

Always resolve; never `git merge --abort` / `git rebase --abort` unless the user explicitly asks. Do **not** invent new behaviour. Do **not** push unless the user asks.

## TokenMarket constraints

- Integration branch is `master-dev` (production is `master`). Environment is `mode=local|test|prod`, never inferred from the branch name.
- Do not take incoming versions of ignored secrets: `.env.local`, `.env.test`, `.env.prod`, `*.pem`, credentials.
- After a conflicted merge, run **root** `make fmt`, then `make lint`, then targeted tests for touched packages; use `make test` / `make ci` when the conflict spans multiple services.
- Conventional Commits. Finish merge with `git commit` (no `--no-edit` if you must record a trade-off in the message). Finish rebase with `git rebase --continue`.
- Silent loss / “merged but we went back to their old file” after the merge **commit** exists → stop this skill and use `merge-reconciler`.

## Process

1. **See the current state.** `git status`, `git diff`, conflicted paths (`UU` / unmerged). Read `HEAD`, `MERGE_HEAD` or rebase onto-commit. Skim recent `git log --oneline` on both sides.

2. **Find the primary sources** for each conflict. Read both sides’ commit messages and the surrounding code. Understand original intent. Do not resolve from the marker text alone.

3. **Resolve each hunk.** Preserve both intents where possible. Where incompatible, pick the side that matches **this merge’s stated goal** (usually keep `master-dev` product rules: native passthrough, fail-closed, no invented API) and note the trade-off. Leave no `<<<<<<<` / `=======` / `>>>>>>>`. Never delete a still-needed side silently.

4. **Automated checks.** Discover and run this repo’s checks — typically `make fmt`, then `make lint`, then tests for the touched tree (`go test`, `pytest`, frontend vitest). Fix anything the merge broke. Do not lower coverage gates.

5. **Finish the merge/rebase.** `git add` the resolved paths. Complete with a merge commit or `git rebase --continue`. Stop if hooks fail; fix, then finish. Do not `--abort`.

## Quick checks

```bash
git status
git diff --name-only --diff-filter=U
rg -n '^(<<<<<<<|=======|>>>>>>>)' .
```

After resolve, markers must be gone before `git add`.
