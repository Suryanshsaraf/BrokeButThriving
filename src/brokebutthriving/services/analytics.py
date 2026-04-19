from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from sqlmodel import Session, func, select

from brokebutthriving.models.entities import CashflowEntry, DailyCheckIn, ExpenseEntry, Participant
from brokebutthriving.schemas.api import (
    AlertItem,
    CategoryBreakdown,
    DailySpendPoint,
    DashboardSummary,
    MoodReading,
    MoodSpendingResponse,
    PeerComparisonItem,
    PeerComparisonResponse,
    SemesterProjectionPoint,
    SemesterProjectionResponse,
    SimulationRequest,
    SimulationResponse,
    SpendingTrendsResponse,
)


def _coerce_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _month_start(today: date) -> date:
    return today.replace(day=1)


def _latest_reported_balance(
    participant: Participant,
    expenses: list[ExpenseEntry],
    cashflows: list[CashflowEntry],
    checkins: list[DailyCheckIn],
) -> float:
    if checkins:
        latest = sorted(checkins, key=lambda item: item.check_in_date)[-1]
        if latest.closing_balance is not None:
            return latest.closing_balance

    baseline = participant.starting_balance
    expense_total = sum(item.amount for item in expenses)
    inflow_total = sum(item.amount for item in cashflows)
    return baseline + inflow_total - expense_total


def _risk_from_projection(balance: float, daily_spend: float, days_left: int) -> tuple[float, str]:
    if days_left <= 0:
        return 0.0, "stable"

    required_balance = daily_spend * days_left
    if required_balance <= 0:
        return 0.0, "stable"

    shortfall_ratio = max(0.0, (required_balance - balance) / required_balance)
    risk_score = round(min(1.0, shortfall_ratio), 3)

    if risk_score >= 0.75:
        return risk_score, "critical"
    if risk_score >= 0.45:
        return risk_score, "elevated"
    if risk_score >= 0.2:
        return risk_score, "watch"
    return risk_score, "stable"


def _project_end_balance(balance: float, average_daily_spend: float, horizon_days: int) -> float:
    return round(balance - (average_daily_spend * horizon_days), 2)


