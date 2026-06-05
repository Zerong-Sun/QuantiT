# 风险因子

## 1. 系统性风险因子

### 市场因子（MKT）
- **定义**：市场组合超额收益
- **来源**：整体市场风险
- **对冲**：市场中性组合

### 规模因子（SMB）
- **定义**：小市值股票 vs 大市值股票
- **来源**：流动性风险、信息不对称
- **对冲**：调整组合市值分布

### 价值因子（HML）
- **定义**：高 B/M vs 低 B/M 股票
- **来源**：财务困境风险、行为偏差
- **对冲**：平衡价值/成长暴露

### 动量因子（UMD）
- **定义**：过去赢家 vs 过去输家
- **来源**：反应不足、趋势追逐
- **对冲**：反转策略

### 盈利因子（RMW）
- **定义**：高盈利 vs 低盈利公司
- **来源**：商业模式质量
- **对冲**：质量因子中性

### 投资因子（CMA）
- **定义**：保守投资 vs 激进投资公司
- **来源**：增长可持续性
- **对冲**：投资风格中性

## 2. 宏观经济因子

### 利率因子
| 因子 | 定义 | 影响资产 |
|------|------|----------|
| 短期利率 | 联邦基金利率 | 货币市场、银行 |
| 长期利率 | 10年期国债收益率 | 债券、REITs |
| 期限利差 | 长期 - 短期利率 | 银行、金融股 |
| 信用利差 | 公司债 - 国债收益率 | 高收益债、周期股 |

### 通胀因子
$$\text{Real Return} = \text{Nominal Return} - \text{Inflation}$$

- **通胀预期**：TIPS 利差
- **通胀实现**：CPI 变化
- **通胀敏感资产**：大宗商品、TIPS

### 经济增长因子
| 因子 | 指标 | 敏感资产 |
|------|------|----------|
| 经济增长 | GDP 增长率 | 周期股、小盘股 |
| 工业产出 | IP 指数 | 工业股 |
| 就业 | 失业率 | 消费股 |
| 消费信心 | 消费者信心指数 | 可选消费 |

### 流动性因子
| 因子 | 指标 | 影响 |
|------|------|------|
| 市场流动性 | 买卖价差 | 所有资产 |
| 融资流动性 | LIBOR-OIS 利差 | 金融机构 |
| 美元流动性 | 美元指数 | 新兴市场 |
| VIX | 波动率指数 | 风险资产 |

## 3. 风险因子模型

### Barra 模型
```
r_i = Σ_k (β_ik * f_k) + ε_i

其中：
r_i = 股票i的收益
β_ik = 股票i对因子k的暴露
f_k = 因子k的收益
ε_i = 特异性收益
```

### 因子暴露计算
```python
def factor_exposures(stock_data, factors):
    """
    计算股票的因子暴露
    """
    exposures = {}
    for factor_name, factor_data in factors.items():
        # OLS 回归
        from sklearn.linear_model import LinearRegression
        reg = LinearRegression()
        reg.fit(factor_data.values.reshape(-1, 1), stock_data['returns'])
        exposures[factor_name] = reg.coef_[0]
    return exposures
```

### 因子收益估计
```python
def factor_returns(stock_returns, factor_exposures):
    """
    估计因子收益
    """
    from sklearn.linear_model import LinearRegression
    reg = LinearRegression()
    reg.fit(factor_exposures, stock_returns)
    return reg.coef_
```

## 4. 风险分解

### 总风险分解
$$\sigma^2_{total} = \sigma^2_{factor} + \sigma^2_{specific}$$

### 因子风险
$$\sigma^2_{factor} = \beta' \Sigma_f \beta$$

其中 $\Sigma_f$ 是因子协方差矩阵

### 特异性风险
$$\sigma^2_{specific} = \text{diag}(\Delta)$$

其中 $\Delta$ 是特异性方差矩阵

## 5. 因子风险控制

### 因子中性化
```python
def neutralize_portfolio(weights, factor_exposures):
    """
    使组合对特定因子中性
    """
    portfolio_exposure = weights @ factor_exposures
    # 调整权重使暴露为零
    # ...
    return adjusted_weights
```

### 风险预算
```python
def risk_budget(portfolio_weights, cov_matrix):
    """
    计算各资产的风险贡献
    """
    portfolio_vol = np.sqrt(portfolio_weights @ cov_matrix @ portfolio_weights)
    marginal_contrib = cov_matrix @ portfolio_weights
    risk_contrib = portfolio_weights * marginal_contrib / portfolio_vol
    return risk_contrib
```

## 6. 因子择时

### 估值信号
$$\text{Factor Value} = \frac{E[R_{factor}]}{\sigma(R_{factor})}$$

### 动量信号
$$\text{Factor Momentum} = R_{factor, t-12:t-1}$$

### 宏观信号
| 经济状态 | 推荐因子 |
|----------|----------|
| 经济扩张 | 价值、规模、动量 |
| 经济衰退 | 质量、低波动、防御 |
| 通胀上升 | 大宗商品、TIPS |
| 通胀下降 | 长期债券、成长股 |

## 7. 实际应用

### 因子暴露监控
```python
def monitor_factor_exposures(portfolio, factor_model):
    """
    监控组合的因子暴露
    """
    exposures = {}
    for factor in factor_model.factors:
        exposures[factor] = portfolio.get_exposure(factor)
    return exposures
```

### 风险归因
```python
def risk_attribution(portfolio, factor_model):
    """
    风险归因
    """
    total_risk = portfolio.volatility
    factor_risk = portfolio.factor_risk
    specific_risk = portfolio.specific_risk

    return {
        'total_risk': total_risk,
        'factor_risk_pct': factor_risk / total_risk,
        'specific_risk_pct': specific_risk / total_risk,
        'factor_contributions': portfolio.factor_risk_contributions
    }
```

## 8. 注意事项

| 问题 | 说明 |
|------|------|
| 因子拥挤 | 过多人使用同一因子 |
| 因子时变 | 因子效果随时间变化 |
| 模型风险 | 因子模型可能不准确 |
| 数据挖掘 | 过度拟合历史数据 |
| 相关性突变 | 危机时相关性上升 |
