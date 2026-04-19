/* TypeScript interfaces for all API types */

// Enums
export type ExpenseCategory =
  | 'rent' | 'food' | 'transport' | 'entertainment' | 'shopping'
  | 'education' | 'health' | 'utilities' | 'subscription'
  | 'travel' | 'social' | 'emergency' | 'other';

export type CashflowCategory =
  | 'allowance' | 'salary' | 'freelance'
  | 'scholarship' | 'refund' | 'transfer' | 'other';

export type LivingSituation = 'hostel' | 'pg' | 'with_family' | 'rental' | 'other';
export type DietPreference = 'veg' | 'non_veg' | 'vegan' | 'eggetarian' | 'other';
export type RecurrenceFrequency = 'daily' | 'weekly' | 'monthly';
export type ChallengeStatus = 'active' | 'completed' | 'expired';

// Participant
export interface ParticipantCreate {
  participant_code: string;
  first_name?: string;
  age?: number;
  institution?: string;
  course_name?: string;
  country?: string;
  timezone?: string;
  living_situation?: LivingSituation;
  dietary_preference?: DietPreference;
  monthly_budget: number;
  monthly_income?: number;
  starting_balance?: number;
}

export interface ParticipantRead extends ParticipantCreate {
  id: string;
  created_at: string;
}

// Survey
export interface BehaviorSurveyCreate {
  stress_spending_score: number;
  social_pressure_score: number;
  boredom_spending_score: number;
  planning_confidence_score: number;
  self_described_trigger?: string;
}

export interface BehaviorSurveyRead extends BehaviorSurveyCreate {
  id: string;
  participant_id: string;
  created_at: string;
}

// Expense
export interface ExpenseEntryCreate {
  occurred_at: string;
  amount: number;
  category: ExpenseCategory;
  merchant?: string;
  note?: string;
  is_social?: boolean;
  is_essential?: boolean;
  payment_mode?: string;
  source?: string;
}

export interface ExpenseEntryRead extends ExpenseEntryCreate {
  id: string;
  participant_id: string;
  created_at: string;
}

export interface ExpenseBatchCreate {
  expenses: ExpenseEntryCreate[];
}

// Cashflow
export interface CashflowEntryCreate {
  occurred_at: string;
  amount: number;
  category?: CashflowCategory;
  source?: string;
  note?: string;
}

export interface CashflowEntryRead extends CashflowEntryCreate {
  id: string;
  participant_id: string;
  created_at: string;
}

// Check-in
export interface DailyCheckInCreate {
  check_in_date: string;
  opening_balance?: number;
  closing_balance?: number;
  stress_level: number;
  exam_pressure: number;
  social_pressure: number;
  mood_energy: number;
  sleep_hours?: number;
  notes?: string;
}

export interface DailyCheckInRead extends DailyCheckInCreate {
  id: string;
  participant_id: string;
  created_at: string;
}

// Dashboard
export interface CategoryBreakdown {
  category: string;
  total_spend: number;
  share_of_spend: number;
}

export interface DashboardSummary {
  participant_id: string;
  current_balance: number;
  current_month_spend: number;
  current_month_inflow: number;
  average_daily_spend_14d: number;
  projected_days_remaining: number;
  risk_score: number;
  risk_band: string;
  top_categories: CategoryBreakdown[];
  highlight_messages: string[];
  monthly_budget: number;
  budget_used_pct: number;
  budget_remaining: number;
  budget_status: string;
  // Tactical Breakdowns (new)
  today_spend: number;
  current_week_spend: number;
  target_daily_budget: number;
  target_weekly_budget: number;
  short_term_forecasts: string[];
  recovery_plan: string[];
}

// Simulation
export interface SimulationRequest {
  lookback_days?: number;
  horizon_days?: number;
  category_adjustments?: Record<string, number>;
  additional_income?: number;
}

export interface SimulationResponse {
  baseline_end_balance: number;
  adjusted_end_balance: number;
  balance_delta: number;
  baseline_risk_score: number;
  adjusted_risk_score: number;
  key_takeaways: string[];
}