def build_dashboard(session: Session, participant_id: str) -> DashboardSummary:
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise ValueError("Participant not found")

    expenses = session.exec(
        select(ExpenseEntry).where(ExpenseEntry.participant_id == participant_id)
    ).all()
    cashflows = session.exec(
        select(CashflowEntry).where(CashflowEntry.participant_id == participant_id)
    ).all()
    checkins = session.exec(
        select(DailyCheckIn).where(DailyCheckIn.participant_id == participant_id)
    ).all()

    today = date.today()
    start_of_month = _month_start(today)
    recent_cutoff = datetime.now(UTC) - timedelta(days=14)

    current_month_spend = round(
        sum(item.amount for item in expenses if _coerce_utc(item.occurred_at).date() >= start_of_month),
        2,
    )
    current_month_inflow = round(
        sum(item.amount for item in cashflows if _coerce_utc(item.occurred_at).date() >= start_of_month),
        2,
    )

    recent_expenses = [item for item in expenses if _coerce_utc(item.occurred_at) >= recent_cutoff]
    avg_daily_spend_14d = round(
        sum(item.amount for item in recent_expenses) / max(1, 14),
        2,
    )

    current_balance = round(_latest_reported_balance(participant, expenses, cashflows, checkins), 2)
    days_left = max(1, monthrange(today.year, today.month)[1] - today.day + 1)
    risk_score, risk_band = _risk_from_projection(current_balance, avg_daily_spend_14d, days_left)

    # Tactical Calculations & AI Forecasting
    start_of_week = today - timedelta(days=today.weekday())
    today_spend = round(sum(item.amount for item in expenses if _coerce_utc(item.occurred_at).date() == today), 2)
    current_week_spend = round(sum(item.amount for item in expenses if _coerce_utc(item.occurred_at).date() >= start_of_week), 2)

    monthly_budget = participant.monthly_budget
    # "Organic" budget shrinking: we calculate the limit based on what was remaining at the start of the day
    # so that spending today doesn't unfairly shrink today's limit.
    # We also explicitly include extra cashflows to increase the allowance capacity dynamically.
    effective_budget = monthly_budget + max(0.0, current_month_inflow - (participant.monthly_income or 0)) 
    spend_before_today = max(0.0, current_month_spend - today_spend)
    dynamic_budget_remaining_start_of_day = max(0.0, effective_budget - spend_before_today)
    
    target_daily_budget = round(dynamic_budget_remaining_start_of_day / days_left, 2) if effective_budget > 0 and days_left > 0 else 0
    
    days_left_in_week = 7 - today.weekday()
    target_weekly_budget = round(target_daily_budget * days_left_in_week, 2) if effective_budget > 0 else 0
    days_elapsed = max(1, monthrange(today.year, today.month)[1] - days_left)
    projected_days_remaining = 99 if avg_daily_spend_14d == 0 else max(0, int(current_balance / avg_daily_spend_14d))

    dynamic_budget_remaining = max(0.0, effective_budget - current_month_spend)
    budget_remaining = round(effective_budget - current_month_spend, 2)
    short_term_forecasts: list[str] = []

    # ── Velocity-adjusted limit (organic shrinking) ──────────────────────────
    velocity_offset = 0.0
    if avg_daily_spend_14d > target_daily_budget > 0:
        velocity_offset = (avg_daily_spend_14d - target_daily_budget) * 0.2
        conservative_limit = max(0, target_daily_budget - velocity_offset)
        if velocity_offset > 50:
            short_term_forecasts.append(
                f"Your 14-day velocity is ₹{avg_daily_spend_14d:.0f}/day — {((avg_daily_spend_14d/target_daily_budget-1)*100):.0f}% above your ₹{target_daily_budget:.0f} limit. "
                f"Tactical ceiling: ₹{conservative_limit:.0f}/day to protect end-of-month runway."
            )

    # ── Today vs limit ───────────────────────────────────────────────────────
    if target_daily_budget > 0 and today_spend > target_daily_budget:
        overage = today_spend - target_daily_budget
        new_safe_daily = round((dynamic_budget_remaining - overage) / max(1, days_left - 1), 0)
        if new_safe_daily > 0:
            short_term_forecasts.append(
                f"Today: ₹{today_spend:.0f} spent (₹{overage:.0f} over limit). "
                f"Spend ≤ ₹{new_safe_daily:.0f}/day for the next {days_left - 1} days to recover."
            )
        else:
            short_term_forecasts.append(
                "🚨 Budget fully exhausted for this month. Zero headroom left — defer all non-essential purchases."
            )
    elif target_daily_budget > 0:
        unspent = target_daily_budget - today_spend
        if today_spend == 0:
            short_term_forecasts.append(
                f"Zero spend today! That's a full ₹{target_daily_budget:.0f} saved vs your daily limit. "
                f"Your current runway extends to {projected_days_remaining} days."
            )
        elif today_spend < target_daily_budget * 0.5:
            short_term_forecasts.append(
                f"Great discipline today — ₹{unspent:.0f} unused from your ₹{target_daily_budget:.0f} allowance. "
                f"Every surplus day extends your month-end runway."
            )
        else:
            short_term_forecasts.append(
                f"Target: ₹{target_daily_budget:.0f}/day → you've used ₹{today_spend:.0f} so far. "
                f"₹{unspent:.0f} remaining today to stay on track for ₹{monthly_budget:.0f}/month."
            )

    # ── Weekly velocity ──────────────────────────────────────────────────────
    if current_week_spend > target_weekly_budget * 0.8 and days_left_in_week > 2 and target_weekly_budget > 0:
        short_term_forecasts.append(
            f"Weekly pace: ₹{current_week_spend:.0f} of ₹{target_weekly_budget:.0f} used with "
            f"{days_left_in_week} days left. You need ≤ ₹{(target_weekly_budget - current_week_spend) / max(1, days_left_in_week):.0f}/day to stay in band."
        )

    # ── Month progress ───────────────────────────────────────────────────────
    days_elapsed = max(1, monthrange(today.year, today.month)[1] - days_left)
    expected_spend_by_now = (monthly_budget / max(1, monthrange(today.year, today.month)[1])) * days_elapsed if monthly_budget > 0 else 0
    if expected_spend_by_now > 0 and current_month_spend > expected_spend_by_now:
        lead_pct = ((current_month_spend - expected_spend_by_now) / expected_spend_by_now) * 100
        short_term_forecasts.append(
            f"Spend pace is running {lead_pct:.0f}% ahead of the calendar — you've used ₹{current_month_spend:.0f} "
            f"when the expected pace projects ₹{expected_spend_by_now:.0f} by day {days_elapsed}."
        )
    elif expected_spend_by_now > 0 and current_month_spend < expected_spend_by_now * 0.7:
        saving_vs_pace = expected_spend_by_now - current_month_spend
        short_term_forecasts.append(
            f"You're ₹{saving_vs_pace:.0f} under the expected monthly pace — excellent! "
            f"At this rate you'll finish the month with ₹{budget_remaining:.0f} to spare."
        )

    # ── Income gap check ─────────────────────────────────────────────────────
    monthly_income = participant.monthly_income or 0
    if monthly_income > 0 and current_month_spend > monthly_income * 0.9:
        gap = current_month_spend - monthly_income
        if gap > 0:
            short_term_forecasts.append(
                f"⚠️ You've spent ₹{current_month_spend:.0f} against a ₹{monthly_income:.0f} monthly income — "
                f"a ₹{gap:.0f} deficit that could be drawing down savings."
            )
        else:
            short_term_forecasts.append(
                f"Spending-to-income ratio is high at {(current_month_spend/monthly_income*100):.0f}%. "
                f"Aim to keep this under 80% (₹{monthly_income*0.8:.0f}) for healthy savings."
            )

    totals_by_category: dict[str, float] = defaultdict(float)
    for item in expenses:
        if _coerce_utc(item.occurred_at).date() >= start_of_month:
            totals_by_category[item.category.value] += item.amount

    ordered_categories = sorted(totals_by_category.items(), key=lambda pair: pair[1], reverse=True)
    top_categories = [
        CategoryBreakdown(
            category=category,
            total_spend=round(total, 2),
            share_of_spend=round(total / current_month_spend, 3) if current_month_spend else 0,
        )
        for category, total in ordered_categories[:4]
    ]

    projected_days_remaining = 99 if avg_daily_spend_14d == 0 else max(0, int(current_balance / avg_daily_spend_14d))

    highlights: list[str] = []

    # ── Top category insight ─────────────────────────────────────────────────
    if top_categories:
        top = top_categories[0]
        pct_share = round(top.share_of_spend * 100)
        highlights.append(
            f"{top.category.title()} is your biggest spend this month at ₹{top.total_spend:.0f} ({pct_share}% of total). "
            + ("Look for ways to trim here first." if pct_share > 40 else "Keep monitoring this category.")
        )
        # Second category if significant
        if len(top_categories) >= 2 and top_categories[1].share_of_spend > 0.2:
            cat2 = top_categories[1]
            highlights.append(
                f"{cat2.category.title()} is your #2 spend at ₹{cat2.total_spend:.0f} ({round(cat2.share_of_spend*100)}%). "
                "Combined, your top 2 categories drive most of your burn."
            )

    # ── Risk / runway insights ───────────────────────────────────────────────
    if risk_band == "critical":
        highlights.append(
            f"🚨 Critical risk: at ₹{avg_daily_spend_14d:.0f}/day you'll exhaust funds in ~{projected_days_remaining} days — "
            f"{max(0, days_left - projected_days_remaining)} days before month-end. "
            "Ask the Copilot for an emergency simulation now."
        )
    elif risk_band == "elevated":
        shortfall = round(avg_daily_spend_14d * days_left - current_balance)
        highlights.append(
            f"⚠️ Elevated risk: your current velocity creates a projected ₹{max(0, shortfall):.0f} shortfall this month. "
            f"Reduce daily spend to ₹{target_daily_budget:.0f} to close the gap."
        )
    elif risk_band == "watch":
        highlights.append(
            f"🟡 On watch: runway is {projected_days_remaining} days at current pace. "
            f"You have {days_left} days left — stay within ₹{target_daily_budget:.0f}/day to remain safe."
        )
    elif risk_band == "stable" and projected_days_remaining > days_left + 10:
        highlights.append(
            f"✅ Healthy runway: your balance can sustain {projected_days_remaining} days at current spend — "
            f"{projected_days_remaining - days_left} days beyond month-end. Great buffer!"
        )

    # ── Checkin-based psychographic insights ────────────────────────────────
    if checkins:
        latest_checkin = sorted(checkins, key=lambda item: item.check_in_date)[-1]
        if latest_checkin.exam_pressure >= 4:
            highlights.append(
                f"📚 High exam pressure detected in recent check-ins (score: {latest_checkin.exam_pressure}/5). "
                "Stress and exam pressure historically correlate with 20–30% higher impulse spend. Set a spending pause today."
            )
        if latest_checkin.stress_level >= 4:
            highlights.append(
                f"😰 Stress level is high ({latest_checkin.stress_level}/5). "
                "Consider a 24-hour spending freeze on non-essentials before your next big purchase."
            )
        if latest_checkin.social_pressure >= 4:
            highlights.append(
                f"🎉 Social pressure score is high ({latest_checkin.social_pressure}/5) in recent check-ins. "
                "Peer spending can trigger FOMO. Set a weekend social cap to stay within your weekly target."
            )
        if latest_checkin.mood_energy <= 2:
            highlights.append(
                "😴 Low energy/mood in recent check-ins. Low-energy days often lead to convenience spending (delivery, snacks). "
                "Prep cheap meals or snacks in advance when you feel burnout coming."
            )

    # ── Weekend warning ──────────────────────────────────────────────────────
    if today.weekday() in {4, 5}:  # Friday or Saturday
        highlights.append(
            f"🗓️ It's {'Friday' if today.weekday() == 4 else 'Saturday'} — weekends are the highest-spend 2 days for most students. "
            f"Your remaining weekly budget is ₹{max(0, target_weekly_budget - current_week_spend):.0f}. Track every spend."
        )

    # ── Savings rate ─────────────────────────────────────────────────────────
    monthly_income = participant.monthly_income or 0
    if monthly_income > 0:
        savings_rate = max(0.0, (monthly_income - current_month_spend) / monthly_income * 100)
        if savings_rate >= 20:
            highlights.append(
                f"💚 Savings rate: {savings_rate:.0f}% this month — above the 20% target. "
                "Consider parking the surplus in a liquid FD or high-yield savings."
            )
        elif savings_rate > 0:
            highlights.append(
                f"💛 Savings rate: {savings_rate:.0f}% this month. Target 20% (₹{monthly_income * 0.2:.0f}) for financial resilience."
            )
        else:
            highlights.append(
                f"🔴 Savings rate: negative this month — you've spent more than your income of ₹{monthly_income:.0f}. "
                "Deficit spending erodes your emergency buffer."
            )

    if not highlights:
        highlights.append(
            "Log at least 3 expenses and 1 check-in to unlock personalized insights from the AI Copilot."
        )

    # Budget tracking
    # effective_budget was computed above as: monthly_budget + max(0.0, current_month_inflow - participant.monthly_income)
    budget_used_pct = round((current_month_spend / effective_budget) * 100, 1) if effective_budget > 0 else 0
    budget_remaining = round(effective_budget - current_month_spend, 2)
    if budget_used_pct >= 100:
        budget_status = "over_budget"
    elif budget_used_pct >= 80:
        budget_status = "warning"
    elif budget_used_pct >= 60:
        budget_status = "caution"
    else:
        budget_status = "on_track"

    summary = DashboardSummary(
        participant_id=participant_id,
        current_balance=current_balance,
        current_month_spend=current_month_spend,
        current_month_inflow=current_month_inflow,
        average_daily_spend_14d=avg_daily_spend_14d,
        projected_days_remaining=projected_days_remaining,
        risk_score=risk_score,
        risk_band=risk_band,
        top_categories=top_categories,
        highlight_messages=highlights,
        monthly_budget=monthly_budget,
        budget_used_pct=budget_used_pct,
        budget_remaining=budget_remaining,
        budget_status=budget_status,
        today_spend=today_spend,
        current_week_spend=current_week_spend,
        target_daily_budget=target_daily_budget,
        target_weekly_budget=target_weekly_budget,
        short_term_forecasts=short_term_forecasts,
    )
    
    # Generate recovery plan based on final dashboard state
    summary.recovery_plan = _generate_recovery_plan(summary, participant)
    return summary


