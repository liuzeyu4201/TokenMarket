"""SF34 release mapping and fail-closed go/no-go."""

from __future__ import annotations

from pathlib import Path

from workflow.release_gate import (
    CONVERGED,
    DEFAULT_PUBLIC_BLOCKERS,
    EvidencePack,
    SFBinding,
    SF_SPEC_DIRS,
    decide,
    mapping_pct,
    scan_bindings,
)

from .helpers import find_repo_root, load_text


def test_all_thirty_four_sfs_mapped_on_disk() -> None:
    root = find_repo_root()
    assert len(SF_SPEC_DIRS) == 34
    bindings = scan_bindings(root)
    assert len(bindings) == 34
    missing = [
        b.sf_id
        for b in bindings
        if not (b.has_spec and b.has_tasks)
    ]
    assert missing == [], missing
    dirs = {b.spec_dir for b in bindings}
    assert len(dirs) == 34


def test_mapping_requires_converge_sentence() -> None:
    root = find_repo_root()
    bindings = scan_bindings(root)
    # SF34 evidence may still be in-flight during TDD; require 33 prior SFs.
    prior = [b for b in bindings if b.sf_id != "SF34"]
    pct = mapping_pct(prior)
    assert pct == 100.0
    for b in prior:
        assert b.has_converge, b.sf_id


def test_public_launch_nogo_without_pentest() -> None:
    root = find_repo_root()
    bindings = scan_bindings(root)
    decision = decide(
        "public",
        bindings,
        EvidencePack(
            p0_p1=0,
            security_critical_high=0,
            pentest_closed=False,
            blockers=list(DEFAULT_PUBLIC_BLOCKERS),
        ),
    )
    assert decision.status == "no-go"
    assert "independent_pentest" in decision.blockers


def test_p0_forces_nogo() -> None:
    bindings = [
        SFBinding(sf, dirname, True, True, True)
        for sf, dirname in SF_SPEC_DIRS.items()
    ]
    decision = decide(
        "implementation",
        bindings,
        EvidencePack(p0_p1=1, pentest_closed=True, capacity_full=True),
    )
    assert decision.status == "no-go"


def test_implementation_go_with_blockers() -> None:
    bindings = [
        SFBinding(sf, dirname, True, True, True)
        for sf, dirname in SF_SPEC_DIRS.items()
    ]
    pack = EvidencePack(
        p0_p1=0,
        security_critical_high=0,
        pentest_closed=False,
        capacity_full=False,
        blockers=["real_sms"],
    )
    decision = decide("implementation", bindings, pack)
    assert decision.status == "go-with-blockers"
    assert "independent_pentest" in decision.blockers
    assert "real_sms" in decision.blockers


def test_converge_sentence_is_exact() -> None:
    assert CONVERGED.startswith("Converged —")
    assert "spec, plan, and tasks." in CONVERGED


def test_no_mega_spec_directory() -> None:
    root = Path(find_repo_root())
    names = [p.name for p in (root / "specs").iterdir() if p.is_dir()]
    assert not any("v0.2-all" in n or "mega" in n for n in names)
    readme = load_text("shared", "contracts", "README.md").lower()
    assert "new-api" not in readme
