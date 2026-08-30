# Implementation evidence: 038-anthropic-stable-dataplane

**Date**: 2026-08-31

`TestAnthropicStableCatalogContractTable` covers all embedded anthropic stable records (10/10).

Messages body is not rewritten to OpenAI `choices`; SSE event names stay `message_start` → `content_block_delta` → `message_stop`; `anthropic-version` is forwarded.

Batches pin Connection; shared batches return `DEDICATED_PROJECT_REQUIRED`; all anthropic control-plane records are blocked; beta `/v1/files` without opt-in is `PREVIEW_NOT_ENABLED`.