def _generate_recovery_plan(d: DashboardSummary, p: Participant) -> list[str]:
    plan: list[str] = []
    
    if d.budget_remaining <= 0:
        plan.append("🚨 Phase 1: Survival Mode — Budget is 100% depleted. Freeze all non-essential spending immediately.")
        plan.append("  → Unsubscribe from unused streaming/app services for this month.")
        plan.append("  → Defer any shopping or entertainment to next month's allowance.")
        return plan

    # 1. Over Today?
    if d.today_spend > d.target_daily_budget > 0:
        overage = d.today_spend - d.target_daily_budget
        recovery_limit = max(0, d.target_daily_budget - (overage * 0.5))
        plan.append(f"💪 Immediate Repair: Spend ≤ ₹{recovery_limit:.0f} tomorrow to neutralize today's ₹{overage:.0f} overage.")

    # 2. Over Week?
    if d.current_week_spend > d.target_weekly_budget > 0:
        plan.append("🧘 Weekly Reset: Use a 'No Spend' day this weekend to reclaim 48 hours of budget.")

    # 3. High category focus
    if d.top_categories:
        top = d.top_categories[0]
        if top.share_of_spend > 0.4:
            plan.append(f"✂️ Tactical Cut: Reduce {top.category.title()} spending by 30% next week — it's driving {top.share_of_spend*100:.0f}% of burn.")

    # 4. Runway focus
    if d.projected_days_remaining < 7:
        plan.append("🚩 Runway Boost: Your current balance is dangerously low. Delay rent/bill payments (if possible) or seek a partial refund on recent large purchases.")

    # 5. General health
    if not plan and d.risk_band == "stable":
        plan.append("✨ Maintaining: You're currently on track. Automate a ₹500 transfer to savings now to build resilience.")

    return plan


