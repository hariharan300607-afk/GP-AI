import json
import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test_gp_ai.sqlite3")
    monkeypatch.setattr(main, "SEED_DEMO_DATA", False)
    with TestClient(main.app) as test_client:
        yield test_client


def transaction_payload(**overrides):
    payload = {
        "date": date.today().isoformat(),
        "merchant": "Coffee at Example Cafe",
        "amount": 25.50,
        "type": "Expense",
        "category": "Auto-detect",
        "method": "UPI",
    }
    return {**payload, **overrides}


def test_health_describes_rule_based_categorizer(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "rule-based" in response.json()["categorizer"]
    assert "not a trained ML model" in response.json()["categorizer"]


def test_dashboard_empty_and_populated_values(client):
    empty = client.get("/api/dashboard")
    assert empty.status_code == 200
    assert empty.json()["transaction_count"] == 0
    assert empty.json()["income"] == 0
    assert empty.json()["expense"] == 0
    assert empty.json()["monthly"] == []

    client.post("/api/transactions", json=transaction_payload(amount=10.25))
    client.post(
        "/api/transactions",
        json=transaction_payload(type="Income", category="Auto-detect", amount=100),
    )
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["income"] == 100
    assert dashboard["expense"] == 10.25
    assert dashboard["balance"] == 89.75
    assert dashboard["transaction_count"] == 2
    assert dashboard["monthly"] == [
        {"month": date.today().strftime("%Y-%m"), "income": 100.0, "expense": 10.25}
    ]


def test_transaction_listing_starts_empty_and_returns_added_records(client):
    assert client.get("/api/transactions").json() == []
    created = client.post("/api/transactions", json=transaction_payload())
    assert created.status_code == 201
    rows = client.get("/api/transactions").json()
    assert len(rows) == 1
    assert rows[0]["id"] == created.json()["id"]


def test_adding_expense_uses_rule_based_category(client):
    response = client.post(
        "/api/transactions",
        json=transaction_payload(merchant="Swiggy dinner"),
    )
    assert response.status_code == 201
    assert response.json()["type"] == "Expense"
    assert response.json()["category"] == "Food & Dining"
    assert response.json()["category_source"] == "rule_based"
    assert 0 < response.json()["category_confidence"] <= 1


def test_adding_income_uses_income_category(client):
    response = client.post(
        "/api/transactions",
        json=transaction_payload(type="Income", merchant="Monthly salary"),
    )
    assert response.status_code == 201
    assert response.json()["type"] == "Income"
    assert response.json()["category"] == "Income"


def test_manual_category_selection_is_preserved(client):
    response = client.post(
        "/api/transactions",
        json=transaction_payload(merchant="A description without keywords", category="Fitness"),
    )
    assert response.status_code == 201
    assert response.json()["category"] == "Fitness"
    assert response.json()["category_source"] == "user_selected"
    assert response.json()["category_confidence"] is None


@pytest.mark.parametrize("amount", [0, -1, float("inf"), float("nan")])
def test_invalid_transaction_amount_is_rejected(client, amount):
    payload = json.dumps(transaction_payload(amount=amount))
    response = client.post(
        "/api/transactions",
        content=payload,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("invalid_date", ["not-a-date", "2026-02-30", "2026/11/16"])
def test_invalid_transaction_date_is_rejected(client, invalid_date):
    response = client.post("/api/transactions", json=transaction_payload(date=invalid_date))
    assert response.status_code == 422


def test_invalid_transaction_type_is_rejected(client):
    response = client.post("/api/transactions", json=transaction_payload(type="Transfer"))
    assert response.status_code == 422


def test_transaction_can_be_deleted(client):
    created = client.post("/api/transactions", json=transaction_payload())
    transaction_id = created.json()["id"]
    deleted = client.delete(f"/api/transactions/{transaction_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": transaction_id}
    assert client.get("/api/transactions").json() == []
    assert client.delete(f"/api/transactions/{transaction_id}").status_code == 404


def test_budgets_can_be_listed_created_and_updated(client):
    assert client.get("/api/budgets").json() == []
    created = client.put(
        "/api/budgets",
        json={"category": "Food & Dining", "amount": 100},
    )
    assert created.status_code == 200
    assert created.json()["saved"] is True

    client.post(
        "/api/transactions",
        json=transaction_payload(date=date.today().isoformat(), amount=35.25),
    )
    listing = client.get("/api/budgets").json()
    assert listing == [
        {
            "category": "Food & Dining",
            "amount": 100.0,
            "spent": 35.25,
            "remaining": 64.75,
            "percent": 35.2,
        }
    ]

    updated = client.put(
        "/api/budgets",
        json={"category": "Food & Dining", "amount": 200},
    )
    assert updated.status_code == 200
    assert client.get("/api/budgets").json()[0]["amount"] == 200


def test_finance_advisor_uses_recorded_transactions_and_budgets(client):
    client.post(
        "/api/transactions",
        json=transaction_payload(merchant="Pharmacy medicine", amount=50),
    )
    client.post(
        "/api/transactions",
        json=transaction_payload(merchant="Rent for apartment", amount=800),
    )
    response = client.post(
        "/api/advisor",
        json={"question": "Which category is my highest spend?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["top_category"] == "Housing"
    assert "₹800.00" in body["answer"]
    assert "entered into GP AI" in body["basis"]

    client.put("/api/budgets", json={"category": "Housing", "amount": 100})
    budget_advice = client.post(
        "/api/advisor",
        json={"question": "Am I close to a budget limit?"},
    ).json()
    assert "Housing" in budget_advice["answer"]
    assert "800%" in budget_advice["answer"]


def test_finance_advisor_handles_an_empty_ledger(client):
    response = client.post("/api/advisor", json={"question": "How can I save more?"})
    assert response.status_code == 200
    assert "no transactions entered" in response.json()["answer"]
    assert "income" in response.json()["answer"].lower()
    assert response.json()["top_category"] is None


@pytest.mark.parametrize(
    ("description", "expected_category"),
    [
        ("SWIGGY lunch", "Food & Dining"),
        ("Uber ride", "Transport"),
        ("Flipkart shoes", "Shopping"),
        ("BigBasket vegetables", "Groceries"),
        ("Monthly SALARY deposit", "Income"),
        ("Netflix subscription", "Entertainment"),
        ("Electricity bill", "Bills & Utilities"),
        ("Hospital appointment", "Healthcare"),
        ("College tuition", "Education"),
        ("Apartment rent", "Housing"),
        ("Gym membership", "Fitness"),
        ("", "Other"),
        ("   ", "Other"),
        ("miscellaneous xyz merchant", "Other"),
        ("Amazon supermarket", "Other"),
        ("Business hotel", "Other"),
    ],
)
def test_category_prediction(description, expected_category, client):
    response = client.post("/api/predict-category", json={"question": description})
    assert response.status_code == 200
    body = response.json()
    assert body["category"] == expected_category
    assert 0 <= body["confidence"] <= 1
    assert "rule-based" in body["method"]


def test_demo_data_is_only_seeded_for_an_empty_database(tmp_path, monkeypatch):
    database_path = tmp_path / "seed_test.sqlite3"
    monkeypatch.setattr(main, "DB_PATH", database_path)

    main.init_db(seed_demo_data=True)
    with sqlite3.connect(database_path) as connection:
        sample_count = connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        budget_count = connection.execute("SELECT COUNT(*) FROM budgets").fetchone()[0]
        connection.execute(
            "INSERT INTO transactions(date, merchant, category, method, amount, type) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (date.today().isoformat(), "Personal record", "Other", "Cash", 12, "Expense"),
        )

    main.init_db(seed_demo_data=True)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == sample_count + 1
        assert connection.execute("SELECT COUNT(*) FROM budgets").fetchone()[0] == budget_count
        assert connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE merchant = ?", ("Personal record",)
        ).fetchone()[0] == 1


def test_existing_budget_prevents_sample_transaction_seeding(tmp_path, monkeypatch):
    database_path = tmp_path / "existing_budget.sqlite3"
    monkeypatch.setattr(main, "DB_PATH", database_path)
    main.init_db(seed_demo_data=False)
    with sqlite3.connect(database_path) as connection:
        connection.execute("INSERT INTO budgets(category, amount) VALUES (?, ?)", ("Fitness", 50))

    main.init_db(seed_demo_data=True)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM budgets").fetchone()[0] == 1


def test_frontend_pages_are_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Your finance brief" in response.text
    assert client.get("/docs").status_code == 200
    assert client.get("/transactions.html").status_code == 200
    assert client.get("/budgets.html").status_code == 200
    assert client.get("/advisor.html").status_code == 200
