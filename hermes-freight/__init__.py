"""hermes-freight: back-office tools and approval rules for independent freight dispatchers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import broker_check, brokers, carriers, loads, policy, ratecon, reference, schemas, weather

TOOLSET = "freight"

_TOOLS = (
    (schemas.CARRIER_UPSERT, carriers.carrier_upsert),
    (schemas.CARRIER_GET, carriers.carrier_get),
    (schemas.CARRIER_LIST, carriers.carrier_list),
    (schemas.BROKER_CHECK, broker_check.broker_check),
    (schemas.BROKER_REMEMBER, brokers.broker_remember),
    (schemas.BROKER_RECALL, brokers.broker_recall),
    (schemas.RATECON_READ, ratecon.ratecon_read),
    (schemas.WEATHER_ALERTS, weather.weather_alerts),
    (schemas.LOAD_EVALUATE, loads.load_evaluate),
    (schemas.BROKER_SEARCH, reference.broker_search),
)


def register(ctx: Any) -> None:
    """Register freight tools, the approval hook, and bundled skills with Hermes.

    Args:
        ctx: Hermes plugin context.
    """
    for schema, handler in _TOOLS:
        ctx.register_tool(name=schema["name"], toolset=TOOLSET, schema=schema, handler=handler)
    ctx.register_hook("pre_tool_call", policy.pre_tool_call)
    skills_dir = Path(__file__).parent / "skills"
    for child in sorted(skills_dir.iterdir()):
        skill_md = child / "SKILL.md"
        if child.is_dir() and skill_md.exists():
            ctx.register_skill(child.name, skill_md)
