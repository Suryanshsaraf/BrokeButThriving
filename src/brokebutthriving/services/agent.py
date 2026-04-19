"""Agentic AI copilot service.

Uses an OpenAI-compatible LLM (default: Groq / Llama-3.3-70B) with
function-calling to give participants personalised financial coaching
grounded in their real data.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from openai import OpenAI
from sqlmodel import Session, select

from brokebutthriving.core.config import settings
from brokebutthriving.models.entities import (
    CashflowEntry,
    DailyCheckIn,
    ExpenseEntry,
    Participant,
)
from brokebutthriving.schemas.api import (
    ChatMessage,
    SimulationRequest,
)
from brokebutthriving.services.analytics import build_dashboard, simulate_plan

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are **BrokeButThriving Copilot**, a friendly and supportive personal finance coach for college students.

Rules you MUST follow:
1. Always ground your advice in the participant's REAL data — use the tools provided to fetch it.
2. Never invent or hallucinate numbers. If you don't have data, say so and suggest logging some.
3. Keep responses concise (2–4 short paragraphs max). Use bullet points when listing items.
4. Speak in a warm, encouraging tone. The student may be stressed about money — be empathetic.
5. When you spot risky patterns (high burn rate, stress-correlated spending), flag them gently with actionable suggestions.
6. Use Indian Rupees (Rs) for currency. Use the student's first name if available.
7. If the student asks something unrelated to personal finance, gently redirect them.
8. After analysing data, always end with one concrete, actionable tip.
9. BE AWARE OF DYNAMIC BUDGET ALLOCATIONS: If you receive the user's custom category budget allocations in the context, evaluate their choices. Warn them if they are heavily indexing into non-essential categories (like entertainment or shopping) at the risk of essential categories (like rent, food, health, utilities). Positive reinforcement should be given for good balanced saving habits.
"""

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_dashboard",
            "description": (
                "Get the participant's live financial dashboard including current balance, "
                "monthly spend, daily burn rate, risk score, risk band, top spending categories, "
                "and highlight messages."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_expenses",
            "description": (
                "Get the participant's recent expense entries. "
                "Returns a list of expenses with amount, category, merchant, date, and notes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of past days to look back. Default 14.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_cashflows",
            "description": (
                "Get the participant's recent cash inflows (allowance, salary, freelance, etc.)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of past days to look back. Default 30.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_what_if",
            "description": (
                "Run a what-if simulation. Adjusts spending in specific categories and/or "
                "adds income to see the projected impact on end-of-period balance and risk."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "food_change_pct": {
                        "type": "number",
                        "description": "Fractional change for food, e.g. -0.2 = cut food by 20%.",
                    },
                    "entertainment_change_pct": {
                        "type": "number",
                        "description": "Fractional change for entertainment spending.",
                    },
                    "shopping_change_pct": {
                        "type": "number",
                        "description": "Fractional change for shopping spending.",
                    },
                    "additional_income": {
                        "type": "number",
                        "description": "Extra one-time income to add to the projection.",
                    },
                    "horizon_days": {
                        "type": "integer",
                        "description": "Number of days to project forward. Default 14.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spending_by_category",
            "description": (
                "Get a breakdown of the participant's spending grouped by category "
                "for a given time period."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of past days to aggregate. Default 30.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_checkin_summary",
            "description": (
                "Get a summary of the participant's recent daily check-ins including "
                "average stress, exam pressure, social pressure, mood/energy, and sleep hours."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of past days to look back. Default 14.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_expense",
            "description": (
                "Log a new expense for the participant automatically when they tell you they bought something. Extracts the amount, "
                "category, and a short note from the user's message."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "The amount spent (in Rupees).",
                    },
                    "category": {
                        "type": "string",
                        "description": "The inferred category (food, transport, entertainment, shopping, bills, health, education, other).",
                    },
                    "merchant": {
                        "type": "string",
                        "description": "The inferred merchant or location (e.g. Starbucks, Zomato, BookStore).",
                    },
                    "note": {
                        "type": "string",
                        "description": "A short note about what the expense was.",
                    },
                },
                "required": ["amount", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_challenge",
            "description": (
                "Create a new gamification challenge for the user. Call this tool when predicting "
                "or simulating a budget cut to give the user an actionable saving goal."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "A short, catchy title (e.g. 'Coffee Detox', 'Pizza Freeze').",
                    },
                    "description": {
                        "type": "string",
                        "description": "Details about how to achieve it.",
                    },
                    "target_amount": {
                        "type": "number",
                        "description": "The target Rupee amount to save or cut back on.",
                    },
                    "days": {
                        "type": "integer",
                        "description": "How many days the challenge lasts.",
                    },
                },
                "required": ["title", "description", "target_amount", "days"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Tool executors — each reads real data from the DB
# ---------------------------------------------------------------------------


def _exec_get_dashboard(session: Session, participant_id: str, _args: dict[str, Any]) -> dict:
    summary = build_dashboard(session, participant_id)
    return summary.model_dump()


def _exec_get_recent_expenses(
    session: Session, participant_id: str, args: dict[str, Any]
) -> dict:
    days = int(args.get("days", 14))
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = session.exec(
        select(ExpenseEntry)
        .where(ExpenseEntry.participant_id == participant_id)
        .where(ExpenseEntry.occurred_at >= cutoff)
        .order_by(ExpenseEntry.occurred_at.desc())
    ).all()
    return {
        "count": len(rows),
        "total": round(sum(r.amount for r in rows), 2),
        "expenses": [
            {
                "date": r.occurred_at.isoformat(),
                "amount": r.amount,
                "category": r.category.value,
                "merchant": r.merchant,
                "note": r.note,
                "is_social": r.is_social,
                "is_essential": r.is_essential,
            }
            for r in rows[:20]  # cap to avoid token overflow
        ],
    }


def _exec_get_recent_cashflows(
    session: Session, participant_id: str, args: dict[str, Any]
) -> dict:
    days = int(args.get("days", 30))
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = session.exec(
        select(CashflowEntry)
        .where(CashflowEntry.participant_id == participant_id)
        .where(CashflowEntry.occurred_at >= cutoff)
        .order_by(CashflowEntry.occurred_at.desc())
    ).all()
    return {
        "count": len(rows),
        "total": round(sum(r.amount for r in rows), 2),
        "cashflows": [
            {
                "date": r.occurred_at.isoformat(),
                "amount": r.amount,
                "category": r.category.value,
                "note": r.note,
            }
            for r in rows
        ],
    }


def _exec_run_what_if(session: Session, participant_id: str, args: dict[str, Any]) -> dict:
    adjustments: dict[str, float] = {}
    if "food_change_pct" in args:
        adjustments["food"] = float(args["food_change_pct"])
    if "entertainment_change_pct" in args:
        adjustments["entertainment"] = float(args["entertainment_change_pct"])
    if "shopping_change_pct" in args:
        adjustments["shopping"] = float(args["shopping_change_pct"])

    req = SimulationRequest(
        lookback_days=21,
        horizon_days=int(args.get("horizon_days", 14)),
        category_adjustments=adjustments,
        additional_income=float(args.get("additional_income", 0)),
    )
    result = simulate_plan(session, participant_id, req)
    return result.model_dump()


def _exec_get_spending_by_category(
    session: Session, participant_id: str, args: dict[str, Any]
) -> dict:
    days = int(args.get("days", 30))
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = session.exec(
        select(ExpenseEntry)
        .where(ExpenseEntry.participant_id == participant_id)
        .where(ExpenseEntry.occurred_at >= cutoff)
    ).all()
    totals: dict[str, float] = defaultdict(float)
    for r in rows:
        totals[r.category.value] += r.amount
    grand_total = sum(totals.values())
    breakdown = [
        {
            "category": cat,
            "total": round(total, 2),
            "share": round(total / grand_total, 3) if grand_total else 0,
        }
        for cat, total in sorted(totals.items(), key=lambda x: x[1], reverse=True)
    ]
    return {"days": days, "grand_total": round(grand_total, 2), "categories": breakdown}


def _exec_get_checkin_summary(
    session: Session, participant_id: str, args: dict[str, Any]
) -> dict:
    days = int(args.get("days", 14))
    cutoff = datetime.now(UTC).date() - timedelta(days=days)
    rows = session.exec(
        select(DailyCheckIn)
        .where(DailyCheckIn.participant_id == participant_id)
        .where(DailyCheckIn.check_in_date >= cutoff)
        .order_by(DailyCheckIn.check_in_date.desc())
    ).all()
    if not rows:
        return {"count": 0, "message": "No check-ins found in the last {} days.".format(days)}

    avg = lambda attr: round(sum(getattr(r, attr) for r in rows) / len(rows), 1)  # noqa: E731
    sleep_vals = [r.sleep_hours for r in rows if r.sleep_hours is not None]
    return {
        "count": len(rows),
        "days_covered": days,
        "avg_stress": avg("stress_level"),
        "avg_exam_pressure": avg("exam_pressure"),
        "avg_social_pressure": avg("social_pressure"),
        "avg_mood_energy": avg("mood_energy"),
        "latest_notes": rows[0].notes if rows[0].notes else None,
    }


def _exec_log_expense(
    session: Session, participant_id: str, args: dict[str, Any]
) -> dict:
    try:
        from brokebutthriving.models.entities import ExpenseCategory
        amount = float(args["amount"])
        try:
            category = ExpenseCategory(args["category"].lower())
        except ValueError:
            category = ExpenseCategory.OTHER
            
        entry = ExpenseEntry(
            participant_id=participant_id,
            occurred_at=datetime.now(UTC),
            amount=amount,
            category=category,
            merchant=args.get("merchant"),
            note=args.get("note"),
            source="copilot",
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return {"success": True, "message": f"Logged Rs {amount} for {category.value}", "entry_id": entry.id}
    except Exception as exc:
        return {"error": f"Failed to log expense: {str(exc)}"}


def _exec_create_challenge(
    session: Session, participant_id: str, args: dict[str, Any]
) -> dict:
    try:
        from brokebutthriving.models.entities import Challenge, ChallengeStatus
        import datetime
        end_date = datetime.date.today() + datetime.timedelta(days=int(args.get("days", 7)))
        challenge = Challenge(
            participant_id=participant_id,
            title=args["title"],
            description=args["description"],
            challenge_type="saving_goal",
            target_value=float(args["target_amount"]),
            status=ChallengeStatus.ACTIVE,
            end_date=end_date,
        )
        session.add(challenge)
        session.commit()
        session.refresh(challenge)
        return {"success": True, "message": f"Successfully created Active Challenge: {challenge.title}"}
    except Exception as exc:
        return {"error": f"Failed to create challenge: {str(exc)}"}


TOOL_EXECUTORS: dict[str, Any] = {
    "get_dashboard": _exec_get_dashboard,
    "get_recent_expenses": _exec_get_recent_expenses,
    "get_recent_cashflows": _exec_get_recent_cashflows,
    "run_what_if": _exec_run_what_if,
    "get_spending_by_category": _exec_get_spending_by_category,
    "get_checkin_summary": _exec_get_checkin_summary,
    "log_expense": _exec_log_expense,
    "create_challenge": _exec_create_challenge,
}

# ---------------------------------------------------------------------------
# Agent loop (OpenAI SDK — works with Groq, OpenAI, Together, etc.)
# ---------------------------------------------------------------------------


def _build_messages(
    participant: Participant,
    message: str,
    history: list[ChatMessage],
    category_budgets: dict[str, float] | None = None,
) -> list[dict[str, str]]:
    """Convert frontend chat history into OpenAI message dicts."""
    allocations_text = f", Custom Category Budgets: {category_budgets}" if category_budgets else ""
    context_text = (
        f"[Participant context — name: {participant.first_name or participant.participant_code}, "
        f"age: {participant.age}, institution: {participant.institution or 'unknown'}, "
        f"budget: Rs {participant.monthly_budget:.0f}/month, "
        f"income: Rs {participant.monthly_income:.0f}/month, "
        f"living: {participant.living_situation.value}{allocations_text}]"
    )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})

    # Current message — prepend participant context on the first user turn
    user_content = f"{context_text}\n\n{message}" if not history else message
    messages.append({"role": "user", "content": user_content})

    return messages


def run_agent(
    session: Session,
    participant_id: str,
    message: str,
    history: list[ChatMessage],
    category_budgets: dict[str, float] | None = None,
) -> tuple[str, list[str]]:
    """Run one agentic turn: send message → handle tool calls → return reply.

    Returns (reply_text, tools_used_list).
    """
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise ValueError("Participant not found")

    if not settings.llm_api_key:
        return (
            "The AI copilot is not configured yet. Please set the `BBT_LLM_API_KEY` "
            "environment variable and restart the backend.",
            [],
        )

    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )
    messages = _build_messages(participant, message, history, category_budgets)
    tools_used: list[str] = []

    # Agentic loop — keep going while the model requests tool calls
    max_iterations = 6
    for _ in range(max_iterations):
        # Retry with exponential backoff for rate-limit (429) errors
        response = None
        for attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=settings.llm_model,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    temperature=0.7,
                    max_tokens=1024,
                )
                break  # success
            except Exception as api_err:
                err_str = str(api_err)
                if "429" in err_str or "rate" in err_str.lower():
                    if attempt < 2:
                        wait = 2 ** (attempt + 1)  # 2s, 4s
                        logger.warning("Rate limited, retrying in %ds…", wait)
                        time.sleep(wait)
                        continue
                    return (
                        "I'm currently rate-limited by the AI service. "
                        "Please wait a moment and try again.",
                        tools_used,
                    )
                raise

        if response is None:
            return "I couldn't reach the AI service. Please try again later.", tools_used

        choice = response.choices[0] if response.choices else None
        if choice is None:
            return "I'm sorry, I couldn't generate a response. Please try again.", tools_used

        assistant_message = choice.message

        # If the model wants to call tools
        if assistant_message.tool_calls:
            # Add the assistant's message (with tool calls) to conversation
            # Note: we build the dict manually to avoid unsupported fields
            # like 'annotations' that some providers (e.g. Groq) reject.
            assistant_dict: dict[str, Any] = {
                "role": "assistant",
                "content": assistant_message.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in assistant_message.tool_calls
                ],
            }
            messages.append(assistant_dict)

            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                except json.JSONDecodeError:
                    tool_args = {}
                tools_used.append(tool_name)

                executor = TOOL_EXECUTORS.get(tool_name)
                if executor is None:
                    result = {"error": f"Unknown tool: {tool_name}"}
                else:
                    try:
                        result = executor(session, participant_id, tool_args)
                    except Exception as exc:
                        logger.exception("Tool %s failed", tool_name)
                        result = {"error": str(exc)}

                # Add tool result
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str),
                })

            continue  # Let the model process the tool results

        # Model returned a text response — we're done
        reply = assistant_message.content or "I have nothing to add right now."
        return reply, tools_used

    # Safety: if we exhausted iterations
    return "I ran into a loop while analysing your data. Please try a simpler question.", tools_used
