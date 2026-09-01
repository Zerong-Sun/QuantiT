# 恒生科技主题轮动

## 1. 定义

在**恒生科技 + 中资互联网核心池**内，按月把资金分配到四个主题（平台、硬件、半导体、新能源车），而不是做分钟级交易或全市场金融/地产轮动。

成分（Yahoo 代码）见 `quantit.markets.hk.HSTECH_THEMES`。

## 2. 合成分数

对主题 $k$：

$$
S_{k,t} = 0.35\, \text{Demand}_{k,t} + 0.35\, \text{Policy}_{k,t} + 0.30\, \text{Intl}_t
$$

Demand / Policy / Intl 均裁剪到 $[-2, 2]$ 后再加权，使量纲一致。

## 3. 月频权重

在每月最后一个港股交易日：

1. 若 $\max_k S_{k,t} < \tau_{\text{cash}}$（默认 $-0.5$），提高现金比例（默认目标投资不超过 40%）
2. 否则对 $\exp(S_k)$ 做 softmax，映射为主题权重；主题内等权到个股
3. 若主题分数极差过小，向等权收缩，避免无信息时空转

$$
w_k \propto \exp(S_{k,t}), \quad \sum_k w_k = 1 - w_{\text{cash}}
$$

## 4. 直觉

- 政策日历给出「哪一类生意被允许增长」
- 供需给出「有没有人在买」
- 国际分给出「全球折现率和美元是否允许给成长股估值」
- 月频是为了匹配这些变量的变化速度，而不是捕捉 K 线噪音

## 5. 实际应用

```text
Macro + OHLCV + YAML
        → regime scores
        → ThemeRotationStrategy
        → Backtester.run(dict of frames)
```

示例：`examples/hk_tech_rotation.py`。

## 6. 局限性

- 主题内等权忽略市值与流动性差异
- 未做手数取整；腾讯等高价股在小资金下份额粗糙
- 事后政策日历有前视偏差
- 股票池固定，不等于官方恒生科技指数定期检讨
