/**
 * Typed API service layer.
 * One function per backend endpoint.
 */

import { api } from "@/lib/api-client";
import type {
  Candle,
  PaperTrade,
  PaperPosition,
  PortfolioSummary,
  WatchlistItem,
  Strategy,
  TradeSignal,
  AnalyticsSummary,
  ChartPoint,
  SymbolAnalytics,
  TimeframeAnalytics,
} from "@/types";

// --- Candles ---
export const candleService = {
  getCandles: (symbol: string, timeframe: string, limit = 200) =>
    api.get<Candle[]>(`/candles/${symbol}/${timeframe}?limit=${limit}`),

  fetchAndStore: (symbol: string, timeframe: string, useSample = false) =>
    api.post<{ symbol: string; inserted: number; total_in_db: number }>(
      `/candles/${symbol}/${timeframe}/fetch?use_sample=${useSample}`,
      {}
    ),
};

// --- Paper Trading ---
export const tradingService = {
  getPortfolio: () => api.get<PortfolioSummary>("/trading/portfolio"),

  getPositions: () => api.get<PaperPosition[]>("/trading/positions"),

  getTrades: (symbol?: string, status?: string, limit = 50) => {
    const params = new URLSearchParams();
    if (symbol) params.set("symbol", symbol);
    if (status) params.set("status", status);
    params.set("limit", String(limit));
    return api.get<PaperTrade[]>(`/trading/trades?${params}`);
  },

  simulateOrder: (order: {
    symbol: string;
    side: "BUY" | "SELL";
    quantity: number;
    price: number;
    strategy_name: string;
    stop_loss?: number;
    target_price?: number;
  }) => api.post<PaperTrade>("/trading/simulate-order", order),

  closePosition: (symbol: string, price: number) =>
    api.post<PaperTrade>("/trading/close-position", { symbol, price }),

  resetPortfolio: () => api.post<{ message: string; balance: number }>("/trading/reset", {}),
};

// --- Watchlist ---
export const watchlistService = {
  getWatchlist: () => api.get<WatchlistItem[]>("/watchlist"),

  addSymbol: (symbol: string) =>
    api.post<WatchlistItem>("/watchlist", { symbol }),

  removeSymbol: (symbol: string) =>
    api.delete<{ message: string }>(`/watchlist/${symbol}`),
};

// --- Strategies ---
export const strategyService = {
  listStrategies: () => api.get<Strategy[]>("/strategies"),

  toggleStrategy: (name: string, enabled: boolean) =>
    api.patch<Strategy>(`/strategies/${name}/toggle`, { enabled }),
};

// --- Signals ---
export const signalService = {
  getSignal: (symbol: string, timeframe: string, strategyName = "ema_rsi_volume") =>
    api.get<TradeSignal>(
      `/signals/${symbol}/${timeframe}?strategy_name=${strategyName}`
    ),
};

// --- Backtesting ---
export const backtestService = {
  run: (symbol: string, timeframe: string, strategyName = "ema_rsi_volume", initialBalance = 100000) =>
    api.post<Record<string, unknown>>(
      `/backtest/run?symbol=${symbol}&timeframe=${timeframe}&strategy_name=${strategyName}&initial_balance=${initialBalance}`,
      {}
    ),
};

// --- Analytics ---
export const analyticsService = {
  getSummary: () => api.get<AnalyticsSummary>("/analytics/summary"),
  getEquityCurve: (limit = 500) => api.get<ChartPoint[]>(`/analytics/equity-curve?limit=${limit}`),
  getDrawdownCurve: (limit = 500) => api.get<ChartPoint[]>(`/analytics/drawdown?limit=${limit}`),
  getSymbolAnalytics: () => api.get<SymbolAnalytics[]>("/analytics/symbols"),
  getTimeframeAnalytics: () => api.get<TimeframeAnalytics[]>("/analytics/timeframes"),
  getTradeStreaks: () => api.get<Record<string, unknown>>("/analytics/trade-streaks"),
};
