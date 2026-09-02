import type {
  Account,
  Bar,
  Instrument,
  Market,
  Note,
  Order,
  Position,
  Quote,
  SignalBundle,
  Strategy,
  Trade,
  Runner,
  PortfolioOverview,
} from "./types";

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  markets: () => getJson<Market[]>("/api/v1/markets"),
  search: (market: string, q: string) =>
    getJson<Instrument[]>(`/api/v1/search?market=${encodeURIComponent(market)}&q=${encodeURIComponent(q)}`),
  instrument: (market: string, symbol: string) =>
    getJson<Instrument>(
      `/api/v1/instrument?market=${encodeURIComponent(market)}&symbol=${encodeURIComponent(symbol)}`,
    ),
  quote: (market: string, symbol: string) =>
    getJson<Quote>(`/api/v1/quote?market=${encodeURIComponent(market)}&symbol=${encodeURIComponent(symbol)}`),
  bars: (market: string, symbol: string, interval: string) =>
    getJson<Bar[]>(
      `/api/v1/bars?market=${encodeURIComponent(market)}&symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}`,
    ),
  accounts: () => getJson<Account[]>("/api/v1/accounts"),
  positions: (market?: string) =>
    getJson<Position[]>(market ? `/api/v1/positions?market=${encodeURIComponent(market)}` : "/api/v1/positions"),
  portfolio: () => getJson<PortfolioOverview>("/api/v1/portfolio"),
  orders: (market?: string) =>
    getJson<Order[]>(market ? `/api/v1/orders?market=${encodeURIComponent(market)}` : "/api/v1/orders"),
  trades: (market?: string) =>
    getJson<Trade[]>(market ? `/api/v1/trades?market=${encodeURIComponent(market)}` : "/api/v1/trades"),
  strategies: (market?: string) =>
    getJson<Strategy[]>(
      market ? `/api/v1/strategies?market=${encodeURIComponent(market)}` : "/api/v1/strategies",
    ),
  signals: (market: string, symbol: string) =>
    getJson<SignalBundle>(
      `/api/v1/signals?market=${encodeURIComponent(market)}&symbol=${encodeURIComponent(symbol)}`,
    ),
  notes: () => getJson<Note[]>("/api/v1/notes"),
  addNote: async (body: { body: string; market_id?: string | null; symbol?: string | null }) => {
    const res = await fetch("/api/v1/notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      throw new Error(await res.text());
    }
    return res.json() as Promise<Note>;
  },
  deleteNote: async (id: number) => {
    const res = await fetch(`/api/v1/notes/${id}`, { method: "DELETE" });
    if (!res.ok) {
      throw new Error(await res.text());
    }
  },
  placeOrder: async (body: {
    market: string;
    symbol: string;
    side: string;
    quantity: number;
    rationale?: string;
  }) => {
    const res = await fetch("/api/v1/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      throw new Error(await res.text());
    }
    return res.json() as Promise<Order>;
  },
  runner: () => getJson<Runner>("/api/v1/runner"),
  runnerStart: async () => {
    const res = await fetch("/api/v1/runner/start", { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<Runner>;
  },
  runnerStop: async () => {
    const res = await fetch("/api/v1/runner/stop", { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<Runner>;
  },
  runnerTick: async () => {
    const res = await fetch("/api/v1/runner/tick", { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<Runner>;
  },
};
