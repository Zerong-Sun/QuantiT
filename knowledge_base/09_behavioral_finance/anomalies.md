# 市场异象

## 1. 价值异象
高 B/M 股票跑赢低 B/M 股票，年化溢价 +4.5% (1926-2020)

## 2. 规模异象
小市值股票跑赢大市值股票，年化溢价 +3.5%

## 3. 动量异象
过去赢家继续赢，输家继续输，年化溢价 +8.0%

```python
def momentum_strategy(returns, lookback=252, holding=21):
    past_returns = returns.rolling(lookback).sum()
    ranks = past_returns.rank(pct=True)
    long = (ranks > 0.8).astype(float)
    short = (ranks < 0.2).astype(float)
    return (long - short) / 2
```

## 4. 低波动异象
低波动股票风险调整后收益更高，与 CAPM 矛盾

## 5. 盈利能力异象
高盈利能力公司跑赢低盈利能力公司

| 指标 | 溢价 |
|------|------|
| ROE | +2.5% |
| Gross Profitability | +4.0% |
| Accruals | +3.0% |

## 6. 盈余公告后漂移（PEAD）
盈利超预期后，股价在60天内持续漂移，年化溢价 +10.0%

## 7. 异象的衰减
发现 -> 发表 -> 媒体报道 -> 资金涌入 -> 溢价下降 -> 衰减
