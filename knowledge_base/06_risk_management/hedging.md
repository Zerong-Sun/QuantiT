# 对冲策略

## 1. 对冲基础

### 什么是对冲
对冲是通过建立相反头寸来降低风险的策略。

### 对冲比率
$$h = \frac{\text{对冲头寸价值}}{\text{被对冲头寸价值}}$$

### 完美对冲 vs 不完美对冲
- **完美对冲**：完全消除风险（如期货对冲现货）
- **不完美对冲**：降低但不消除风险（如 beta 对冲）

## 2. Beta 对冲

### 概念
通过调整组合 beta 来控制市场风险暴露。

### 对冲比率
$$h = \frac{\beta_{portfolio}}{\beta_{hedge}}$$

### 实现
```python
def beta_hedge(portfolio, market_returns, hedge_asset_returns, target_beta=0):
    """
    Beta 对冲
    """
    # 计算当前 beta
    from sklearn.linear_model import LinearRegression
    reg = LinearRegression()
    reg.fit(market_returns.values.reshape(-1, 1), portfolio.returns)
    current_beta = reg.coef_[0]

    # 计算对冲所需头寸
    hedge_ratio = (current_beta - target_beta) / reg.coef_[0]

    return hedge_ratio
```

## 3. 统计对冲

### 配对交易对冲
```python
def pairs_hedge_ratio(series_x, series_y, lookback=60):
    """
    计算配对交易的对冲比率
    """
    from sklearn.linear_model import LinearRegression
    reg = LinearRegression()
    reg.fit(series_x.values.reshape(-1, 1), series_y)
    return reg.coef_[0]  # hedge ratio = beta
```

### 协整对冲
```python
def cointegration_hedge(series_x, series_y, lookback=252):
    """
    基于协整的对冲
    """
    from statsmodels.tsa.stattools import coint
    score, pvalue, hedge_ratio = coint(series_x, series_y)
    return hedge_ratio
```

## 4. 期权对冲

### Delta 对冲
$$\Delta = \frac{\partial V}{\partial S}$$

**对冲方法**：
```python
def delta_hedge(option_position, underlying):
    """
    Delta 对冲
    """
    delta = option_position.delta
    hedge_units = -delta * option_position.quantity
    return hedge_units
```

### Gamma 对冲
$$\Gamma = \frac{\partial^2 V}{\partial S^2}$$

**目的**：对冲 delta 的变化率

### Vega 对冲
$$\text{Vega} = \frac{\partial V}{\partial \sigma}$$

**目的**：对冲波动率风险

### 对冲组合
| 策略 | 目标 | 工具 |
|------|------|------|
| Delta 对冲 | 方向风险 | 标的资产 |
| Gamma 对冲 | 曲率风险 | 期权 |
| Vega 对冲 | 波动率风险 | 期权 |
| Theta 对冲 | 时间衰减 | 期权 |

## 5. 组合对冲

### 因子中性
```python
def factor_neutral_portfolio(weights, factor_exposures, target_exposure=0):
    """
    构建因子中性组合
    """
    from scipy.optimize import minimize

    def objective(w):
        portfolio_exposure = w @ factor_exposures
        return (portfolio_exposure - target_exposure)**2

    constraints = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}
    result = minimize(objective, weights, constraints=constraints)
    return result.x
```

### 行业中性
```python
def industry_neutral_portfolio(weights, industry_weights, market_weights):
    """
    行业中性组合
    """
    # 调整权重使行业暴露与市场一致
    adjusted_weights = {}
    for industry in industry_weights:
        target = market_weights[industry]
        current = industry_weights[industry]
        adjustment = target / current if current > 0 else 1
        adjusted_weights[industry] = weights[industry] * adjustment
    return adjusted_weights
```

## 6. 动态对冲

### 调仓频率
| 频率 | 优点 | 缺点 |
|------|------|------|
| 每日 | 精确 | 成本高 |
| 每周 | 平衡 | 中等 |
| 每月 | 成本低 | 不精确 |

### 阈值对冲
```python
def threshold_rebalance(current_hedge, target_hedge, threshold=0.1):
    """
    阈值调仓
    """
    deviation = abs(current_hedge - target_hedge) / target_hedge
    if deviation > threshold:
        return target_hedge
    return current_hedge
```

### 成本优化
$$\text{Total Cost} = \text{Transaction Cost} + \text{Hedge Error Cost}$$

## 7. 对冲风险管理

### 基差风险
**定义**：对冲工具与被对冲资产价格差异的风险

**来源**：
- 期货与现货价差
- 不同股票间价差
- 不同期限债券价差

### 对冲失效风险
**原因**：
- 市场结构变化
- 模型假设失效
- 极端市场条件

### 监控指标
| 指标 | 说明 |
|------|------|
| 对冲误差 | 实际对冲效果与预期的差异 |
| 对冲比率偏离 | 实际比率与目标比率的差异 |
| 基差变化 | 对冲工具与被对冲资产价差变化 |

## 8. 实际案例

### 股票多空策略对冲
```python
def long_short_hedge(long_portfolio, short_portfolio):
    """
    股票多空策略
    """
    # 做多被低估股票
    long_weights = select_stocks('undervalued')

    # 做空被高估股票
    short_weights = select_stocks('overvalued')

    # 市场中性：使 beta 为零
    net_beta = long_beta + short_beta
    if abs(net_beta) > 0.1:
        # 调整仓位使 beta 为零
        adjust_positions()

    return combined_portfolio
```

### 期权保护性看跌
```python
def protective_put(stock_position, put_options):
    """
    保护性看跌期权
    """
    # 持有股票
    # 买入看跌期权保护下行风险

    portfolio_value = stock_position.value
    put_cost = put_options.premium * put_options.quantity

    # 最大损失 = put_cost（而非股票全部价值）
    max_loss = put_cost

    return {
        'upside': 'unlimited',
        'downside': f'{max_loss} ({max_loss/portfolio_value*100}%)'
    }
```

## 9. 对冲效率评估

### 对冲效率指标
$$\text{Hedge Efficiency} = 1 - \frac{\text{Var}(\text{hedged})}{\text{Var}(\text{unhedged})}$$

### 回测评估
```python
def evaluate_hedge(hedged_returns, unhedged_returns):
    """
    评估对冲效果
    """
    hedged_vol = hedged_returns.std() * np.sqrt(252)
    unhedged_vol = unhedged_returns.std() * np.sqrt(252)

    hedge_efficiency = 1 - (hedged_vol / unhedged_vol)

    return {
        'hedged_volatility': hedged_vol,
        'unhedged_volatility': unhedged_vol,
        'hedge_efficiency': hedge_efficiency,
        'reduction_pct': (unhedged_vol - hedged_vol) / unhedged_vol * 100
    }
```
