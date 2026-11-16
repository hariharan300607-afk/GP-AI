# GP AI — Personal Finance Management System

GP AI is a college-level personal finance application for recording income and expenses, reviewing spending, and tracking category budgets. The project uses a FastAPI backend, a browser-based HTML/CSS/JavaScript frontend, and a local SQLite database.

## Features

- Dashboard totals for recorded income, expenses, net balance, and savings rate.
- Transaction ledger with manual or rule-based categories, search, CSV export, and deletion.
- Monthly budget creation and updates, with current-month recorded spending comparisons.
- A rules-based Finance Advisor that summarizes entered transactions and budgets.
- REST API with interactive Swagger documentation.
- Optional one-time sample data for a new, empty database.
- Isolated API tests and a GitHub Actions test workflow.

## Technology

- Python 3.10+
- FastAPI, Pydantic, and Uvicorn
- SQLite from the Python standard library
- HTML, CSS, and vanilla JavaScript
- pytest and FastAPI TestClient for automated tests

The frontend loads Lucide icons and fonts from CDNs, and the dashboard loads Chart.js for charts. An internet connection is needed for those optional visual assets; the backend and API do not depend on external services.

## Project structure

```text
GP_AI_FullStack/
├── .github/
│   └── workflows/
│       └── tests.yml       # GitHub Actions test workflow
├── frontend/
│   ├── advisor.html        # Rules-based Finance Advisor
│   ├── app.js              # API requests and page behavior
│   ├── budgets.html        # Budget tracking
│   ├── index.html          # Dashboard
│   ├── README.md           # Frontend notes
│   ├── styles.css          # Shared application styling
│   └── transactions.html   # Transaction ledger
├── tests/
│   └── test_api.py         # Isolated FastAPI and categorizer tests
├── .gitignore
├── main.py                 # FastAPI app, SQLite access, and finance rules
├── render.yaml             # Optional Render web-service configuration
├── requirements.txt
├── requirements-dev.txt
├── run_mac_linux.sh
└── run_windows.bat
```

## Prerequisites

- Windows 10/11, macOS, or Linux
- Python 3.10 or later
- Internet access if you want the frontend's CDN-provided icons, charts, styles, and fonts

## Install and run on Windows

Open PowerShell in the project folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

To activate the environment for later commands:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, continue using the explicit `.venv\Scripts\python.exe` commands above; changing the machine's execution policy is not required.

The included `run_windows.bat` can also create the virtual environment, install dependencies, and start the application.

## Run and test

- Application: <http://127.0.0.1:8000>
- API documentation (Swagger UI): <http://127.0.0.1:8000/docs>
- Alternate API documentation (ReDoc): <http://127.0.0.1:8000/redoc>
- Health check: <http://127.0.0.1:8000/api/health>

Install the test dependencies and run the complete suite:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Tests use a temporary SQLite database and do not read or modify the normal application database.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Service status and categorization method |
| GET | `/api/dashboard` | Recorded totals, category spending, monthly totals, and recent entries |
| GET | `/api/transactions` | List transactions |
| POST | `/api/transactions` | Add an income or expense transaction |
| DELETE | `/api/transactions/{transaction_id}` | Delete a transaction |
| GET | `/api/budgets` | List saved budgets and current-month spending |
| PUT | `/api/budgets` | Create or update a category budget |
| POST | `/api/advisor` | Ask a rules-based question about saved records |
| POST | `/api/predict-category` | Predict a category from a description |

## Database and sample records

By default, the application creates `gp_ai.db` in the project directory when it starts. The file is local and is excluded from Git. On its first run, GP AI inserts demo transactions and budgets only when both database tables are empty; subsequent starts do not replace or add sample records to an initialized or populated database.

To store the database elsewhere, set `GP_AI_DB_PATH` before starting the application, for example:

```powershell
$env:GP_AI_DB_PATH = "C:\Users\YourName\Documents\gp_ai.db"
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Back up the SQLite database before moving or resetting it. Do not remove it if you need to keep its transaction or budget records.

## Categorization methodology

Automatic transaction categorization uses deterministic keyword and whole-word/phrase matching implemented with Python's standard library. The rules are case-insensitive, return a confidence estimate, and use `Other` for empty, ambiguous, or unrecognized descriptions. Users can select a category manually instead. This is a rule-based categorizer, **not a trained machine-learning model**.

## Finance Advisor methodology

The Finance Advisor reads transactions and budgets from SQLite and applies simple, explainable rules to calculate totals, identify the largest recorded expense category, compare current-month spending against saved budgets, and discuss income versus recorded expenses. Its recommendations use only data entered into GP AI. They are not generated by an LLM, do not infer missing financial details, and are not professional financial advice.

## Known limitations

- GP AI does not connect to banks, import account statements, or authenticate users.
- Categorization is limited to the configured keywords and may need manual correction.
- Dashboard all-time totals and current-month budget progress use the records currently saved in the local database; missing entries make the picture incomplete.
- SQLite persistence depends on the host's storage. A deployment with ephemeral storage can lose its database after a restart or redeploy.
- Several frontend visual assets are loaded from third-party CDNs.

## Future improvements

- Add optional transaction editing and statement import with review before saving.
- Add configurable reporting periods and downloadable budget reports.
- Add user authentication and protected, per-user storage before any multi-user deployment.
- Expand the keyword rules and provide user-managed category suggestions.
- Use a persistent database volume or managed database for hosted deployments.

## Optional Render deployment

`render.yaml` configures one Python web service with the project requirements, a Uvicorn start command, and `/api/health` as its health check. No paid integrations or external APIs are required. Configure persistent storage separately if deployed transaction data must survive service restarts.
