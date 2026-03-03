// ─── Auth ──────────────────────────────────────────────────────────────────────
export interface User {
  id: string;
  email: string;
  is_active: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

// ─── Brokerage ─────────────────────────────────────────────────────────────────
export interface Account {
  account_id: string;
  account_type: string;
  currency: string;
  is_primary: boolean;
  status: string;
}

export interface Position {
  symbol: string;
  quantity: number;
  average_cost: number;
  current_price: number;
  market_value: number;
  pnl: number;
  pnl_pct: number;
  instrument_type: string;
}

export interface Balance {
  currency: string;
  cash: number;
  market_value: number;
  total_equity: number;
  buying_power: number;
  maintenance_excess: number;
}

export interface Quote {
  symbol: string;
  symbol_id: number;
  bid: number;
  ask: number;
  last: number;
  open: number;
  high: number;
  low: number;
  volume: number;
}

export interface SymbolSearchResult {
  symbol: string;
  symbolId: number;
  description: string;
  securityType: string;
  listingExchange: string;
  currency: string;
}

// ─── Risk ──────────────────────────────────────────────────────────────────────
export interface RiskSettings {
  id: string;
  max_risk_per_trade: number;
  max_risk_per_trade_pct: number;
  max_risk_daily: number;
  max_risk_daily_pct: number;
  max_risk_weekly: number;
  max_risk_weekly_pct: number;
  max_risk_monthly: number;
  max_risk_monthly_pct: number;
  currency: string;
  use_percentage: boolean;
  circuit_breaker_active: boolean;
}

// ─── Playbook ──────────────────────────────────────────────────────────────────
export interface Playbook {
  id: string;
  name: string;
  description?: string;
  goals?: Record<string, unknown>;
  theory?: string;
  security_criteria?: Record<string, unknown>;
  context_rules?: unknown[];
  trigger_rules?: unknown[];
  management_rules?: Record<string, unknown>;
  sizing_tiers?: unknown[];
  tracking_abbreviations?: Record<string, string>;
  questions?: unknown[];
  ideas?: unknown[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Strategy {
  id: string;
  playbook_id: string;
  name: string;
  description?: string;
  automation_mode: "disabled" | "semi_auto" | "full_auto";
  is_active: boolean;
  config?: Record<string, unknown>;
  watchlist?: string[];
}

// ─── Trade & Journal ───────────────────────────────────────────────────────────
export interface Trade {
  id: string;
  symbol: string;
  instrument_type: "stock" | "option" | "etf";
  side: "long" | "short";
  quantity: number;
  entry_price?: number;
  exit_price?: number;
  stop_loss?: number;
  take_profit?: number;
  entry_time?: string;
  exit_time?: string;
  status: "open" | "closed" | "cancelled";
  pnl?: number;
  pnl_pct?: number;
  r_multiple?: number;
  strategy_id?: string;
}

export interface JournalEntry {
  id: string;
  trade_id?: string;
  entry_date: string;
  title?: string;
  notes?: string;
  tags?: string[];
  context_abbreviation?: string;
  trigger_abbreviation?: string;
  management_abbreviation?: string;
  sizing_tier?: string;
  confidence_before?: number;
  execution_quality?: number;
  followed_playbook?: boolean;
  lessons_learned?: string;
  trade?: Trade;
}

// ─── Signals ───────────────────────────────────────────────────────────────────
export interface TradingSignal {
  id: string;
  symbol: string;
  pattern: string;
  direction: "long" | "short";
  confidence: number;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  strategy_id: string;
  detected_at: string;
  status: "pending" | "confirmed" | "rejected" | "expired";
}

// ─── WebSocket Events ──────────────────────────────────────────────────────────
export type WSEventType =
  | "quote_update"
  | "candle_update"
  | "risk_warning"
  | "risk_limit_hit"
  | "circuit_breaker"
  | "pnl_update"
  | "position_update"
  | "order_filled"
  | "trade_opened"
  | "trade_closed"
  | "signal_detected"
  | "semi_auto_alert"
  | "auto_order_placed"
  | "connected"
  | "heartbeat";

export interface WSEvent<T = unknown> {
  type: WSEventType;
  data: T;
  timestamp: string;
  user_id?: string;
}
