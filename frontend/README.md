# GP AI frontend

This is the browser interface served by the FastAPI application in the parent project folder.

- `index.html` — dashboard and spending overview
- `transactions.html` — transaction ledger and CSV export
- `budgets.html` — category budget tracker
- `advisor.html` — data-based finance advisor
- `styles.css` — shared visual system
- `app.js` — API-connected frontend behavior

Do not open the HTML files directly with `file://`. Start the backend with `uvicorn main:app --reload` from the project root and visit `http://127.0.0.1:8000` so the pages can call the API.
