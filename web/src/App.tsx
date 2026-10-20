import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "./api";
import { StrategyOverview, bookState } from "./components/StrategyOverview";
import { BookLedger } from "./components/BookLedger";
import { KLineChart } from "./components/KLineChart";
import { NotesBoard } from "./components/NotesBoard";
import { CloseloopPage } from "./components/CloseloopPage";
import { PortfolioPage } from "./components/PortfolioPage";
import { ReasonBanner, signalRationale } from "./components/ReasonBanner";
import { canSubmitOrder } from "./orderEligibility";
import { ResizableCard } from "./components/ResizableCard";
import { StrategyDesk } from "./components/StrategyDesk";
import { TradeToasts, toastsFromTrades, type TradeToastItem } from "./components/TradeToasts";
import { DEFAULT_SYMBOL, DESK_MARKET_IDS, marketUi } from "./markets/config";
import { instrumentLabel, usesNameCodeLabel } from "./markets/display";
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
type Page = "overview" | "desk" | "portfolio" | "research";

function readPage(): Page {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  if (path.endsWith("/research") || window.location.hash === "#/research") {
    return "research";
  }
  if (path.endsWith("/portfolio") || window.location.hash === "#/portfolio") {
    return "portfolio";
  }
  return path.endsWith("/desk") || window.location.hash === "#/desk" ? "desk" : "overview";
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
  const [symbol, setSymbol] = useState("JNJ");
  const [query, setQuery] = useState("JNJ");
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
  const [submitting, setSubmitting] = useState(false);
  const [runnerBusy, setRunnerBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [error, setError] = useState("");
  const [symbolError, setSymbolError] = useState("");
  const [symbolLoading, setSymbolLoading] = useState(true);
  const [blotterLoading, setBlotterLoading] = useState(true);
  const [deskLoading, setDeskLoading] = useState(true);
  const [page, setPage] = useState<Page>(readPage);
  const symbolLoadGen = useRef(0);
  const userLoadGen = useRef(0);
  const viewRef = useRef({ market: "us", symbol: "JNJ" });
  const seenTradeIds = useRef<Set<number> | null>(null);
  const [tradeToasts, setTradeToasts] = useState<TradeToastItem[]>([]);

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
      const paper = tr;
      const seen = seenTradeIds.current;
      if (seen === null) {
        seenTradeIds.current = new Set(paper.map((t) => t.id));
      } else {
        const fresh = paper.filter((t) => !seen.has(t.id));
        for (const t of fresh) {
          seen.add(t.id);
        }
        if (fresh.length) {
          setTradeToasts((prev) => [...toastsFromTrades(fresh), ...prev].slice(0, 4));
        }
      }
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
    viewRef.current = { market: nextMarket, symbol: nextSymbol };
    if (opts?.quiet && userLoadGen.current) {
      return;
    }
    const gen = opts?.quiet ? symbolLoadGen.current : ++symbolLoadGen.current;
    if (!opts?.quiet) {
      userLoadGen.current = gen;
    }
    if (!opts?.quiet) {
      setError("");
      setSymbolError("");
      setSymbol(nextSymbol);
      setQuery(nextSymbol);
      setInstrument(null);
      setQuote(null);
      setBars([]);
      setSignals(null);
      setSelectedOrder(null);
      setMessage("");
      setSymbolLoading(true);
    }
    try {
      const [inst, q, b, sig] = await Promise.all([
        api.instrument(nextMarket, nextSymbol),
        api.quote(nextMarket, nextSymbol),
        api.bars(nextMarket, nextSymbol, nextInterval),
        api.signals(nextMarket, nextSymbol),
      ]);
      if (gen !== symbolLoadGen.current) {
        return;
      }
      setInstrument(inst);
      setSymbolError("");
      setQuote(q);
      setBars(b);
      setSignals(sig);
      setSymbol(inst.symbol);
      if (!opts?.quiet) setQuery(inst.symbol);
    } catch (err) {
      if (gen !== symbolLoadGen.current) {
        return;
      }
      setSymbolError(err instanceof Error ? err.message : String(err));
    } finally {
      if (!opts?.quiet && userLoadGen.current === gen) {
        userLoadGen.current = 0;
      }
      if (!opts?.quiet && gen === symbolLoadGen.current) {
        setSymbolLoading(false);
      }
    }
  }

  function goPage(next: Page) {
    const url = next === "portfolio" ? "/portfolio" : next === "research" ? "/research" : next === "desk" ? "/desk" : "/";
    window.history.pushState({ page: next }, "", url);
    setPage(next);
    window.scrollTo(0, 0);
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
      const sym = DEFAULT_SYMBOL[first] ?? "JNJ";
      setSymbol(sym);
      setQuery(sym);
    }).catch((err: unknown) => {
      setError(err instanceof Error ? err.message : String(err));
      setSymbolLoading(false);
    });
    loadBlotter().catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
    loadDesk().catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  useEffect(() => {
    if (page === "desk" && !instrument && !userLoadGen.current) {
      void loadSymbol(market, symbol);
    }
  }, [page]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      loadBlotter({ quiet: true }).catch(() => undefined);
      if (page !== "desk") {
        return;
      }
      if (symbol) {
        const view = viewRef.current;
        loadSymbol(view.market, view.symbol, interval, { quiet: true }).catch(() => undefined);
      }
      api.notes().then(setNotes).catch(() => undefined);
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [page, market, symbol, interval]);

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    if (submitting || symbolLoading || !query.trim()) return;
    const selection = symbolLoadGen.current;
    try {
      const hits = await api.search(market, query.trim());
      if (selection !== symbolLoadGen.current || market !== viewRef.current.market) return;
      if (!hits[0]) { setError("未找到标的，请检查代码。"); return; }
      await loadSymbol(market, hits[0].symbol);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }

  async function switchMarket(id: string) {
    if (submitting) return;
    setMarket(id);
    const next = DEFAULT_SYMBOL[id] ?? query;
    setInterval("1d");
    const match = strategies.find((s) => s.book_id === id) ?? strategies.find((s) => s.markets.includes(id));
    if (match) {
      setStrategyId(match.id);
    }
    await loadSymbol(id, next, "1d");
  }

  async function submit(side: "buy" | "sell") {
    if (!canSubmit) return;
    setSubmitting(true);
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
        setMessage(`${side.toUpperCase()} ${order.quantity} ${instrumentLabel(market, order.symbol, order.name)} @ ${fmt(order.fill_price, ui.pricePrecision)}`);
      }
      setSelectedOrder(order);
      await loadBlotter();
      await loadSymbol(market, symbol, interval, { quiet: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally { setSubmitting(false); }
  }

  async function controlRunner(action: "tick" | "toggle") {
    if (runnerBusy) return;
    setRunnerBusy(true);
    try {
      setRunner(await (action === "tick" ? api.runnerTick() : runner?.running ? api.runnerStop() : api.runnerStart()));
      await loadBlotter({ quiet: true });
    } catch (err) { setError(String(err)); }
    finally { setRunnerBusy(false); }
  }

  const state = bookState(runner, market);
  const canSubmit = canSubmitOrder({
    submitting, loading: symbolLoading, quoteError: symbolError, hasAccount: !!account,
    symbol, instrumentSymbol: instrument?.symbol, quoteSymbol: quote?.symbol, quantity: qty, last: quote?.last,
  });
  const changeClass = (quote?.change ?? 0) >= 0 ? "up" : "down";
  const estNotional = (quote?.last ?? 0) * qty * (instrument?.multiplier ?? 1);

  return (
    <div className="terminal">
      <TradeToasts items={tradeToasts} />
      <header className="topbar">
        <button className="brand" onClick={() => goPage("overview")}>QuantiT <span>模拟交易</span></button>
        <nav className="pages" aria-label="主导航">
          {([["overview", "策略总览"], ["desk", "交易工作台"], ["portfolio", "资产组合"], ["research", "因子研究"]] as const).map(([id, title]) =>
            <button key={id} aria-current={page === id ? "page" : undefined} className={page === id ? "active" : ""} onClick={() => goPage(id)}>{title}</button>)}
        </nav>
        <span className={`status-pill ${runner?.running ? "success" : "neutral"}`}>{runner ? runner.running ? "调度运行中" : "调度已暂停" : "连接中"}</span>
      </header>
      {error ? <div className="global-error" role="alert"><span>{error}</span><button onClick={() => setError("")} aria-label="关闭提示">×</button></div> : null}
      {page === "overview" ? <>
        <StrategyOverview markets={markets} accounts={accounts} runner={runner}
          onOpen={(id) => { goPage("desk"); void switchMarket(id); }} onResearch={() => goPage("research")} />
        <div className="runner-controls"><span>策略调度 · 最近评估 {runner?.last_tick ? new Date(runner.last_tick.endsWith("Z") ? runner.last_tick : `${runner.last_tick}Z`).toLocaleString("zh-CN") : "—"}</span>
          <button disabled={runnerBusy || !runner} onClick={() => controlRunner("tick")}>{runnerBusy ? "处理中…" : "评估自动策略"}</button>
          <button disabled={runnerBusy || !runner} onClick={() => controlRunner("toggle")}>{runner?.running ? "暂停策略调度" : "启动策略调度"}</button></div>
      </> : null}
      {page === "portfolio" ? <PortfolioPage /> : null}
      {page === "research" ? <CloseloopPage /> : null}
      {page === "desk" ? <>
        <div className="desk-context">
          <div className="markets" aria-label="选择策略账户">{markets.filter((m) => m.id !== "cl" && (DESK_MARKET_IDS as readonly string[]).includes(m.id)).map((m) =>
            <button key={m.id} disabled={submitting} aria-pressed={m.id === market} className={m.id === market ? "active" : ""} onClick={() => switchMarket(m.id)}>{marketUi(m.id).label}</button>)}</div>
          <form className="search" onSubmit={onSearch}><input aria-label="标的代码" disabled={submitting} value={query} onChange={(e) => setQuery(e.target.value.toUpperCase())} placeholder="输入标的代码" />
            <button type="submit" disabled={symbolLoading || submitting || !query.trim()}>{symbolLoading ? "加载中…" : "查看行情"}</button></form>
        </div>
        <div className="book-context"><strong>{ui.label}</strong><span className={`status-pill ${state.tone}`}>{state.label}</span>
          <span>可用现金 {fmt(account?.cash)} {account?.currency}</span><span className="session">{currentMarket?.session_hours} · 延迟行情</span>
          {state.detail ? <details className="status-detail"><summary>查看账户阻塞原因</summary><p>{state.detail}</p></details> : null}
        </div>
      </> : null}
      {page === "desk" ? (
      <main className="dashboard desk-dashboard" aria-busy={blotterLoading}>
        <ResizableCard id="chart" className="chart" loading={symbolLoading} minWidth={360} minHeight={280}>
          <div className="quote-bar">
            <div>
              <h1>{instrumentLabel(instrument?.market_id ?? market, instrument?.symbol ?? symbol, instrument?.name)}</h1>
              <p>{instrument && !usesNameCodeLabel(instrument.market_id) ? `${instrument.name} · ` : ""}{instrument?.asset_class ?? "equity"} · {instrument?.currency} · lot {instrument?.lot_size ?? "—"}{instrument?.multiplier && instrument.multiplier > 1 ? ` · ×${instrument.multiplier}` : ""}</p>
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
          {symbolError ? <details className="quote-error" role="alert">
            <summary>{quote ? "行情刷新失败，保留上次行情；手动下单已暂停" : "行情暂不可用，手动下单已暂停"}</summary>
            <p>{symbolError}</p>
          </details> : null}
          <KLineChart bars={bars} />
          <ReasonBanner signals={signals?.signals ?? []} />
        </ResizableCard>

        <ResizableCard id="order" title="手动模拟下单" className="ticket" loading={symbolLoading} minWidth={240} minHeight={280}>
          <p className="hint">{ui.lotHint}{currentMarket?.t_plus ? ` · T+${currentMarket.t_plus}` : ""}</p>
          <label>
            数量
            <input type="number" min={1} value={qty} onChange={(e) => setQty(Number(e.target.value))} />
          </label>
          <p className="est">预计金额 {fmt(estNotional, ui.pricePrecision)} {account?.currency}</p>
          <p className="cash">可用现金 {fmt(account?.cash)} {account?.currency}</p>
          <div className="sides">
            <button className="buy" disabled={!canSubmit} onClick={() => submit("buy")}>{submitting ? "提交中…" : "模拟买入"}</button>
            <button className="sell" disabled={!canSubmit} onClick={() => submit("sell")}>模拟卖出</button>
          </div>
          {message ? <p className="msg">{message}</p> : null}

          <p className="hint">订单仅记入 {ui.label} 模拟账户。手续费及可成交数量由账户规则校验。</p>
          {selectedOrder ? (
            <div className="detail">
              <h3>委托 #{selectedOrder.id}</h3>
              <p>{instrumentLabel(selectedOrder.market_id, selectedOrder.symbol, selectedOrder.name)} · {ui.label}</p>
              <dl>
                <dt>状态</dt><dd>{selectedOrder.status}</dd>
                <dt>方向</dt><dd>{selectedOrder.side === "buy" ? "买入" : "卖出"}</dd>
                <dt>数量</dt><dd>{selectedOrder.quantity}</dd>
                <dt>成交价</dt><dd>{fmt(selectedOrder.fill_price, ui.pricePrecision)}</dd>
                <dt>手续费</dt><dd>{fmt(selectedOrder.commission, 4)}</dd>
                {selectedOrder.rationale ? (
                  <>
                    <dt>执行依据</dt>
                    <dd className="wrap">{selectedOrder.rationale}</dd>
                  </>
                ) : null}
                {selectedOrder.reject_reason ? (
                  <>
                    <dt>拒绝原因</dt>
                    <dd>{selectedOrder.reject_reason}</dd>
                  </>
                ) : null}
              </dl>
            </div>
          ) : null}
        </ResizableCard>

        <div className="desk-tabs">
          {([
            ["blotter", "账户记录"],
            ["strategies", "策略说明"],
            ["notes", "研究笔记"],
          ] as const).map(([id, label]) => (
            <button key={id} className={desk === id ? "active" : ""} onClick={() => setDesk(id)}>
              {label}
            </button>
          ))}
        </div>

        {desk === "blotter" ? <BookLedger key={market} market={market} positions={positions} trades={trades} orders={orders}
          onSymbol={(next) => { if (!submitting) void loadSymbol(market, next); }} onOrder={setSelectedOrder} /> : null}
        {desk === "strategies" ? (
          <ResizableCard id="strategies" title="策略说明" className="wide" loading={deskLoading} minWidth={360} minHeight={220}>
            <StrategyDesk
              strategies={strategies.filter((s) => s.book_id ? s.book_id === market : s.markets.includes(market))}
              selectedId={strategyId}
              onSelect={setStrategyId}
              market={market}
            />
          </ResizableCard>
        ) : null}
        {desk === "notes" ? (
          <ResizableCard id="notes" title="研究笔记" className="wide" loading={deskLoading} minWidth={360} minHeight={220}>
            <NotesBoard
              notes={notes}
              market={market}
              symbol={instrumentLabel(instrument?.market_id ?? market, symbol, instrument?.name)}
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
