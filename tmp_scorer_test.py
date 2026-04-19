"""Quick end-to-end scorer test using a mock participant."""
import sys, os
sys.path.insert(0, 'src')

from types import SimpleNamespace
from datetime import datetime, UTC, timedelta
from brokebutthriving.services.ml_scorer import score_participant, _model_cache

# Clear any cached state
_model_cache.clear()

# Mock participant
participant = SimpleNamespace(
    monthly_income=15000,
    monthly_budget=12000,
    age=21,
)

# Mock expenses: 14000 spent in last 30 days (3 essential, 11 discretionary)
now = datetime.now(UTC)
expenses = [
    SimpleNamespace(amount=3000, is_essential=True,  occurred_at=now - timedelta(days=5)),
    SimpleNamespace(amount=2000, is_essential=False, occurred_at=now - timedelta(days=8)),
    SimpleNamespace(amount=4000, is_essential=False, occurred_at=now - timedelta(days=12)),
    SimpleNamespace(amount=5000, is_essential=False, occurred_at=now - timedelta(days=20)),
]

# Mock check-ins: moderate stress
checkins = [
    SimpleNamespace(check_in_date=(now - timedelta(days=i)).date(),
                    stress_level=3, exam_pressure=2, social_pressure=2, mood_energy=3)
    for i in range(7)
]

result = score_participant(
    participant=participant,
    expenses=expenses,
    cashflows=[],
    checkins=checkins,
    surveys=[],
    risk_band="elevated",
    avg_daily_spend_14d=500,
)

print(f"model_available      : {result.model_available}")
print(f"wellbeing_score      : {result.wellbeing_score}  ({result.wellbeing_band})")
print(f"hardship_risk        : {result.hardship_risk}   ({result.hardship_band})")
print(f"bill_difficulty_risk : {result.bill_difficulty_risk}  ({result.bill_difficulty_band})")
print(f"spending_archetype   : {result.spending_archetype}")
print(f"discretionary_ratio  : {result.discretionary_ratio}")
print(f"spend_to_income_ratio: {result.spend_to_income_ratio}")
print(f"insights ({len(result.insights)}):")
for ins in result.insights:
    print(f"  - {ins}")
