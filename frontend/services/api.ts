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
} from "@/types";

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
  closePosition: (symbol: string, price: number) =>
    api.post<PaperTrade>("/trading/close-position", { symbol, price }),
  resetPortfolio: () => api.post<{ message: string; balance: number }>("/trading/reset", {}),
};

export const candleService = {
  getCandles: (symbol: string, timeframe: string, limit = 200) =>
    api.get<Candle[]>(`/candles/${symbol}/${timeframe}?limit=${limit}`),
  fetchAndStore: (symbol: string, timeframe: string, useSample = false) =>
    api.post<{ total_in_db: number }>("/candles/fetch", { symbol, timeframe, use_sample: useSample }),
};

export const signalService = {
  getSignal: (symbol: string, timeframe: string) =>
    api.get<TradeSignal>(`/signals/${symbol}/${timeframe}`),
  listSignals: (symbol?: string) => {
    const params = symbol ? `?symbol=${symbol}` : "";
    return api.get<TradeSignal[]>(`/signals${params}`);
  },
};

export const strategyService = {
  listStrategies: () => api.get<Strategy[]>("/strategies"),
  toggleStrategy: (name: string, enabled: boolean) =>
    api.patch<Strategy>(`/strategies/${name}/toggle`, { enabled }),
};

export const backtestService = {
  run: (symbol: string, timeframe: string, strategyName?: string) =>
    api.post<Record<string, unknown>>("/backtesting/run", {
      symbol,
      timeframe,
      ...(strategyName ? { strategy_name: strategyName } : {}),
    }),
};

export const watchlistService = {
  getWatchlist: () => api.get<WatchlistItem[]>("/watchlist"),
  addSymbol: (symbol: string) => api.post<WatchlistItem>("/watchlist", { symbol }),
  removeSymbol: (symbol: string) => api.delete<void>(`/watchlist/${symbol}`),
};

export const analyticsService = {
  getSummary: () => api.get<AnalyticsSummary>("/analytics/summary"),
  getEquityCurve: () => api.get<ChartPoint[]>("/analytics/equity-curve"),
  getDrawdownCurve: () => api.get<ChartPoint[]>("/analytics/drawdown-curve"),
  getSymbolAnalytics: () => api.get<SymbolAnalytics[]>("/analytics/by-symbol"),
};
