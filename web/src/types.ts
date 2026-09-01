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