def simulate_plan(session: Session, participant_id: str, request: SimulationRequest) -> SimulationResponse:
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise ValueError("Participant not found")

    expenses = session.exec(
        select(ExpenseEntry).where(ExpenseEntry.participant_id == participant_id)
    ).all()
    cashflows = session.exec(
        select(CashflowEntry).where(CashflowEntry.participant_id == participant_id)
    ).all()
    checkins = session.exec(
        select(DailyCheckIn).where(DailyCheckIn.participant_id == participant_id)
    ).all()

    current_balance = _latest_reported_balance(participant, expenses, cashflows, checkins)
    cutoff = datetime.now(UTC) - timedelta(days=request.lookback_days)

    category_daily_average: dict[str, float] = defaultdict(float)
    for item in expenses:
        if _coerce_utc(item.occurred_at) >= cutoff:
            category_daily_average[item.category.value] += item.amount / request.lookback_days

    baseline_daily_spend = sum(category_daily_average.values())
    adjusted_daily_spend = baseline_daily_spend
    takeaways: list[str] = []
    for category, pct_change in request.category_adjustments.items():
        average = category_daily_average.get(category, 0)
        adjusted_daily_spend += average * pct_change
        if average:
            takeaways.append(
                f"{category.title()} adjusted by {pct_change * 100:.0f}% changes daily burn by about Rs {average * pct_change:.0f}."
            )

    adjusted_balance = current_balance + request.additional_income
    baseline_end_balance = _project_end_balance(current_balance, baseline_daily_spend, request.horizon_days)
    adjusted_end_balance = _project_end_balance(adjusted_balance, adjusted_daily_spend, request.horizon_days)

    baseline_risk, _ = _risk_from_projection(current_balance, baseline_daily_spend, request.horizon_days)
    adjusted_risk, _ = _risk_from_projection(adjusted_balance, adjusted_daily_spend, request.horizon_days)

    takeaways.append(
        f"Projected end balance moves by Rs {adjusted_end_balance - baseline_end_balance:.0f} over the next {request.horizon_days} days."
    )
    if request.additional_income:
        takeaways.append(f"An extra Rs {request.additional_income:.0f} improves cash runway immediately.")

    return SimulationResponse(
        baseline_end_balance=baseline_end_balance,
        adjusted_end_balance=adjusted_end_balance,
        balance_delta=round(adjusted_end_balance - baseline_end_balance, 2),
        baseline_risk_score=baseline_risk,
        adjusted_risk_score=adjusted_risk,
        key_takeaways=takeaways,
    )


