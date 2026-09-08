/** Markets that show 公司名字（股票代码）instead of the bare ticker. */
const NAME_CODE_MARKETS = new Set(["hk", "hk_theme", "cn", "cn_etf", "cl", "fut", "futures"]);

export function usesNameCodeLabel(marketId: string): boolean {
  return NAME_CODE_MARKETS.has((marketId || "").toLowerCase());
}

export function instrumentLabel(marketId: string, symbol: string, name?: string | null): string {
  if (!usesNameCodeLabel(marketId)) {
    return symbol;
  }
  const label = (name ?? "").trim();
  if (!label || label === symbol) {
    return symbol;
  }
  return `${label}（${symbol}）`;
}
