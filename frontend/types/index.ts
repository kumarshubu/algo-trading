// Shared TypeScript types matching backend Pydantic schemas

export interface Candle {
  id: number;
  symbol: string;
  timeframe: "15m" | "1h" | "1d";
  timestamp_utc: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  created_at: string;
}

export interface PaperTrade {
  id: number;
  symbol: string;
  side: "BUY" | "SELL";
  entry_price: number;
  exit_price: number | null;
  quantity: number;
  pnl: number | null;
  strategy_name: string;
  status: "OPEN" | "CLOSED";
  stop_loss: number | null;
  target_price: number | null;
  created_at: string;
  closed_at: string | null;
}

export interface PaperPosition {
  id: number;
  symbol: string;
  quantity: number;
  average_price: number;
  unrealized_pnl: number;
  updated_at: string;
}

export interface PortfolioSummary {
  virtual_balance: number;
  initial_balance: number;
  total_realized_pnl: number;
  daily_loss: number;
  open_positions_count: number;
  total_unrealized_pnl: number;
  portfolio_value: number;
}

export interface WatchlistItem {
  id: number;
  symbol: string;
  created_at: string;
}

export interface Strategy {
  id: number;
  name: string;
  enabled: boolean;
  created_at: string;
}

export interface TradeSignal {
  symbol: string;
  timeframe: string;
  strategy: string;
  signal: "BUY" | "SELL" | "HOLD";
  price: number;
  stop_loss: number | null;
  target_price: number | null;
  reason: string;
}

export interface AnalyticsSummary {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  loss_rate: number;
  total_realized_pnl: number;
  gross_profit: number;
  gross_loss: number;
  avg_profit_per_trade: number;
  avg_loss_per_trade: number;
  profit_factor: number | null;
  expectancy: number;
  avg_holding_hours: number;
  max_drawdown_pct: number;
  current_drawdown_pct: number;
  largest_win: number;
  largest_loss: number;
  max_win_streak: number;
  max_loss_streak: number;
  current_streak: number;
  current_streak_type: "WIN" | "LOSS" | "NONE";
  portfolio_value: number;
  virtual_balance: number;
  initial_balance: number;
  unrealized_pnl: number;
  open_positions_count: number;
  total_return_pct: number;
}

export interface ChartPoint {
  time: number;
  value: number;
}

export interface SymbolAnalytics {
  symbol: string;
  total_trades: number;
  winning_trades: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl: number;
  best_trade: number;
  worst_trade: number;
}

export interface TimeframeAnalytics {
  strategy_name: string;
  total_trades: number;
  winning_trades: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl: number;
}

// Generic API response shapes
export interface ApiSuccess<T> {
  success: true;
  data: T;
}

export interface ApiError {
  success: false;
  error: string;
  details?: unknown;
}

export type ApiResponse<T> = ApiSuccess<T> | ApiError;
