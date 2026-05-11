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
