"""Executable alert evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.admin.errors import MSG, VALIDATION, AdminError

RUNBOOK = "ops/runbooks/slo-alerts.md"
DASHBOARD = "v02-slo-overview"

CATALOG: dict[str, dict[str, Any]] = {
    "upstream_slow": {
        "threshold": 2.0,
        "field": "p95_seconds",
        "op": "gt",
        "impact": "数据面上游变慢，买家延迟上升",
        "owner": "proxy-gateway",
        "escalation": "P1 on-call",
    },
    "no_candidate": {
        "threshold": 0,
        "field": "count",
        "op": "gt",
        "impact": "无合格路由候选，请求失败关闭",
        "owner": "proxy-gateway",
        "escalation": "P1 on-call",
    },
    "event_backlog": {
        "threshold": 1000,
        "field": "depth",
        "op": "gt",
        "impact": "用量/结算事件积压",
        "owner": "proxy-gateway",
        "escalation": "P1 on-call",
    },
    "unresolved_spike": {
        "threshold": 10,
        "field": "delta",
        "op": "gt",
        "impact": "未决账务突增",
        "owner": "billing-service",
        "escalation": "P1 finance/ops",
    },
    "connection_unhealthy": {
        "threshold": 0,
        "field": "unhealthy",
        "op": "gt",
        "impact": "连接健康失败",
        "owner": "supply_ops",
        "escalation": "P1 supply",
    },
}


@dataclass
class AlertInstance:
    kind: str
    firing: bool
    threshold: float
    impact: str
    dashboard: str
    runbook: str
    owner: str
    escalation: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "firing": self.firing,
            "threshold": self.threshold,
            "impact": self.impact,
            "dashboard": self.dashboard,
            "runbook": self.runbook,
            "owner": self.owner,
            "escalation": self.escalation,
        }


def evaluate_alert(kind: str, sample: dict[str, float | int]) -> AlertInstance:
    spec = CATALOG.get(kind)
    if spec is None:
        raise AdminError(VALIDATION, MSG[VALIDATION], http_status=400)
    value = float(sample.get(spec["field"], 0))
    thresh = float(spec["threshold"])
    firing = value > thresh
    return AlertInstance(
        kind=kind,
        firing=firing,
        threshold=thresh,
        impact=str(spec["impact"]),
        dashboard=DASHBOARD,
        runbook=RUNBOOK,
        owner=str(spec["owner"]),
        escalation=str(spec["escalation"]),
    )
