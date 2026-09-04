import { useEffect, useState, type FormEvent } from "react";
import { api } from "./api";
import { KLineChart } from "./components/KLineChart";
import { NotesBoard } from "./components/NotesBoard";
import { CloseloopPage } from "./components/CloseloopPage";
import { PortfolioPage } from "./components/PortfolioPage";
import { ReasonBanner, signalRationale } from "./components/ReasonBanner";
import { ResizableCard } from "./components/ResizableCard";
import { StrategyDesk } from "./components/StrategyDesk";
import { DEFAULT_SYMBOL, DESK_MARKET_IDS, marketUi } from "./markets/config";
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
} from "./types";

const POLL_MS = 15_000;
type DeskTab = "blotter" | "strategies" | "notes";
type Page = "desk" | "portfolio" | "research";

function readPage(): Page {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  if (path.endsWith("/research") || window.location.hash === "#/research") {
    return "research";
  }
  if (path.endsWith("/portfolio") || window.location.hash === "#/portfolio") {
    return "portfolio";
  }
  return "desk";
}

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
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [strategyId, setStrategyId] = useState("");
  const [signals, setSignals] = useState<SignalBundle | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [runner, setRunner] = useState<Runner | null>(null);
  const [desk, setDesk] = useState<DeskTab>("blotter");
  const [qty, setQty] = useState(100);
  const [message, setMessage] = useState("");
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [error, setError] = useState("");
  const [symbolLoading, setSymbolLoading] = useState(true);
  const [blotterLoading, setBlotterLoading] = useState(true);
  const [deskLoading, setDeskLoading] = useState(true);
  const [page, setPage] = useState<Page>(readPage);

  const ui = marketUi(market);
  const account = accounts.find((a) => a.market_id === market);
  const currentMarket = markets.find((m) => m.id === market);

  async function loadBlotter(opts?: { quiet?: boolean }) {
    if (!opts?.quiet) {
      setBlotterLoading(true);
    }
    try {
      const [acc, pos, ord, tr, run] = await Promise.all([
        api.accounts(),
        api.positions(),
        api.orders(),
        api.trades(),
        api.runner(),
      ]);
      setAccounts(acc);
      setPositions(pos);
      setOrders(ord);
      setTrades(tr);
      setRunner(run);
    } finally {
      if (!opts?.quiet) {
        setBlotterLoading(false);
      }
    }
  }

  async function loadDesk(opts?: { quiet?: boolean }) {
    if (!opts?.quiet) {
      setDeskLoading(true);
    }
    try {
      const [cats, board] = await Promise.all([api.strategies(), api.notes()]);
      setStrategies(cats);
      setNotes(board);
      setStrategyId((prev) => {
        if (prev && cats.some((s) => s.id === prev)) {
          return prev;
        }
        const match = cats.find((s) => s.markets.includes(market));
        return match?.id ?? cats[0]?.id ?? "";
      });
    } finally {
      if (!opts?.quiet) {
        setDeskLoading(false);
      }
    }
  }

  async function loadSymbol(
    nextMarket: string,
    nextSymbol: string,
    nextInterval = interval,
    opts?: { quiet?: boolean },
  ) {
    setError("");
    if (!opts?.quiet) {
      setSymbolLoading(true);
    }
    try {
      const [inst, q, b, sig] = await Promise.all([
        api.instrument(nextMarket, nextSymbol),
        api.quote(nextMarket, nextSymbol),
        api.bars(nextMarket, nextSymbol, nextInterval),
        api.signals(nextMarket, nextSymbol),
      ]);
      setInstrument(inst);
      setQuote(q);
      setBars(b);
      setSignals(sig);
      setSymbol(inst.symbol);
      setQuery(inst.symbol);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (!opts?.quiet) {
        setSymbolLoading(false);
      }
    }
  }

  function goPage(next: Page) {
    const url = next === "portfolio" ? "/portfolio" : next === "research" ? "/research" : "/";
    window.history.pushState({ page: next }, "", url);
    setPage(next);
  }

  useEffect(() => {
    const onPop = () => setPage(readPage());
    window.addEventListener("popstate", onPop);
    window.addEventListener("hashchange", onPop);
    return () => {
      window.removeEventListener("popstate", onPop);
      window.removeEventListener("hashchange", onPop);
    };
  }, []);

  useEffect(() => {
    api.markets().then((list) => {
      setMarkets(list);
      const desk = list.filter((m) => (DESK_MARKET_IDS as readonly string[]).includes(m.id));
      const first = desk[0]?.id ?? "us";
      setMarket(first);
      const sym = DEFAULT_SYMBOL[first] ?? "AAPL";
      setSymbol(sym);
      setQuery(sym);
      return loadSymbol(first, sym);
    }).catch((err: unknown) => {
      setError(err instanceof Error ? err.message : String(err));
      setSymbolLoading(false);
    });
    loadBlotter().catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
    loadDesk().catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (page !== "desk") {
        return;
      }
      if (symbol) {
        loadSymbol(market, symbol, interval, { quiet: true }).catch(() => undefined);
      }
      loadBlotter({ quiet: true }).catch(() => undefined);
      api.notes().then(setNotes).catch(() => undefined);
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [page, market, symbol, interval]);

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
    const match = strategies.find((s) => s.markets.includes(id));
    if (match) {
      setStrategyId(match.id);
    }
    await loadSymbol(id, next, "1d");
    await loadBlotter();
  }

  async function submit(side: "buy" | "sell") {
    setMessage("");
    setError("");
    try {
      const rationale = signalRationale(signals?.signals ?? [], side);
      const order = await api.placeOrder({
        market,
        symbol,
        side,
        quantity: qty,
        rationale: rationale || undefined,
      });
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
  const estNotional = (quote?.last ?? 0) * qty * (instrument?.multiplier ?? 1);

  return (
    <div className="terminal">
      <header className="topbar">
        <div className="brand">QuantiT <span>paper</span></div>
        <div className="pages">
          <button className={page === "desk" ? "active" : ""} onClick={() => goPage("desk")}>Desk</button>
          <button className={page === "portfolio" ? "active" : ""} onClick={() => goPage("portfolio")}>Portfolio</button>
          <button className={page === "research" ? "active" : ""} onClick={() => goPage("research")}>Research</button>
        </div>
        {page === "desk" ? (
          <>
            <div className="markets">
              {markets.filter((m) => (DESK_MARKET_IDS as readonly string[]).includes(m.id)).map((m) => (
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
              <button type="submit" disabled={symbolLoading}>
                {symbolLoading ? <span className="spinner" aria-label="loading" /> : "Go"}
              </button>
            </form>
          </>
        ) : null}
        {page === "desk" ? (
        <div className="session">
          {currentMarket ? `${currentMarket.session_hours} · delayed` : "delayed quotes"}
          {currentMarket?.allowed_asset_classes?.length ? ` · ${currentMarket.allowed_asset_classes.join("/")}` : ""}
        </div>
        ) : null}
      </header>
      {page === "portfolio" ? <PortfolioPage /> : null}
      {page === "research" ? <CloseloopPage /> : null}
      {page === "desk" && runner ? (
        <div className="runner-bar">
          <span className={runner.running ? "live" : "off"}>{runner.running ? "LIVE" : "PAUSED"}</span>
          <span>US {fmt(runner.cash?.us ?? accounts.find((a) => a.market_id === "us")?.cash, 0)} USD · seed {fmt(runner.seed_cash?.us, 0)}</span>
          <span>HK {fmt(runner.cash?.hk ?? accounts.find((a) => a.market_id === "hk")?.cash, 0)} HKD · seed {fmt(runner.seed_cash?.hk, 0)}</span>
          <span>CN {fmt(runner.cash?.cn ?? accounts.find((a) => a.market_id === "cn")?.cash, 0)} CNY · seed {fmt(runner.seed_cash?.cn, 0)}</span>
          <span>{(runner.allowed?.us ?? []).join("/")} · {(runner.allowed?.hk ?? []).join("/")}</span>
          <span>{runner.last_tick ? `tick ${runner.last_tick.replace("T", " ").slice(0, 19)}` : "waiting for first tick"}</span>
          {runner.actions[0] ? (
            <span>{runner.actions[0].side} {runner.actions[0].quantity} {runner.actions[0].symbol} ({runner.actions[0].status})</span>
          ) : null}
          <button type="button" onClick={() => api.runnerTick().then(setRunner).then(() => loadBlotter())}>Run now</button>
          {runner.running ? (
            <button type="button" onClick={() => api.runnerStop().then(setRunner)}>Pause</button>
          ) : (
            <button type="button" onClick={() => api.runnerStart().then(setRunner)}>Start</button>
          )}
          {runner.last_error ? <span className="banner error">{runner.last_error.split("\n")[0]}</span> : null}
        </div>
      ) : null}

      {page === "desk" ? (
      <main className="dashboard">
        <ResizableCard id="chart" className="chart" loading={symbolLoading} minWidth={360} minHeight={280}>
          <div className="quote-bar">
            <div>
              <h1>{instrument?.symbol ?? symbol}</h1>
              <p>{instrument?.name} · {instrument?.asset_class ?? "equity"} · {instrument?.currency} · lot {instrument?.lot_size ?? "—"}{instrument?.multiplier && instrument.multiplier > 1 ? ` · ×${instrument.multiplier}` : ""}</p>
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
              {symbolLoading ? <span className="spinner" aria-label="loading" /> : null}
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
          <ReasonBanner signals={signals?.signals ?? []} />
          <KLineChart bars={bars} />
          {error ? <div className="banner error">{error}</div> : null}
        </ResizableCard>

        <ResizableCard id="order" title="Order" className="ticket" loading={symbolLoading} minWidth={240} minHeight={280}>
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

          {signals?.signals.length ? (
            <div className="ticket-reasons">
              <h3>Why</h3>
              {signals.signals.map((s) => (
                <p key={s.strategy_id}>
                  <span className={`chip-action ${s.action}`}>{s.action}</span>
                  {s.reason}
                </p>
              ))}
            </div>
          ) : null}

          {selectedOrder ? (
            <div className="detail">
              <h3>Order #{selectedOrder.id}</h3>
              <dl>
                <dt>Status</dt><dd>{selectedOrder.status}</dd>
                <dt>Side</dt><dd>{selectedOrder.side}</dd>
                <dt>Qty</dt><dd>{selectedOrder.quantity}</dd>
                <dt>Fill</dt><dd>{fmt(selectedOrder.fill_price, ui.pricePrecision)}</dd>
                <dt>Commission</dt><dd>{fmt(selectedOrder.commission, 4)}</dd>
                {selectedOrder.rationale ? (
                  <>
                    <dt>Why</dt>
                    <dd className="wrap">{selectedOrder.rationale}</dd>
                  </>
                ) : null}
                {selectedOrder.reject_reason ? (
                  <>
                    <dt>Rejected</dt>
                    <dd>{selectedOrder.reject_reason}</dd>
                  </>
                ) : null}
              </dl>
            </div>
          ) : null}
        </ResizableCard>

        <div className="desk-tabs">
          {([
            ["blotter", "Blotter"],
            ["strategies", "Strategies"],
            ["notes", "Notes"],
          ] as const).map(([id, label]) => (
            <button key={id} className={desk === id ? "active" : ""} onClick={() => setDesk(id)}>
              {label}
            </button>
          ))}
        </div>

        {desk === "blotter" ? (
          <>
            <ResizableCard id="positions" title="Positions" className="pane" loading={blotterLoading}>
              <table>
                <thead>
                  <tr><th>Mkt</th><th>Symbol</th><th>Qty</th><th>Avg</th></tr>
                </thead>
                <tbody>
                  {positions.filter((p) => p.market_id !== "cl").length === 0 ? (
                    <tr><td colSpan={4}>No positions</td></tr>
                  ) : positions.filter((p) => p.market_id !== "cl").map((p) => (
                    <tr key={`${p.market_id}-${p.symbol}`} onClick={() => { setMarket(p.market_id); loadSymbol(p.market_id, p.symbol); }}>
                      <td>{p.market_id}</td>
                      <td>{p.symbol}</td>
                      <td>{p.quantity}</td>
                      <td>{fmt(p.avg_cost)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ResizableCard>
            <ResizableCard id="trades" title="Trades" className="pane" loading={blotterLoading}>
              <table>
                <thead>
                  <tr><th>Time</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Price</th></tr>
                </thead>
                <tbody>
                  {trades.filter((t) => t.market_id !== "cl").length === 0 ? (
                    <tr><td colSpan={5}>No trades</td></tr>
                  ) : trades.filter((t) => t.market_id !== "cl").map((t) => (
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
            </ResizableCard>
            <ResizableCard id="orders" title="Orders" className="pane" loading={blotterLoading}>
              <table>
                <thead>
                  <tr><th>ID</th><th>Symbol</th><th>Status</th><th>Qty</th><th>Why</th></tr>
                </thead>
                <tbody>
                  {orders.filter((o) => o.market_id !== "cl").length === 0 ? (
                    <tr><td colSpan={5}>No orders</td></tr>
                  ) : orders.filter((o) => o.market_id !== "cl").map((o) => (
                    <tr key={o.id} onClick={() => setSelectedOrder(o)}>
                      <td>{o.id}</td>
                      <td>{o.symbol}</td>
                      <td>{o.status}</td>
                      <td>{o.quantity}</td>
                      <td className="why">{o.rationale ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ResizableCard>
          </>
        ) : null}
        {desk === "strategies" ? (
          <ResizableCard id="strategies" title="Strategies" className="wide" loading={deskLoading} minWidth={360} minHeight={220}>
            <StrategyDesk
              strategies={strategies}
              selectedId={strategyId}
              onSelect={setStrategyId}
              market={market}
            />
          </ResizableCard>
        ) : null}
        {desk === "notes" ? (
          <ResizableCard id="notes" title="Notes" className="wide" loading={deskLoading} minWidth={360} minHeight={220}>
            <NotesBoard
              notes={notes}
              market={market}
              symbol={symbol}
              onAdd={async (body, tagSymbol) => {
                await api.addNote({
                  body,
                  market_id: tagSymbol ? market : null,
                  symbol: tagSymbol ? symbol : null,
                });
                setNotes(await api.notes());
              }}
              onDelete={async (id) => {
                await api.deleteNote(id);
                setNotes(await api.notes());
              }}
            />
          </ResizableCard>
        ) : null}
      </main>
      ) : null}
    </div>
  );
}
