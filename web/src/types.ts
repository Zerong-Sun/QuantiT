export type MarketId = string;

export interface Market {
  id: MarketId;
  name: string;
  currency: string;
  timezone: string;
  session_hours: string;
  t_plus: number;
  intervals: string[];
}

export interface Instrument {
  symbol: string;
  market_id: MarketId;
  name: string;
  currency: string;
  lot_size: number;
  timezone: string;
  session_hours: string;
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
