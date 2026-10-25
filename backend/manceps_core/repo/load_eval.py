"""Run the load economics for a load and store the evaluation on it (audited, on the load's timeline)."""

from __future__ import annotations

from typing import Any

from ..loads import machine
from ..loads.evaluate import DEFAULT_MPG, DieselLookup, MilesLookup, evaluate
from ..mongo import Doc, MongoDb
from .carriers import get_carrier
from .errors import Conflict, NotFound
from .load_status import record_event, transition
from .loads import LOADS, REF_TYPE, get_load
from .store import WriteContext, update


def _carrier(db: MongoDb, load: Doc) -> Doc | None:
    """Load the load's carrier if it is still live.

    Args:
        db: Firm database.
        load: The load.

    Returns:
        The carrier, or None.
    """
    if load.get("carrier_id") is None:
        return None
    try:
        return get_carrier(db, load["carrier_id"])
    except NotFound:
        return None


def evaluate_load(db: MongoDb, ctx: WriteContext, load_id: Any, miles: MilesLookup | None,
                  diesel: DieselLookup | None, mpg: float = DEFAULT_MPG) -> Doc:
    """Evaluate a load; an offered load moves to evaluating first.

    Looked-up loaded miles are stored on the load when it had none (the source is kept in the evaluation).

    Args:
        db: Firm database.
        ctx: Writer.
        load_id: Load id.
        miles: Routing lookup, or None when not configured.
        diesel: Diesel lookup, or None when not configured.
        mpg: Fuel economy.

    Returns:
        The load with its new `evaluation`.

    Raises:
        NotFound: If the load is not live.
        Conflict: 409 load_closed for paid, declined, cancelled or TONU loads.
    """
    load = get_load(db, load_id)
    if load.get("status") in machine.TERMINAL:
        raise Conflict("load_closed", "this load is closed", {"status": load["status"]})
    result = evaluate(load, _carrier(db, load), miles, diesel, mpg)
    if load.get("status") == machine.OFFERED:
        load = transition(db, ctx, load["_id"], machine.EVALUATING)
    changes: dict[str, Any] = {"evaluation": {**result, "mpg": mpg, "at": ctx.now()}}
    econ = result.get("economics")
    if load.get("loaded_miles") is None and isinstance(econ, dict):
        changes["loaded_miles"] = econ["loaded_miles"]  # pyright: ignore[reportUnknownMemberType]
    after = update(db, ctx, LOADS, REF_TYPE, load, changes)
    record_event(db, ctx, after, "evaluated", {"verdict": result["verdict"]})
    return after