# ---------------------------------------------------------------------------
# Smart Alerts
# ---------------------------------------------------------------------------

def generate_alerts(session: Session, participant_id: str) -> list[AlertItem]:
    """Rule-based alert engine generating actionable notifications."""
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise ValueError("Participant not found")

    dashboard = build_dashboard(session, participant_id)
    alerts: list[AlertItem] = []

    # Budget alerts
    if dashboard.budget_used_pct >= 100:
        alerts.append(AlertItem(
            id=uuid4().hex[:8], severity="critical", icon="🔴",
            title="Over budget!",
            message=f"You've spent Rs {dashboard.current_month_spend:.0f} against Rs {dashboard.monthly_budget:.0f} budget. Time to cut non-essentials.",
        ))
    elif dashboard.budget_used_pct >= 80:
        alerts.append(AlertItem(
            id=uuid4().hex[:8], severity="warning", icon="🟡",
            title="Budget almost used up",
            message=f"{dashboard.budget_used_pct:.0f}% of your budget is used with {dashboard.projected_days_remaining} days left this month.",
        ))

    # Risk alerts
    if dashboard.risk_band == "critical":
        alerts.append(AlertItem(
            id=uuid4().hex[:8], severity="critical", icon="🚨",
            title="High financial risk",
            message="At your current burn rate, funds may run out before the month ends. Consider reducing discretionary spending.",
        ))
    elif dashboard.risk_band == "elevated":
        alerts.append(AlertItem(
            id=uuid4().hex[:8], severity="warning", icon="⚠️",
            title="Elevated risk level",
            message="Your spending pace is higher than your runway can comfortably support.",
        ))

    # Category spikes — compare last 7 days vs prior 7 days
    now = datetime.now(UTC)
    cutoff_7 = now - timedelta(days=7)
    cutoff_14 = now - timedelta(days=14)
    expenses = session.exec(
        select(ExpenseEntry)
        .where(ExpenseEntry.participant_id == participant_id)
        .where(ExpenseEntry.occurred_at >= cutoff_14)
    ).all()

    recent_totals: dict[str, float] = defaultdict(float)
    prior_totals: dict[str, float] = defaultdict(float)
    for item in expenses:
        dt = _coerce_utc(item.occurred_at)
        if dt >= cutoff_7:
            recent_totals[item.category.value] += item.amount
        else:
            prior_totals[item.category.value] += item.amount

    for cat, recent_val in recent_totals.items():
        prior_val = prior_totals.get(cat, 0)
        if prior_val > 0 and recent_val > prior_val * 1.4:
            pct_increase = int(((recent_val - prior_val) / prior_val) * 100)
            alerts.append(AlertItem(
                id=uuid4().hex[:8], severity="info", icon="📈",
                title=f"{cat.title()} spending up {pct_increase}%",
                message=f"Your {cat} spending this week (Rs {recent_val:.0f}) is {pct_increase}% higher than last week (Rs {prior_val:.0f}).",
            ))

    # Positive alerts
    streak = compute_no_spend_streak(session, participant_id)
    if streak >= 3:
        alerts.append(AlertItem(
            id=uuid4().hex[:8], severity="success", icon="🔥",
            title=f"{streak}-day no-spend streak!",
            message=f"Amazing! You've gone {streak} days without spending. Keep it up!",
        ))

    under_budget = compute_under_budget_days(session, participant_id)
    if under_budget >= 5:
        alerts.append(AlertItem(
            id=uuid4().hex[:8], severity="success", icon="🏆",
            title=f"Under budget for {under_budget} days",
            message=f"Great discipline! You've stayed under your daily target for {under_budget} consecutive days.",
        ))

    if not alerts:
        alerts.append(AlertItem(
            id=uuid4().hex[:8], severity="info", icon="✨",
            title="All looks good",
            message="No alerts right now. Keep logging to stay on track!",
        ))

    return alerts


