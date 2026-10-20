/** UI guard only; the server remains authoritative for funds, lots and fills. */
export function canSubmitOrder(input: {
  submitting: boolean;
  loading: boolean;
  quoteError: string;
  hasAccount: boolean;
  symbol: string;
  instrumentSymbol?: string;
  quoteSymbol?: string;
  quantity: number;
  last?: number;
}): boolean {
  return !input.submitting && !input.loading && !input.quoteError && input.hasAccount
    && !!input.symbol && input.instrumentSymbol === input.symbol && input.quoteSymbol === input.symbol
    && Number.isInteger(input.quantity) && input.quantity > 0
    && typeof input.last === "number" && Number.isFinite(input.last) && input.last > 0;
}
