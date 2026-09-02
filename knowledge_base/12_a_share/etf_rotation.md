# A 股行业 ETF 轮动

## 1. 定义

在**场内行业 ETF 核心池**内，按月把资金分配到四个主题（半导体、新能源/车、医药、军工），而不是做分钟级交易或全市场风格轮动。

成分见 `quantit.markets.cn.CN_ETF_THEMES`。买不起 100 股一手的权重拨到 `510300.SS`（沪深300），对应港股的 `3033.HK`。

## 2. 合成分数

对主题 $k$：

$$
S_{k,t} = 0.35\, \text{Demand}_{k,t} + 0.35\, \text{Policy}_{k,t} + 0.30\, \text{Intl}_t
$$

Demand / Policy / Intl 均裁剪到 $[-2, 2]$ 后再加权。

**Demand**（主题级，与港股不同）：相对成交 + 相对沪深300（`510300.SS`）的累积收益。港股需求分里「相对纳指」是四个主题共享的；A 股让超额收益留在主题上，袖套才能分开。

**Policy**：见 [policy_regimes.md](policy_regimes.md)。

**Intl**：美元、美债 10Y、纳指、USDCNY 的滚动 z（与港股同一套宏）。

## 3. 月频权重

在每月最后一个 A 股交易日：

1. 若 $\max_k S_{k,t} < \tau_{\text{cash}}$（默认 $-0.5$），提高现金比例（默认目标投资不超过 40%）
2. 否则对 $\exp(S_k)$ 做 softmax，映射为主题权重；主题内对**当日有报价**的 ETF 等权
3. 若主题分数极差过小，向等权收缩
4. 纸面再按 100 股一手向下取整；残差到 510300 或现金

$$
w_k \propto \exp(S_{k,t}), \quad \sum_k w_k = 1 - w_{\text{cash}}
$$

## 4. 直觉

- 政策日历给出「哪一条产业链被允许增长」
- 供需给出「相对 300 有没有人在买这条链」
- 国际分给出「全球折现率和美元是否允许给成长/北向估值」
- 月频匹配这些变量的变化速度，而不是捕捉 ETF 日内折溢价

## 5. 实际应用

```text
CSV/AkShare OHLCV + Macro + YAML
        → compute_cn_etf_scores
        → ThemeRotationStrategy(themes=CN_ETF_THEMES)
        → Backtester.run(dict of frames)
```

示例：`examples/cn_etf_rotation.py`。纸面：`PaperRunner._tick_cn`。

## 6. 局限性

- 主题内等权忽略规模与流动性
- 股票池固定，不等于中证行业官方定期检讨
- 事后政策日历有前视偏差
- CSV 可能短于 AkShare 全历史；回测窗口取决于两者并集
