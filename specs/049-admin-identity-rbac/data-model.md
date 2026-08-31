# Data Model

## AdminAccount

admin_id, login, password_digest, role, readonly, mfa_enrolled

## AdminSession

session_id, admin_id, created_at, step_up_at?, cookie_digest

## AuditRecord

event_id, actor, role, action, target, reason, request_id, before, after, result, source, prev_hash, record_hash

## BreakGlassCase

case_id, actor, reason, alerted, closed_at, review
