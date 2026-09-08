import { useEffect, useRef, useState } from "react";
import { instrumentLabel } from "../markets/display";
import { marketUi } from "../markets/config";
import type { Trade } from "../types";

export interface TradeToastItem {
  key: string;
  tradeId: number;
  side: string;
  marketId: string;
  label: string;
  quantity: number;
  price: number;
}

function fmtPrice(marketId: string, n: number): string {
  const digits = marketUi(marketId).pricePrecision;
  return n.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function toastsFromTrades(trades: Trade[]): TradeToastItem[] {
  return [...trades]
    .sort((a, b) => b.id - a.id)
    .map((t) => ({
      key: `trade-${t.id}`,
      tradeId: t.id,
      side: t.side,
      marketId: t.market_id,
      label: instrumentLabel(t.market_id, t.symbol, t.name),
      quantity: t.quantity,
      price: t.price,
    }));
}

export function TradeToasts({ items }: { items: TradeToastItem[] }) {
  const [leaving, setLeaving] = useState<Set<string>>(() => new Set());
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const armed = useRef<Set<string>>(new Set());

  useEffect(() => {
    for (const item of items) {
      if (armed.current.has(item.key)) {
        continue;
      }
      armed.current.add(item.key);
      window.setTimeout(() => {
        setLeaving((prev) => new Set(prev).add(item.key));
      }, 4800);
    }
  }, [items]);

  function dismiss(key: string) {
    setLeaving((prev) => new Set(prev).add(key));
  }

  const visible = items.filter((item) => !hidden.has(item.key));
  if (!visible.length) {
    return null;
  }

  return (
    <div className="trade-toasts" aria-live="polite">
      {visible.map((item) => {
        const side = item.side.toLowerCase();
        const buy = side === "buy";
        return (
          <button
            key={item.key}
            type="button"
            className={`trade-toast ${buy ? "buy" : "sell"}${leaving.has(item.key) ? " leaving" : ""}`}
            onClick={() => dismiss(item.key)}
            onAnimationEnd={(event) => {
              if (event.animationName === "trade-toast-out") {
                setHidden((prev) => new Set(prev).add(item.key));
              }
            }}
          >
            <span className="trade-toast-side">{buy ? "买入" : "卖出"}</span>
            <span className="trade-toast-label">{item.label}</span>
            <span className="trade-toast-fill">
              {item.quantity} @ {fmtPrice(item.marketId, item.price)}
            </span>
          </button>
        );
      })}
    </div>
  );
}
