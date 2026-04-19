"""ML Scorer — loads trained model artifacts and scores a participant.

Produces:
  - wellbeing_score      (0–100, TabularMLP on FWB benchmark)
  - hardship_risk        (0–1 probability, TabularMLP on hardship benchmark)
  - bill_difficulty_risk (0–1 probability, TabularMLP on future_difficulty benchmark)
  - spending_archetype   (str: stress | social_pressure | boredom | balanced)
  - discretionary_ratio  (float: share of spending that is optional)
  - spend_to_income_ratio (float: monthly spend / monthly income proxy)

Feature mapping strategy: build a row using the EXACT column names seen during
training (read from each preprocessor's .numeric_features / .boolean_features /
.categorical_features attributes). Missing values are filled with sensible
student-finance priors and left as NaN where truly unknown — the trained imputer
handles them the same way it handled missing survey fields during training.

Graceful degradation: if model files are missing every field returns None and
`model_available` is False — the dashboard still works without crashing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from brokebutthriving.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class MLInsights:
    """All ML-derived scores for one participant. None = model unavailable."""
    model_available: bool = False

    wellbeing_score: float | None = None        # 0–100
    wellbeing_band: str | None = None           # low / moderate / good / excellent

    hardship_risk: float | None = None          # 0–1 probability
    hardship_band: str | None = None            # low / moderate / high / critical

    bill_difficulty_risk: float | None = None   # 0–1 probability
    bill_difficulty_band: str | None = None     # low / moderate / high

    spending_archetype: str | None = None       # stress | social_pressure | boredom | balanced
    archetype_confidence: float | None = None   # 0–1

    discretionary_ratio: float | None = None    # share of optional spend
    spend_to_income_ratio: float | None = None  # monthly spend / monthly income

    insights: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Model cache (loaded once at first call)
# ---------------------------------------------------------------------------

_model_cache: dict[str, Any] = {}


def _load_joblib(path: Path) -> Any | None:
    try:
        from joblib import load
        if path.exists():
            return load(path)
    except Exception as exc:
        logger.warning("Could not load joblib model %s: %s", path, exc)
    return None


def _load_torch(path: Path) -> dict | None:
    try:
        import torch
        if path.exists():
            return torch.load(path, map_location="cpu", weights_only=False)
    except Exception as exc:
        logger.warning("Could not load torch checkpoint %s: %s", path, exc)
    return None


def _latest_run(root: Path) -> Path | None:
    if not root.exists():
        return None
    dirs = [p for p in root.iterdir() if p.is_dir()]
    return sorted(dirs, key=lambda p: (p.name, p.stat().st_mtime_ns))[-1] if dirs else None


def _get_models() -> dict[str, Any]:
    """Load and cache all scorer models."""
    global _model_cache
    if _model_cache.get("_loaded"):
        return _model_cache

    pub_run = _latest_run(settings.public_benchmark_runs_root)
    if pub_run is None:
        logger.info("No public benchmark run directory found — ML scoring disabled.")
        _model_cache["_loaded"] = True
        return _model_cache

    task_map = {
        "hardship": "hardship_classification",
        "wellbeing": "wellbeing_regression",
        "bill_difficulty": "future_difficulty_classification",
    }

    for key, task_id in task_map.items():
        task_dir = pub_run / task_id / "models"
        torch_path = task_dir / "mlp_model.pt"
        preprocessor_path = task_dir / "preprocessor.joblib"

        checkpoint = _load_torch(torch_path)
        preprocessor = _load_joblib(preprocessor_path)

        if checkpoint and preprocessor:
            _model_cache[f"{key}_checkpoint"] = checkpoint
            _model_cache[f"{key}_preprocessor"] = preprocessor
            logger.info("Loaded %s MLP model for live scoring.", task_id)
        else:
            gbm_path = task_dir / "hist_gradient_boosting.joblib"
            gbm = _load_joblib(gbm_path)
            if gbm and preprocessor:
                _model_cache[f"{key}_sklearn"] = gbm
                _model_cache[f"{key}_preprocessor"] = preprocessor
                logger.info("Loaded %s GBM sklearn model (MLP unavailable).", task_id)

    _model_cache["_loaded"] = True
    return _model_cache


# ---------------------------------------------------------------------------
# Feature builder — uses EXACT column names the preprocessors were trained on
# ---------------------------------------------------------------------------

def _spend_stats(expenses: list, now: datetime) -> tuple[float, float]:
    """Returns (monthly_spend_30d, essential_spend_30d)."""
    total = 0.0
    essential = 0.0
    for e in expenses:
        dt = e.occurred_at if e.occurred_at.tzinfo else e.occurred_at.replace(tzinfo=UTC)
        if (now - dt).days <= 30:
            total += e.amount
            if getattr(e, "is_essential", False):
                essential += e.amount
    return total, essential


def _checkin_averages(checkins: list, now: datetime) -> dict[str, float]:
    recent = [c for c in checkins if (now.date() - c.check_in_date).days <= 14]
    n = max(len(recent), 1)
    return {
        "stress": sum(c.stress_level for c in recent) / n,
        "exam": sum(c.exam_pressure for c in recent) / n,
        "social": sum(c.social_pressure for c in recent) / n,
        "mood": sum(c.mood_energy for c in recent) / n,
    }


def _build_scoring_frame(
    participant: Any,
    expenses: list,
    cashflows: list,
    checkins: list,
    risk_band: str,
    avg_daily_spend_14d: float,
) -> pd.DataFrame:
    """
    Build a single-row DataFrame using EXACT column names from the benchmark
    preprocessors. Unknown/unmeasurable features are left as NaN so the
    preprocessor's trained imputer fills them with training-set means/modes.
    """
    now = datetime.now(UTC)
    monthly_spend, essential_spend = _spend_stats(expenses, now)
    monthly_income = float(participant.monthly_income or 0)
    total_spend = max(monthly_spend, 1.0)
    discretionary_spend = total_spend - essential_spend
    mood = _checkin_averages(checkins, now)

    is_strained = risk_band in ("elevated", "critical")
    is_critical  = risk_band == "critical"
    is_watch_plus = risk_band in ("watch", "elevated", "critical")

    # Encode risk_band → ordinal proxies for codes that use 1–5 scale
    # (1 = worst, 5 = best for most FWB codes)
    risk_ordinal = {"stable": 4, "watch": 3, "elevated": 2, "critical": 1}.get(risk_band, 3)

    # Map risk → categorical strings used in SHED / CFPB categorical features
    fin_status_map = {
        "stable": "living_comfortably",
        "watch": "doing_okay",
        "elevated": "just_getting_by",
        "critical": "finding_it_difficult",
    }
    fin_change_map = {
        "stable": "somewhat_better_off",
        "watch": "about_the_same",
        "elevated": "somewhat_worse_off",
        "critical": "much_worse_off",
    }
    ends_meet_map = {
        "stable": "4",   # "about the same"
        "watch": "3",
        "elevated": "2",
        "critical": "1",  # "much worse off"
    }
    save_habit_map = {
        "stable": "3",
        "watch": "2",
        "elevated": "2",
        "critical": "1",
    }

    has_income = monthly_income > 0
    spend_ratio = monthly_spend / max(monthly_income, 1)

    # Proxy for financial wellbeing (financial_skill_score, money_management_score)
    # Lower stress → higher scores
    skill_score = max(20.0, 65.0 - mood["stress"] * 6)
    mgmt_score  = max(1.0,  4.0  - mood["stress"] * 0.4)

    row: dict[str, Any] = {
        # ── Shared identifiers (handled as categoricals) ──────────────────
        "source_dataset": "student_app",
        "sample_id": "student_app",
        "wave_id": "student_app",

        # ── Numeric: demographics & survey year ───────────────────────────
        "survey_year": now.year,
        "age": float(participant.age or 21),
        "household_size": 1.0,

        # ── Numeric: financial signals ────────────────────────────────────
        "fwb_score": float(np.clip(skill_score, 0, 100)),  # used by wellbeing + bill-difficulty models
        "financial_skill_score": skill_score,
        "money_management_score": mgmt_score,
        "health_knowledge_score": 3.0,                     # neutral prior
        "lower_income_flag": 1.0 if spend_ratio > 0.9 else 0.0,
        "higher_expenses_flag": 1.0 if spend_ratio > 1.0 else 0.0,
        "is_worse_off_than_last_year": 1.0 if is_critical else 0.0,
        "is_current_student": 1.0,
        "is_full_time_student": 1.0,

        # ── Numeric: hardship amounts (NaN = let imputer fill) ────────────
        "difficulty_event_amount": np.nan,
        "medical_collection_amount": 0.0,
        "out_of_pocket_medical_amount": 0.0,
        "emergency_savings_amount": 0.0,

        # ── Boolean features shared across all three models ───────────────
        "had_bill_difficulty_past_12m": is_strained,
        "expects_bill_difficulty_next_12m": is_critical,
        "cut_nonessential_spending": is_watch_plus,
        "used_credit": False,
        "borrowed_from_family_or_friends": False,
        "used_nonretirement_savings": is_watch_plus,
        "used_retirement_savings": False,
        "used_payday_or_auto_title_loan": False,
        "difficulty_event_caused_by_specific_event": False,
        "has_student_loan_debt": False,
        "student_loan_delinquent": False,
        "has_credit_card": False,
        "credit_card_late_fee_past_12m": is_strained,
        "skipped_other_bill_or_paid_late": is_strained,
        "has_checking_savings_account": True,
        "has_checking_or_savings_account": True,
        "has_retirement_account": False,
        "has_student_education_loan": False,
        "received_snap": False,
        "contacted_debt_collector_past_12m": False,
        "works_full_time": False,
        "works_part_time": has_income,
        "owns_rental_property_for_income": False,
        "medical_financed_with_credit_or_loan": False,
        "has_medical_credit_card": False,
        "provider_threatened_collection": False,
        "medical_collection_contact": False,
        "medical_collection_disputed": False,
        "out_of_pocket_medical_expense_past_12m": False,
        "any_unexpected_expense_past_12m": is_strained,
        "any_income_loss_past_12m": is_critical,
        "difficulty_paying_mortgage_or_rent": is_critical,
        "difficulty_paying_home_repair": False,
        "difficulty_paying_food": is_critical,
        "difficulty_paying_utilities": is_strained,
        "difficulty_paying_taxes_or_legal_bills": False,
        "medical_debt_past_due": False,
        "medical_payment_plan": False,

        # ── Categorical: housing / school / employment status ─────────────
        "housing_tenure_code": "renting",
        "current_student_status": "full_time",
        "current_school_status": "full_time_student",
        "student_status_proxy": "student",
        "education_level": "some_college",
        "current_program_type": "undergraduate",
        "employment_status": "part_time" if has_income else "not_employed",
        "gender": "unknown",
        "household_income_band": "low" if spend_ratio > 1.0 else "middle",
        "marital_status": "single",
        "housing_status": "renting",
        "housing_status_code": "renting",
        "housing_concern_level": "moderate" if is_strained else "low",
        "making_ends_meet_concern": "worried" if is_strained else "okay",
        "student_loan_concern": "not_applicable",
        "student_loan_amount_band": "none",
        "student_loan_payment_band": "none",

        # ── Categorical: CFPB FWB code fields ─────────────────────────────
        "save_habit_code": save_habit_map.get(risk_band, "2"),
        "frugality_code": "3" if essential_spend / total_spend > 0.6 else "2",
        "financial_goals_code": "3",
        "ends_meet_code": ends_meet_map.get(risk_band, "3"),
        "living_arrangement_code": "alone",
        "savings_range_code": "low",
        "household_earners_code": "1",
        "income_volatility_code": "2",   # students have irregular income
        "food_worry_hardship_code": "2" if is_critical else "1",
        "food_shortage_hardship_code": "1",
        "housing_hardship_code": "1",
        "medical_access_hardship_code": "1",
        "medication_cost_hardship_code": "1",
        "utilities_hardship_code": "2" if is_strained else "1",
        "absorb_shock_confidence_code": str(risk_ordinal),
        "cover_costs_strategy_code": "spending_less" if is_watch_plus else "using_savings",
        "primary_employment_status_code": "part_time" if has_income else "student",
        "age_category_code": "18_24",
        "household_education_code": "some_college",
        "respondent_education_code": "some_college",
        "parent_education_code": "some_college",
        "household_income_code": "low" if spend_ratio > 1.0 else "middle",
        "poverty_level_band_code": "at_or_above",

        # ── Categorical: SHED / bill-difficulty specific ───────────────────
        "financial_management_status": fin_status_map.get(risk_band, "doing_okay"),
        "financial_change_12m": fin_change_map.get(risk_band, "about_the_same"),
        "checking_savings_balance_band": "low" if spend_ratio > 1.0 else "moderate",
        "savings_habit_band": "irregular" if is_watch_plus else "regular",
        "bill_difficulty_frequency_band": "often" if is_strained else "rarely",
        "bill_difficulty_recency_band": "recent" if is_strained else "not_recent",
        "difficulty_event_expectedness": "unexpected" if is_critical else "not_applicable",
        "expense_coverage_horizon_band": "less_than_1_week" if is_critical else "1_3_months",
        "medical_debt_sued_status": "not_applicable",
        "medical_collection_count_band": "none",
        "medical_collection_frequency_band": "never",
    }

    return pd.DataFrame([row])


# ---------------------------------------------------------------------------
# Inference helpers
# ---------------------------------------------------------------------------

def _transform_frame(preprocessor: Any, frame: pd.DataFrame) -> Any | None:
    """
    Select only columns the preprocessor knows and call transform().
    The preprocessor's imputer handles NaN values for the rest.
    """
    all_known = (
        list(getattr(preprocessor, "numeric_features", []) or [])
        + list(getattr(preprocessor, "boolean_features", []) or [])
        + list(getattr(preprocessor, "categorical_features", []) or [])
    )
    # Keep only columns that exist in our frame AND the preprocessor knows
    cols = [c for c in all_known if c in frame.columns]
    if not cols:
        logger.warning("No feature overlap between scoring frame and preprocessor — returning None")
        return None
    logger.debug("Matched %d / %d features for scoring", len(cols), len(all_known))
    try:
        return preprocessor.transform(frame[cols])
    except Exception as exc:
        logger.warning("Preprocessor.transform failed: %s", exc)
        return None


def _predict_mlp(checkpoint: dict, preprocessor: Any, frame: pd.DataFrame, task_type: str) -> float | None:
    try:
        import torch
        from brokebutthriving.ml.models import TabularMLP

        features = _transform_frame(preprocessor, frame)
        if features is None:
            return None

        input_dim = features.shape[1]
        model = TabularMLP(input_dim=input_dim)
        model.load_state_dict(checkpoint["model_state"])
        model.eval()

        with torch.inference_mode():
            tensor = torch.tensor(features, dtype=torch.float32)
            logit = model(tensor).squeeze(-1).item()

        if task_type == "classification":
            return float(1.0 / (1.0 + np.exp(-logit)))
        return float(logit)
    except Exception as exc:
        logger.warning("MLP inference failed: %s", exc)
        return None


def _predict_sklearn(model: Any, preprocessor: Any, frame: pd.DataFrame, task_type: str) -> float | None:
    try:
        features = _transform_frame(preprocessor, frame)
        if features is None:
            return None
        if task_type == "classification":
            return float(model.predict_proba(features)[0, 1])
        return float(model.predict(features)[0])
    except Exception as exc:
        logger.warning("Sklearn inference failed: %s", exc)
        return None


def _score_task(models: dict, key: str, frame: pd.DataFrame, task_type: str) -> float | None:
    preprocessor = models.get(f"{key}_preprocessor")
    if preprocessor is None:
        return None

    checkpoint = models.get(f"{key}_checkpoint")
    if checkpoint:
        result = _predict_mlp(checkpoint, preprocessor, frame, task_type)
        if result is not None:
            return result

    sklearn_model = models.get(f"{key}_sklearn")
    if sklearn_model:
        return _predict_sklearn(sklearn_model, preprocessor, frame, task_type)

    return None


# ---------------------------------------------------------------------------
# Archetype from behavior survey
# ---------------------------------------------------------------------------

def _compute_archetype(surveys: list) -> tuple[str | None, float | None]:
    if not surveys:
        return None, None
    latest = sorted(surveys, key=lambda s: s.created_at)[-1]
    scores = {
        "stress": getattr(latest, "stress_spending_score", 0) or 0,
        "social_pressure": getattr(latest, "social_pressure_score", 0) or 0,
        "boredom": getattr(latest, "boredom_spending_score", 0) or 0,
    }
    max_score = max(scores.values())
    if max_score < 2:
        return "balanced", 1.0
    archetype = max(scores, key=scores.__getitem__)
    return archetype, round(max_score / 5.0, 2)


# ---------------------------------------------------------------------------
# Band helpers
# ---------------------------------------------------------------------------

def _wellbeing_band(score: float) -> str:
    if score >= 70: return "excellent"
    if score >= 55: return "good"
    if score >= 40: return "moderate"
    return "low"

def _hardship_band(prob: float) -> str:
    if prob >= 0.75: return "critical"
    if prob >= 0.50: return "high"
    if prob >= 0.25: return "moderate"
    return "low"

def _bill_band(prob: float) -> str:
    if prob >= 0.65: return "high"
    if prob >= 0.35: return "moderate"
    return "low"


# ---------------------------------------------------------------------------
# Insight generator
# ---------------------------------------------------------------------------

def _generate_insights(result: MLInsights, participant: Any) -> list[str]:
    insights: list[str] = []
    monthly_income = float(participant.monthly_income or 0)

    # ── Wellbeing score ────────────────────────────────────────────────────────
    if result.wellbeing_score is not None:
        wb = result.wellbeing_score
        if wb < 35:
            insights.append(
                f"🔴 Wellbeing Score: {wb:.0f}/100 — We know things feel tough right now. "
                "Money stress is really getting to you. Try to write down everything you spend money on "
                "this week to see where it goes, and don't be afraid to ask your college for financial help if you need it."
            )
        elif wb < 45:
            insights.append(
                f"🟠 Wellbeing Score: {wb:.0f}/100 — You're feeling a bit more financial stress than average. "
                "You can turn this around! Pick just one habit—like packing snacks instead of buying them—to start taking back control."
            )
        elif wb < 55:
            insights.append(
                f"🟡 Wellbeing Score: {wb:.0f}/100 — You're right in the middle! "
                "You're doing okay, but setting a simple 'no-spend' day once a week could make you feel a lot more secure."
            )
        elif wb < 70:
            insights.append(
                f"🟢 Wellbeing Score: {wb:.0f}/100 — Looking good! "
                "You feel pretty confident about your money. A great next step is to start saving a small, fixed amount every week automatically."
            )
        else:
            insights.append(
                f"✨ Wellbeing Score: {wb:.0f}/100 — You're doing amazing! "
                "You have excellent money habits. Keep doing what you're doing, and focus on building a bigger savings buffer for emergencies."
            )

    # ── Hardship risk ──────────────────────────────────────────────────────────
    if result.hardship_risk is not None:
        hr = result.hardship_risk
        if hr >= 0.75:
            insights.append(
                f"🚨 Money Warning: {hr*100:.0f}% Risk. It looks like you might run out of money soon if things don't change. "
                "Hold off on any fun purchases immediately and just stick to the absolute essentials like food and rent!"
            )
        elif hr >= 0.50:
            insights.append(
                f"⚠️ Watch Out: {hr*100:.0f}% Risk. Money might get tight soon. "
                "Try to avoid buying anything with \"buy now, pay later\" apps, and try to save just a little bit of cash today."
            )
        elif hr >= 0.25:
            insights.append(
                f"🟡 Check Engine Light: {hr*100:.0f}% Risk. You're mostly fine, but one unexpected expense "
                "could mess up your month. Try to save a tiny bit of your budget just for emergencies."
            )
        else:
            insights.append(
                f"✅ Safe Zone: Your risk of running completely out of money is very low. "
                "Your spending habits look really sustainable!"
            )

    # ── Bill difficulty ────────────────────────────────────────────────────────
    if result.bill_difficulty_risk is not None:
        bd = result.bill_difficulty_risk
        if bd >= 0.65:
            insights.append(
                f"📋 Bill Trouble: {bd*100:.0f}% Risk. There's a high chance you might struggle to pay upcoming bills. "
                "Look at your subscriptions right now—cancel any streaming or delivery apps you aren't using actively."
            )
        elif bd >= 0.35:
            insights.append(
                f"📋 Bill Checker: {bd*100:.0f}% Risk. Money could be a little short when your next rent or phone bill arrives. "
                "Make sure you set exactly what you need for bills aside first, before spending on anything else."
            )
        else:
            insights.append(
                f"📋 Bills covered: You're in a great spot to pay all your regular bills easily!"
            )

    # ── Spend-to-income ratio ──────────────────────────────────────────────────
    if result.spend_to_income_ratio is not None:
        sir = result.spend_to_income_ratio
        if sir > 1.2:
            insights.append(
                f"💸 Spending vs Income: You are spending way more than you are earning! "
                "This will drain your savings quickly. You need to either find a way to earn a little extra cash, or seriously cut down your shopping."
            )
        elif sir > 1.0:
            excess = (sir - 1.0) * monthly_income
            insights.append(
                f"⚠️ Spending vs Income: You are spending about ₹{excess:.0f} more than you bring in. "
                "Pick one fun thing to cut back on for the next 30 days to get back to even."
            )
        elif sir > 0.8:
            insights.append(
                f"📊 Spending vs Income: You are spending almost all the money you get. It's safe, but leaves you with nothing extra. "
                "Try to aim to save a small chunk every time you get paid."
            )
        else:
            savings = (1.0 - sir) * monthly_income if monthly_income > 0 else 0
            insights.append(
                f"💪 Spending vs Income: You are saving around ₹{savings:.0f} this month! "
                "Awesome job keeping your spending way below what you have."
            )

    # ── Discretionary ratio ────────────────────────────────────────────────────
    if result.discretionary_ratio is not None:
        dr = result.discretionary_ratio * 100
        if dr > 55:
            insights.append(
                f"🛍️ \"Fun\" Spending: {dr:.0f}%. A massive chunk of your money is going towards things you want, rather than things you need. "
                "Try picking your two favorite fun categories and giving yourself a strict weekly limit for them."
            )
        elif dr > 35:
            insights.append(
                f"🛒 \"Fun\" Spending: {dr:.0f}%. You spend quite a bit on non-essentials. "
                "To keep it under control, try taking out cash for fun spending and making it last the whole week."
            )
        elif dr > 0:
            insights.append(
                f"✅ \"Fun\" Spending: {dr:.0f}%. You have a really good balance between buying what you need and enjoying yourself!"
            )

    # ── Archetype-specific deep coaching ──────────────────────────────────────
    archetype_coaching = {
        "stress": (
            "😰 **Stress Spender:** It looks like you shop when you feel overwhelmed (like during exams!). "
            "Next time you feel the urge to shop just to feel better, try forcing yourself to wait 15 minutes, or try calling a friend instead."
        ),
        "social_pressure": (
            "🎉 **Social Spender:** You spend the most when you're out with friends. FOMO is real! "
            "Try setting a clear budget for the weekend. When it's gone, suggest free hangouts like going for a walk, game night, or cooking together."
        ),
        "boredom": (
            "😑 **Boredom Spender:** You spend money just because you don't have anything better to do! "
            "Make a list of 5 free things you actually enjoy doing (like gaming, reading, or watching a movie). Pick one of those next time you want to online shop."
        ),
        "balanced": (
            "⚖️ **Balanced Spender:** You don't let your emotions control your money! You're very intentional with what you buy. "
            "Since you're so good at this, focus on automating your savings so you don't even have to think about it."
        ),
    }
    if result.spending_archetype and result.spending_archetype in archetype_coaching:
        insights.append(archetype_coaching[result.spending_archetype])

    return insights



# ---------------------------------------------------------------------------
# Main scorer entry point
# ---------------------------------------------------------------------------

def score_participant(
    participant: Any,
    expenses: list,
    cashflows: list,
    checkins: list,
    surveys: list,
    risk_band: str,
    avg_daily_spend_14d: float,
) -> MLInsights:
    """Score a participant using all available trained models."""
    result = MLInsights()

    try:
        models = _get_models()
        has_any = any(k for k in models if not k.startswith("_"))
        if not has_any:
            return result

        result.model_available = True

        frame = _build_scoring_frame(
            participant=participant,
            expenses=expenses,
            cashflows=cashflows,
            checkins=checkins,
            risk_band=risk_band,
            avg_daily_spend_14d=avg_daily_spend_14d,
        )

        # Wellbeing score (regression → raw score on 0–100 FWB scale)
        wb_raw = _score_task(models, "wellbeing", frame, "regression")
        if wb_raw is not None:
            result.wellbeing_score = round(float(np.clip(wb_raw, 0, 100)), 1)
            result.wellbeing_band = _wellbeing_band(result.wellbeing_score)

        # Hardship risk
        hr = _score_task(models, "hardship", frame, "classification")
        if hr is not None:
            result.hardship_risk = round(float(hr), 3)
            result.hardship_band = _hardship_band(result.hardship_risk)

        # Future bill difficulty
        bd = _score_task(models, "bill_difficulty", frame, "classification")
        if bd is not None:
            result.bill_difficulty_risk = round(float(bd), 3)
            result.bill_difficulty_band = _bill_band(result.bill_difficulty_risk)

        # Archetype
        result.spending_archetype, result.archetype_confidence = _compute_archetype(surveys)

        # Ratios from live data
        now = datetime.now(UTC)
        monthly_spend, essential_spend = _spend_stats(expenses, now)
        monthly_income = float(participant.monthly_income or 1)
        result.spend_to_income_ratio = round(monthly_spend / max(monthly_income, 1), 3)
        result.discretionary_ratio = round(
            (monthly_spend - essential_spend) / max(monthly_spend, 1), 3
        )

        result.insights = _generate_insights(result, participant)

    except Exception as exc:
        logger.exception("ML scoring failed for participant: %s", exc)
        result.model_available = False

    return result
