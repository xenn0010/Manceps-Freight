"""Drivers and trucks of the firm's carriers: list, create, read, update, delete (soft)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response
from pydantic import AwareDatetime, BaseModel, Field

from manceps_core.mongo import Doc
from manceps_core.repo import fleet

from ..auditing import write_context
from ..auth.models import StrictModel
from ..auth.principal import FirmDispatcher, FirmIdempotency, FirmViewer
from ..context import firm_db
from ..pagination import DEFAULT_LIMIT, CursorQuery, LimitQuery, Page, decode_cursor, page_of
from .common import ID_MAX, Code, ConsentState, Email, Name, Number, Phone, RecordId, consent_state, text_of

router = APIRouter(prefix="/v1", tags=["fleet"])

DriverStatus = Literal["active", "inactive"]
CarrierRef = Annotated[str, Field(max_length=ID_MAX, description="Id of a carrier of this firm.")]
CarrierFilter = Annotated[str | None, Query(max_length=ID_MAX)]


class DriverFields(StrictModel):
    """Writable driver fields (consent is not writable here)."""

    phone: Phone | None = None
    email: Email | None = None
    status: DriverStatus | None = None
    license_state: Code | None = None
    license_expires_at: AwareDatetime | None = None


class DriverCreate(DriverFields):
    """A new driver of one of the firm's carriers."""

    carrier_id: CarrierRef
    name: Name


class DriverPatch(DriverFields):
    """Driver changes; null removes an optional field."""

    carrier_id: CarrierRef | None = None
    name: Name | None = None


class Driver(BaseModel):
    """A driver."""

    id: str
    carrier_id: str
    name: str | None
    phone: str | None
    email: str | None
    status: str
    license_state: str | None
    license_expires_at: datetime | None
    consent: ConsentState | None
    created_at: datetime
    updated_at: datetime


class TruckFields(StrictModel):
    """Writable truck fields."""

    equipment: Code | None = None
    vin: Number | None = None
    plate: Number | None = None
    plate_state: Code | None = None
    max_weight_lbs: int | None = None


class TruckCreate(TruckFields):
    """A new truck of one of the firm's carriers."""

    carrier_id: CarrierRef
    unit: Name


class TruckPatch(TruckFields):
    """Truck changes; null removes an optional field."""

    carrier_id: CarrierRef | None = None
    unit: Name | None = None


class Truck(BaseModel):
    """A truck."""

    id: str
    carrier_id: str
    unit: str
    equipment: str | None
    vin: str | None
    plate: str | None
    plate_state: str | None
    max_weight_lbs: int | None
    created_at: datetime
    updated_at: datetime


def render_driver(doc: Doc) -> Driver:
    """Render a driver.

    Args:
        doc: Driver document.

    Returns:
        The model.
    """
    return Driver(id=str(doc["_id"]), carrier_id=str(doc["carrier_id"]), name=text_of(doc, "name"),
                  phone=text_of(doc, "phone"), email=text_of(doc, "email"), status=str(doc.get("status")),
                  license_state=text_of(doc, "license_state"), license_expires_at=doc.get("license_expires_at"),
                  consent=consent_state(doc.get("consent")), created_at=doc["created_at"],
                  updated_at=doc["updated_at"])


def render_truck(doc: Doc) -> Truck:
    """Render a truck.

    Args:
        doc: Truck document.

    Returns:
        The model.
    """
    weight = doc.get("max_weight_lbs")
    return Truck(id=str(doc["_id"]), carrier_id=str(doc["carrier_id"]), unit=str(doc["unit"]),
                 equipment=text_of(doc, "equipment"), vin=text_of(doc, "vin"), plate=text_of(doc, "plate"),
                 plate_state=text_of(doc, "plate_state"), max_weight_lbs=weight if isinstance(weight, int) else None,
                 created_at=doc["created_at"], updated_at=doc["updated_at"])


@router.get("/drivers", operation_id="drivers_list", summary="List drivers")
def drivers_list(request: Request, principal: FirmViewer, carrier_id: CarrierFilter = None,
                 status: DriverStatus | None = None, limit: LimitQuery = DEFAULT_LIMIT,
                 cursor: CursorQuery = None) -> Page[Driver]:
    """List live drivers, oldest first.

    Args:
        request: Incoming request.
        principal: Firm member.
        carrier_id: Only drivers of this carrier.
        status: Only this status.
        limit: Page size.
        cursor: Cursor from the previous page.

    Returns:
        One page.

    Raises:
        ApiError: 400 invalid_cursor.
    """
    docs = fleet.list_records(firm_db(request, principal), "driver", {"carrier_id": carrier_id, "status": status},
                              decode_cursor(cursor), limit)
    return page_of(docs, limit, render_driver)


@router.post("/drivers", status_code=201, operation_id="drivers_create", summary="Add a driver")
def drivers_create(body: DriverCreate, request: Request, principal: FirmDispatcher,
                   guard: FirmIdempotency) -> Driver:
    """Add a driver to a carrier of this firm (audited).

    Args:
        body: Driver fields.
        request: Incoming request.
        principal: Dispatcher or owner.
        guard: Idempotency guard.

    Returns:
        The driver.

    Raises:
        RepoError: 409 duplicate_phone, 422 on invalid values or an unknown carrier.
    """
    doc = fleet.create_driver(firm_db(request, principal), write_context(request, principal),
                              body.model_dump(exclude_unset=True))
    driver = render_driver(doc)
    guard.save(201, driver.model_dump(mode="json"))
    return driver


