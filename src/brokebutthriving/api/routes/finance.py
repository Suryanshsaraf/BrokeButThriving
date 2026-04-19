"""Finance routes — expenses, cashflows, check-ins, dashboard, simulation,
alerts, spending trends, peer comparison, recurring entries, data export,
SMS import, and semester projection.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from brokebutthriving.core.database import get_session
from brokebutthriving.models.entities import (
    CashflowEntry,
    DailyCheckIn,
    ExpenseEntry,
    Participant,
    RecurringEntry,
)
from brokebutthriving.schemas.api import (
    AlertItem,
    CashflowEntryCreate,
    CashflowEntryRead,
    DailyCheckInCreate,
    DailyCheckInRead,
    DashboardSummary,
    ExpenseBatchCreate,
    ExpenseEntryCreate,
    ExpenseEntryRead,
    MLInsightsResponse,
    MoodSpendingResponse,
    PeerComparisonResponse,
    RecurringEntryCreate,
    RecurringEntryRead,
    SemesterProjectionResponse,
    SimulationRequest,
    SimulationResponse,
    SmsImportRequest,
    SmsImportResponse,
    SpendingTrendsResponse,
)
from brokebutthriving.services.analytics import (
    build_dashboard,
    generate_alerts,
    get_mood_spending_trends,
    get_peer_comparison,
    get_semester_projection,
    get_spending_trends,
    simulate_plan,
)
from brokebutthriving.services.categorizer import auto_categorize, parse_sms_messages
from brokebutthriving.services.ml_scorer import score_participant

router = APIRouter(prefix="/participants/{participant_id}/finance", tags=["finance"])


def _ensure_participant(session: Session, participant_id: str) -> Participant:
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="Participant not found")
    return participant


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------

@router.post("/expenses", response_model=ExpenseEntryRead, status_code=201)
def create_expense(
    participant_id: str,
    payload: ExpenseEntryCreate,
    session: Session = Depends(get_session),
) -> ExpenseEntryRead:
    _ensure_participant(session, participant_id)
    # Auto-categorize if category is OTHER and merchant/note exist
    category = payload.category
    if category.value == "other" and (payload.merchant or payload.note):
        category = auto_categorize(payload.merchant, payload.note)
    entry = ExpenseEntry(participant_id=participant_id, **payload.model_dump(exclude={"category"}), category=category)
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return ExpenseEntryRead.model_validate(entry)


@router.post("/expenses/batch", response_model=list[ExpenseEntryRead], status_code=201)
def create_expenses_batch(
    participant_id: str,
    payload: ExpenseBatchCreate,
    session: Session = Depends(get_session),
) -> list[ExpenseEntryRead]:
    _ensure_participant(session, participant_id)
    created: list[ExpenseEntryRead] = []
    for item in payload.expenses:
        category = item.category
        if category.value == "other" and (item.merchant or item.note):
            category = auto_categorize(item.merchant, item.note)
        entry = ExpenseEntry(participant_id=participant_id, **item.model_dump(exclude={"category"}), category=category)
        session.add(entry)
        session.commit()
        session.refresh(entry)
        created.append(ExpenseEntryRead.model_validate(entry))
    return created


@router.get("/expenses", response_model=list[ExpenseEntryRead])
def list_expenses(
    participant_id: str,
    limit: int = 50,
    session: Session = Depends(get_session),
) -> list[ExpenseEntryRead]:
    _ensure_participant(session, participant_id)
    rows = session.exec(
        select(ExpenseEntry)
        .where(ExpenseEntry.participant_id == participant_id)
        .order_by(ExpenseEntry.occurred_at.desc())
        .limit(limit)
    ).all()
    return [ExpenseEntryRead.model_validate(row) for row in rows]


# ---------------------------------------------------------------------------
# Cashflows
# ---------------------------------------------------------------------------

@router.post("/cashflows", response_model=CashflowEntryRead, status_code=201)
def create_cashflow(
    participant_id: str,
    payload: CashflowEntryCreate,
    session: Session = Depends(get_session),
) -> CashflowEntryRead:
    _ensure_participant(session, participant_id)
    entry = CashflowEntry(participant_id=participant_id, **payload.model_dump())
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return CashflowEntryRead.model_validate(entry)


@router.get("/cashflows", response_model=list[CashflowEntryRead])
def list_cashflows(
    participant_id: str,
    limit: int = 50,
    session: Session = Depends(get_session),
) -> list[CashflowEntryRead]:
    _ensure_participant(session, participant_id)
    rows = session.exec(
        select(CashflowEntry)
        .where(CashflowEntry.participant_id == participant_id)
        .order_by(CashflowEntry.occurred_at.desc())
        .limit(limit)
    ).all()
    return [CashflowEntryRead.model_validate(row) for row in rows]


# ---------------------------------------------------------------------------
# Check-ins
# ---------------------------------------------------------------------------

@router.post("/checkins", response_model=DailyCheckInRead, status_code=201)
def create_checkin(
    participant_id: str,
    payload: DailyCheckInCreate,
    session: Session = Depends(get_session),
) -> DailyCheckInRead:
    _ensure_participant(session, participant_id)
    entry = DailyCheckIn(participant_id=participant_id, **payload.model_dump())
    session.add(entry)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Check-in already exists for {payload.check_in_date}. Only one check-in per day is allowed."
        )
    session.refresh(entry)
    return DailyCheckInRead.model_validate(entry)


# ---------------------------------------------------------------------------
# Dashboard & simulation
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_model=DashboardSummary)
def get_dashboard(
    participant_id: str,
    session: Session = Depends(get_session),
) -> DashboardSummary:
    _ensure_participant(session, participant_id)
    return build_dashboard(session, participant_id)


# ---------------------------------------------------------------------------
# ML Insights
# ---------------------------------------------------------------------------

@router.get("/ml-insights", response_model=MLInsightsResponse)
def get_ml_insights(
    participant_id: str,
    session: Session = Depends(get_session),
) -> MLInsightsResponse:
    """Return ML-powered financial insights: wellbeing score, hardship risk,
    bill difficulty risk, spending archetype, and spend ratios."""
    participant = _ensure_participant(session, participant_id)

    from brokebutthriving.models.entities import BehaviorSurvey
    expenses = session.exec(
        select(ExpenseEntry).where(ExpenseEntry.participant_id == participant_id)
    ).all()
    cashflows = session.exec(
        select(CashflowEntry).where(CashflowEntry.participant_id == participant_id)
    ).all()
    checkins = session.exec(
        select(DailyCheckIn).where(DailyCheckIn.participant_id == participant_id)
    ).all()
    surveys = session.exec(
        select(BehaviorSurvey).where(BehaviorSurvey.participant_id == participant_id)
    ).all()

    # Get risk_band and avg_daily_spend from the existing dashboard builder
    from brokebutthriving.services.analytics import build_dashboard
    dash = build_dashboard(session, participant_id)
    risk_band = dash.risk_band
    avg_daily_spend_14d = dash.average_daily_spend_14d

    insights = score_participant(
        participant=participant,
        expenses=list(expenses),
        cashflows=list(cashflows),
        checkins=list(checkins),
        surveys=list(surveys),
        risk_band=risk_band,
        avg_daily_spend_14d=avg_daily_spend_14d,
    )

    return MLInsightsResponse(
        model_available=insights.model_available,
        wellbeing_score=insights.wellbeing_score,
        wellbeing_band=insights.wellbeing_band,
        hardship_risk=insights.hardship_risk,
        hardship_band=insights.hardship_band,
        bill_difficulty_risk=insights.bill_difficulty_risk,
        bill_difficulty_band=insights.bill_difficulty_band,
        spending_archetype=insights.spending_archetype,
        archetype_confidence=insights.archetype_confidence,
        discretionary_ratio=insights.discretionary_ratio,
        spend_to_income_ratio=insights.spend_to_income_ratio,
        insights=insights.insights,
    )


@router.post("/simulation", response_model=SimulationResponse)
def run_simulation(
    participant_id: str,
    payload: SimulationRequest,
    session: Session = Depends(get_session),
) -> SimulationResponse:
    _ensure_participant(session, participant_id)
    return simulate_plan(session, participant_id, payload)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@router.get("/alerts", response_model=list[AlertItem])
def get_alerts(
    participant_id: str,
    session: Session = Depends(get_session),
) -> list[AlertItem]:
    _ensure_participant(session, participant_id)
    return generate_alerts(session, participant_id)


# ---------------------------------------------------------------------------
# Spending trends (for charts)
# ---------------------------------------------------------------------------

@router.get("/spending-trends", response_model=SpendingTrendsResponse)
def spending_trends(
    participant_id: str,
    days: int = 30,
    session: Session = Depends(get_session),
) -> SpendingTrendsResponse:
    _ensure_participant(session, participant_id)
    return get_spending_trends(session, participant_id, days)


@router.get("/mood-trends", response_model=MoodSpendingResponse)
def mood_trends(
    participant_id: str,
    days: int = 30,
    session: Session = Depends(get_session),
) -> MoodSpendingResponse:
    _ensure_participant(session, participant_id)
    return get_mood_spending_trends(session, participant_id, days)


# ---------------------------------------------------------------------------
# Peer comparison
# ---------------------------------------------------------------------------

@router.get("/peer-comparison", response_model=PeerComparisonResponse)
def peer_comparison(
    participant_id: str,
    session: Session = Depends(get_session),
) -> PeerComparisonResponse:
    _ensure_participant(session, participant_id)
    return get_peer_comparison(session, participant_id)


# ---------------------------------------------------------------------------
# Recurring entries
# ---------------------------------------------------------------------------

@router.post("/recurring", response_model=RecurringEntryRead, status_code=201)
def create_recurring(
    participant_id: str,
    payload: RecurringEntryCreate,
    session: Session = Depends(get_session),
) -> RecurringEntryRead:
    _ensure_participant(session, participant_id)
    entry = RecurringEntry(participant_id=participant_id, **payload.model_dump())
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return RecurringEntryRead.model_validate(entry)


@router.get("/recurring", response_model=list[RecurringEntryRead])
def list_recurring(
    participant_id: str,
    session: Session = Depends(get_session),
) -> list[RecurringEntryRead]:
    _ensure_participant(session, participant_id)
    rows = session.exec(
        select(RecurringEntry)
        .where(RecurringEntry.participant_id == participant_id)
        .where(RecurringEntry.is_active == True)
    ).all()
    return [RecurringEntryRead.model_validate(row) for row in rows]


@router.delete("/recurring/{recurring_id}", status_code=204)
def delete_recurring(
    participant_id: str,
    recurring_id: str,
    session: Session = Depends(get_session),
) -> None:
    _ensure_participant(session, participant_id)
    entry = session.get(RecurringEntry, recurring_id)
    if entry is None or entry.participant_id != participant_id:
        raise HTTPException(status_code=404, detail="Recurring entry not found")
    entry.is_active = False
    session.add(entry)
    session.commit()


# ---------------------------------------------------------------------------
# Data export (CSV)
# ---------------------------------------------------------------------------

@router.get("/export/csv")
def export_csv(
    participant_id: str,
    session: Session = Depends(get_session),
) -> StreamingResponse:
    _ensure_participant(session, participant_id)
    expenses = session.exec(
        select(ExpenseEntry)
        .where(ExpenseEntry.participant_id == participant_id)
        .order_by(ExpenseEntry.occurred_at.desc())
    ).all()
    cashflows = session.exec(
        select(CashflowEntry)
        .where(CashflowEntry.participant_id == participant_id)
        .order_by(CashflowEntry.occurred_at.desc())
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["type", "date", "category", "amount", "merchant", "note"])
    for e in expenses:
        writer.writerow(["expense", e.occurred_at.isoformat(), e.category.value, e.amount, e.merchant or "", e.note or ""])
    for c in cashflows:
        writer.writerow(["income", c.occurred_at.isoformat(), c.category.value, c.amount, "", c.note or ""])

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=bbt_export_{participant_id[:8]}.csv"},
    )


# ---------------------------------------------------------------------------
# SMS import
# ---------------------------------------------------------------------------

@router.post("/import/sms", response_model=SmsImportResponse)
def import_sms(
    participant_id: str,
    payload: SmsImportRequest,
    session: Session = Depends(get_session),
) -> SmsImportResponse:
    _ensure_participant(session, participant_id)
    parsed = parse_sms_messages(payload.sms_text)
    created: list[ExpenseEntryRead] = []
    errors: list[str] = []

    for item in parsed:
        try:
            entry = ExpenseEntry(
                participant_id=participant_id,
                occurred_at=datetime.now(UTC),
                amount=item["amount"],
                category=item["category"],
                merchant=item.get("merchant"),
                note=item.get("note"),
                source="sms_import",
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            created.append(ExpenseEntryRead.model_validate(entry))
        except Exception as exc:
            errors.append(f"Failed to import: {item.get('note', '')[:60]} — {exc}")

    return SmsImportResponse(parsed_count=len(parsed), expenses=created, errors=errors)


# ---------------------------------------------------------------------------
# Semester projection
# ---------------------------------------------------------------------------

@router.get("/semester-projection", response_model=SemesterProjectionResponse)
def semester_projection(
    participant_id: str,
    months: int = 4,
    session: Session = Depends(get_session),
) -> SemesterProjectionResponse:
    _ensure_participant(session, participant_id)
    return get_semester_projection(session, participant_id, months)
