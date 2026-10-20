export const MARKET_UI: Record<
  string,
  { label: string; pricePrecision: number; lotHint: string }
> = {
  us: { label: "美股质量", pricePrecision: 2, lotHint: "股票 / ETF / 期权（乘数 ×100）" },
  us_book: { label: "美股 MA/RSI", pricePrecision: 2, lotHint: "股票 / ETF / 期权（乘数 ×100）" },
  hk: { label: "港股质量", pricePrecision: 3, lotHint: "股票 / ETF / 认购证" },
  hk_theme: { label: "港股科技主题", pricePrecision: 3, lotHint: "恒生科技主题 / 认购证" },
  cn: { label: "A 股质量", pricePrecision: 2, lotHint: "每手 100 股，T+1" },
  cn_etf: { label: "行业 ETF", pricePrecision: 2, lotHint: "行业 ETF，每手 100 份，T+1" },
  cl: { label: "因子研究账户", pricePrecision: 2, lotHint: "固定研究股票池，每手 100 股" },
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
