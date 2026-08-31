# Data Model

## BudgetPolicy

project_id, key_id?, hard_minor, soft_minor

## QuotaOverview

available, reserved, settled, unresolved, warning?, requests[]

## Guide

checklist[] (binding|key|sample|result), samples{openai,anthropic,vertex}

## UsageRow

request_id, key_id, status, amount_minor, reason?, protocol?
