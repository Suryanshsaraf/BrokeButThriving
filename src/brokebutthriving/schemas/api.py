from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from brokebutthriving.models.entities import (
    CashflowCategory,
    ChallengeStatus,
    DietPreference,
    ExpenseCategory,
    LivingSituation,
    RecurrenceFrequency,
)


class ParticipantCreate(BaseModel):
    participant_code: str = Field(min_length=3, max_length=32)
    first_name: str | None = Field(default=None, max_length=80)
    age: int | None = Field(default=None, ge=16, le=35)
    institution: str | None = Field(default=None, max_length=160)
    course_name: str | None = Field(default=None, max_length=120)
    country: str = Field(default="India", max_length=80)
    timezone: str = Field(default="Asia/Kolkata", max_length=80)
    living_situation: LivingSituation = LivingSituation.HOSTEL
    dietary_preference: DietPreference = DietPreference.VEG
    monthly_budget: float = Field(ge=0)
    monthly_income: float = Field(default=0, ge=0)
    starting_balance: float = Field(default=0)


class ParticipantRead(ParticipantCreate):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ParticipantUpdate(BaseModel):
    first_name: str | None = Field(default=None, max_length=80)
    monthly_budget: float | None = Field(default=None, ge=0)
    monthly_income: float | None = Field(default=None, ge=0)


class BehaviorSurveyCreate(BaseModel):
    stress_spending_score: int = Field(ge=1, le=5)
    social_pressure_score: int = Field(ge=1, le=5)
    boredom_spending_score: int = Field(ge=1, le=5)
    planning_confidence_score: int = Field(ge=1, le=5)
    self_described_trigger: str | None = Field(default=None, max_length=320)


class BehaviorSurveyRead(BehaviorSurveyCreate):
    id: str
    participant_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExpenseEntryCreate(BaseModel):
    occurred_at: datetime
    amount: float = Field(gt=0)
    category: ExpenseCategory
    merchant: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=240)
    is_social: bool = False
    is_essential: bool = False
    payment_mode: str | None = Field(default=None, max_length=40)
    source: str = Field(default="manual", max_length=40)


class ExpenseEntryRead(ExpenseEntryCreate):
    id: str
    participant_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExpenseBatchCreate(BaseModel):
    expenses: list[ExpenseEntryCreate]


class CashflowEntryCreate(BaseModel):
    occurred_at: datetime
    amount: float = Field(gt=0)
    category: CashflowCategory = CashflowCategory.OTHER
    source: str = Field(default="manual", max_length=40)
    note: str | None = Field(default=None, max_length=240)


class CashflowEntryRead(CashflowEntryCreate):
    id: str
    participant_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DailyCheckInCreate(BaseModel):
    check_in_date: date
    opening_balance: float | None = None
    closing_balance: float | None = None
    stress_level: int = Field(ge=1, le=5)
    exam_pressure: int = Field(ge=1, le=5)
    social_pressure: int = Field(ge=1, le=5)
    mood_energy: int = Field(ge=1, le=5)
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    notes: str | None = Field(default=None, max_length=320)


class DailyCheckInRead(DailyCheckInCreate):
    id: str
    participant_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CategoryBreakdown(BaseModel):
    category: str
    total_spend: float
    share_of_spend: float


class DashboardSummary(BaseModel):
    participant_id: str
    current_balance: float
    current_month_spend: float
    current_month_inflow: float
    average_daily_spend_14d: float
    projected_days_remaining: int
    risk_score: float
    risk_band: str
    top_categories: list[CategoryBreakdown]
    highlight_messages: list[str]
    # Budget tracking (new)
    monthly_budget: float = 0
    budget_used_pct: float = 0
    budget_remaining: float = 0
    budget_status: str = "on_track"
    # Tactical Breakdowns (new)
    today_spend: float = 0
    current_week_spend: float = 0
    target_daily_budget: float = 0
    target_weekly_budget: float = 0
    short_term_forecasts: list[str] = Field(default_factory=list)
    recovery_plan: list[str] = Field(default_factory=list)


class SimulationRequest(BaseModel):
    lookback_days: int = Field(default=21, ge=7, le=90)
    horizon_days: int = Field(default=14, ge=7, le=45)
    category_adjustments: dict[str, float] = Field(
        default_factory=dict,
        description="Percentage adjustments per category, such as {'food': -0.2}.",
    )
    additional_income: float = 0


class SimulationResponse(BaseModel):
    baseline_end_balance: float
    adjusted_end_balance: float
    balance_delta: float
    baseline_risk_score: float
    adjusted_risk_score: float
    key_takeaways: list[str]


class DailyDatasetRecord(BaseModel):
    participant_id: str
    date: date
    spend_total: float
    inflow_total: float
    estimated_balance: float
    risk_label_14d: int
    spend_next_7d: float
    primary_archetype: str | None


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class AlertItem(BaseModel):
    id: str
    severity: str  # "critical" | "warning" | "info" | "success"
    icon: str
    title: str
    message: str


# ---------------------------------------------------------------------------
# Spending Trends
# ---------------------------------------------------------------------------

class DailySpendPoint(BaseModel):
    date: str
    amount: float


