export const MARKET_UI: Record<
  string,
  { label: string; pricePrecision: number; lotHint: string }
> = {
  us: { label: "US", pricePrecision: 2, lotHint: "Odd lots allowed" },
  hk: { label: "HK", pricePrecision: 3, lotHint: "Board lot when known" },
  cn: { label: "A-share", pricePrecision: 2, lotHint: "100-share lots, T+1" },
};

export const DEFAULT_SYMBOL: Record<string, string> = {
  us: "AAPL",
  hk: "0700.HK",
  cn: "600519.SS",
};

export function marketUi(id: string) {
  return MARKET_UI[id] ?? { label: id.toUpperCase(), pricePrecision: 2, lotHint: "" };
}
