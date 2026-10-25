import os
import re
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# Thin Vapi proxy: the private key never leaves the server.
VAPI_URL = "https://api.vapi.ai"
E164 = re.compile(r"^\+[1-9]\d{7,14}$")
router = APIRouter(prefix="/api/voice")
_by_key: Dict[str, str] = {}


def _headers() -> Dict[str, str]:
    key = os.environ.get("VAPI_PRIVATE_KEY")
    if not key or not os.environ.get("VAPI_PHONE_NUMBER_ID"):
        raise HTTPException(503, "Live calling is not configured on the server")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


async def _vapi(method: str, path: str, **kw) -> Any:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.request(method, VAPI_URL + path, headers=_headers(), **kw)
    if r.is_error:
        raise HTTPException(502 if r.status_code >= 500 else r.status_code, f"Vapi {r.status_code}: {r.text[:300]}")
    return r.json() if r.content else None


def _mask(n: Optional[str]) -> str:
    return f"{n[:2]} •••-•••-{n[-4:]}" if n and len(n) > 6 else ""


class Contact(BaseModel):
    id: str
    name: str
    role: str
    company: Optional[str] = None
    phone: Optional[str] = ""


class Task(BaseModel):
    type: str
    objective: str
    facts: List[str] = []
    allowedOutcomes: List[str] = []
    firstMessage: str
    schema_: Dict[str, Any] = Field(alias="schema")


class CallRequest(BaseModel):
    contact: Contact
    task: Task
    linked: Optional[Dict[str, Any]] = None
    idempotencyKey: str


def _assistant(req: CallRequest) -> Dict[str, Any]:
    t, c = req.task, req.contact
    who = f"{c.name}{' of ' + c.company if c.company else ''} ({c.role})"
    prompt = (
        f"You are FreightOS, the AI dispatch assistant for Demo West Freight, on a phone call with {who}.\n"
        f"Objective: {t.objective}\nFacts you may share:\n- " + "\n- ".join(t.facts) +
        f"\nAllowed outcomes: {', '.join(t.allowedOutcomes)}.\n"
        "Rules: keep turns short and natural, ask one question at a time, read key times back to confirm, "
        "never invent facts or agree to anything outside the objective. If asked, say you are an AI assistant. "
        "Once the objective is reached or clearly refused, thank them and end the call."
    )
    return {
        "name": f"FreightOS {t.type}"[:40],
        "firstMessage": t.firstMessage,
        "model": {"provider": "openai", "model": "gpt-4.1-mini", "temperature": 0.3, "messages": [{"role": "system", "content": prompt}]},
        "voice": {"provider": "vapi", "voiceId": "Elliot"},
        "transcriber": {"provider": "deepgram", "model": "nova-3", "language": "en"},
        "endCallFunctionEnabled": True,
        "maxDurationSeconds": 240,
        "monitorPlan": {"controlEnabled": True, "listenEnabled": True},
        "analysisPlan": {
            "summaryPrompt": "Summarize the call outcome in one sentence.",
            "structuredDataPrompt": "Extract the outcome fields from the call transcript. Use null when unknown.",
            "structuredDataSchema": t.schema_,
        },
    }


@router.get("/config")
async def config():
    return {
        "configured": bool(os.environ.get("VAPI_PRIVATE_KEY") and os.environ.get("VAPI_PHONE_NUMBER_ID")),
        "demoDriverPhone": _mask(os.environ.get("DEMO_DRIVER_PHONE")),
    }


@router.get("/validate")
async def validate():
    n = await _vapi("GET", f"/phone-number/{os.environ.get('VAPI_PHONE_NUMBER_ID')}")
    return {"ok": True, "number": n.get("number"), "provider": n.get("provider"), "name": n.get("name"), "status": n.get("status")}


@router.post("/calls")
async def create_call(req: CallRequest):
    if req.idempotencyKey in _by_key:
        return {"id": _by_key[req.idempotencyKey], "duplicate": True}
    phone = (req.contact.phone or "").strip()
    if not phone and req.contact.role == "driver":
        phone = os.environ.get("DEMO_DRIVER_PHONE", "")
    if not E164.match(phone):
        raise HTTPException(400, f"No valid phone number for {req.contact.name}. Add one in AI settings → Calling.")
    payload = {
        "phoneNumberId": os.environ.get("VAPI_PHONE_NUMBER_ID"),
        "customer": {"number": phone, "name": req.contact.name[:40]},
        "assistant": _assistant(req),
        "metadata": {"linked": req.linked or {}, "task": req.task.type},
    }
    _headers()
    call = await _vapi("POST", "/call", json=payload)
    _by_key[req.idempotencyKey] = call["id"]
    return {"id": call["id"], "status": call.get("status"), "to": _mask(phone)}


def _transcript(call: Dict[str, Any]) -> List[Dict[str, str]]:
    msgs = (call.get("artifact") or {}).get("messages") or call.get("messages") or []
    out = []
    for m in msgs:
        role = m.get("role")
        if role in ("bot", "assistant") and m.get("message"):
            out.append({"role": "ai", "text": m["message"]})
        elif role == "user" and m.get("message"):
            out.append({"role": "contact", "text": m["message"]})
    return out


@router.get("/calls/{call_id}")
async def get_call(call_id: str):
    call = await _vapi("GET", f"/call/{call_id}")
    analysis = call.get("analysis") or {}
    return {
        "id": call_id,
        "status": call.get("status"),
        "endedReason": call.get("endedReason"),
        "transcript": _transcript(call),
        "summary": analysis.get("summary"),
        "structuredData": analysis.get("structuredData"),
        "listenUrl": (call.get("monitor") or {}).get("listenUrl"),
    }


@router.post("/calls/{call_id}/end")
async def end_call(call_id: str):
    call = await _vapi("GET", f"/call/{call_id}")
    control = (call.get("monitor") or {}).get("controlUrl")
    if control:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(control, json={"type": "end-call"})
        if not r.is_error:
            return {"ok": True}
    await _vapi("DELETE", f"/call/{call_id}")
    return {"ok": True}
