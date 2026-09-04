export const MARKET_UI: Record<
  string,
  { label: string; pricePrecision: number; lotHint: string }
> = {
  us: { label: "US", pricePrecision: 2, lotHint: "Stocks, ETFs, options (×100)" },
  hk: { label: "HK", pricePrecision: 3, lotHint: "Stocks, ETFs, warrants" },
  cn: { label: "A-share", pricePrecision: 2, lotHint: "100-share lots, T+1, ETFs" },
  cl: { label: "CL", pricePrecision: 2, lotHint: "CSI300 research book, lots of 100" },
};

export const DEFAULT_SYMBOL: Record<string, string> = {
  us: "AAPL",
  hk: "0700.HK",
  cn: "510300.SS",
};

export const DESK_MARKET_IDS = ["us", "hk", "cn"] as const;

export function marketUi(id: string) {
  return MARKET_UI[id] ?? { label: id.toUpperCase(), pricePrecision: 2, lotHint: "" };
}
