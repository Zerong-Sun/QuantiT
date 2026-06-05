# 配对交易

## 1. 基本概念

### 什么是配对交易
配对交易是一种市场中性策略，通过同时买入和卖出两只高度相关的股票来获利：
- **买入**被低估的股票（相对便宜）
- **卖出**被高估的股票（相对昂贵）
- 利用价差的均值回复获利

### 市场中性
$$\text{Portfolio Beta} = w_1 \beta_1 + w_2 \beta_2 \approx 0$$

## 2. 配对选择方法

### 距离法（Distance Method）
```python
def distance_method(prices, lookback=60):
    """距离法选择配对"""
    n = len(prices.columns)
    pairs = []
    for i in range(n):
        for j in range(i+1, n):
            norm_i = prices.iloc[:, i] / prices.iloc[:, i].iloc[0]
            norm_j = prices.iloc[:, j] / prices.iloc[:, j].iloc[0]
            distance = np.sum((norm_i - norm_j)**2)
            pairs.append((prices.columns[i], prices.columns[j], distance))
    return sorted(pairs, key=lambda x: x[2])[:10]
```

### 协整法（Cointegration）
```python
def cointegration_method(prices, lookback=252):
    """协整法选择配对"""
    from statsmodels.tsa.stattools import coint
    pairs = []
    n = len(prices.columns)
    for i in range(n):
        for j in range(i+1, n):
            score, pvalue, _ = coint(prices.iloc[:, i].tail(lookback),
                                      prices.iloc[:, j].tail(lookback))
            if pvalue < 0.05:
                pairs.append((prices.columns[i], prices.columns[j], pvalue))
    return sorted(pairs, key=lambda x: x[2])[:10]
```

## 3. 价差建模

### Ornstein-Uhlenbeck 过程
$$dS_t = \theta(\mu - S_t)dt + \sigma dW_t$$

### 参数估计
```python
def estimate_ou_params(spread):
    """估计 OU 过程参数"""
    from scipy.optimize import minimize
    def neg_log_likelihood(params):
        theta, mu, sigma = params
        if theta <= 0 or sigma <= 0:
            return 1e10
        dt = 1/252
        mean = spread[:-1] * np.exp(-theta * dt) + mu * (1 - np.exp(-theta * dt))
        var = sigma**2 / (2*theta) * (1 - np.exp(-2*theta * dt))
        log_lik = -0.5 * np.sum(np.log(2*np.pi*var) + (spread[1:] - mean)**2 / var)
        return -log_lik
    x0 = [0.1, np.mean(spread), np.std(spread)]
    result = minimize(neg_log_likelihood, x0, method='L-BFGS-B',
                     bounds=[(0.01, 10), (-10, 10), (0.01, 10)])
    return result.x
```

### 半衰期
$$t_{1/2} = \frac{\ln 2}{\theta}$$

## 4. 交易信号

### Z-Score 信号
$$Z_t = \frac{S_t - \mu}{\sigma}$$

| Z-Score | 信号 |
|---------|------|
| Z < -2 | 买入价差（买A卖B） |
| Z > 2 | 卖出差价（卖A买B） |
| \|Z\| < 0.5 | 平仓 |

## 5. 风险管理

### 止损
- **价格止损**：价差偏离超过 3-4 个标准差
- **时间止损**：持仓超过 N 天
- **亏损止损**：单笔亏损超过阈值

### 仓位管理
```python
def position_size(capital, spread_std, risk_per_trade=0.01):
    """基于波动率的仓位管理"""
    dollar_risk = capital * risk_per_trade
    position_value = dollar_risk / spread_std
    return position_value
```

## 6. 实际考虑

| 因素 | 说明 |
|------|------|
| 交易成本 | 买卖价差、佣金、市场冲击 |
| 融券限制 | 借券可用性、借券利率 |
| 基本面风险 | 公司特定事件（并购、破产） |
| 流动性 | 成交量是否足够 |

## 7. 回测框架

```python
class PairsBacktest:
    def __init__(self, pair, lookback, entry_z, exit_z, stop_z):
        self.pair = pair
        self.lookback = lookback
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.stop_z = stop_z

    def run(self, prices):
        spread = prices[self.pair[0]] - prices[self.pair[1]]
        theta, mu, sigma = estimate_ou_params(spread)
        signals = []
        position = 0
        for i in range(self.lookback, len(spread)):
            z = (spread[i] - mu) / sigma
            if position == 0:
                if z < -self.entry_z:
                    signals.append(1)
                    position = 1
                elif z > self.entry_z:
                    signals.append(-1)
                    position = -1
            elif position == 1:
                if z > -self.exit_z or z < -self.stop_z:
                    signals.append(0)
                    position = 0
                else:
                    signals.append(1)
            elif position == -1:
                if z < self.exit_z or z > self.stop_z:
                    signals.append(0)
                    position = 0
                else:
                    signals.append(-1)
        return signals
```