@router.get("/drivers/{driver_id}", operation_id="drivers_get", summary="Get a driver")
def drivers_get(driver_id: RecordId, request: Request, principal: FirmViewer) -> Driver:
    """Return one live driver.

    Args:
        driver_id: Driver id.
        request: Incoming request.
        principal: Firm member.

    Returns:
        The driver.

    Raises:
        RepoError: 404.
    """
    return render_driver(fleet.get_record(firm_db(request, principal), "driver", driver_id))


@router.patch("/drivers/{driver_id}", operation_id="drivers_update", summary="Update a driver")
def drivers_update(driver_id: RecordId, body: DriverPatch, request: Request, principal: FirmDispatcher) -> Driver:
    """Change a driver (audited).

    Args:
        driver_id: Driver id.
        body: Changes.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        The driver.

    Raises:
        RepoError: 404, 409 duplicate_phone, 422.
    """
    doc = fleet.update_record(firm_db(request, principal), write_context(request, principal), "driver", driver_id,
                              body.model_dump(exclude_unset=True))
    return render_driver(doc)


@router.delete("/drivers/{driver_id}", status_code=204, operation_id="drivers_delete", summary="Delete a driver")
def drivers_delete(driver_id: RecordId, request: Request, principal: FirmDispatcher) -> Response:
    """Soft-delete a driver; the phone number can be used again.

    Args:
        driver_id: Driver id.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        204.

    Raises:
        RepoError: 404.
    """
    fleet.delete_record(firm_db(request, principal), write_context(request, principal), "driver", driver_id)
    return Response(status_code=204)


@router.get("/trucks", operation_id="trucks_list", summary="List trucks")
def trucks_list(request: Request, principal: FirmViewer, carrier_id: CarrierFilter = None,
                limit: LimitQuery = DEFAULT_LIMIT, cursor: CursorQuery = None) -> Page[Truck]:
    """List live trucks, oldest first.

    Args:
        request: Incoming request.
        principal: Firm member.
        carrier_id: Only trucks of this carrier.
        limit: Page size.
        cursor: Cursor from the previous page.

    Returns:
        One page.

    Raises:
        ApiError: 400 invalid_cursor.
    """
    docs = fleet.list_records(firm_db(request, principal), "truck", {"carrier_id": carrier_id},
                              decode_cursor(cursor), limit)
    return page_of(docs, limit, render_truck)


@router.post("/trucks", status_code=201, operation_id="trucks_create", summary="Add a truck")
def trucks_create(body: TruckCreate, request: Request, principal: FirmDispatcher, guard: FirmIdempotency) -> Truck:
    """Add a truck to a carrier of this firm (audited).

    Args:
        body: Truck fields.
        request: Incoming request.
        principal: Dispatcher or owner.
        guard: Idempotency guard.

    Returns:
        The truck.

    Raises:
        RepoError: 409 duplicate_vin, 422 on invalid values or an unknown carrier.
    """
    doc = fleet.create_truck(firm_db(request, principal), write_context(request, principal),
                             body.model_dump(exclude_unset=True))
    truck = render_truck(doc)
    guard.save(201, truck.model_dump(mode="json"))
    return truck


@router.get("/trucks/{truck_id}", operation_id="trucks_get", summary="Get a truck")
def trucks_get(truck_id: RecordId, request: Request, principal: FirmViewer) -> Truck:
    """Return one live truck.

    Args:
        truck_id: Truck id.
        request: Incoming request.
        principal: Firm member.

    Returns:
        The truck.

    Raises:
        RepoError: 404.
    """
    return render_truck(fleet.get_record(firm_db(request, principal), "truck", truck_id))


@router.patch("/trucks/{truck_id}", operation_id="trucks_update", summary="Update a truck")
def trucks_update(truck_id: RecordId, body: TruckPatch, request: Request, principal: FirmDispatcher) -> Truck:
    """Change a truck (audited).

    Args:
        truck_id: Truck id.
        body: Changes.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        The truck.

    Raises:
        RepoError: 404, 409 duplicate_vin, 422.
    """
    doc = fleet.update_record(firm_db(request, principal), write_context(request, principal), "truck", truck_id,
                              body.model_dump(exclude_unset=True))
    return render_truck(doc)


@router.delete("/trucks/{truck_id}", status_code=204, operation_id="trucks_delete", summary="Delete a truck")
def trucks_delete(truck_id: RecordId, request: Request, principal: FirmDispatcher) -> Response:
    """Soft-delete a truck; its VIN can be used again.

    Args:
        truck_id: Truck id.
        request: Incoming request.
        principal: Dispatcher or owner.

    Returns:
        204.

    Raises:
        RepoError: 404.
    """
    fleet.delete_record(firm_db(request, principal), write_context(request, principal), "truck", truck_id)
    return Response(status_code=204)
