"""V0.2 release go/no-go evaluator (SF34). Fail-closed on hard gates."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

SF_SPEC_DIRS: dict[str, str] = {
    "SF01": "020-endpoint-catalog-governance",
    "SF02": "021-gateway-stateless-scale",
    "SF03": "022-distributed-auth-routing-capacity",
    "SF04": "023-reliable-usage-events",
    "SF05": "024-ha-deploy-rollout-rollback",
    "SF06": "025-unified-phone-auth",
    "SF07": "026-single-session-auth-hardening",
    "SF08": "027-web-design-system-shell",
    "SF09": "028-workspace-switch-authorization",
    "SF10": "029-buyer-project-lifecycle",
    "SF11": "030-provider-binding",
    "SF12": "031-project-proxy-key-scope",
    "SF13": "048-project-budget-guide",
    "SF14": "032-provider-connection-credentials",
    "SF15": "033-connection-verify-health",
    "SF16": "034-supply-mode-lifecycle",
    "SF17": "042-seller-quote-workbench",
    "SF18": "035-native-passthrough-kernel",
    "SF19": "037-openai-stable-dataplane",
    "SF20": "038-anthropic-stable-dataplane",
    "SF21": "039-vertex-stable-dataplane",
    "SF22": "036-stream-file-async-affinity",
    "SF23": "043-shared-route-qualification",
    "SF24": "044-composite-score-routing",
    "SF25": "045-dedicated-binding-fail-closed",
    "SF26": "040-native-spend-usage-capture",
    "SF27": "041-versioned-rates-quotes",
    "SF28": "046-immutable-ledger-settlement",
    "SF29": "047-async-settlement-recon",
    "SF30": "049-admin-identity-rbac",
    "SF31": "050-ops-admin-console",
    "SF32": "051-observability-slo-alerts",
    "SF33": "052-capacity-resilience",
    "SF34": "053-release-gates",
}

CONVERGED = "Converged — the implementation satisfies the spec, plan, and tasks."

DEFAULT_PUBLIC_BLOCKERS = (
    "independent_pentest",
    "paid_vendor_smoke",
    "real_sms",
    "production_credentials",
    "git_push",
    "prod_deploy",
    "capacity_full_wall_clock",
)


@dataclass
class SFBinding:
    sf_id: str
    spec_dir: str
    has_spec: bool
    has_tasks: bool
    has_converge: bool


@dataclass
class EvidencePack:
    p0_p1: int = 0
    security_critical_high: int = 0
    pentest_closed: bool = False
    capacity_full: bool = False
    public_claim: bool = False
    p2_unaccepted: int = 0
    blockers: list[str] = field(default_factory=list)


@dataclass
class ReleaseDecision:
    claim: str
    status: str
    mapping_pct: float
    blockers: list[str]


def scan_bindings(repo_root: Path) -> list[SFBinding]:
    specs = repo_root / "specs"
    out: list[SFBinding] = []
    for sf_id, dirname in SF_SPEC_DIRS.items():
        root = specs / dirname
        converge = root / "evidence"
        has_converge = False
        if converge.is_dir():
            files = list(converge.glob("converge*.md"))
            has_converge = any(path.is_file() for path in files)
        out.append(
            SFBinding(
                sf_id=sf_id,
                spec_dir=dirname,
                has_spec=(root / "spec.md").is_file(),
                has_tasks=(root / "tasks.md").is_file(),
                has_converge=has_converge,
            )
        )
    return out


def mapping_pct(bindings: list[SFBinding]) -> float:
    if not bindings:
        return 0.0
    ok = sum(1 for b in bindings if b.has_spec and b.has_tasks and b.has_converge)
    return 100.0 * ok / len(bindings)


def decide(
    claim: str, bindings: list[SFBinding], evidence: EvidencePack
) -> ReleaseDecision:
    pct = mapping_pct(bindings)
    blockers = list(evidence.blockers)
    if not evidence.pentest_closed:
        blockers.append("independent_pentest")
    if not evidence.capacity_full:
        blockers.append("capacity_full_wall_clock")
    unique: list[str] = []
    for item in blockers:
        if item not in unique:
            unique.append(item)

    hard_fail = (
        pct < 100.0
        or evidence.p0_p1 > 0
        or evidence.security_critical_high > 0
        or evidence.p2_unaccepted > 0
    )
    if claim == "public":
        if hard_fail or unique or evidence.public_claim and not evidence.pentest_closed:
            return ReleaseDecision("public", "no-go", pct, unique)
        return ReleaseDecision("public", "go", pct, [])
    if hard_fail:
        return ReleaseDecision("implementation", "no-go", pct, unique)
    if unique:
        return ReleaseDecision("implementation", "go-with-blockers", pct, unique)
    return ReleaseDecision("implementation", "go", pct, [])
