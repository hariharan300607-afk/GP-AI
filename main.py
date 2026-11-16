from __future__ import annotations

import os
import re
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import date
from pathlib import Path
from typing import Any, AsyncGenerator, Generator, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
DB_PATH = Path(os.environ.get("GP_AI_DB_PATH", str(BASE_DIR / "gp_ai.db")))
SEED_DEMO_DATA = True
CATEGORIES = (
    "Food & Dining",
    "Transport",
    "Shopping",
    "Income",
    "Entertainment",
    "Groceries",
    "Bills & Utilities",
    "Healthcare",
    "Education",
    "Housing",
    "Fitness",
    "Other",
)
CATEGORIZER_DESCRIPTION = "rule-based keyword matching (not a trained ML model)"

# Scores represent the relative reliability of an exact word or phrase match.
CATEGORY_KEYWORDS = {
    "Food & Dining": {
        "swiggy": 0.96, "zomato": 0.96, "restaurant": 0.96, "food delivery": 0.98,
        "cafe": 0.90, "café": 0.90, "pizza": 0.90, "burger": 0.90, "takeaway": 0.90,
        "dining": 0.87, "breakfast": 0.84, "lunch": 0.80, "dinner": 0.80,
        "bakery": 0.88, "coffee": 0.75, "food": 0.72, "dominos": 0.95, "kfc": 0.95,
        "mcdonalds": 0.95, "subway": 0.90,
    },
    "Transport": {
        "uber": 0.96, "ola": 0.94, "rapido": 0.96, "taxi": 0.92, "cab": 0.88,
        "metro": 0.92, "bus": 0.86, "train": 0.87, "petrol": 0.96, "fuel": 0.90,
        "parking": 0.94, "commute": 0.84, "flight": 0.92, "airline": 0.94,
        "toll": 0.92, "rickshaw": 0.95, "ride": 0.72,
    },
    "Shopping": {
        "flipkart": 0.96, "shopping": 0.86, "clothes": 0.82, "clothing": 0.82,
        "shoes": 0.82, "mall": 0.84, "electronics": 0.91, "amazon": 0.84,
        "apparel": 0.88, "retail": 0.80,
    },
    "Income": {
        "salary": 0.98, "payroll": 0.97, "wages": 0.94, "freelance": 0.92,
        "paycheck": 0.96, "stipend": 0.94, "dividend": 0.92, "income": 0.90,
    },
    "Entertainment": {
        "netflix": 0.98, "spotify": 0.98, "hotstar": 0.97, "movie": 0.92,
        "cinema": 0.92, "concert": 0.96, "gaming": 0.84, "games": 0.76,
        "subscription": 0.72, "theatre": 0.90,
    },
    "Groceries": {
        "bigbasket": 0.97, "supermarket": 0.94, "groceries": 0.96, "grocery": 0.95,
        "vegetables": 0.86, "fruit": 0.80, "fruits": 0.84, "milk": 0.80,
        "provisions": 0.90, "produce": 0.77,
    },
    "Bills & Utilities": {
        "electricity": 0.97, "electricity bill": 0.99, "water bill": 0.96,
        "internet bill": 0.97, "gas bill": 0.95, "utility bill": 0.97,
        "mobile recharge": 0.97, "phone recharge": 0.97, "wifi": 0.84,
        "broadband": 0.92, "internet": 0.78, "recharge": 0.84, "utilities": 0.89,
    },
    "Healthcare": {
        "doctor": 0.95, "hospital": 0.98, "pharmacy": 0.95, "medicine": 0.92,
        "medical": 0.92, "clinic": 0.94, "healthcare": 0.98, "dentist": 0.95,
        "dental": 0.93, "lab test": 0.94, "health": 0.76,
    },
    "Education": {
        "college": 0.91, "tuition": 0.97, "course fee": 0.96, "school": 0.88,
        "university": 0.93, "education": 0.94, "course": 0.78, "textbook": 0.91,
        "class fee": 0.92,
    },
    "Housing": {
        "rent": 0.98, "landlord": 0.97, "apartment": 0.94, "mortgage": 0.98,
        "housing": 0.92, "house rent": 0.99, "home maintenance": 0.88,
    },
    "Fitness": {
        "gym": 0.97, "fitness": 0.95, "yoga": 0.91, "workout": 0.90,
        "membership": 0.72, "sports club": 0.94, "exercise": 0.86,
    },
}


def _phrase_matches(tokens: list[str], phrase: str) -> bool:
    phrase_tokens = re.findall(r"[a-z0-9]+", phrase.casefold())
    width = len(phrase_tokens)
    return any(tokens[index:index + width] == phrase_tokens for index in range(len(tokens) - width + 1))


