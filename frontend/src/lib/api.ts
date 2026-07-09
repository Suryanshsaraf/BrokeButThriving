/* API client — all endpoints with local mock DB fallback */

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
  AchievementRead,
} from '../types/api';

export type ParticipantUpdate = {
  first_name?: string;
  monthly_budget?: number;
  monthly_income?: number;
};

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

// MOCK DATA STORAGE KEYS
const KEYS = {
  PARTICIPANTS: 'bbt_mock_participants',
  EXPENSES: 'bbt_mock_expenses',
  CASHFLOWS: 'bbt_mock_cashflows',
  CHECKINS: 'bbt_mock_checkins',
  SURVEY: 'bbt_mock_survey',
  RECURRING: 'bbt_mock_recurring',
  CHALLENGES: 'bbt_mock_challenges',
};

// HELPER TO SEED DEFAULT DEMO DATA
function getLocalStorage<T>(key: string, defaultValue: T): T {
  const data = localStorage.getItem(key);
  if (!data) {
    localStorage.setItem(key, JSON.stringify(defaultValue));
    return defaultValue;
  }
  return JSON.parse(data);
}

function setLocalStorage<T>(key: string, value: T): void {
  localStorage.setItem(key, JSON.stringify(value));
}

// Initial seeding if empty
const defaultParticipants: ParticipantRead[] = [
  {
    id: 'demo-user',
    participant_code: 'SURYANSH-DEMO',
    first_name: 'Suryansh (Demo)',
    age: 21,
    institution: 'VJTI Mumbai',
    course_name: 'Computer Engineering',
    living_situation: 'hostel',
    dietary_preference: 'veg',
    monthly_budget: 12000,
    monthly_income: 15000,
    starting_balance: 8500,
    created_at: new Date().toISOString(),
  },
];

const defaultExpenses: ExpenseEntryRead[] = [
  {
    id: 'exp-1',
    participant_id: 'demo-user',
    occurred_at: new Date(Date.now() - 4 * 24 * 60 * 60 * 1000).toISOString(),
    amount: 1200,
    category: 'rent',
    merchant: 'Hostel Rent Co.',
    note: 'Monthly hostel share room fee',
    is_social: false,
    is_essential: true,
    created_at: new Date().toISOString(),
  },
  {
    id: 'exp-2',
    participant_id: 'demo-user',
    occurred_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
    amount: 350,
    category: 'food',
    merchant: 'VJTI Mess',
    note: 'Lunch and snacks',
    is_social: false,
    is_essential: true,
    created_at: new Date().toISOString(),
  },
  {
    id: 'exp-3',
    participant_id: 'demo-user',
    occurred_at: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString(),
    amount: 1500,
    category: 'entertainment',
    merchant: 'Immersive Movie Lounge',
    note: 'Weekend film with project team',
    is_social: true,
    is_essential: false,
    created_at: new Date().toISOString(),
  },
  {
    id: 'exp-4',
    participant_id: 'demo-user',
    occurred_at: new Date(Date.now() - 12 * 60 * 60 * 1000).toISOString(),
    amount: 180,
    category: 'transport',
    merchant: 'Uber Auto',
    note: 'Commute to lab',
    is_social: false,
    is_essential: true,
    created_at: new Date().toISOString(),
  },
];

const defaultCashflows: CashflowEntryRead[] = [
  {
    id: 'cf-1',
    participant_id: 'demo-user',
    occurred_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
    amount: 15000,
    category: 'allowance',
    source: 'Parents',
    note: 'Monthly allowance stipend',
    created_at: new Date().toISOString(),
  },
];

const defaultChallenges: ChallengeRead[] = [
  {
    id: 'ch-1',
    participant_id: 'demo-user',
    title: 'Frugal Week',
    description: 'Keep entertainment and social spends below ₹1,000 for 7 days.',
    challenge_type: 'spend_limit',
    target_value: 1000,
    current_value: 1500,
    progress_pct: 66,
    status: 'active',
    start_date: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
    end_date: null,
  },
  {
    id: 'ch-2',
    participant_id: 'demo-user',
    title: 'Streak Starter',
    description: 'Complete 3 daily check-ins in a row.',
    challenge_type: 'checkin_streak',
    target_value: 3,
    current_value: 3,
    progress_pct: 100,
    status: 'completed',
    start_date: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
    end_date: new Date().toISOString(),
  },
];

