/* API client — all endpoints */

import type {
  AlertItem,
  BehaviorSurveyCreate,
  BehaviorSurveyRead,
  CashflowEntryCreate,
  CashflowEntryRead,
  ChatResponse,
  DailyCheckInCreate,
  DailyCheckInRead,
  DashboardSummary,
  ExpenseBatchCreate,
  ExpenseEntryCreate,
  ExpenseEntryRead,
  GamificationSummary,
  ChallengeRead,
  MLInsightsResponse,
  ParticipantCreate,
  ParticipantRead,
  MoodSpendingResponse,
  PeerComparisonResponse,
  RecurringEntryCreate,
  RecurringEntryRead,
  SemesterProjectionResponse,
  SimulationRequest,
  SimulationResponse,
  SmsImportResponse,
  SpendingTrendsResponse,
} from '../types/api';

export type ParticipantUpdate = {
  first_name?: string;
  monthly_budget?: number;
  monthly_income?: number;
};

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!resp.ok) throw new Error(`API error ${resp.status}: ${await resp.text()}`);
  return resp.json();
}

// Participants
export const listParticipants = () => request<ParticipantRead[]>('/participants');
export const createParticipant = (data: ParticipantCreate) =>
  request<ParticipantRead>('/participants', { method: 'POST', body: JSON.stringify(data) });
export const getParticipant = (id: string) => request<ParticipantRead>(`/participants/${id}`);
export const updateParticipant = (id: string, data: ParticipantUpdate) =>
  request<ParticipantRead>(`/participants/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
export const deleteParticipant = (id: string) =>
  fetch(`${BASE}/participants/${id}`, { method: 'DELETE' });

// Survey
export const upsertSurvey = (pid: string, data: BehaviorSurveyCreate) =>
  request<BehaviorSurveyRead>(`/participants/${pid}/survey`, { method: 'PUT', body: JSON.stringify(data) });

// Finance
export const createExpense = (pid: string, data: ExpenseEntryCreate) =>
  request<ExpenseEntryRead>(`/participants/${pid}/finance/expenses`, { method: 'POST', body: JSON.stringify(data) });
export const createExpenseBatch = (pid: string, data: ExpenseBatchCreate) =>
  request<ExpenseEntryRead[]>(`/participants/${pid}/finance/expenses/batch`, { method: 'POST', body: JSON.stringify(data) });
export const listExpenses = (pid: string, limit = 50) =>
  request<ExpenseEntryRead[]>(`/participants/${pid}/finance/expenses?limit=${limit}`);
export const createCashflow = (pid: string, data: CashflowEntryCreate) =>
  request<CashflowEntryRead>(`/participants/${pid}/finance/cashflows`, { method: 'POST', body: JSON.stringify(data) });
export const listCashflows = (pid: string, limit = 50) =>
  request<CashflowEntryRead[]>(`/participants/${pid}/finance/cashflows?limit=${limit}`);
export const createCheckin = (pid: string, data: DailyCheckInCreate) =>
  request<DailyCheckInRead>(`/participants/${pid}/finance/checkins`, { method: 'POST', body: JSON.stringify(data) });

// Dashboard & Simulation
export const getDashboard = (pid: string) =>
  request<DashboardSummary>(`/participants/${pid}/finance/dashboard`);
export const runSimulation = (pid: string, data: SimulationRequest) =>
  request<SimulationResponse>(`/participants/${pid}/finance/simulation`, { method: 'POST', body: JSON.stringify(data) });

// Alerts
export const getAlerts = (pid: string) =>
  request<AlertItem[]>(`/participants/${pid}/finance/alerts`);

// Spending Trends
export const getSpendingTrends = (pid: string, days = 30) =>
  request<SpendingTrendsResponse>(`/participants/${pid}/finance/spending-trends?days=${days}`);

export const getMoodTrends = (pid: string, days = 30) =>
  request<MoodSpendingResponse>(`/participants/${pid}/finance/mood-trends?days=${days}`);

// Peer Comparison
export const getPeerComparison = (pid: string) =>
  request<PeerComparisonResponse>(`/participants/${pid}/finance/peer-comparison`);

// Recurring
export const createRecurring = (pid: string, data: RecurringEntryCreate) =>
  request<RecurringEntryRead>(`/participants/${pid}/finance/recurring`, { method: 'POST', body: JSON.stringify(data) });
export const listRecurring = (pid: string) =>
  request<RecurringEntryRead[]>(`/participants/${pid}/finance/recurring`);
export const deleteRecurring = (pid: string, rid: string) =>
  fetch(`${BASE}/participants/${pid}/finance/recurring/${rid}`, { method: 'DELETE' });

// Data Export
export const exportCsv = (pid: string) =>
  `${BASE}/participants/${pid}/finance/export/csv`;

// SMS Import
export const importSms = (pid: string, sms_text: string) =>
  request<SmsImportResponse>(`/participants/${pid}/finance/import/sms`, { method: 'POST', body: JSON.stringify({ sms_text }) });

// Semester Projection
export const getSemesterProjection = (pid: string, months = 4) =>
  request<SemesterProjectionResponse>(`/participants/${pid}/finance/semester-projection?months=${months}`);

// Gamification
export const getGamification = (pid: string) =>
  request<GamificationSummary>(`/participants/${pid}/gamification`);
export const createChallenge = (pid: string) =>
  request<ChallengeRead>(`/participants/${pid}/gamification/challenges`, { method: 'POST' });

// Chat
export const sendChat = (pid: string, message: string, history: { role: string; content: string }[]) => {
  const saved = localStorage.getItem(`bbt_alloc_${pid}`);
  const category_budgets = saved ? JSON.parse(saved) : null;
  return request<ChatResponse>(`/participants/${pid}/chat`, { 
    method: 'POST', 
    body: JSON.stringify({ message, history, category_budgets }) 
  });
};

// ML Insights
export const getMLInsights = (pid: string) =>
  request<MLInsightsResponse>(`/participants/${pid}/finance/ml-insights`);