class SpendingTrendsResponse(BaseModel):
    daily_spend: list[DailySpendPoint]
    weekly_totals: list[DailySpendPoint]
    category_totals: list[CategoryBreakdown]
    income_vs_expense: list[dict[str, float | str]]


class MoodReading(BaseModel):
    date: str
    amount: float
    stress_level: int
    exam_pressure: int
    mood_energy: int


class MoodSpendingResponse(BaseModel):
    trends: list[MoodReading]
    correlation_insight: str


# ---------------------------------------------------------------------------
# Peer comparison
# ---------------------------------------------------------------------------

class PeerComparisonItem(BaseModel):
    metric: str
    your_value: float
    peer_avg: float
    percentile: int
    interpretation: str


class PeerComparisonResponse(BaseModel):
    peer_count: int
    comparisons: list[PeerComparisonItem]


# ---------------------------------------------------------------------------
# Recurring entries
# ---------------------------------------------------------------------------

class RecurringEntryCreate(BaseModel):
    amount: float = Field(gt=0)
    category: ExpenseCategory = ExpenseCategory.OTHER
    merchant: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=240)
    frequency: RecurrenceFrequency = RecurrenceFrequency.MONTHLY
    is_expense: bool = True
    next_due: date


class RecurringEntryRead(RecurringEntryCreate):
    id: str
    participant_id: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Gamification
# ---------------------------------------------------------------------------

class ChallengeRead(BaseModel):
    id: str
    participant_id: str
    title: str
    description: str
    challenge_type: str
    target_value: float
    current_value: float
    progress_pct: float
    status: ChallengeStatus
    start_date: date
    end_date: date | None

    model_config = ConfigDict(from_attributes=True)


class AchievementRead(BaseModel):
    id: str
    badge_id: str
    title: str
    description: str
    icon: str
    earned_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GamificationSummary(BaseModel):
    active_challenges: list[ChallengeRead]
    achievements: list[AchievementRead]
    no_spend_streak: int
    under_budget_days: int


# ---------------------------------------------------------------------------
# Semester planner
# ---------------------------------------------------------------------------

class SemesterProjectionPoint(BaseModel):
    date: str
    projected_balance: float


class SemesterProjectionResponse(BaseModel):
    current_balance: float
    projected_end_balance: float
    monthly_burn: float
    months_remaining: int
    projection_points: list[SemesterProjectionPoint]
    recommendations: list[str]


# ---------------------------------------------------------------------------
# SMS import
# ---------------------------------------------------------------------------

class SmsImportRequest(BaseModel):
    sms_text: str = Field(min_length=5, max_length=5000)


class SmsImportResponse(BaseModel):
    parsed_count: int
    expenses: list[ExpenseEntryRead]
    errors: list[str]


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

class ModelMetricSummary(BaseModel):
    model_id: str
    model_label: str
    primary_metric_name: str
    primary_metric_value: float
    metrics: dict[str, float]
    is_best: bool = False


class ModelFeatureGroup(BaseModel):
    name: str
    features: list[str]


class SubgroupEvaluationSummary(BaseModel):
    label: str
    row_count: int
    group_count: int
    best_model: str | None = None
    primary_metric_name: str | None = None
    primary_metric_value: float | None = None


class TrainedModelTask(BaseModel):
    task_id: str
    title: str
    family: str
    task_type: str
    benchmark_file: str | None = None
    run_id: str
    note: str
    dataset_sources: list[str]
    row_count: int
    split_counts: dict[str, int]
    feature_count: int
    auxiliary_feature_count: int | None = None
    auxiliary_feature_label: str | None = None
    positive_class_rate: float | None = None
    best_model: str
    primary_metric_name: str
    primary_metric_value: float
    highlight: str
    feature_summary: str
    feature_groups: list[ModelFeatureGroup]
    metrics: list[ModelMetricSummary]
    subgroup_evaluation: SubgroupEvaluationSummary | None = None


class ModelRegistrySummary(BaseModel):
    public_benchmark_run_id: str | None = None
    sequence_run_id: str | None = None
    total_trained_tasks: int
    available_families: list[str]
    note: str
    missing_artifacts: list[str]
    tasks: list[TrainedModelTask]


# ---------------------------------------------------------------------------
# ML Insights
# ---------------------------------------------------------------------------

class MLInsightsResponse(BaseModel):
    model_available: bool

    # Wellbeing
    wellbeing_score: float | None = None        # 0–100
    wellbeing_band: str | None = None           # low / moderate / good / excellent

    # Hardship
    hardship_risk: float | None = None          # 0–1 probability
    hardship_band: str | None = None            # low / moderate / high / critical

    # Bill difficulty
    bill_difficulty_risk: float | None = None   # 0–1 probability
    bill_difficulty_band: str | None = None     # low / moderate / high

    # Spending archetype
    spending_archetype: str | None = None       # stress | social_pressure | boredom | balanced
    archetype_confidence: float | None = None   # 0–1

    # Financial ratios
    discretionary_ratio: float | None = None    # share of spend that is optional
    spend_to_income_ratio: float | None = None  # monthly spend / monthly income

    # Narrative insights
    insights: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str = Field(description="Either 'user' or 'assistant'.")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list)
    category_budgets: dict[str, float] | None = None


class ChatResponse(BaseModel):
    reply: str
    tools_used: list[str] = Field(default_factory=list)


