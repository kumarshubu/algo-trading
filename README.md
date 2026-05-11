# Algo Trading Platform

> **PAPER TRADING ONLY — NO REAL TRADES ARE PLACED.**
> This is a learning platform for algo trading, backtesting, and strategy research.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, React 19, TypeScript, TailwindCSS v4 |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.x, Pydantic v2 |
| Database | SQLite + Alembic |
| Charts | TradingView Lightweight Charts |
| Data Analysis | pandas, pandas-ta, numpy |
| Backtesting | Custom walk-forward engine (no lookahead bias) |

---

## Features

- **Dashboard** — Candlestick chart, portfolio stats, strategy signal badge
- **Watchlist** — Add/remove symbols, check live signals
- **Portfolio** — Virtual balance, open positions, trade history, P&L
- **Strategies** — Enable/disable via kill switch, run backtests
- **Paper Trading Engine** — Slippage, brokerage simulation, stop loss/target
- **EMA + RSI + Volume strategy** — Built-in trend-following strategy
- **Backtesting** — Walk-forward engine, no lookahead bias

---

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+

### 1. Setup (one time)

```bash
./scripts/setup.sh
```

### 2. Run everything

```bash
npm run dev
```

That's it. Both backend and frontend start together with color-coded output.

- Frontend: http://localhost:3000
- Backend API docs: http://127.0.0.1:8000/docs

### Available scripts

| Command | What it does |
|---------|-------------|
| `npm run dev` | Start backend + frontend together |
| `npm run build` | Build frontend for production |
| `npm run start` | Start both in production mode |
| `npm run test` | Run backend pytest suite |
| `npm run lint` | Lint frontend |
| `npm run type-check` | TypeScript check |

---

## Manual Setup

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Copy env config
cp ../.env.example ../.env

# Run DB migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## Loading Market Data

From the Dashboard, click **Load Data** to load sample candle data for any symbol.

To load real data via Yahoo Finance (free, unofficial):

```bash
# In the backend venv
pip install yfinance

# Then use the API
POST http://127.0.0.1:8000/api/v1/candles/RELIANCE/1h/fetch
```

Or use sample data (synthetic but realistic):

```
POST /api/v1/candles/RELIANCE/1h/fetch?use_sample=true
```

---

## Running Tests

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

---

## Project Structure

```
algo-trading/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI route handlers
│   │   ├── core/         # Config, logging, exceptions
│   │   ├── db/           # SQLAlchemy engine + session
│   │   ├── models/       # ORM models
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   ├── services/     # Business logic (candles, paper trading)
│   │   ├── strategies/   # Trading strategies
│   │   ├── backtesting/  # Backtest engine
│   │   └── utils/        # Retry, market calendar
│   ├── tests/
│   ├── alembic/          # DB migrations
│   └── requirements.txt
│
├── frontend/
│   ├── app/              # Next.js app router pages
│   ├── components/       # React components
│   ├── services/         # API service layer
│   ├── hooks/            # Custom React hooks
│   ├── types/            # TypeScript types
│   └── lib/              # API client
│
├── scripts/              # Setup and run scripts
├── .env.example          # Environment variable template
└── README.md
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| GET | /api/v1/candles/{symbol}/{timeframe} | Get stored candles |
| POST | /api/v1/candles/{symbol}/{timeframe}/fetch | Fetch & store candles |
| GET | /api/v1/trading/portfolio | Paper portfolio summary |
| GET | /api/v1/trading/positions | Open positions |
| GET | /api/v1/trading/trades | Trade history |
| POST | /api/v1/trading/simulate-order | Simulate a paper order |
| POST | /api/v1/trading/close-position | Close a paper position |
| POST | /api/v1/trading/reset | Reset paper portfolio |
| GET | /api/v1/watchlist | Get watchlist |
| POST | /api/v1/watchlist | Add symbol |
| DELETE | /api/v1/watchlist/{symbol} | Remove symbol |
| GET | /api/v1/strategies | List strategies |
| PATCH | /api/v1/strategies/{name}/toggle | Enable/disable strategy |
| GET | /api/v1/signals/{symbol}/{timeframe} | Get strategy signal |
| POST | /api/v1/backtest/run | Run backtest |

---

## Strategy: EMA + RSI + Volume

**Buy signal:**
- EMA20 > EMA50 (uptrend confirmed)
- RSI > 60 (momentum)
- Volume > 1.5x 20-period average (volume confirmation)

**Exit:**
- Stop loss: 3% below entry
- Target: 6% above entry (2:1 risk-reward)

---

## Safety

- `PAPER_TRADING=true` must be set — backend refuses to start otherwise
- No broker API integration
- No real order placement functions
- Virtual balance starts at ₹1,00,000 INR
- Risk controls: max 10% capital per trade, max 5 positions, 5% daily loss limit
- API keys loaded from `.env` only — never hardcoded
- Stack traces never returned to frontend
- Backend binds to `127.0.0.1` only

---

## License

MIT — For educational use only. Not financial advice.
