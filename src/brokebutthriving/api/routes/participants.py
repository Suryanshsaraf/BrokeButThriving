from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from brokebutthriving.core.database import get_session
from brokebutthriving.models.entities import BehaviorSurvey, Participant
from brokebutthriving.schemas.api import (
    BehaviorSurveyCreate,
    BehaviorSurveyRead,
    ParticipantCreate,
    ParticipantRead,
    ParticipantUpdate,
)


router = APIRouter(prefix="/participants", tags=["participants"])


@router.get("", response_model=list[ParticipantRead])
def list_participants(session: Session = Depends(get_session)) -> list[Participant]:
    return session.exec(select(Participant).order_by(Participant.created_at.desc())).all()


@router.patch("/{participant_id}", response_model=ParticipantRead)
def update_participant(
    participant_id: str, payload: ParticipantUpdate, session: Session = Depends(get_session)
) -> Participant:
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="Participant not found")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(participant, key, value)

    session.add(participant)
    session.commit()
    session.refresh(participant)
    return participant


@router.post("", response_model=ParticipantRead, status_code=status.HTTP_201_CREATED)
def create_participant(
    payload: ParticipantCreate, session: Session = Depends(get_session)
) -> Participant:
    existing = session.exec(
        select(Participant).where(Participant.participant_code == payload.participant_code)
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Participant code already exists")

    participant = Participant.model_validate(payload)
    session.add(participant)
    session.commit()
    session.refresh(participant)
    return participant


@router.get("/{participant_id}", response_model=ParticipantRead)
def get_participant(participant_id: str, session: Session = Depends(get_session)) -> Participant:
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="Participant not found")
    return participant


@router.post(
    "/{participant_id}/survey",
    response_model=BehaviorSurveyRead,
    status_code=status.HTTP_201_CREATED,
)
def upsert_behavior_survey(
    participant_id: str,
    payload: BehaviorSurveyCreate,
    session: Session = Depends(get_session),
) -> BehaviorSurvey:
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="Participant not found")

    survey = session.exec(
        select(BehaviorSurvey).where(BehaviorSurvey.participant_id == participant_id)
    ).first()

    if survey is None:
        survey = BehaviorSurvey(participant_id=participant_id, **payload.model_dump())
        session.add(survey)
    else:
        for field, value in payload.model_dump().items():
            setattr(survey, field, value)

    session.commit()
    session.refresh(survey)
    return survey


@router.delete("/{participant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_participant(
    participant_id: str, session: Session = Depends(get_session)
) -> None:
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="Participant not found")
    session.delete(participant)
    session.commit()
