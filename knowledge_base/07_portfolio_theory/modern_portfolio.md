# 现代投资组合理论

## 1. Markowitz 均值-方差框架

### 基本假设
1. 投资者只关心期望收益和方差
2. 投资者是风险厌恶的
3. 所有投资者在同一投资期
4. 资产无限可分

### 优化问题
$$\min_w \quad w' \Sigma w$$
$$s.t. \quad w' \mu = \mu_p$$
$$\quad \quad w' \mathbf{1} = 1$$

其中：
- $w$：权重向量
- $\Sigma$：协方差矩阵
- $\mu$：期望收益向量
- $\mu_p$：目标收益

### 有效前沿
```python
import numpy as np
from scipy.optimize import minimize

def efficient_frontier(mu, sigma, n_portfolios=100):
    """
    计算有效前沿
    """
    n_assets = len(mu)
    results = np.zeros((3, n_portfolios))

    for i in range(n_portfolios):
        target_return = np.linspace(mu.min(), mu.max(), n_portfolios)[i]

        def portfolio_volatility(w):
            return np.sqrt(w @ sigma @ w)

        constraints = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1},
            {'type': 'eq', 'fun': lambda w: w @ mu - target_return}
        ]
        bounds = tuple((0, 1) for _ in range(n_assets))

        result = minimize(portfolio_volatility, np.ones(n_assets)/n_assets,
                         method='SLSQP', bounds=bounds, constraints=constraints)

        results[0, i] = result.fun
        results[1, i] = target_return
        results[2, i] = target_return / result.fun  # Sharpe ratio

    return results
```

## 2. 最小方差组合

### 问题
$$\min_w \quad w' \Sigma w$$
$$s.t. \quad w' \mathbf{1} = 1$$

### 解析解
$$w_{mv} = \frac{\Sigma^{-1} \mathbf{1}}{\mathbf{1}' \Sigma^{-1} \mathbf{1}}$$

### 实现
```python
def min_variance_portfolio(cov_matrix):
    """
    最小方差组合
    """
    n = len(cov_matrix)
    inv_cov = np.linalg.inv(cov_matrix)
    w = inv_cov @ np.ones(n) / (np.ones(n) @ inv_cov @ np.ones(n))
    return w
```

## 3. 最大 Sharpe 比率组合

### 问题
$$\max_w \quad \frac{w' \mu - r_f}{\sqrt{w' \Sigma w}}$$
$$s.t. \quad w' \mathbf{1} = 1$$

### 解析解
$$w_{tangency} = \frac{\Sigma^{-1}(\mu - r_f \mathbf{1})}{\mathbf{1}' \Sigma^{-1}(\mu - r_f \mathbf{1})}$$

### 实现
```python
def max_sharpe_portfolio(mu, cov_matrix, risk_free_rate=0.02):
    """
    最大 Sharpe 比率组合
    """
    n = len(mu)
    excess_returns = mu - risk_free_rate
    inv_cov = np.linalg.inv(cov_matrix)
    w = inv_cov @ excess_returns / (np.ones(n) @ inv_cov @ excess_returns)
    return w
```

## 4. Black-Litterman 模型

### 基本思想
结合市场均衡收益与投资者观点

### 步骤

**1. 市场均衡收益**
$$\Pi = \delta \Sigma w_{mkt}$$

其中 $\delta$ 是风险厌恶系数

**2. 投资者观点**
$$P \mu = Q + \epsilon$$

其中 $P$ 是观点矩阵，$Q$ 是观点收益

**3. 后验收益**
$$E[\mu] = [(\tau \Sigma)^{-1} + P' \Omega^{-1} P]^{-1} [(\tau \Sigma)^{-1} \Pi + P' \Omega^{-1} Q]$$

### 实现
```python
def black_litterman(mu_mkt, cov_matrix, P, Q, omega, tau=0.05, delta=2.5):
    """
    Black-Litterman 模型
    """
    n = len(mu_mkt)

    # 市场均衡收益
    Pi = delta * cov_matrix @ mu_mkt

    # 后验收益
    tau_cov = tau * cov_matrix
    inv_tau_cov = np.linalg.inv(tau_cov)
    inv_omega = np.linalg.inv(omega)

    posterior_cov = np.linalg.inv(inv_tau_cov + P.T @ inv_omega @ P)
    posterior_mu = posterior_cov @ (inv_tau_cov @ Pi + P.T @ inv_omega @ Q)

    return posterior_mu, posterior_cov
```

## 5. Robust 优化

### 参数不确定性
- **Box 不确定性**：$\mu \in [\mu - \Delta, \mu + \Delta]$
- **椭球不确定性**：$(\mu - \mu_0)' \Sigma_\mu^{-1} (\mu - \mu_0) \leq \kappa^2$

### 鲁棒优化问题
$$\max_w \min_{\mu \in U} \quad w' \mu - \lambda w' \Sigma w$$

### 实现
```python
def robust_portfolio(mu, cov_matrix, uncertainty_set, lambda_risk=1):
    """
    鲁棒优化组合
    """
    from scipy.optimize import minimize

    def robust_objective(w):
        # 最坏情况收益
        worst_case_return = min(w @ mu_scenario for mu_scenario in uncertainty_set)
        return -(w @ mu - lambda_risk * w @ cov_matrix @ w)

    constraints = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}
    result = minimize(robust_objective, np.ones(len(mu))/len(mu),
                     constraints=constraints, method='SLSQP')
    return result.x
```

## 6. 交易成本考虑

### 换手率约束
$$\sum_{i=1}^n |w_i - w_i^{prev}| \leq T_{max}$$

### 二次交易成本
$$\text{Cost} = \sum_{i=1}^n c_i |w_i - w_i^{prev}| + \sum_{i=1}^n d_i (w_i - w_i^{prev})^2$$

### 实现
```python
def portfolio_with_turnover(current_weights, target_weights, max_turnover=0.3):
    """
    带换手率约束的组合优化
    """
    turnover = np.sum(np.abs(target_weights - current_weights))
    if turnover > max_turnover:
        # 缩减调整幅度
        adjustment = max_turnover / turnover
        target_weights = current_weights + adjustment * (target_weights - current_weights)
    return target_weights
```

## 7. 实际应用

### 再平衡策略
| 策略 | 触发条件 | 优点 | 缺点 |
|------|----------|------|------|
| 定期再平衡 | 固定时间 | 简单 | 可能过频 |
| 阈值再平衡 | 偏离超过阈值 | 成本低 | 可能滞后 |
| 比例再平衡 | 偏离比例 | 平衡 | 复杂 |

### 误差度量
$$\text{Tracking Error} = \sqrt{(w_p - w_b)' \Sigma (w_p - w_b)}$$

### 风格暴露
```python
def style_exposures(weights, style_factors):
    """
    计算组合的风格暴露
    """
    exposures = {}
    for factor_name, factor_values in style_factors.items():
        exposures[factor_name] = weights @ factor_values
    return exposures
```

## 8. 局限性

| 局限 | 说明 |
|------|------|
| 参数敏感 | 对输入参数高度敏感 |
| 正态假设 | 假设收益正态分布 |
| 单期模型 | 不考虑动态调整 |
| 估计误差 | 协方差矩阵估计困难 |
| 尾部风险 | 不捕捉极端损失 |