// Fallback logic if API throws or doesn't resolve
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  try {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), 1200); // Fast timeout to trigger mock mode quickly

    const resp = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...options?.headers },
      signal: controller.signal,
      ...options,
    });
    clearTimeout(id);
    if (!resp.ok) throw new Error(`API error ${resp.status}`);
    return await resp.json();
  } catch (err) {
    console.warn(`[BBT Demo DB] Redirecting '${path}' request to in-browser storage. Reason:`, err);
    return getMockData<T>(path, options);
  }
}

// MOCK CLIENT DATABASE PROCESSOR
function getMockData<T>(path: string, options?: RequestInit): Promise<T> {
  const parts = path.split('/').filter(Boolean);
  
  // SEED DATABASES
  const participants = getLocalStorage<ParticipantRead[]>(KEYS.PARTICIPANTS, defaultParticipants);
  const expenses = getLocalStorage<ExpenseEntryRead[]>(KEYS.EXPENSES, defaultExpenses);
  const cashflows = getLocalStorage<CashflowEntryRead[]>(KEYS.CASHFLOWS, defaultCashflows);
  const checkins = getLocalStorage<DailyCheckInRead[]>(KEYS.CHECKINS, []);
  const challenges = getLocalStorage<ChallengeRead[]>(KEYS.CHALLENGES, defaultChallenges);

  // Parse Method
  const method = options?.method || 'GET';
  const body = options?.body ? JSON.parse(options.body) : null;

  // 1. GET /participants or POST /participants
  if (parts[0] === 'participants' && parts.length === 1) {
    if (method === 'POST') {
      const newP: ParticipantRead = {
        ...body,
        id: `p-${Math.random().toString(36).substr(2, 9)}`,
        created_at: new Date().toISOString(),
      };
      participants.push(newP);
      setLocalStorage(KEYS.PARTICIPANTS, participants);
      return Promise.resolve(newP as unknown as T);
    }
    return Promise.resolve(participants as unknown as T);
  }

  // 2. GET/PATCH/DELETE /participants/:id
  if (parts[0] === 'participants' && parts.length === 2) {
    const pid = parts[1];
    const index = participants.findIndex((p) => p.id === pid);
    
    if (method === 'PATCH') {
      if (index !== -1) {
        participants[index] = { ...participants[index], ...body };
        setLocalStorage(KEYS.PARTICIPANTS, participants);
        return Promise.resolve(participants[index] as unknown as T);
      }
    }
    const found = participants.find((p) => p.id === pid) || participants[0];
    return Promise.resolve(found as unknown as T);
  }

  // 3. /participants/:id/survey
  if (parts[0] === 'participants' && parts[2] === 'survey') {
    const pid = parts[1];
    if (method === 'PUT') {
      const survey: BehaviorSurveyRead = {
        ...body,
        id: `survey-${pid}`,
        participant_id: pid,
        created_at: new Date().toISOString(),
      };
      setLocalStorage(`${KEYS.SURVEY}_${pid}`, survey);
      return Promise.resolve(survey as unknown as T);
    }
    const emptySurvey: BehaviorSurveyRead = {
      id: `survey-${pid}`,
      participant_id: pid,
      stress_spending_score: 5,
      social_pressure_score: 5,
      boredom_spending_score: 5,
      planning_confidence_score: 5,
      created_at: new Date().toISOString(),
    };
    const saved = getLocalStorage(`${KEYS.SURVEY}_${pid}`, emptySurvey);
    return Promise.resolve(saved as unknown as T);
  }

  // 4. /participants/:id/finance/expenses
  if (parts[0] === 'participants' && parts[2] === 'finance' && parts[3] === 'expenses') {
    const pid = parts[1];
    if (method === 'POST') {
      const newE: ExpenseEntryRead = {
        ...body,
        id: `exp-${Math.random().toString(36).substr(2, 9)}`,
        participant_id: pid,
        created_at: new Date().toISOString(),
      };
      expenses.push(newE);
      setLocalStorage(KEYS.EXPENSES, expenses);
      return Promise.resolve(newE as unknown as T);
    }
    
    // Batch import
    if (parts[4] === 'batch' && method === 'POST') {
      const newBatch = (body.expenses || []).map((e: any) => ({
        ...e,
        id: `exp-${Math.random().toString(36).substr(2, 9)}`,
        participant_id: pid,
        created_at: new Date().toISOString(),
      }));
      expenses.push(...newBatch);
      setLocalStorage(KEYS.EXPENSES, expenses);
      return Promise.resolve(newBatch as unknown as T);
    }

    const filtered = expenses.filter((e) => e.participant_id === pid);
    return Promise.resolve(filtered as unknown as T);
  }

  // 5. /participants/:id/finance/cashflows
  if (parts[0] === 'participants' && parts[2] === 'finance' && parts[3] === 'cashflows') {
    const pid = parts[1];
    if (method === 'POST') {
      const newC: CashflowEntryRead = {
        ...body,
        id: `cf-${Math.random().toString(36).substr(2, 9)}`,
        participant_id: pid,
        created_at: new Date().toISOString(),
      };
      cashflows.push(newC);
      setLocalStorage(KEYS.CASHFLOWS, cashflows);
      return Promise.resolve(newC as unknown as T);
    }
    const filtered = cashflows.filter((c) => c.participant_id === pid);
    return Promise.resolve(filtered as unknown as T);
  }

  // 6. /participants/:id/finance/checkins
  if (parts[0] === 'participants' && parts[2] === 'finance' && parts[3] === 'checkins') {
    const pid = parts[1];
    if (method === 'POST') {
      const newCh: DailyCheckInRead = {
        ...body,
        id: `chin-${Math.random().toString(36).substr(2, 9)}`,
        participant_id: pid,
        created_at: new Date().toISOString(),
      };
      checkins.push(newCh);
      setLocalStorage(KEYS.CHECKINS, checkins);
      return Promise.resolve(newCh as unknown as T);
    }
    const filtered = checkins.filter((ch) => ch.participant_id === pid);
    return Promise.resolve(filtered as unknown as T);
  }

  // 7. /participants/:id/finance/dashboard
  if (parts[0] === 'participants' && parts[2] === 'finance' && parts[3] === 'dashboard') {
    const pid = parts[1];
    const user = participants.find((p) => p.id === pid) || participants[0];
    const userExpenses = expenses.filter((e) => e.participant_id === pid);
    const userCashflows = cashflows.filter((c) => c.participant_id === pid);

    const monthlyBudget = user?.monthly_budget || 12000;
    const monthlyIncome = user?.monthly_income || 15000;
    const startingBalance = user?.starting_balance || 8500;

    const totalExpense = userExpenses.reduce((sum, e) => sum + e.amount, 0);
    const totalInflow = userCashflows.reduce((sum, c) => sum + c.amount, 0);
    const currentBalance = startingBalance + totalInflow - totalExpense;

    // Categorized breakdown
    const categorySum: Record<string, number> = {};
    userExpenses.forEach((e) => {
      categorySum[e.category] = (categorySum[e.category] || 0) + e.amount;
    });
    
    const topCategories = Object.entries(categorySum)
      .map(([category, total_spend]) => ({
        category,
        total_spend,
        share_of_spend: totalExpense ? Math.round((total_spend / totalExpense) * 100) : 0,
      }))
      .sort((a, b) => b.total_spend - a.total_spend);

    const budgetUsedPct = Math.round((totalExpense / monthlyBudget) * 100);
    const budgetRemaining = Math.max(0, monthlyBudget - totalExpense);

    const avgDaily14 = Math.round(totalExpense / 14) || 250;
    const daysRemaining = avgDaily14 ? Math.round(currentBalance / avgDaily14) : 30;

    const riskScore = Math.min(100, Math.max(10, Math.round((totalExpense / monthlyBudget) * 80)));
    const riskBand = riskScore > 80 ? 'critical' : riskScore > 50 ? 'moderate' : 'low';

    const dashboard: DashboardSummary = {
      participant_id: pid,
      current_balance: currentBalance,
      current_month_spend: totalExpense,
      current_month_inflow: totalInflow,
      average_daily_spend_14d: avgDaily14,
      projected_days_remaining: daysRemaining,
      risk_score: riskScore,
      risk_band: riskBand,
      top_categories: topCategories,
      highlight_messages: [
        totalExpense > monthlyBudget ? '⚠️ Monthly budget threshold breached!' : '✅ Spending is currently within safe limits.',
        currentBalance < 2000 ? '🚨 Low balance warning — avoid premium entertainment!' : '💡 Savings projection is positive.',
      ],
      monthly_budget: monthlyBudget,
      budget_used_pct: budgetUsedPct,
      budget_remaining: budgetRemaining,
      budget_status: totalExpense > monthlyBudget ? 'over_budget' : 'healthy',
      today_spend: userExpenses.filter(e => new Date(e.occurred_at).toDateString() === new Date().toDateString()).reduce((sum, e) => sum + e.amount, 0),
      current_week_spend: totalExpense,
      target_daily_budget: Math.round(monthlyBudget / 30),
      target_weekly_budget: Math.round(monthlyBudget / 4),
      short_term_forecasts: ['High likelihood of social weekend spending triggers.', 'Low-risk bill timeline ahead.'],
      recovery_plan: ['Reduce dining out/shopping next week by 20%', 'Switch to on-campus library utilities for printing'],
    };

    return Promise.resolve(dashboard as unknown as T);
  }

  // 8. /participants/:id/finance/spending-trends
  if (parts[0] === 'participants' && parts[2] === 'finance' && parts[3] === 'spending-trends') {
    const pid = parts[1];
    const userExpenses = expenses.filter((e) => e.participant_id === pid);
    
    // Last 7 days daily spending
    const daily: Record<string, number> = {};
    for (let i = 6; i >= 0; i--) {
      const d = new Date(Date.now() - i * 24 * 60 * 60 * 1000).toDateString();
      daily[d] = 0;
    }
    userExpenses.forEach((e) => {
      const d = new Date(e.occurred_at).toDateString();
      if (d in daily) {
        daily[d] += e.amount;
      }
    });

    const daily_spend = Object.entries(daily).map(([date, amount]) => ({
      date: date.substring(0, 10),
      amount,
    }));

    const trends: SpendingTrendsResponse = {
      daily_spend,
      weekly_totals: [{ date: 'Week 1', amount: 3500 }, { date: 'Week 2', amount: 2800 }],
      category_totals: [],
      income_vs_expense: [
        { week: 'W1', income: 15000, expense: totalSum(userExpenses) },
      ],
    };
    return Promise.resolve(trends as unknown as T);
  }

  // 9. /participants/:id/finance/mood-trends
  if (parts[0] === 'participants' && parts[2] === 'finance' && parts[3] === 'mood-trends') {
    const mockMood: MoodSpendingResponse = {
      trends: [
        { date: 'Mon', amount: 150, stress_level: 3, exam_pressure: 2, mood_energy: 7 },
        { date: 'Tue', amount: 0, stress_level: 4, exam_pressure: 3, mood_energy: 6 },
        { date: 'Wed', amount: 350, stress_level: 7, exam_pressure: 6, mood_energy: 4 },
        { date: 'Thu', amount: 50, stress_level: 5, exam_pressure: 5, mood_energy: 5 },
        { date: 'Fri', amount: 1500, stress_level: 8, exam_pressure: 7, mood_energy: 3 },
      ],
      correlation_insight: 'High exam/stress days correlate with an average +120% increase in food & entertainment spending (stress buying).',
    };
    return Promise.resolve(mockMood as unknown as T);
  }

  // 10. /participants/:id/finance/peer-comparison
  if (parts[0] === 'participants' && parts[2] === 'finance' && parts[3] === 'peer-comparison') {
    const res: PeerComparisonResponse = {
      peer_count: 142,
      comparisons: [
        {
          metric: 'Food Spend Ratio',
          your_value: 38,
          peer_avg: 42,
          percentile: 45,
          interpretation: 'You are spending slightly less than similar students on eating out.',
        },
        {
          metric: 'Impulse Spending',
          your_value: 18,
          peer_avg: 12,
          percentile: 72,
          interpretation: 'Your entertainment-category spends rank higher than 72% of peers.',
        },
      ],
    };
    return Promise.resolve(res as unknown as T);
  }

  // 11. /participants/:id/finance/semester-projection
  if (parts[0] === 'participants' && parts[2] === 'finance' && parts[3] === 'semester-projection') {
    const res: SemesterProjectionResponse = {
      current_balance: 14500,
      projected_end_balance: 2400,
      monthly_burn: 4100,
      months_remaining: 3.5,
      projection_points: [
        { date: 'Month 1', projected_balance: 14500 },
        { date: 'Month 2', projected_balance: 10400 },
        { date: 'Month 3', projected_balance: 6300 },
        { date: 'Month 4', projected_balance: 2200 },
      ],
      recommendations: [
        'Consolidate subscription services (Netflix/Spotify) into student bundles to save ₹550/mo.',
        'Cook in-house dinner twice a week rather than food delivery.',
      ],
    };
    return Promise.resolve(res as unknown as T);
  }

  // 12. /participants/:id/gamification
  if (parts[0] === 'participants' && parts[2] === 'gamification') {
    const res: GamificationSummary = {
      active_challenges: challenges.filter(c => c.status === 'active'),
      achievements: [
        { id: 'ach-1', badge_id: 'streak_3d', title: 'Frugal Spark', description: 'Met checkin goal 3 days straight', icon: '🔥', earned_at: new Date().toISOString() },
        { id: 'ach-2', badge_id: 'budget_master', title: 'Budget Captain', description: 'Setup structured budget configuration', icon: '🛡️', earned_at: new Date().toISOString() },
      ],
      no_spend_streak: 2,
      under_budget_days: 12,
    };
    return Promise.resolve(res as unknown as T);
  }

  // 13. /participants/:id/chat
  if (parts[0] === 'participants' && parts[2] === 'chat') {
    const userMsg = body.message?.toLowerCase() || '';
    let reply = "Hello! I am your Broke But Thriving personal finance agent running in Offline Demo Mode. I can help analyze your budget, plan for saving, and run simulations. If you log a transaction under 'Log Entry', I'll update your charts!";
    
    if (userMsg.includes('help') || userMsg.includes('what') || userMsg.includes('can you')) {
      reply = "In sandbox mode, you can log expenses, track monthly projections, and query your budget. Try asking me 'Should I buy a new laptop?' or 'How is my budget looking?'";
    } else if (userMsg.includes('laptop') || userMsg.includes('buy') || userMsg.includes('spend')) {
      reply = "Looking at your current balance and monthly trajectory: Buying a laptop will breach your ₹12,000 threshold and reduce your semester-end forecast to critical levels. I suggest exploring zero-down student EMI options or delaying the purchase by 2 months.";
    } else if (userMsg.includes('budget') || userMsg.includes('track') || userMsg.includes('status')) {
      reply = `You have already spent ₹${totalSum(expenses)} out of your monthly budget. Your remaining budget is looking stable. Keep tracking daily!`;
    }

    const res: ChatResponse = {
      reply,
      tools_used: ['query_database', 'run_monte_carlo'],
    };
    return Promise.resolve(res as unknown as T);
  }

  // 14. /participants/:id/finance/ml-insights
  if (parts[0] === 'participants' && parts[2] === 'finance' && parts[3] === 'ml-insights') {
    const res: MLInsightsResponse = {
      model_available: true,
      wellbeing_score: 72,
      wellbeing_band: 'good',
      hardship_risk: 15,
      hardship_band: 'low',
      bill_difficulty_risk: 20,
      bill_difficulty_band: 'low',
      spending_archetype: 'balanced',
      archetype_confidence: 88,
      discretionary_ratio: 0.24,
      spend_to_income_ratio: 0.35,
      insights: [
        'LSTM predicts budget compliance with 90% confidence.',
        'High food share is compensated by zero transport expenses (campus PG).',
      ],
    };
    return Promise.resolve(res as unknown as T);
  }

  // 15. SMS Import
  if (parts[0] === 'participants' && parts[2] === 'finance' && parts[3] === 'import' && parts[4] === 'sms') {
    const parsedText = body.sms_text || '';
    let amount = 250;
    let merchant = 'Unknown Merchant';
    
    const matchAmt = parsedText.match(/Rs\.?\s?([0-9,]+)/i) || parsedText.match(/INR\s?([0-9,]+)/i);
    if (matchAmt) amount = parseFloat(matchAmt[1].replace(/,/g, ''));
    
    const matchMerch = parsedText.match(/spent at ([a-zA-Z0-9\s]+)/i) || parsedText.match(/sent to ([a-zA-Z0-9\s]+)/i);
    if (matchMerch) merchant = matchMerch[1].trim();

    const newSmsExpense: ExpenseEntryRead = {
      id: `exp-sms-${Date.now()}`,
      participant_id: pidFromParts(parts),
      occurred_at: new Date().toISOString(),
      amount,
      category: 'other',
      merchant,
      note: `SMS Import: "${parsedText.substring(0, 30)}..."`,
      is_social: false,
      is_essential: true,
      created_at: new Date().toISOString(),
    };

    expenses.push(newSmsExpense);
    setLocalStorage(KEYS.EXPENSES, expenses);

    const res: SmsImportResponse = {
      parsed_count: 1,
      expenses: [newSmsExpense],
      errors: [],
    };
    return Promise.resolve(res as unknown as T);
  }

  return Promise.resolve({} as unknown as T);
}

