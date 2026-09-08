export const MARKET_UI: Record<
  string,
  { label: string; pricePrecision: number; lotHint: string }
> = {
  us: { label: "US quality", pricePrecision: 2, lotHint: "Stocks, ETFs, options (×100)" },
  us_book: { label: "US MA/RSI", pricePrecision: 2, lotHint: "Stocks, ETFs, options (×100)" },
  hk: { label: "HK quality", pricePrecision: 3, lotHint: "Stocks, ETFs, warrants" },
  hk_theme: { label: "HK theme", pricePrecision: 3, lotHint: "Hang Seng TECH + warrants" },
  cn: { label: "CN quality", pricePrecision: 2, lotHint: "100-share lots, T+1" },
  cn_etf: { label: "CN ETFs", pricePrecision: 2, lotHint: "Industry ETFs, lots of 100, T+1" },
  cl: { label: "CL CSI300", pricePrecision: 2, lotHint: "CSI300 research book, lots of 100" },
};

export const DEFAULT_SYMBOL: Record<string, string> = {
  us: "JNJ",
  us_book: "JNJ",
  hk: "0002.HK",
  hk_theme: "0700.HK",
  cn: "600519.SS",
  cn_etf: "510300.SS",
  cl: "SH600519",
};

export const DESK_MARKET_IDS = ["us", "us_book", "hk", "hk_theme", "cn", "cn_etf", "cl"] as const;

export function marketUi(id: string) {
  return MARKET_UI[id] ?? { label: id.toUpperCase(), pricePrecision: 2, lotHint: "" };
}
