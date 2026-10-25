"""Load status machine and load money math: table-driven checks plus Hypothesis properties."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from manceps_core.loads import machine, money
from manceps_core.repo.errors import Conflict

PLANNED: dict[str, set[str]] = {
    "offered": {"evaluating", "declined", "cancelled"},
    "evaluating": {"countered", "approved", "declined", "cancelled"},
    "countered": {"evaluating", "approved", "declined", "cancelled"},
    "approved": {"booked", "cancelled"},
    "booked": {"ratecon_received", "cancelled"},
    "ratecon_received": {"dispatched", "cancelled"},
    "dispatched": {"at_pickup", "tonu", "cancelled"},
    "at_pickup": {"in_transit", "tonu"},
    "in_transit": {"at_delivery"},
    "at_delivery": {"delivered"},
    "delivered": {"pod_received"},
    "pod_received": {"invoiced"},
    "invoiced": {"paid"},
    "paid": set(),
    "declined": set(),
    "cancelled": set(),
    "tonu": set(),
}

statuses = st.sampled_from(machine.STATUSES)


def test_transition_table_matches_the_plan() -> None:
    assert set(machine.STATUSES) == set(PLANNED)
    for source, targets in PLANNED.items():
        assert set(machine.TRANSITIONS[source]) == targets, source


def test_approval_only_targets_are_refused_directly() -> None:
    with pytest.raises(Conflict) as approved:
        machine.check_direct("evaluating", "approved")
    assert approved.value.code == "approval_required"
    assert approved.value.details["approval_kind"] == "accept_rate"
    with pytest.raises(Conflict) as booked:
        machine.check_direct("approved", "booked")
    assert booked.value.code == "approval_required"


def test_illegal_transition_is_refused() -> None:
    with pytest.raises(Conflict) as exc:
        machine.check_direct("offered", "delivered")
    assert exc.value.code == "illegal_transition"
    assert exc.value.details == {"from": "offered", "to": "delivered"}


def test_cancelling_a_booked_load_needs_an_approval() -> None:
    machine.check_direct("evaluating", "cancelled")
    with pytest.raises(Conflict) as exc:
        machine.check_direct("booked", "cancelled")
    assert exc.value.code == "approval_required"
    assert exc.value.details["approval_kind"] == "cancel_load"


@given(statuses, statuses)
def test_direct_check_never_admits_an_approval_only_or_illegal_move(source: str, target: str) -> None:
    try:
        machine.check_direct(source, target)
    except Conflict as exc:
        assert exc.code in {"approval_required", "illegal_transition"}
        assert (exc.code == "approval_required") == (target in machine.APPROVAL_ONLY or (
            target == "cancelled" and source in machine.CONTRACTED and target in machine.TRANSITIONS[source]))
        return
    assert target in machine.TRANSITIONS[source]
    assert target not in machine.APPROVAL_ONLY
    assert not (target == "cancelled" and source in machine.CONTRACTED)


@given(st.lists(statuses, max_size=40))
def test_random_walks_through_direct_moves_stay_in_known_states(path: list[str]) -> None:
    state = "offered"
    for target in path:
        try:
            machine.check_direct(state, target)
        except Conflict:
            continue
        state = target
        assert state in machine.STATUSES
        assert state not in machine.APPROVAL_ONLY
        assert state not in machine.CONTRACTED, "a direct walk reached a booked state without an approval"


def test_terminal_states_have_no_exit() -> None:
    for status in machine.TERMINAL:
        assert machine.TRANSITIONS[status] == ()


@given(st.integers(min_value=0, max_value=10**9), st.decimals(min_value=Decimal("0.1"), max_value=Decimal(10_000),
                                                              places=1))
def test_rate_per_mile_is_half_up_integer_cents(rate_cents: int, miles: Decimal) -> None:
    result = money.per_mile_cents(rate_cents, float(miles))
    assert isinstance(result, int)
    exact = Decimal(rate_cents) / miles
    assert abs(Decimal(result) - exact) <= Decimal("0.5")


def test_rate_per_mile_rounds_half_up_and_refuses_zero_miles() -> None:
    assert money.per_mile_cents(225_000, 382) == 589
    assert money.per_mile_cents(5, 2) == 3
    assert money.per_mile_cents(1000, 0) is None
    assert money.per_mile_cents(1000, None) is None


@given(st.integers(min_value=0, max_value=10**9), st.floats(min_value=0, max_value=25, allow_nan=False))
def test_percent_of_is_half_up_and_bounded(cents: int, pct: float) -> None:
    fee = money.percent_of(cents, pct)
    assert isinstance(fee, int)
    assert 0 <= fee <= cents
    exact = Decimal(cents) * Decimal(str(pct)) / 100
    assert abs(Decimal(fee) - exact) <= Decimal("0.5")


@given(st.one_of(st.integers(), st.floats(allow_nan=True, allow_infinity=True), st.text(max_size=12), st.none(),
                 st.booleans()))
def test_dollars_to_cents_never_crashes(raw: object) -> None:
    try:
        cents = money.dollars_to_cents(raw)
    except ValueError:
        return
    assert isinstance(cents, int)
    assert 0 <= cents <= money.MAX_RATE_CENTS


def test_dollars_to_cents_parses_sheet_values() -> None:
    assert money.dollars_to_cents("$2,240") == 224_000
    assert money.dollars_to_cents("650.505") == 65_051
    assert money.dollars_to_cents(380) == 38_000
    with pytest.raises(ValueError):
        money.dollars_to_cents("-5")
