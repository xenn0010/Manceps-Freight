"""Load status machine: the only table of legal moves, and the rules for which moves need an approval.

`approved` and `booked` are reachable only through an approval being applied (`accept_rate`); a direct request is
409 `approval_required`. Cancelling a load that is already contracted (booked or later) is a contract action too and
needs a `cancel_load` approval. Everything else in the table may be requested directly by a dispatcher.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..repo.errors import Conflict

OFFERED, EVALUATING, COUNTERED, APPROVED, BOOKED = "offered", "evaluating", "countered", "approved", "booked"
RATECON_RECEIVED, DISPATCHED, AT_PICKUP, IN_TRANSIT = "ratecon_received", "dispatched", "at_pickup", "in_transit"
AT_DELIVERY, DELIVERED, POD_RECEIVED, INVOICED, PAID = "at_delivery", "delivered", "pod_received", "invoiced", "paid"
DECLINED, CANCELLED, TONU = "declined", "cancelled", "tonu"

TRANSITIONS: Mapping[str, tuple[str, ...]] = {
    OFFERED: (EVALUATING, DECLINED, CANCELLED),
    EVALUATING: (COUNTERED, APPROVED, DECLINED, CANCELLED),
    COUNTERED: (EVALUATING, APPROVED, DECLINED, CANCELLED),
    APPROVED: (BOOKED, CANCELLED),
    BOOKED: (RATECON_RECEIVED, CANCELLED),
    RATECON_RECEIVED: (DISPATCHED, CANCELLED),
    DISPATCHED: (AT_PICKUP, TONU, CANCELLED),
    AT_PICKUP: (IN_TRANSIT, TONU),
    IN_TRANSIT: (AT_DELIVERY,),
    AT_DELIVERY: (DELIVERED,),
    DELIVERED: (POD_RECEIVED,),
    POD_RECEIVED: (INVOICED,),
    INVOICED: (PAID,),
    PAID: (),
    DECLINED: (),
    CANCELLED: (),
    TONU: (),
}
STATUSES: tuple[str, ...] = tuple(TRANSITIONS)
APPROVAL_ONLY = frozenset({APPROVED, BOOKED})
TERMINAL = frozenset({PAID, DECLINED, CANCELLED, TONU})
NEGOTIABLE = frozenset({OFFERED, EVALUATING, COUNTERED})
CONTRACTED = frozenset({BOOKED, RATECON_RECEIVED, DISPATCHED, AT_PICKUP, IN_TRANSIT, AT_DELIVERY, DELIVERED,
                        POD_RECEIVED, INVOICED, PAID})
NEEDS_CARRIER = CONTRACTED
IN_MOTION = frozenset({DISPATCHED, AT_PICKUP, IN_TRANSIT, AT_DELIVERY})
NEEDS_RATECON_APPROVAL = frozenset({DISPATCHED})
ACCEPT_RATE_KIND = "accept_rate"
CANCEL_KIND = "cancel_load"
RATECON_KIND = "approve_ratecon"


def is_legal(source: str, target: str) -> bool:
    """Tell whether the table has a move.

    Args:
        source: Current status.
        target: Wanted status.

    Returns:
        True when the move exists (approval rules not considered).
    """
    return target in TRANSITIONS.get(source, ())


def require_legal(source: str, target: str) -> None:
    """Refuse a move the table does not have.

    Args:
        source: Current status.
        target: Wanted status.

    Raises:
        Conflict: 409 illegal_transition.
    """
    if not is_legal(source, target):
        raise Conflict("illegal_transition", f"a load cannot move from {source} to {target}",
                       {"from": source, "to": target})


def approval_kind_for(source: str, target: str) -> str | None:
    """Name the approval a legal move needs, if any.

    Args:
        source: Current status.
        target: Wanted status.

    Returns:
        accept_rate for approved/booked, cancel_load for cancelling a contracted load, else None.
    """
    if target in APPROVAL_ONLY:
        return ACCEPT_RATE_KIND
    if target == CANCELLED and source in CONTRACTED:
        return CANCEL_KIND
    return None


def check_direct(source: str, target: str) -> None:
    """Check a move a person or import asks for directly (not through an approval).

    approved and booked always answer approval_required (from any status): they are never a direct move.

    Args:
        source: Current status.
        target: Wanted status.

    Raises:
        Conflict: 409 illegal_transition, or 409 approval_required naming the approval kind.
    """
    if target not in APPROVAL_ONLY:
        require_legal(source, target)
    kind = approval_kind_for(source, target)
    if kind is not None:
        raise Conflict("approval_required", f"moving a load to {target} needs an approved {kind}",
                       {"approval_kind": kind, "from": source, "to": target})