// Sub Helpers
function totalSum(list: any[]): number {
  return list.reduce((sum, item) => sum + (item.amount || 0), 0);
}
function pidFromParts(parts: string[]): string {
  return parts[1] || 'demo-user';
}

// Participants API Actions mapping to Local Mock DB
export const listParticipants = () => request<ParticipantRead[]>('/participants');
export const createParticipant = (data: ParticipantCreate) =>
  request<ParticipantRead>('/participants', { method: 'POST', body: JSON.stringify(data) });
export const getParticipant = (id: string) => request<ParticipantRead>(`/participants/${id}`);
export const updateParticipant = (id: string, data: ParticipantUpdate) =>
  request<ParticipantRead>(`/participants/${id}`, { method: 'PATCH', body: JSON.stringify(data) });

export const deleteParticipant = (id: string) => {
  const participants = getLocalStorage<ParticipantRead[]>(KEYS.PARTICIPANTS, defaultParticipants);
  const filtered = participants.filter((p) => p.id !== id);
  setLocalStorage(KEYS.PARTICIPANTS, filtered);
  return Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true }) } as unknown as Response);
};

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
export const createRecurring = (pid: string, data: RecurringEntryCreate) => {
  const recurring = getLocalStorage<RecurringEntryRead[]>(KEYS.RECURRING, []);
  const newRec: RecurringEntryRead = {
    ...data,
    id: `rec-${Date.now()}`,
    participant_id: pid,
    is_active: true,
    created_at: new Date().toISOString(),
  };
  recurring.push(newRec);
  setLocalStorage(KEYS.RECURRING, recurring);
  return Promise.resolve(newRec);
};

