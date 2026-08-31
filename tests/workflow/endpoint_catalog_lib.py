"""Endpoint Catalog source, validation, and deterministic listing (SF01)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"
CATALOG_MAJOR = 1
CATALOG_MINOR = 0
FREEZE_DATE = "2026-08-31"
PROVIDERS = ("openai", "anthropic", "vertex")
STABILITIES = frozenset({"stable", "preview", "beta", "control_plane"})
METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "WEBSOCKET"})
TRANSPORTS = frozenset({"http", "sse", "websocket", "multipart", "binary"})
AFFINITIES = frozenset({"none", "connection", "resource_id"})
METERING = frozenset({"usage", "reported_cost", "mixed", "unresolved", "none"})
REQUIRED = (
    "id",
    "provider",
    "protocol_version",
    "method",
    "path_template",
    "stability",
    "capability_tags",
    "stateful",
    "transport",
    "affinity",
    "metering_source",
    "first_supported_version",
    "test_fixture_version",
    "official_source",
    "owning_sf",
    "requires_project_opt_in",
)

SRC_OA = "https://developers.openai.com/api/reference/"
SRC_AN = "https://platform.claude.com/docs/en/api/overview"
SRC_VX = "https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest"

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class CatalogError(ValueError):
    """Directory completeness or uniqueness failure."""


def _ep(
    provider: str,
    method: str,
    path: str,
    *,
    stability: str = "stable",
    stateful: bool = False,
    transport: str = "http",
    affinity: str = "none",
    metering_source: str = "usage",
    tags: list[str] | None = None,
    owning_sf: str,
    official_source: str,
    protocol_version: str = "v1",
    opt_in: bool | None = None,
) -> dict[str, Any]:
    if opt_in is None:
        opt_in = stability in {"preview", "beta"}
    normalized = (
        path.strip("/").replace("/", ".").replace("{", "").replace("}", "").replace(":", ".")
    )
    slug = f"{provider}.{method.lower()}.{normalized}"
    slug = re.sub(r"[^a-z0-9._-]+", "-", slug.lower()).strip("-")
    return {
        "id": slug,
        "provider": provider,
        "protocol_version": protocol_version,
        "method": method,
        "path_template": path,
        "stability": stability,
        "capability_tags": list(tags or []),
        "stateful": stateful,
        "transport": transport,
        "affinity": affinity,
        "metering_source": metering_source,
        "first_supported_version": "v0.2.0",
        "test_fixture_version": "fx-v0.2.0",
        "official_source": official_source,
        "owning_sf": owning_sf,
        "requires_project_opt_in": opt_in,
    }


def _oa(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    kwargs.setdefault("owning_sf", "SF19")
    kwargs.setdefault("official_source", SRC_OA)
    return _ep("openai", method, path, **kwargs)


def _an(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    kwargs.setdefault("owning_sf", "SF20")
    kwargs.setdefault("official_source", SRC_AN)
    return _ep("anthropic", method, path, **kwargs)


def _vx(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    kwargs.setdefault("owning_sf", "SF21")
    kwargs.setdefault("official_source", SRC_VX)
    kwargs.setdefault("protocol_version", "vertex-v1")
    return _ep("vertex", method, path, **kwargs)


def openai_records() -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    # Responses
    recs += [
        _oa(
            "POST",
            "/v1/responses",
            tags=["responses", "tools"],
            metering_source="mixed",
            transport="sse",
        ),
        _oa("GET", "/v1/responses", stateful=True, affinity="resource_id"),
        _oa("GET", "/v1/responses/{response_id}", stateful=True, affinity="resource_id"),
        _oa("POST", "/v1/responses/{response_id}", stateful=True, affinity="resource_id"),
        _oa(
            "DELETE",
            "/v1/responses/{response_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/responses/{response_id}/cancel",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/responses/{response_id}/input_items",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/responses/{response_id}/compact",
            stateful=True,
            affinity="resource_id",
        ),
    ]
    recs += [
        _oa(
            "POST",
            "/v1/conversations",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/conversations/{conversation_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/conversations/{conversation_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "DELETE",
            "/v1/conversations/{conversation_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/conversations/{conversation_id}/items",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/conversations/{conversation_id}/items",
            stateful=True,
            affinity="resource_id",
        ),
        _oa(
            "GET",
            "/v1/conversations/{conversation_id}/items/{item_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "DELETE",
            "/v1/conversations/{conversation_id}/items/{item_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
    ]
    recs += [
        _oa(
            "POST",
            "/v1/chat/completions",
            tags=["chat", "tools"],
            metering_source="mixed",
            transport="sse",
        ),
        _oa("GET", "/v1/chat/completions", stateful=True, affinity="resource_id"),
        _oa(
            "GET",
            "/v1/chat/completions/{completion_id}",
            stateful=True,
            affinity="resource_id",
        ),
        _oa(
            "POST",
            "/v1/chat/completions/{completion_id}",
            stateful=True,
            affinity="resource_id",
        ),
        _oa(
            "DELETE",
            "/v1/chat/completions/{completion_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/chat/completions/{completion_id}/messages",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa("POST", "/v1/completions", tags=["legacy"], metering_source="usage"),
        _oa("GET", "/v1/models", metering_source="none"),
        _oa("GET", "/v1/models/{model}", metering_source="none"),
        _oa("DELETE", "/v1/models/{model}", metering_source="none"),
        _oa("POST", "/v1/embeddings", tags=["embeddings"]),
        _oa("POST", "/v1/moderations", tags=["moderation"], metering_source="none"),
        _oa("POST", "/v1/images/generations", tags=["images"], metering_source="mixed"),
        _oa(
            "POST",
            "/v1/images/edits",
            tags=["images"],
            metering_source="mixed",
            transport="multipart",
        ),
        _oa(
            "POST",
            "/v1/images/variations",
            tags=["images"],
            metering_source="mixed",
            transport="multipart",
        ),
        _oa(
            "POST",
            "/v1/audio/speech",
            tags=["audio"],
            metering_source="mixed",
            transport="binary",
        ),
        _oa(
            "POST",
            "/v1/audio/transcriptions",
            tags=["audio"],
            metering_source="mixed",
            transport="multipart",
        ),
        _oa(
            "POST",
            "/v1/audio/translations",
            tags=["audio"],
            metering_source="mixed",
            transport="multipart",
        ),
    ]
    recs += [
        _oa(
            "GET",
            "/v1/files",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/files",
            stateful=True,
            affinity="resource_id",
            transport="multipart",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/files/{file_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "DELETE",
            "/v1/files/{file_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/files/{file_id}/content",
            stateful=True,
            affinity="resource_id",
            transport="binary",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/uploads",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/uploads/{upload_id}/parts",
            stateful=True,
            affinity="resource_id",
            transport="multipart",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/uploads/{upload_id}/complete",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/uploads/{upload_id}/cancel",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/batches",
            stateful=True,
            affinity="resource_id",
            metering_source="mixed",
        ),
        _oa(
            "GET",
            "/v1/batches",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/batches/{batch_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/batches/{batch_id}/cancel",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
    ]
    recs += [
        _oa("POST", "/v1/fine_tuning/jobs", stateful=True, affinity="resource_id"),
        _oa(
            "GET",
            "/v1/fine_tuning/jobs",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/fine_tuning/jobs/{fine_tuning_job_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/fine_tuning/jobs/{fine_tuning_job_id}/cancel",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/fine_tuning/jobs/{fine_tuning_job_id}/events",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/fine_tuning/jobs/{fine_tuning_job_id}/checkpoints",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/fine_tuning/checkpoints/{checkpoint_id}/permissions",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/fine_tuning/checkpoints/{checkpoint_id}/permissions",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "DELETE",
            "/v1/fine_tuning/checkpoints/{checkpoint_id}/permissions/{permission_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
    ]
    recs += [
        _oa(
            "POST",
            "/v1/vector_stores",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/vector_stores",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/vector_stores/{vector_store_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/vector_stores/{vector_store_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "DELETE",
            "/v1/vector_stores/{vector_store_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/vector_stores/{vector_store_id}/search",
            stateful=True,
            affinity="resource_id",
        ),
        _oa(
            "POST",
            "/v1/vector_stores/{vector_store_id}/files",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/vector_stores/{vector_store_id}/files",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/vector_stores/{vector_store_id}/files/{file_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/vector_stores/{vector_store_id}/files/{file_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "DELETE",
            "/v1/vector_stores/{vector_store_id}/files/{file_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/vector_stores/{vector_store_id}/files/{file_id}/content",
            stateful=True,
            affinity="resource_id",
            transport="binary",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/vector_stores/{vector_store_id}/file_batches",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/vector_stores/{vector_store_id}/file_batches/{batch_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/vector_stores/{vector_store_id}/file_batches/{batch_id}/cancel",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/vector_stores/{vector_store_id}/file_batches/{batch_id}/files",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
    ]
    recs += [
        _oa(
            "WEBSOCKET",
            "/v1/realtime",
            tags=["realtime"],
            stateful=True,
            transport="websocket",
            affinity="connection",
            metering_source="mixed",
        ),
        _oa(
            "POST",
            "/v1/realtime/sessions",
            stateful=True,
            affinity="connection",
            metering_source="mixed",
        ),
        _oa(
            "POST",
            "/v1/realtime/client_secrets",
            stateful=True,
            affinity="connection",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/realtime/calls",
            stateful=True,
            affinity="connection",
            metering_source="mixed",
        ),
        _oa(
            "GET",
            "/v1/realtime/calls/{call_id}",
            stateful=True,
            affinity="connection",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/realtime/calls/{call_id}/accept",
            stateful=True,
            affinity="connection",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/realtime/calls/{call_id}/hangup",
            stateful=True,
            affinity="connection",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/realtime/calls/{call_id}/refer",
            stateful=True,
            affinity="connection",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/realtime/calls/{call_id}/reject",
            stateful=True,
            affinity="connection",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/realtime/transcription_sessions",
            stateful=True,
            affinity="connection",
        ),
    ]
    recs += [
        _oa(
            "POST",
            "/v1/assistants",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/assistants",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/assistants/{assistant_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/assistants/{assistant_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "DELETE",
            "/v1/assistants/{assistant_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/threads",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/threads/{thread_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/threads/{thread_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "DELETE",
            "/v1/threads/{thread_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/threads/{thread_id}/messages",
            stateful=True,
            affinity="resource_id",
        ),
        _oa(
            "GET",
            "/v1/threads/{thread_id}/messages",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/threads/{thread_id}/messages/{message_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/threads/{thread_id}/messages/{message_id}",
            stateful=True,
            affinity="resource_id",
        ),
        _oa(
            "DELETE",
            "/v1/threads/{thread_id}/messages/{message_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/threads/{thread_id}/runs",
            stateful=True,
            affinity="resource_id",
            metering_source="mixed",
        ),
        _oa(
            "GET",
            "/v1/threads/{thread_id}/runs",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/threads/{thread_id}/runs/{run_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/threads/{thread_id}/runs/{run_id}",
            stateful=True,
            affinity="resource_id",
        ),
        _oa(
            "POST",
            "/v1/threads/{thread_id}/runs/{run_id}/cancel",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/threads/{thread_id}/runs/{run_id}/submit_tool_outputs",
            stateful=True,
            affinity="resource_id",
        ),
        _oa(
            "GET",
            "/v1/threads/{thread_id}/runs/{run_id}/steps",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/threads/{thread_id}/runs/{run_id}/steps/{step_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/threads/runs",
            stateful=True,
            affinity="resource_id",
            metering_source="mixed",
        ),
    ]
    recs += [
        _oa(
            "POST",
            "/v1/videos",
            stability="preview",
            stateful=True,
            affinity="resource_id",
            tags=["video"],
        ),
        _oa(
            "GET",
            "/v1/videos",
            stability="preview",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/videos/{video_id}",
            stability="preview",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "DELETE",
            "/v1/videos/{video_id}",
            stability="preview",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _oa(
            "GET",
            "/v1/videos/{video_id}/content",
            stability="preview",
            stateful=True,
            affinity="resource_id",
            transport="binary",
            metering_source="none",
        ),
        _oa(
            "POST",
            "/v1/fine_tuning/alpha/graders/run",
            stability="preview",
            tags=["alpha"],
        ),
        _oa(
            "POST",
            "/v1/fine_tuning/alpha/graders/validate",
            stability="preview",
            tags=["alpha"],
            metering_source="none",
        ),
    ]
    control = [
        ("GET", "/v1/organization"),
        ("GET", "/v1/organization/users"),
        ("POST", "/v1/organization/users"),
        ("GET", "/v1/organization/users/{user_id}"),
        ("POST", "/v1/organization/users/{user_id}"),
        ("DELETE", "/v1/organization/users/{user_id}"),
        ("GET", "/v1/organization/invites"),
        ("POST", "/v1/organization/invites"),
        ("DELETE", "/v1/organization/invites/{invite_id}"),
        ("GET", "/v1/organization/projects"),
        ("POST", "/v1/organization/projects"),
        ("GET", "/v1/organization/projects/{project_id}"),
        ("POST", "/v1/organization/projects/{project_id}"),
        ("GET", "/v1/organization/projects/{project_id}/users"),
        ("POST", "/v1/organization/projects/{project_id}/users"),
        ("GET", "/v1/organization/projects/{project_id}/api_keys"),
        ("POST", "/v1/organization/projects/{project_id}/api_keys"),
        ("DELETE", "/v1/organization/projects/{project_id}/api_keys/{key_id}"),
        ("GET", "/v1/organization/audit_logs"),
        ("GET", "/v1/organization/usage"),
        ("GET", "/v1/organization/costs"),
        ("GET", "/v1/organization/admin_api_keys"),
        ("POST", "/v1/organization/admin_api_keys"),
        ("DELETE", "/v1/organization/admin_api_keys/{key_id}"),
        ("GET", "/v1/organization/certificates"),
    ]
    for method, path in control:
        recs.append(
            _oa(
                method,
                path,
                stability="control_plane",
                metering_source="none",
                owning_sf="SF01",
                tags=["control_plane"],
            )
        )
    return recs


def anthropic_records() -> list[dict[str, Any]]:
    recs = [
        _an(
            "POST",
            "/v1/messages",
            tags=["messages", "tools"],
            metering_source="mixed",
            transport="sse",
        ),
        _an(
            "POST",
            "/v1/messages/count_tokens",
            tags=["count_tokens"],
            metering_source="none",
        ),
        _an(
            "POST",
            "/v1/messages/batches",
            stateful=True,
            affinity="resource_id",
            metering_source="mixed",
        ),
        _an(
            "GET",
            "/v1/messages/batches",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _an(
            "GET",
            "/v1/messages/batches/{message_batch_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _an(
            "POST",
            "/v1/messages/batches/{message_batch_id}/cancel",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _an(
            "GET",
            "/v1/messages/batches/{message_batch_id}/results",
            stateful=True,
            affinity="resource_id",
            transport="binary",
            metering_source="none",
        ),
        _an(
            "DELETE",
            "/v1/messages/batches/{message_batch_id}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _an("GET", "/v1/models", metering_source="none"),
        _an("GET", "/v1/models/{model_id}", metering_source="none"),
        _an(
            "GET",
            "/v1/files",
            stability="beta",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _an(
            "POST",
            "/v1/files",
            stability="beta",
            stateful=True,
            affinity="resource_id",
            transport="multipart",
            metering_source="none",
        ),
        _an(
            "GET",
            "/v1/files/{file_id}",
            stability="beta",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _an(
            "DELETE",
            "/v1/files/{file_id}",
            stability="beta",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _an(
            "GET",
            "/v1/files/{file_id}/content",
            stability="beta",
            stateful=True,
            affinity="resource_id",
            transport="binary",
            metering_source="none",
        ),
    ]
    for method, path in [
        ("GET", "/v1/organizations"),
        ("GET", "/v1/organizations/{organization_id}"),
        ("GET", "/v1/users"),
        ("GET", "/v1/api_keys"),
        ("POST", "/v1/api_keys"),
        ("DELETE", "/v1/api_keys/{api_key_id}"),
        ("GET", "/v1/workspaces"),
        ("GET", "/v1/invites"),
        ("GET", "/v1/organizations/{organization_id}/usage"),
        ("GET", "/v1/organizations/{organization_id}/cost_report"),
    ]:
        recs.append(
            _an(
                method,
                path,
                stability="control_plane",
                metering_source="none",
                owning_sf="SF01",
                tags=["control_plane"],
            )
        )
    return recs


def vertex_records() -> list[dict[str, Any]]:
    base = "/v1/projects/{project}/locations/{location}/publishers/{publisher}/models/{model}"
    recs = [
        _vx(
            "POST",
            f"{base}:generateContent",
            tags=["generate"],
            metering_source="mixed",
        ),
        _vx(
            "POST",
            f"{base}:streamGenerateContent",
            tags=["generate"],
            metering_source="mixed",
            transport="sse",
        ),
        _vx("POST", f"{base}:countTokens", metering_source="none"),
        _vx("POST", f"{base}:computeTokens", metering_source="none"),
        _vx("POST", f"{base}:embedContent", tags=["embeddings"]),
        _vx("POST", f"{base}:predict", tags=["predict"], metering_source="mixed"),
        _vx("POST", f"{base}:rawPredict", tags=["predict"], metering_source="mixed"),
        _vx(
            "POST",
            f"{base}:streamRawPredict",
            tags=["predict"],
            metering_source="mixed",
            transport="sse",
        ),
        _vx(
            "POST",
            f"{base}:serverStreamingPredict",
            tags=["predict"],
            metering_source="mixed",
            transport="sse",
        ),
        _vx(
            "POST",
            f"{base}:predictLongRunning",
            stateful=True,
            affinity="resource_id",
            metering_source="mixed",
        ),
        _vx(
            "POST",
            f"{base}:fetchPredictOperation",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _vx(
            "GET",
            "/v1/projects/{project}/locations/{location}/publishers/{publisher}/models/{model}",
            metering_source="none",
        ),
        _vx(
            "GET",
            "/v1/projects/{project}/locations/{location}/publishers/{publisher}/models",
            metering_source="none",
        ),
        _vx(
            "POST",
            "/v1/projects/{project}/locations/{location}/cachedContents",
            stateful=True,
            affinity="resource_id",
        ),
        _vx(
            "GET",
            "/v1/projects/{project}/locations/{location}/cachedContents",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _vx(
            "GET",
            "/v1/projects/{project}/locations/{location}/cachedContents/{cachedContent}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _vx(
            "PATCH",
            "/v1/projects/{project}/locations/{location}/cachedContents/{cachedContent}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _vx(
            "DELETE",
            "/v1/projects/{project}/locations/{location}/cachedContents/{cachedContent}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _vx(
            "POST",
            "/v1/projects/{project}/locations/{location}/batchPredictionJobs",
            stateful=True,
            affinity="resource_id",
            metering_source="mixed",
        ),
        _vx(
            "GET",
            "/v1/projects/{project}/locations/{location}/batchPredictionJobs",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _vx(
            "GET",
            "/v1/projects/{project}/locations/{location}/batchPredictionJobs/{batchPredictionJob}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _vx(
            "DELETE",
            "/v1/projects/{project}/locations/{location}/batchPredictionJobs/{batchPredictionJob}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _vx(
            "POST",
            "/v1/projects/{project}/locations/{location}/batchPredictionJobs/"
            "{batchPredictionJob}:cancel",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _vx(
            "POST",
            "/v1/projects/{project}/locations/{location}/tuningJobs",
            stateful=True,
            affinity="resource_id",
        ),
        _vx(
            "GET",
            "/v1/projects/{project}/locations/{location}/tuningJobs",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _vx(
            "GET",
            "/v1/projects/{project}/locations/{location}/tuningJobs/{tuningJob}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _vx(
            "POST",
            "/v1/projects/{project}/locations/{location}/tuningJobs/{tuningJob}:cancel",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _vx(
            "GET",
            "/v1/projects/{project}/locations/{location}/operations/{operation}",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _vx(
            "POST",
            "/v1/projects/{project}/locations/{location}/operations/{operation}:cancel",
            stateful=True,
            affinity="resource_id",
            metering_source="none",
        ),
        _vx(
            "POST",
            "/v1beta1/projects/{project}/locations/{location}/publishers/"
            "{publisher}/models/{model}:generateContent",
            stability="preview",
            protocol_version="vertex-v1beta1",
            tags=["preview"],
        ),
    ]
    for method, path in [
        ("POST", "/v1/projects/{project}/locations/{location}/endpoints"),
        ("DELETE", "/v1/projects/{project}/locations/{location}/endpoints/{endpoint}"),
        ("POST", "/v1/projects/{project}:setIamPolicy"),
        ("POST", "/v1/projects/{project}:getIamPolicy"),
        ("POST", "/v1/projects/{project}:testIamPermissions"),
    ]:
        recs.append(
            _vx(
                method,
                path,
                stability="control_plane",
                metering_source="none",
                owning_sf="SF01",
                tags=["control_plane"],
            )
        )
    return recs


def all_records() -> list[dict[str, Any]]:
    recs = openai_records() + anthropic_records() + vertex_records()
    recs.sort(key=lambda r: (r["provider"], r["path_template"], r["method"]))
    return recs


def build_catalog() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "catalog_major": CATALOG_MAJOR,
        "catalog_minor": CATALOG_MINOR,
        "freeze_date": FREEZE_DATE,
        "providers": list(PROVIDERS),
        "records": all_records(),
    }


def validate_catalog(catalog: dict[str, Any]) -> None:
    if catalog.get("schema_version") != SCHEMA_VERSION:
        raise CatalogError("schema_version")
    if catalog.get("catalog_major") != CATALOG_MAJOR:
        raise CatalogError("catalog_major")
    if catalog.get("freeze_date") != FREEZE_DATE:
        raise CatalogError("freeze_date")
    if list(catalog.get("providers") or []) != list(PROVIDERS):
        raise CatalogError("providers")
    records = catalog.get("records")
    if not isinstance(records, list) or not records:
        raise CatalogError("records")
    seen_keys: set[tuple[str, str, str, str]] = set()
    seen_ids: set[str] = set()
    for rec in records:
        for field in REQUIRED:
            if field not in rec:
                raise CatalogError(f"missing {field}")
        if rec["stability"] not in STABILITIES:
            raise CatalogError("stability")
        if rec["method"] not in METHODS:
            raise CatalogError("method")
        if rec["transport"] not in TRANSPORTS:
            raise CatalogError("transport")
        if rec["affinity"] not in AFFINITIES:
            raise CatalogError("affinity")
        if rec["metering_source"] not in METERING:
            raise CatalogError("metering_source")
        if rec["provider"] not in PROVIDERS:
            raise CatalogError("provider")
        if not rec["path_template"].startswith("/"):
            raise CatalogError("path_template")
        if rec["stability"] in {"preview", "beta"} and not rec["requires_project_opt_in"]:
            raise CatalogError("preview must opt-in")
        if not _SLUG_RE.match(rec["id"]):
            raise CatalogError("id")
        key = (
            rec["provider"],
            rec["protocol_version"],
            rec["method"],
            rec["path_template"],
        )
        if key in seen_keys:
            raise CatalogError(f"duplicate {key}")
        seen_keys.add(key)
        if rec["id"] in seen_ids:
            raise CatalogError(f"duplicate id {rec['id']}")
        seen_ids.add(rec["id"])


def dump_catalog(catalog: dict[str, Any]) -> str:
    return json.dumps(catalog, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def render_markdown(catalog: dict[str, Any]) -> str:
    lines = [
        "# TokenMarket V0.2 Endpoint Catalog",
        "",
        f"- freeze_date: `{catalog['freeze_date']}`",
        f"- catalog_major: `{catalog['catalog_major']}`",
        f"- catalog_minor: `{catalog['catalog_minor']}`",
        f"- records: `{len(catalog['records'])}`",
        "",
        "| provider | method | path_template | stability | stateful | transport | owning_sf |",
        "|----------|--------|---------------|-----------|----------|-----------|-----------|",
    ]
    for rec in sorted(
        catalog["records"],
        key=lambda r: (r["provider"], r["path_template"], r["method"]),
    ):
        lines.append(
            f"| {rec['provider']} | {rec['method']} | `{rec['path_template']}` | "
            f"{rec['stability']} | {str(rec['stateful']).lower()} | "
            f"{rec['transport']} | {rec['owning_sf']} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_catalog_artifacts(repo_root: Path) -> dict[str, Any]:
    catalog = build_catalog()
    validate_catalog(catalog)
    payload = dump_catalog(catalog)
    listing = render_markdown(catalog)
    targets = [
        repo_root / "shared/contracts/endpoint-catalog/v1/catalog.json",
        repo_root / "specs/020-endpoint-catalog-governance/contracts/catalog.json",
        repo_root / "services/proxy-gateway/internal/domain/endpcatalog/catalog.snapshot.json",
    ]
    md_targets = [
        repo_root / "shared/contracts/endpoint-catalog/v1/CATALOG.md",
        repo_root / "specs/020-endpoint-catalog-governance/contracts/CATALOG.md",
    ]
    for path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    for path in md_targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(listing, encoding="utf-8")
    return catalog
