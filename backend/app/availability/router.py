from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts.dependencies import get_current_psychologist_id
from app.availability import service
from app.availability.schemas import (
    AvailabilityRuleInput,
    AvailabilityRuleRead,
    AvailabilitySlotRead,
    PublicAvailabilityRead,
)
from app.core.database import get_db

router = APIRouter(prefix="/api/v1", tags=["availability"])
DatabaseSession = Annotated[Session, Depends(get_db)]
AuthenticatedPsychologist = Annotated[UUID, Depends(get_current_psychologist_id)]


@router.get(
    "/accounts/me/availability-rules", response_model=list[AvailabilityRuleRead]
)
def list_availability_rules(
    session: DatabaseSession, psychologist_id: AuthenticatedPsychologist
) -> list[AvailabilityRuleRead]:
    return service.list_rules(session, psychologist_id)


@router.post(
    "/accounts/me/availability-rules",
    response_model=AvailabilityRuleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_availability_rule(
    data: AvailabilityRuleInput,
    session: DatabaseSession,
    psychologist_id: AuthenticatedPsychologist,
) -> AvailabilityRuleRead:
    try:
        return service.create_rule(session, psychologist_id, data)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Psychologist not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except service.AvailabilityConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Availability rule conflicts with existing data") from exc


@router.put(
    "/accounts/me/availability-rules/{rule_id}", response_model=AvailabilityRuleRead
)
def update_availability_rule(
    rule_id: UUID,
    data: AvailabilityRuleInput,
    session: DatabaseSession,
    psychologist_id: AuthenticatedPsychologist,
) -> AvailabilityRuleRead:
    try:
        rule = service.update_rule(session, psychologist_id, rule_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except service.AvailabilityConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Availability rule conflicts with existing data") from exc
    if rule is None:
        raise HTTPException(status_code=404, detail="Active availability rule not found")
    return rule


@router.delete("/accounts/me/availability-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_availability_rule(
    rule_id: UUID,
    session: DatabaseSession,
    psychologist_id: AuthenticatedPsychologist,
) -> Response:
    if not service.retire_rule(session, psychologist_id, rule_id):
        raise HTTPException(status_code=404, detail="Active availability rule not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/psychologists/{public_id}/availability", response_model=PublicAvailabilityRead
)
def get_public_availability(
    public_id: str,
    session: DatabaseSession,
    from_time: Annotated[datetime, Query(alias="from")],
    to_time: Annotated[datetime, Query(alias="to")],
) -> PublicAvailabilityRead:
    try:
        result = service.public_slots(session, public_id, from_time, to_time)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except service.AvailabilityConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Psychologist not found")
    psychologist, slots = result
    return PublicAvailabilityRead(
        psychologist_id=psychologist.public_id,
        time_zone=psychologist.time_zone,
        slots=[
            AvailabilitySlotRead(
                id=slot.id,
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
                price_minor=slot.price_minor,
                currency=slot.currency,
            )
            for slot in slots
        ],
    )