export const listRecurring = (pid: string) => {
  const recurring = getLocalStorage<RecurringEntryRead[]>(KEYS.RECURRING, []);
  return Promise.resolve(recurring.filter(r => r.participant_id === pid));
};

export const deleteRecurring = (pid: string, rid: string) => {
  const recurring = getLocalStorage<RecurringEntryRead[]>(KEYS.RECURRING, []);
  const filtered = recurring.filter(r => r.id !== rid || r.participant_id !== pid);
  setLocalStorage(KEYS.RECURRING, filtered);
  return Promise.resolve({ ok: true } as unknown as Response);
};

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
export const createChallenge = (pid: string) => {
  const challenges = getLocalStorage<ChallengeRead[]>(KEYS.CHALLENGES, defaultChallenges);
  const newC: ChallengeRead = {
    id: `ch-${Date.now()}`,
    participant_id: pid,
    title: 'New Mock Challenge',
    description: 'Reduce weekly transaction count by 10%.',
    challenge_type: 'streak',
    target_value: 5,
    current_value: 0,
    progress_pct: 0,
    status: 'active',
    start_date: new Date().toISOString(),
    end_date: null,
  };
  challenges.push(newC);
  setLocalStorage(KEYS.CHALLENGES, challenges);
  return Promise.resolve(newC);
};

// Chat
export const sendChat = (pid: string, message: string, history: { role: string; content: string }[]) =>
  request<ChatResponse>(`/participants/${pid}/chat`, { 
    method: 'POST', 
    body: JSON.stringify({ message, history }) 
  });

// ML Insights
export const getMLInsights = (pid: string) =>
  request<MLInsightsResponse>(`/participants/${pid}/finance/ml-insights`);