// Alerts
export interface AlertItem {
  id: string;
  severity: 'critical' | 'warning' | 'info' | 'success';
  icon: string;
  title: string;
  message: string;
}

// Spending Trends
export interface DailySpendPoint {
  date: string;
  amount: number;
}

export interface SpendingTrendsResponse {
  daily_spend: DailySpendPoint[];
  weekly_totals: DailySpendPoint[];
  category_totals: CategoryBreakdown[];
  income_vs_expense: { week: string; income: number; expense: number }[];
}

export interface MoodReading {
  date: string;
  amount: number;
  stress_level: number;
  exam_pressure: number;
  mood_energy: number;
}

export interface MoodSpendingResponse {
  trends: MoodReading[];
  correlation_insight: string;
}

// Peer Comparison
export interface PeerComparisonItem {
  metric: string;
  your_value: number;
  peer_avg: number;
  percentile: number;
  interpretation: string;
}

export interface PeerComparisonResponse {
  peer_count: number;
  comparisons: PeerComparisonItem[];
}

// Recurring
export interface RecurringEntryCreate {
  amount: number;
  category?: ExpenseCategory;
  merchant?: string;
  note?: string;
  frequency?: RecurrenceFrequency;
  is_expense?: boolean;
  next_due: string;
}

export interface RecurringEntryRead extends RecurringEntryCreate {
  id: string;
  participant_id: string;
  is_active: boolean;
  created_at: string;
}

// Gamification
export interface ChallengeRead {
  id: string;
  participant_id: string;
  title: string;
  description: string;
  challenge_type: string;
  target_value: number;
  current_value: number;
  progress_pct: number;
  status: ChallengeStatus;
  start_date: string;
  end_date: string | null;
}

export interface AchievementRead {
  id: string;
  badge_id: string;
  title: string;
  description: string;
  icon: string;
  earned_at: string;
}

export interface GamificationSummary {
  active_challenges: ChallengeRead[];
  achievements: AchievementRead[];
  no_spend_streak: number;
  under_budget_days: number;
}

// Semester Projection
export interface SemesterProjectionPoint {
  date: string;
  projected_balance: number;
}

export interface SemesterProjectionResponse {
  current_balance: number;
  projected_end_balance: number;
  monthly_burn: number;
  months_remaining: number;
  projection_points: SemesterProjectionPoint[];
  recommendations: string[];
}

// SMS Import
export interface SmsImportRequest {
  sms_text: string;
}

export interface SmsImportResponse {
  parsed_count: number;
  expenses: ExpenseEntryRead[];
  errors: string[];
}

// Model Registry
export interface ModelRegistrySummary {
  public_benchmark_run_id: string | null;
  sequence_run_id: string | null;
  total_trained_tasks: number;
  available_families: string[];
  note: string;
  missing_artifacts: string[];
  tasks: any[];
}

// Chat
export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  tools_used?: string[];
}

export interface ChatRequest {
  message: string;
  history: { role: string; content: string }[];
}

export interface ChatResponse {
  reply: string;
  tools_used: string[];
}

// ML Insights
export interface MLInsightsResponse {
  model_available: boolean;
  // Wellbeing
  wellbeing_score: number | null;
  wellbeing_band: 'low' | 'moderate' | 'good' | 'excellent' | null;
  // Hardship
  hardship_risk: number | null;
  hardship_band: 'low' | 'moderate' | 'high' | 'critical' | null;
  // Bill difficulty
  bill_difficulty_risk: number | null;
  bill_difficulty_band: 'low' | 'moderate' | 'high' | null;
  // Spending archetype
  spending_archetype: 'stress' | 'social_pressure' | 'boredom' | 'balanced' | null;
  archetype_confidence: number | null;
  // Financial ratios
  discretionary_ratio: number | null;
  spend_to_income_ratio: number | null;
  // Narrative
  insights: string[];
}
