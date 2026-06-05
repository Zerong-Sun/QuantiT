# 均值回复

## 1. 均值回复的定义

### 概念
均值回复（Mean Reversion）是指价格或收益率倾向于向其历史均值回归的现象。

### 数学定义
若价格过程 $P_t$ 满足：
$$E[P_T | P_t] = \mu + (P_t - \mu)e^{-\theta(T-t)}$$
其中 $\theta > 0$ 是回复速度，则 $P_t$ 是均值回复的。

### 与趋势的关系
- **均值回复**：$\theta > 0$，价格向均值回归
- **趋势延续**：$\theta < 0$，价格远离均值
- **随机游走**：$\theta = 0$，无回复

## 2. 均值回复的来源

### 基本面驱动
- **价值回归**：价格偏离内在价值后回归
- **套利力量**：套利者推动价格回归均衡

### 市场微观结构
- **过度反应**：投资者对信息过度反应后修正
- **流动性冲击**：大单导致价格偏离后回复

### 行为金融
- **锚定效应**：投资者锚定于历史价格
- **处置效应**：过早卖出赢家，持有输家

## 3. 检验均值回复

### ADF 检验
$$\Delta P_t = \alpha + \beta P_{t-1} + \sum_{i=1}^p \gamma_i \Delta P_{t-i} + \epsilon_t$$

- $H_0$：$\beta = 0$（随机游走）
- $H_1$：$\beta < 0$（均值回复）

### 方差比检验
$$VR(k) = \frac{\text{Var}(P_t - P_{t-k})}{k \cdot \text{Var}(P_t - P_{t-1})}$$

- $VR(k) = 1$：随机游走
- $VR(k) < 1$：均值回复
- $VR(k) > 1$：趋势延续

### Hurst 指数
$$E[|R_t(\tau)|] = C \tau^H$$

- $H < 0.5$：均值回复
- $H = 0.5$：随机游走
- $H > 0.5$：趋势延续

## 4. Ornstein-Uhlenbeck 过程

### 模型
$$dX_t = \theta(\mu - X_t)dt + \sigma dW_t$$

### 性质

| 性质 | 公式 |
|------|------|
| 均值 | $E[X_t] = \mu + (X_0 - \mu)e^{-\theta t}$ |
| 方差 | $\text{Var}(X_t) = \frac{\sigma^2}{2\theta}(1 - e^{-2\theta t})$ |
| 稳态均值 | $\mu$ |
| 稳态方差 | $\frac{\sigma^2}{2\theta}$ |
| 自协方差 | $\text{Cov}(X_t, X_{t+h}) = \frac{\sigma^2}{2\theta}e^{-\theta h}$ |

### 参数估计

**最大似然估计**：
给定离散观测 $X_0, X_1, \ldots, X_n$，时间间隔 $\Delta t$：

$$\hat{\theta} = -\frac{1}{\Delta t} \ln\left(\frac{\sum_{i=1}^n (X_i - \bar{X})(X_{i-1} - \bar{X})}{\sum_{i=1}^n (X_{i-1} - \bar{X})^2}\right)$$

## 5. 均值回复策略

### 价格均值回复
```python
def mean_reversion_strategy(prices, lookback, entry_z=2, exit_z=0.5):
    """
    基于价格均值回复的策略
    """
    signals = []
    ma = prices.rolling(lookback).mean()
    std = prices.rolling(lookback).std()
    z_score = (prices - ma) / std
    
    position = 0
    for i in range(lookback, len(prices)):
        if position == 0:
            if z_score.iloc[i] < -entry_z:
                signals.append(1)  # 买入
                position = 1
            elif z_score.iloc[i] > entry_z:
                signals.append(-1)  # 卖出
                position = -1
        elif position == 1:
            if z_score.iloc[i] > -exit_z:
                signals.append(0)  # 平仓
                position = 0
            else:
                signals.append(1)
        elif position == -1:
            if z_score.iloc[i] < exit_z:
                signals.append(0)  # 平仓
                position = 0
            else:
                signals.append(-1)
    
    return signals
```

### 截面均值回复
```python
def cross_sectional_reversion(returns, lookback=5, holding=5):
    """
    截面均值回复策略
    买入过去输家，卖出过去赢家
    """
    past_returns = returns.rolling(lookback).sum()
    ranks = past_returns.rank(axis=1, pct=True)
    
    # 做多底部20%，做空顶部20%
    long = (ranks < 0.2).astype(float)
    short = (ranks > 0.8).astype(float)
    
    weights = (long - short) / (long.sum(axis=1) + short.sum(axis=1)).values[:, None]
    return weights
```

## 6. 均值回复 vs 动量

| 特征 | 均值回复 | 动量 |
|------|----------|------|
| 时间尺度 | 短期（1-30天）/长期（3-5年） | 中期（1-12个月） |
| 信号来源 | 价格偏离均值 | 价格趋势 |
| 风险 | 趋势持续风险 | 反转风险 |
| 适用市场 | 震荡市 | 趋势市 |

### 混合策略
结合不同时间尺度：
- 短期动量（1周）
- 中期反转（1月）
- 长期动量（12月）

## 7. 实际考虑

### 交易成本
- 均值回复策略通常换手率高
- 需要扣除交易成本后仍有收益

### 容量限制
- 小市值股票均值回复更强
- 但容量有限

### 市场状态
- 均值回复在震荡市有效
- 趋势市中可能失效

### 风险管理
- 设置止损防止趋势延续
- 控制单笔仓位
- 分散化
