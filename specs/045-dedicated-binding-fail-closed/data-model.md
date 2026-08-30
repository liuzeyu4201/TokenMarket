# Data Model

## Binding (expand)

`draining_connection_id`：更换后仍承接亲和资源的旧 Connection。

## ReplacePreview

`old_connection_id`, `non_migrating[]`（files, batches, caches, fine_tuning, operations）, `migrates=false`

## ReplaceAudit payload

actor, buyer_confirmed, step_up, reason, before_connection_id, after_connection_id, at