# ---------------------------------------------------------------------------
# Spending trends
# ---------------------------------------------------------------------------

def get_spending_trends(session: Session, participant_id: str, days: int = 30) -> SpendingTrendsResponse:
    """Aggregated spending data for charts."""
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise ValueError("Participant not found")

    cutoff = datetime.now(UTC) - timedelta(days=days)
    expenses = session.exec(
        select(ExpenseEntry)
        .where(ExpenseEntry.participant_id == participant_id)
        .where(ExpenseEntry.occurred_at >= cutoff)
    ).all()
    cashflows = session.exec(
        select(CashflowEntry)
        .where(CashflowEntry.participant_id == participant_id)
        .where(CashflowEntry.occurred_at >= cutoff)
    ).all()

    # Daily spend
    daily: dict[str, float] = defaultdict(float)
    for item in expenses:
        day_str = _coerce_utc(item.occurred_at).date().isoformat()
        daily[day_str] += item.amount

    today = date.today()
    daily_spend: list[DailySpendPoint] = []
    for i in range(days):
        d = (today - timedelta(days=days - 1 - i)).isoformat()
        daily_spend.append(DailySpendPoint(date=d, amount=round(daily.get(d, 0), 2)))

    # Weekly totals
    weekly: dict[str, float] = defaultdict(float)
    for item in expenses:
        dt = _coerce_utc(item.occurred_at).date()
        week_start = (dt - timedelta(days=dt.weekday())).isoformat()
        weekly[week_start] += item.amount

    weekly_totals = [DailySpendPoint(date=k, amount=round(v, 2)) for k, v in sorted(weekly.items())]

    # Category totals
    cat_totals: dict[str, float] = defaultdict(float)
    for item in expenses:
        cat_totals[item.category.value] += item.amount
    grand = sum(cat_totals.values())
    category_totals = [
        CategoryBreakdown(
            category=cat,
            total_spend=round(total, 2),
            share_of_spend=round(total / grand, 3) if grand else 0,
        )
        for cat, total in sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)
    ]

    # Income vs expense by week
    weekly_income: dict[str, float] = defaultdict(float)
    for item in cashflows:
        dt = _coerce_utc(item.occurred_at).date()
        week_start = (dt - timedelta(days=dt.weekday())).isoformat()
        weekly_income[week_start] += item.amount

    all_weeks = sorted(set(list(weekly.keys()) + list(weekly_income.keys())))
    income_vs_expense = [
        {"week": w, "income": round(weekly_income.get(w, 0), 2), "expense": round(weekly.get(w, 0), 2)}
        for w in all_weeks
    ]

    return SpendingTrendsResponse(
        daily_spend=daily_spend,
        weekly_totals=weekly_totals,
        category_totals=category_totals,
        income_vs_expense=income_vs_expense,
    )


# ---------------------------------------------------------------------------
# Peer comparison
# ---------------------------------------------------------------------------

