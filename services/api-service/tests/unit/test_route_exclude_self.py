"""Self-route exclusion pure function tests."""

from __future__ import annotations

import random
import uuid

from app.domain.authorization.route_exclude import (
    RouteCandidate,
    exclude_self_owned_seller_keys,
)


def _c(owner: uuid.UUID, status: str = "active") -> RouteCandidate:
    return RouteCandidate(
        resource_id=uuid.uuid4(),
        owner_user_id=owner,
        lifecycle_status=status,
    )


def test_mixed_pool_excludes_self() -> None:
    buyer = uuid.uuid4()
    other = uuid.uuid4()
    pool = [_c(buyer), _c(other), _c(buyer)]
    filtered, excluded = exclude_self_owned_seller_keys(buyer, pool)
    assert len(filtered) == 1
    assert filtered[0].owner_user_id == other
    assert excluded == 2


def test_only_self_empty() -> None:
    buyer = uuid.uuid4()
    filtered, excluded = exclude_self_owned_seller_keys(buyer, [_c(buyer), _c(buyer)])
    assert filtered == []
    assert excluded == 2


def test_empty_input() -> None:
    filtered, excluded = exclude_self_owned_seller_keys(uuid.uuid4(), [])
    assert filtered == []
    assert excluded == 0


def test_disabled_and_soft_deleted_excluded() -> None:
    buyer = uuid.uuid4()
    other = uuid.uuid4()
    pool = [
        _c(other, "disabled"),
        _c(other, "soft_deleted"),
        _c(other, "active"),
    ]
    filtered, excluded = exclude_self_owned_seller_keys(buyer, pool)
    assert len(filtered) == 1
    assert filtered[0].lifecycle_status == "active"
    assert excluded == 2


def test_forged_owner_on_self_owned_resource_still_excluded() -> None:
    """Caller-supplied owner is not authority; the filter still drops self-owned IDs.

    Service-layer tests resolve owner from storage; this covers the last-mile filter
    once authoritative facts are loaded (forged labels never reach it as owner).
    """
    buyer = uuid.uuid4()
    other = uuid.uuid4()
    self_id = uuid.uuid4()
    # Authoritative facts: self_id is owned by buyer even if a caller claimed otherwise.
    authoritative = [
        RouteCandidate(
            resource_id=self_id, owner_user_id=buyer, lifecycle_status="active"
        ),
        RouteCandidate(
            resource_id=uuid.uuid4(), owner_user_id=other, lifecycle_status="active"
        ),
    ]
    filtered, excluded = exclude_self_owned_seller_keys(buyer, authoritative)
    assert excluded == 1
    assert all(c.resource_id != self_id for c in filtered)


def test_relabel_disabled_as_active_loses_to_server_state() -> None:
    buyer = uuid.uuid4()
    other = uuid.uuid4()
    # Server state is disabled regardless of a caller sending lifecycle_status=active.
    pool = [
        RouteCandidate(uuid.uuid4(), other, "disabled"),
        RouteCandidate(uuid.uuid4(), other, "soft_deleted"),
    ]
    filtered, excluded = exclude_self_owned_seller_keys(buyer, pool)
    assert filtered == []
    assert excluded == 2


def test_sc005_hundred_thousand_never_selects_self() -> None:
    rng = random.Random(42)
    buyer = uuid.uuid4()
    for _ in range(100_000):
        pool = []
        for _j in range(rng.randint(1, 8)):
            owner = buyer if rng.random() < 0.4 else uuid.uuid4()
            status = rng.choice(["active", "active", "disabled", "soft_deleted"])
            pool.append(_c(owner, status))
        # guarantee at least one self active sometimes
        if rng.random() < 0.5:
            pool.append(_c(buyer, "active"))
        filtered, _ = exclude_self_owned_seller_keys(buyer, pool)
        assert all(c.owner_user_id != buyer for c in filtered)
        assert all(c.lifecycle_status == "active" for c in filtered)
