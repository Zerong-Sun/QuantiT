import { useEffect, useState, type FormEvent } from "react";
import { api } from "./api";
import { KLineChart } from "./components/KLineChart";
import { DEFAULT_SYMBOL, marketUi } from "./markets/config";
import type {
  Account,
  Bar,
  Instrument,
  Market,
  Order,
  Position,
  Quote,
  Trade,
} from "./types";

const POLL_MS = 15_000;

function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) {
    return "—";
  }
  return n.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function App() {
  const [markets, setMarkets] = useState<Market[]>([]);
  const [market, setMarket] = useState("us");
  const [symbol, setSymbol] = useState("AAPL");
  const [query, setQuery] = useState("AAPL");
  const [interval, setInterval] = useState("1d");
  const [instrument, setInstrument] = useState<Instrument | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [bars, setBars] = useState<Bar[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [qty, setQty] = useState(100);
  const [message, setMessage] = useState("");
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [error, setError] = useState("");

  const ui = marketUi(market);
  const account = accounts.find((a) => a.market_id === market);
  const currentMarket = markets.find((m) => m.id === market);

  async function loadBlotter() {
    const [acc, pos, ord, tr] = await Promise.all([
      api.accounts(),
      api.positions(),
      api.orders(),
      api.trades(),
    ]);
    setAccounts(acc);
    setPositions(pos);
    setOrders(ord);
    setTrades(tr);
  }

  async function loadSymbol(nextMarket: string, nextSymbol: string, nextInterval = interval) {
    setError("");
    try {
      const [inst, q, b] = await Promise.all([
        api.instrument(nextMarket, nextSymbol),
        api.quote(nextMarket, nextSymbol),
        api.bars(nextMarket, nextSymbol, nextInterval),
      ]);
      setInstrument(inst);
      setQuote(q);
      setBars(b);
      setSymbol(inst.symbol);
      setQuery(inst.symbol);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    api.markets().then((list) => {
      setMarkets(list);
      const first = list[0]?.id ?? "us";
      setMarket(first);
      const sym = DEFAULT_SYMBOL[first] ?? "AAPL";
      setSymbol(sym);
      setQuery(sym);
      return loadSymbol(first, sym);
    }).catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
    loadBlotter().catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (symbol) {
        loadSymbol(market, symbol, interval).catch(() => undefined);
      }
      loadBlotter().catch(() => undefined);
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [market, symbol, interval]);

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    const hits = await api.search(market, query);
    const pick = hits[0];
    if (!pick) {
      setError("No symbol found");
      return;
    }
    await loadSymbol(market, pick.symbol);
  }

  async function switchMarket(id: string) {
    setMarket(id);
    const next = DEFAULT_SYMBOL[id] ?? query;
    setInterval("1d");
    await loadSymbol(id, next, "1d");
    await loadBlotter();
  }

  async function submit(side: "buy" | "sell") {
    setMessage("");
    setError("");
    try {
      const order = await api.placeOrder({ market, symbol, side, quantity: qty });
      if (order.status === "rejected") {
        setMessage(`Rejected: ${order.reject_reason ?? "unknown"}`);
      } else {
        setMessage(`${side.toUpperCase()} ${order.quantity} ${order.symbol} @ ${fmt(order.fill_price, ui.pricePrecision)}`);
      }
      setSelectedOrder(order);
      await loadBlotter();
      await loadSymbol(market, symbol);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const changeClass = (quote?.change ?? 0) >= 0 ? "up" : "down";
  const estNotional = (quote?.last ?? 0) * qty;

  return (
    <div className="terminal">
      <header className="topbar">
        <div className="brand">QuantiT <span>paper</span></div>
        <div className="markets">
          {markets.map((m) => (
            <button
              key={m.id}
              className={m.id === market ? "active" : ""}
              onClick={() => switchMarket(m.id)}
            >
              {marketUi(m.id).label}
            </button>
          ))}
        </div>
        <form className="search" onSubmit={onSearch}>
          <input value={query} onChange={(e) => setQuery(e.target.value.toUpperCase())} placeholder="Symbol" />
          <button type="submit">Go</button>
        </form>
        <div className="session">
          {currentMarket ? `${currentMarket.session_hours} · delayed` : "delayed quotes"}
        </div>
      </header>

      <main className="workspace">
        <section className="chart-col">
          <div className="quote-bar">
            <div>
              <h1>{instrument?.symbol ?? symbol}</h1>
              <p>{instrument?.name} · {instrument?.currency} · lot {instrument?.lot_size ?? "—"}</p>
            </div>
            <div className={`last ${changeClass}`}>
              <strong>{fmt(quote?.last, ui.pricePrecision)}</strong>
              <span>
                {fmt(quote?.change, ui.pricePrecision)} ({fmt(quote?.change_pct, 2)}%)
              </span>
            </div>
            <div className="ohlc">
              <span>O {fmt(quote?.open, ui.pricePrecision)}</span>
              <span>H {fmt(quote?.high, ui.pricePrecision)}</span>
              <span>L {fmt(quote?.low, ui.pricePrecision)}</span>
              <span>Vol {fmt(quote?.volume, 0)}</span>
            </div>
            <div className="intervals">
              {(currentMarket?.intervals ?? ["1d", "1h", "5m"]).map((iv) => (
                <button
                  key={iv}
                  className={iv === interval ? "active" : ""}
                  onClick={() => {
                    setInterval(iv);
                    loadSymbol(market, symbol, iv);
                  }}
                >
                  {iv}
                </button>
              ))}
            </div>
          </div>
          <KLineChart bars={bars} />
          {error ? <div className="banner error">{error}</div> : null}
        </section>

        <aside className="ticket">
          <h2>Order</h2>
          <p className="hint">{ui.lotHint}{currentMarket?.t_plus ? ` · T+${currentMarket.t_plus}` : ""}</p>
          <label>
            Quantity
            <input type="number" min={1} value={qty} onChange={(e) => setQty(Number(e.target.value))} />
          </label>
          <p className="est">Est. notional {fmt(estNotional, ui.pricePrecision)} {account?.currency}</p>
          <p className="cash">Cash {fmt(account?.cash)} {account?.currency}</p>
          <div className="sides">
            <button className="buy" onClick={() => submit("buy")}>Buy</button>
            <button className="sell" onClick={() => submit("sell")}>Sell</button>
          </div>
          {message ? <p className="msg">{message}</p> : null}

          {selectedOrder ? (
            <div className="detail">
              <h3>Order #{selectedOrder.id}</h3>
              <dl>
                <dt>Status</dt><dd>{selectedOrder.status}</dd>
                <dt>Side</dt><dd>{selectedOrder.side}</dd>
                <dt>Qty</dt><dd>{selectedOrder.quantity}</dd>
                <dt>Fill</dt><dd>{fmt(selectedOrder.fill_price, ui.pricePrecision)}</dd>
                <dt>Commission</dt><dd>{fmt(selectedOrder.commission, 4)}</dd>
                {selectedOrder.reject_reason ? (
                  <>
                    <dt>Reason</dt>
                    <dd>{selectedOrder.reject_reason}</dd>
                  </>
                ) : null}
              </dl>
            </div>
          ) : null}
        </aside>
      </main>

      <footer className="blotter">
        <div>
          <h2>Positions</h2>
          <table>
            <thead>
              <tr><th>Mkt</th><th>Symbol</th><th>Qty</th><th>Avg</th></tr>
            </thead>
            <tbody>
              {positions.length === 0 ? (
                <tr><td colSpan={4}>No positions</td></tr>
              ) : positions.map((p) => (
                <tr key={`${p.market_id}-${p.symbol}`} onClick={() => { setMarket(p.market_id); loadSymbol(p.market_id, p.symbol); }}>
                  <td>{p.market_id}</td>
                  <td>{p.symbol}</td>
                  <td>{p.quantity}</td>
                  <td>{fmt(p.avg_cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <h2>Trades</h2>
          <table>
            <thead>
              <tr><th>Time</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Price</th></tr>
            </thead>
            <tbody>
              {trades.length === 0 ? (
                <tr><td colSpan={5}>No trades</td></tr>
              ) : trades.map((t) => (
                <tr key={t.id}>
                  <td>{t.timestamp.replace("T", " ").slice(0, 19)}</td>
                  <td>{t.symbol}</td>
                  <td className={t.side}>{t.side}</td>
                  <td>{t.quantity}</td>
                  <td>{fmt(t.price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <h2>Orders</h2>
          <table>
            <thead>
              <tr><th>ID</th><th>Symbol</th><th>Status</th><th>Qty</th></tr>
            </thead>
            <tbody>
              {orders.length === 0 ? (
                <tr><td colSpan={4}>No orders</td></tr>
              ) : orders.map((o) => (
                <tr key={o.id} onClick={() => setSelectedOrder(o)}>
                  <td>{o.id}</td>
                  <td>{o.symbol}</td>
                  <td>{o.status}</td>
                  <td>{o.quantity}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </footer>
    </div>
  );
}