def get_peer_comparison(session: Session, participant_id: str) -> PeerComparisonResponse:
    """Anonymized percentile comparison across all participants."""
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise ValueError("Participant not found")

    cohort_desc = f"{participant.dietary_preference.value} students in {participant.living_situation.value}"
    cohort = session.exec(
        select(Participant)
        .where(Participant.living_situation == participant.living_situation)
        .where(Participant.dietary_preference == participant.dietary_preference)
    ).all()
    if len(cohort) < 2:
        cohort_desc = f"students in {participant.living_situation.value}"
        cohort = session.exec(select(Participant).where(Participant.living_situation == participant.living_situation)).all()
        if len(cohort) < 2:
            cohort_desc = "all participants"
            cohort = session.exec(select(Participant)).all()

    peer_count = len(cohort)
    if peer_count < 2:
        return PeerComparisonResponse(peer_count=peer_count, comparisons=[])

    today = date.today()
    start_of_month = _month_start(today)

    # Compute monthly spend for each participant
    user_spend = 0.0
    monthly_spends: list[float] = []
    monthly_budgets: list[float] = []
    for p in cohort:
        expenses = session.exec(
            select(ExpenseEntry).where(ExpenseEntry.participant_id == p.id)
        ).all()
        spend = sum(
            item.amount for item in expenses
            if _coerce_utc(item.occurred_at).date() >= start_of_month
        )
        monthly_spends.append(spend)
        monthly_budgets.append(p.monthly_budget)
        if p.id == participant_id:
            user_spend = spend

    user_budget = participant.monthly_budget
    user_usage = (user_spend / user_budget * 100) if user_budget > 0 else 0
    budget_usages = [
        (s / b * 100) if b > 0 else 0
        for s, b in zip(monthly_spends, monthly_budgets)
    ]

    comparisons: list[PeerComparisonItem] = []

    # Monthly spend comparison
    avg_spend = sum(monthly_spends) / len(monthly_spends)
    spend_percentile = int(sum(1 for s in monthly_spends if s <= user_spend) / len(monthly_spends) * 100)
    diff_pct = int(((user_spend - avg_spend) / avg_spend) * 100) if avg_spend > 0 else 0
    interp = f"You spend {abs(diff_pct)}% {'more' if diff_pct > 0 else 'less'} than fellow {cohort_desc} this month."
    comparisons.append(PeerComparisonItem(
        metric="Monthly Spend", your_value=round(user_spend, 0),
        peer_avg=round(avg_spend, 0), percentile=spend_percentile, interpretation=interp,
    ))

    # Budget usage comparison
    avg_usage = sum(budget_usages) / len(budget_usages)
    usage_percentile = int(sum(1 for u in budget_usages if u <= user_usage) / len(budget_usages) * 100)
    comparisons.append(PeerComparisonItem(
        metric="Budget Usage %", your_value=round(user_usage, 1),
        peer_avg=round(avg_usage, 1), percentile=usage_percentile,
        interpretation=f"Your budget usage is in the {_ordinal(usage_percentile)} percentile.",
    ))

    # Daily burn comparison
    cutoff_14 = datetime.now(UTC) - timedelta(days=14)
    daily_burns: list[float] = []
    user_burn = 0.0
    for p in cohort:
        recent = session.exec(
            select(ExpenseEntry)
            .where(ExpenseEntry.participant_id == p.id)
            .where(ExpenseEntry.occurred_at >= cutoff_14)
        ).all()
        burn = sum(item.amount for item in recent) / 14
        daily_burns.append(burn)
        if p.id == participant_id:
            user_burn = burn

    avg_burn = sum(daily_burns) / len(daily_burns)
    burn_percentile = int(sum(1 for b in daily_burns if b <= user_burn) / len(daily_burns) * 100)
    comparisons.append(PeerComparisonItem(
        metric="Daily Burn Rate", your_value=round(user_burn, 0),
        peer_avg=round(avg_burn, 0), percentile=burn_percentile,
        interpretation=f"Your daily burn is in the {_ordinal(burn_percentile)} percentile among peers.",
    ))

    return PeerComparisonResponse(peer_count=peer_count, comparisons=comparisons)


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


# ---------------------------------------------------------------------------
# Semester planner
# ---------------------------------------------------------------------------

def get_semester_projection(
    session: Session, participant_id: str, months: int = 4
) -> SemesterProjectionResponse:
    """Projects balance over a multi-month horizon."""
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise ValueError("Participant not found")

    dashboard = build_dashboard(session, participant_id)
    current_balance = dashboard.current_balance
    daily_spend = dashboard.average_daily_spend_14d
    monthly_burn = round(daily_spend * 30, 2)

    today = date.today()
    points: list[SemesterProjectionPoint] = []
    bal = current_balance
    for i in range(months * 30 + 1):
        d = today + timedelta(days=i)
        if i % 7 == 0:  # weekly points
            points.append(SemesterProjectionPoint(date=d.isoformat(), projected_balance=round(bal, 2)))
        bal -= daily_spend
        # Add monthly income
        if i > 0 and (today + timedelta(days=i)).day == 1:
            bal += participant.monthly_income

    projected_end_balance = round(current_balance - (monthly_burn * months) + (participant.monthly_income * months), 2)

    recommendations: list[str] = []
    if projected_end_balance < 0:
        deficit = abs(projected_end_balance)
        monthly_cut = round(deficit / months, 0)
        recommendations.append(f"At this pace you'll be Rs {deficit:.0f} short by semester end. Cutting Rs {monthly_cut:.0f}/month would close the gap.")
    if daily_spend > 0 and participant.monthly_budget > 0:
        target_daily = participant.monthly_budget / 30
        if daily_spend > target_daily * 1.1:
            recommendations.append(f"Your daily burn (Rs {daily_spend:.0f}) exceeds your budget target (Rs {target_daily:.0f}/day). Try the what-if simulator to find comfortable cuts.")
    if participant.monthly_income > 0 and monthly_burn > participant.monthly_income:
        recommendations.append(f"You're spending Rs {monthly_burn - participant.monthly_income:.0f} more per month than you earn. Consider a side gig or reducing non-essentials.")
    if not recommendations:
        recommendations.append("You're on track! Keep maintaining your current spending habits.")

    return SemesterProjectionResponse(
        current_balance=current_balance,
        projected_end_balance=projected_end_balance,
        monthly_burn=monthly_burn,
        months_remaining=months,
        projection_points=points,
        recommendations=recommendations,
    )


