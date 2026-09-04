export type MarketId = string;

export interface Market {
  id: MarketId;
  name: string;
  currency: string;
  timezone: string;
  session_hours: string;
  t_plus: number;
  intervals: string[];
  allowed_asset_classes: string[];
}

export interface Instrument {
  symbol: string;
  market_id: MarketId;
  name: string;
  currency: string;
  lot_size: number;
  timezone: string;
  session_hours: string;
  asset_class: string;
  multiplier: number;
}

export interface Quote {
  symbol: string;
  market_id: MarketId;
  last: number;
  open: number | null;
  high: number | null;
  low: number | null;
  prev_close: number | null;
  volume: number | null;
  change: number | null;
  change_pct: number | null;
  timestamp: string | null;
  delayed: boolean;
}

export interface Bar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Account {
  market_id: MarketId;
  currency: string;
  cash: number;
  initial_cash: number;
}

export interface Position {
  market_id: MarketId;
  symbol: string;
  quantity: number;
  avg_cost: number;
}

export interface Order {
  id: number;
  market_id: MarketId;
  symbol: string;
  side: string;
  quantity: number;
  status: string;
  fill_price: number;
  commission: number;
  reject_reason: string | null;
  rationale: string | null;
  created_at: string;
  fill_time: string | null;
}

export interface Trade {
  id: number;
  order_id: number;
  market_id: MarketId;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  commission: number;
  timestamp: string;
}

export interface StrategyParam {
  name: string;
  value: string | number | boolean | null;
  type: string;
  description: string;
}

export interface StrategyMember {
  symbol: string;
  name: string;
}

export interface Strategy {
  id: string;
  name: string;
  class_name: string;
  markets: string[];
  horizon: string;
  summary: string;
  thesis: string;
  rules: string[];
  parameters: StrategyParam[];
  universe: Record<string, StrategyMember[]> | null;
  score_weights: Record<string, number> | null;
}

export interface Signal {
  strategy_id: string;
  name: string;
  action: string;
  reason: string;
  values: Record<string, unknown>;
}

export interface SignalBundle {
  market_id: string;
  symbol: string;
  asof: string | null;
  headline: string;
  signals: Signal[];
  evaluated_at: string;
}

export interface Note {
  id: number;
  body: string;
  market_id: string | null;
  symbol: string | null;
  created_at: string;
}

export interface RunnerAction {
  time: string | null;
  market_id: string;
  symbol: string;
  side: string;
  quantity: number;
  status: string;
  rationale: string | null;
  reject_reason: string | null;
}

export interface Runner {
  running: boolean;
  interval_sec: number;
  last_tick: string | null;
  last_error: string | null;
  seed_cash: Record<string, number>;
  cash: Record<string, number>;
  allowed: Record<string, string[]>;
  watchlists: Record<string, string[]>;
  actions: RunnerAction[];
}

export interface PortfolioPosition {
  market_id: MarketId;
  symbol: string;
  quantity: number;
  avg_cost: number;
  last: number | null;
  prev_close: number | null;
  multiplier: number;
  asset_class: string;
  currency: string;
  market_value: number;
  cost_value: number;
  unrealized: number | null;
  unrealized_pct: number | null;
  day_pnl: number | null;
  weight: number;
}

export interface PortfolioBook {
  market_id: MarketId;
  currency: string;
  cash: number;
  invested: number;
  equity: number;
  initial_cash: number;
  total_pnl: number;
  day_pnl: number;
  week_pnl: number;
  month_pnl: number;
}

export interface PortfolioOverview {
  asof: string;
  books: PortfolioBook[];
  positions: PortfolioPosition[];
}

export interface CloseloopStatus {
  running: boolean;
  source: string;
  last_alpha: string | null;
  last_tick: string | null;
  last_error: string | null;
  n_library: number;
  interval_sec: number;
  can_trade: boolean;
  ic_mean: number | null;
  ic_ir: number | null;
  passed: boolean | null;
  reasons: string[];
  target: { weights: Record<string, number>; alpha_id: string; rationale: string } | null;
  cl_cash: number | null;
  cl_equity?: number | null;
  cl_currency?: string;
  has_dump?: boolean;
  fills?: { symbol: string; side: string; status: string; qty: number }[];
}

export interface CloseloopLibraryRow {
  alpha_id: string;
  name?: string;
  passed?: boolean;
  ic_mean?: number | null;
  ic_ir?: number | null;
  quantile_spread?: number | null;
  turnover?: number | null;
  universe?: string;
}

export interface CloseloopTraceRow {
  alpha_id?: string;
  passed?: boolean;
  ic_mean?: number | null;
  ic_ir?: number | null;
  reasons?: string[];
}