def predict_category(description: str | None) -> tuple[str, float]:
    """Categorize a description with deterministic keyword rules, not a trained model."""
    if not isinstance(description, str) or not description.strip():
        return "Other", 0.0

    tokens = re.findall(r"[a-z0-9]+", description.casefold())
    matches: list[tuple[str, float, int]] = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        scores = [score for phrase, score in keywords.items() if _phrase_matches(tokens, phrase)]
        if scores:
            scores.sort(reverse=True)
            score = min(1.0, scores[0] + min(sum(scores[1:3]) * 0.03, 0.06))
            matches.append((category, score, len(scores)))

    if not matches:
        return "Other", 0.0

    matches.sort(key=lambda result: result[1], reverse=True)
    category, score, match_count = matches[0]
    if score < 0.70:
        return "Other", round(min(score, 0.59), 2)
    if len(matches) > 1 and score - matches[1][1] < 0.12:
        return "Other", 0.5

    confidence = min(0.99, 0.60 + score * 0.35 + min(match_count - 1, 3) * 0.02)
    return category, round(confidence, 2)


@contextmanager
def connect() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(seed_demo_data: bool = True) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            merchant TEXT NOT NULL,
            category TEXT NOT NULL,
            method TEXT NOT NULL DEFAULT 'UPI',
            amount REAL NOT NULL CHECK(amount > 0),
            type TEXT NOT NULL CHECK(type IN ('Income','Expense'))
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS budgets (
            category TEXT PRIMARY KEY,
            amount REAL NOT NULL CHECK(amount >= 0)
        )""")
        transaction_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        budget_count = conn.execute("SELECT COUNT(*) FROM budgets").fetchone()[0]
        if seed_demo_data and transaction_count == 0 and budget_count == 0:
            today = date.today().isoformat()
            samples = [
                (today, "Monthly Salary", "Income", "Bank transfer", 65000, "Income"),
                (today, "Swiggy Dinner", "Food & Dining", "UPI", 450, "Expense"),
                (today, "Amazon India", "Shopping", "Card", 2499, "Expense"),
                (today, "Uber Ride", "Transport", "UPI", 320, "Expense"),
                (today, "Netflix", "Entertainment", "Card", 649, "Expense"),
                (today, "BigBasket Groceries", "Groceries", "UPI", 1850, "Expense"),
                (today, "Electricity Bill", "Bills & Utilities", "UPI", 1320, "Expense"),
                (today, "Apollo Pharmacy", "Healthcare", "UPI", 780, "Expense"),
            ]
            conn.executemany("INSERT INTO transactions(date,merchant,category,method,amount,type) VALUES(?,?,?,?,?,?)", samples)
            conn.executemany("INSERT INTO budgets(category,amount) VALUES(?,?)", [
                ("Food & Dining", 6000), ("Shopping", 5000), ("Transport", 3000),
                ("Groceries", 5000), ("Bills & Utilities", 4000), ("Entertainment", 2000),
                ("Healthcare", 3000), ("Education", 4000), ("Housing", 12000),
            ])


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    init_db(seed_demo_data=SEED_DEMO_DATA)
    yield


app = FastAPI(
    title="GP AI Finance API",
    version="1.0.0",
    description="Personal finance API with rule-based categorization and data-based insights.",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_error_response(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": details})


class TransactionIn(BaseModel):
    date: str
    merchant: str = Field(min_length=1, max_length=160)
    amount: float = Field(gt=0, allow_inf_nan=False)
    type: str = "Expense"
    category: Optional[str] = "Auto-detect"
    method: str = Field(default="UPI", min_length=1, max_length=40)

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Date must use YYYY-MM-DD format.")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Date must be a valid calendar date.") from exc
        return value

    @field_validator("merchant", "method")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field must not be empty.")
        return value

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {"income", "expense"}:
            raise ValueError("Transaction type must be Income or Expense.")
        return normalized.title()

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if value == "Auto-detect" or value in CATEGORIES:
            return value
        raise ValueError("Choose a supported category or Auto-detect.")


class BudgetIn(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    amount: float = Field(ge=0, allow_inf_nan=False)

    @field_validator("category")
    @classmethod
    def validate_budget_category(cls, value: str) -> str:
        value = value.strip()
        if value not in CATEGORIES:
            raise ValueError("Choose a supported category.")
        return value


class AdvisorIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Question must not be empty.")
        return value


class CategoryPredictionIn(BaseModel):
    question: str = Field(default="", max_length=500)
    description: Optional[str] = Field(default=None, max_length=500)


def rows_to_dict(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def get_transactions() -> list[dict[str, Any]]:
    with connect() as conn:
        return rows_to_dict(conn.execute("SELECT * FROM transactions ORDER BY date DESC, id DESC").fetchall())


def calculate_summary(transactions: list[dict[str, Any]]) -> dict[str, float | int]:
    income = round(sum(float(t["amount"]) for t in transactions if t["type"] == "Income"), 2)
    expenses = round(sum(float(t["amount"]) for t in transactions if t["type"] == "Expense"), 2)
    balance = round(income - expenses, 2)
    return {"income": income, "expense": expenses, "balance": balance,
            "rate": round((balance / income) * 100, 1) if income else 0.0,
            "transaction_count": len(transactions)}


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "GP AI Finance API",
        "categorizer": CATEGORIZER_DESCRIPTION,
        "model": CATEGORIZER_DESCRIPTION,
    }


@app.get("/api/transactions")
def list_transactions():
    return get_transactions()


@app.post("/api/transactions", status_code=201)
def add_transaction(payload: TransactionIn):
    tx_type = payload.type
    if payload.category and payload.category != "Auto-detect":
        category, confidence = payload.category, None
    elif tx_type == "Income":
        category, confidence = "Income", 1.0
    else:
        category, confidence = predict_category(payload.merchant)
    with connect() as conn:
        cur = conn.execute("INSERT INTO transactions(date,merchant,category,method,amount,type) VALUES(?,?,?,?,?,?)",
                           (payload.date, payload.merchant, category, payload.method, payload.amount, tx_type))
        tx_id = cur.lastrowid
        row = conn.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
    result = dict(row)
    result["category_confidence"] = confidence
    result["category_source"] = "rule_based" if confidence is not None else "user_selected"
    return result


@app.delete("/api/transactions/{transaction_id}")
def delete_transaction(transaction_id: int):
    with connect() as conn:
        cur = conn.execute("DELETE FROM transactions WHERE id=?", (transaction_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Transaction not found.")
    return {"deleted": transaction_id}


@app.get("/api/dashboard")
def dashboard():
    tx = get_transactions()
    summary = calculate_summary(tx)
    expenses = [t for t in tx if t["type"] == "Expense"]
    by_category = {}
    for t in expenses:
        by_category[t["category"]] = by_category.get(t["category"], 0) + float(t["amount"])
    monthly = {}
    for t in tx:
        key = t["date"][:7]
        monthly.setdefault(key, {"month": key, "income": 0.0, "expense": 0.0})
        monthly[key]["income" if t["type"] == "Income" else "expense"] += float(t["amount"])
    monthly_values = [
        {**monthly[key], "income": round(monthly[key]["income"], 2), "expense": round(monthly[key]["expense"], 2)}
        for key in sorted(monthly)
    ]
    return {
        **summary,
        "by_category": [
        {"category": category, "amount": round(amount, 2)}
        for category, amount in sorted(by_category.items(), key=lambda item: item[1], reverse=True)
        ],
        "monthly": monthly_values,
        "recent": tx[:7],
    }


@app.get("/api/budgets")
def list_budgets():
    with connect() as conn:
        budgets = rows_to_dict(conn.execute("SELECT category,amount FROM budgets ORDER BY category").fetchall())
    current_month = date.today().strftime("%Y-%m")
    tx = [t for t in get_transactions() if t["type"] == "Expense" and t["date"][:7] == current_month]
    used = {}
    for t in tx:
        used[t["category"]] = used.get(t["category"], 0) + float(t["amount"])
    return [
        {
            "category": budget["category"],
            "amount": float(budget["amount"]),
            "spent": round(used.get(budget["category"], 0), 2),
            "remaining": round(float(budget["amount"]) - used.get(budget["category"], 0), 2),
            "percent": round(used.get(budget["category"], 0) / budget["amount"] * 100, 1)
            if budget["amount"] else 0,
        }
        for budget in budgets
    ]


@app.put("/api/budgets")
def save_budget(payload: BudgetIn):
    with connect() as conn:
        conn.execute("INSERT INTO budgets(category,amount) VALUES(?,?) ON CONFLICT(category) DO UPDATE SET amount=excluded.amount",
                     (payload.category.strip(), payload.amount))
    return {"saved": True, "category": payload.category, "amount": payload.amount}


@app.post("/api/advisor")
def advisor(payload: AdvisorIn):
    question = payload.question.casefold()
    tx = get_transactions()
    summary = calculate_summary(tx)
    expenses = [t for t in tx if t["type"] == "Expense"]
    category_totals = {}
    for t in expenses:
        category_totals[t["category"]] = category_totals.get(t["category"], 0) + float(t["amount"])
    top = max(category_totals, key=category_totals.get) if category_totals else None
    budgets = list_budgets()
    budget_attention = [budget for budget in budgets if budget["percent"] >= 80]
    if not tx:
        empty_note = "There are no transactions entered in your GP AI ledger yet. "
    else:
        empty_note = ""
    if any(word in question for word in ["food", "swiggy", "zomato", "dining"]):
        amount = round(category_totals.get("Food & Dining", 0), 2)
        food_budget = next((budget for budget in budgets if budget["category"] == "Food & Dining"), None)
        if food_budget:
            answer = (
                f"Your recorded Food & Dining expenses total ₹{amount:,.2f} across all entered transactions. "
                f"For {date.today():%B}, the saved budget is ₹{food_budget['amount']:,.2f} and recorded spend "
                f"is ₹{food_budget['spent']:,.2f}. These figures only include entries in GP AI."
            )
        else:
            answer = f"{empty_note}Your recorded Food & Dining expenses total ₹{amount:,.2f}. No Food & Dining budget is saved."
    elif any(word in question for word in ["most", "highest", "category", "spend", "spending"]):
        answer = (
            f"Across all entered expense transactions, your largest recorded category is {top}, "
            f"at ₹{category_totals[top]:,.2f}. This uses {len(expenses)} expense records in GP AI."
            if top else f"{empty_note}There are no recorded expenses yet, so I cannot identify a highest-spend category."
        )
    elif any(word in question for word in ["save", "saving"]):
        if summary["income"] <= 0:
            answer = (
                f"{empty_note}Your records do not include income, so a savings rate cannot be calculated. "
                "Record income and expenses for a more useful view, and account for bills or cash movements "
                "that may not be entered here."
            )
        elif summary["balance"] > 0:
            answer = (
                f"Your entered records show ₹{summary['income']:,.2f} income and ₹{summary['expense']:,.2f} "
                f"expenses, a difference of ₹{summary['balance']:,.2f} ({summary['rate']:.1f}% of recorded income). "
                "That difference is not necessarily cash available to save; first account for bills and financial "
                "activity not entered in GP AI."
            )
        else:
            answer = (
                f"Your entered records show expenses of ₹{abs(summary['balance']):,.2f} more than income. "
                "Review essential and flexible expenses, and check that the records include the relevant period."
            )
    elif any(word in question for word in ["budget", "limit", "overspend"]):
        over_limit = [budget for budget in budget_attention if budget["percent"] >= 100]
        near_limit = [budget for budget in budget_attention if budget["percent"] < 100]
        if not budgets:
            answer = f"{empty_note}No category budgets are saved yet. Add budgets to compare them with this month's recorded expenses."
        elif over_limit:
            answer = (
                "Current-month recorded spending is at or above the saved limit for "
                + ", ".join(f"{budget['category']} ({budget['percent']:.0f}%)" for budget in over_limit)
                + ". Review those records and limits; spending not entered in GP AI is not included."
            )
        elif near_limit:
            answer = (
                "These current-month budgets are at least 80% used: "
                + ", ".join(f"{budget['category']} ({budget['percent']:.0f}%)" for budget in near_limit)
                + ". Compare upcoming needs with each remaining limit."
            )
        else:
            answer = "Current-month recorded spending is below 80% of each saved category budget. This excludes transactions not entered in GP AI."
    elif any(word in question for word in ["afford", "purchase", "buy"]):
        answer = (
            f"Your entered records show ₹{summary['income']:,.2f} income and ₹{summary['expense']:,.2f} "
            f"expenses, a difference of ₹{summary['balance']:,.2f}. Upcoming bills, savings needs, and activity "
            "not entered in GP AI are not reflected, so these figures cannot confirm affordability."
        )
    else:
        answer = (
            f"{empty_note}I can help with recorded spending, budgets, and savings. Your entered expenses total "
            f"₹{summary['expense']:,.2f}. Ask which category is highest, whether a budget is near its limit, "
            "or how recorded income compares with expenses."
        )
    return {
        "answer": answer,
        "basis": "Recommendations use only transactions and budgets entered into GP AI; they are not professional financial advice.",
        "summary": summary,
        "top_category": top,
    }


@app.post("/api/predict-category")
def predict(payload: CategoryPredictionIn):
    description = payload.description if payload.description is not None else payload.question
    category, confidence = predict_category(description)
    return {
        "category": category,
        "confidence": round(confidence, 2),
        "method": CATEGORIZER_DESCRIPTION,
        "model": CATEGORIZER_DESCRIPTION,
    }


@app.get("/")
def home():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