# ---------------------------------------------------------------------------
# Gamification helpers
# ---------------------------------------------------------------------------

def compute_no_spend_streak(session: Session, participant_id: str) -> int:
    """Count consecutive days from today with zero expenses."""
    today = date.today()
    streak = 0
    for i in range(60):
        d = today - timedelta(days=i)
        count = session.exec(
            select(func.count(ExpenseEntry.id))
            .where(ExpenseEntry.participant_id == participant_id)
            .where(func.date(ExpenseEntry.occurred_at) == d)
        ).one()
        if count == 0 and i > 0:
            streak += 1
        elif count > 0 and i > 0:
            break
    return streak


def compute_under_budget_days(session: Session, participant_id: str) -> int:
    """Count consecutive days the user spent less than budget/30."""
    participant = session.get(Participant, participant_id)
    if participant is None or participant.monthly_budget <= 0:
        return 0
    daily_target = participant.monthly_budget / 30
    today = date.today()
    streak = 0
    for i in range(1, 60):
        d = today - timedelta(days=i)
        expenses = session.exec(
            select(ExpenseEntry)
            .where(ExpenseEntry.participant_id == participant_id)
            .where(func.date(ExpenseEntry.occurred_at) == d)
        ).all()
        day_total = sum(e.amount for e in expenses)
        if day_total <= daily_target:
            streak += 1
        else:
            break
    return streak


def get_mood_spending_trends(session: Session, participant_id: str, days: int = 30) -> MoodSpendingResponse:
    """Joins check-in mood data with daily spending to identify psychological triggers."""
    _ensure_participant_exists(session, participant_id)
    
    cutoff = date.today() - timedelta(days=days)
    checkins = session.exec(
        select(DailyCheckIn)
        .where(DailyCheckIn.participant_id == participant_id)
        .where(DailyCheckIn.check_in_date >= cutoff)
        .order_by(DailyCheckIn.check_in_date)
    ).all()
    
    # Daily spending map
    daily_spend: dict[date, float] = defaultdict(float)
    expenses = session.exec(
        select(ExpenseEntry)
        .where(ExpenseEntry.participant_id == participant_id)
        .where(func.date(ExpenseEntry.occurred_at) >= cutoff)
    ).all()
    
    for e in expenses:
        d = _coerce_utc(e.occurred_at).date()
        daily_spend[d] += e.amount
        
    trends: list[MoodReading] = []
    stress_spends = []
    calm_spends = []
    
    for c in checkins:
        amt = daily_spend.get(c.check_in_date, 0)
        trends.append(MoodReading(
            date=c.check_in_date.isoformat(),
            amount=round(amt, 2),
            stress_level=c.stress_level,
            exam_pressure=c.exam_pressure,
            mood_energy=c.mood_energy
        ))
        if c.stress_level >= 4:
            stress_spends.append(amt)
        elif c.stress_level <= 2:
            calm_spends.append(amt)
            
    # Insight generation
    insight = "Keep logging check-ins and expenses to see your mood-spending patterns."
    if len(stress_spends) >= 2 and len(calm_spends) >= 2:
        avg_stress = sum(stress_spends) / len(stress_spends)
        avg_calm = sum(calm_spends) / len(calm_spends)
        if avg_stress > avg_calm * 1.5:
            diff = int(((avg_stress - avg_calm) / avg_calm) * 100)
            insight = f"You spend {diff}% more (avg ₹{avg_stress:.0f} vs ₹{avg_calm:.0f}) on high-stress days. Try deep breathing before opening your wallet!"
        elif avg_calm > avg_stress:
            insight = "Great work! You maintain disciplined spending even when stress is high."

    return MoodSpendingResponse(trends=trends, correlation_insight=insight)


def _ensure_participant_exists(session: Session, pid: str):
    if session.get(Participant, pid) is None:
        raise ValueError("Participant not found")

