# Black-Litterman 模型

## 1. 模型背景

### Markowitz 模型的问题
- 对输入参数（期望收益）高度敏感
- 产生极端的多空头寸
- 缺乏对投资者观点的整合

### Black-Litterman 的优势
- 结合市场均衡与个人观点
- 产生更稳定的组合
- 允许表达相对和绝对观点

## 2. 模型推导

### 步骤 1：隐含均衡收益

$$\Pi = \delta \Sigma w_{mkt}$$

其中：
- $\Pi$：隐含均衡收益向量
- $\delta$：风险厌恶系数（通常 2.5-3.5）
- $\Sigma$：协方差矩阵
- $w_{mkt}$：市场组合权重（如市值加权）

### 步骤 2：投资者观点

$$P \mu = Q + \epsilon$$

- $P$：$K \times N$ 观点矩阵（$K$ 个观点，$N$ 个资产）
- $Q$：$K \times 1$ 观点收益向量
- $\epsilon \sim N(0, \Omega)$：观点不确定性

**观点类型**：

| 类型 | P 矩阵 | Q | 含义 |
|------|--------|---|------|
| 绝对观点 | $[0, \ldots, 1, \ldots, 0]$ | $q$ | 资产 i 收益为 q% |
| 相对观点 | $[0, \ldots, 1, \ldots, -1, \ldots, 0]$ | $q$ | 资产 i 比资产 j 高 q% |

### 步骤 3：不确定性矩阵

**Idzorek 方法**：
$$\Omega_{kk} = \frac{1}{C} \cdot P_k \Sigma P_k'$$

其中 $C$ 是置信度参数（0-1）

### 步骤 4：后验收益

$$E[\mu] = [(\tau \Sigma)^{-1} + P' \Omega^{-1} P]^{-1} [(\tau \Sigma)^{-1} \Pi + P' \Omega^{-1} Q]$$

$$\text{Var}[\mu] = [(\tau \Sigma)^{-1} + P' \Omega^{-1} P]^{-1}$$

其中 $\tau$ 是标量（通常 0.01-0.05）

## 3. 实现

### 基础实现
```python
import numpy as np

class BlackLitterman:
    def __init__(self, cov_matrix, market_weights, risk_aversion=2.5, tau=0.05):
        self.Sigma = cov_matrix
        self.w_mkt = market_weights
        self.delta = risk_aversion
        self.tau = tau

    def implied_returns(self):
        """计算隐含均衡收益"""
        return self.delta * self.Sigma @ self.w_mkt

    def posterior(self, P, Q, omega):
        """计算后验收益"""
        tau_Sigma = self.tau * self.Sigma
        inv_tau_Sigma = np.linalg.inv(tau_Sigma)
        inv_omega = np.linalg.inv(omega)

        posterior_cov = np.linalg.inv(inv_tau_Sigma + P.T @ inv_omega @ P)
        posterior_mu = posterior_cov @ (
            inv_tau_Sigma @ self.implied_returns() +
            P.T @ inv_omega @ Q
        )

        return posterior_mu, posterior_cov
```

### 完整流程
```python
def black_litterman_portfolio(market_data, views, confidence):
    """
    Black-Litterman 组合优化
    """
    # 1. 估计协方差矩阵
    cov_matrix = estimate_covariance(market_data)

    # 2. 市场组合权重
    market_weights = market_data['market_cap'] / market_data['market_cap'].sum()

    # 3. 初始化 BL 模型
    bl = BlackLitterman(cov_matrix, market_weights)

    # 4. 构建观点矩阵
    P, Q = build_view_matrix(views)

    # 5. 不确定性矩阵
    omega = build_uncertainty(P, cov_matrix, confidence)

    # 6. 后验收益
    posterior_mu, posterior_cov = bl.posterior(P, Q, omega)

    # 7. 优化组合
    from scipy.optimize import minimize
    n = len(posterior_mu)

    def portfolio_volatility(w):
        return np.sqrt(w @ posterior_cov @ w)

    def neg_sharpe(w):
        return -(w @ posterior_mu - 0.02) / portfolio_volatility(w)

    constraints = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}
    result = minimize(neg_sharpe, np.ones(n)/n, constraints=constraints)

    return result.x, posterior_mu
```

## 4. 观点构建

### 绝对观点
```python
# 股票 A 年化收益 12%
P = np.array([[1, 0, 0, 0]])  # 只关注股票 A
Q = np.array([0.12])
```

### 相对观点
```python
# 股票 A 比股票 B 高 5%
P = np.array([[1, -1, 0, 0]])  # A - B
Q = np.array([0.05])
```

### 多个观点
```python
# 观点 1: A 绝对收益 12%
# 观点 2: B 比 C 高 3%
# 观点 3: D 绝对收益 8%
P = np.array([
    [1, 0, 0, 0],      # 观点 1
    [0, 1, -1, 0],     # 观点 2
    [0, 0, 0, 1]       # 观点 3
])
Q = np.array([0.12, 0.03, 0.08])
```

## 5. 不确定性设定

### 置信度映射
| 置信度 | 含义 | Omega 缩放 |
|--------|------|------------|
| 100% | 完全确定 | 0.01 |
| 50% | 中等确定 | 0.5 |
| 10% | 低确定 | 5.0 |

### 实现
```python
def idzorek_uncertainty(P, cov_matrix, confidence_scores):
    """
    Idzorek 不确定性矩阵
    """
    K = P.shape[0]
    omega = np.zeros((K, K))

    for k in range(K):
        # 观点方差
        view_var = P[k] @ cov_matrix @ P[k].T

        # 置信度调整
        confidence = confidence_scores[k]
        omega[k, k] = view_var / (1 - confidence) * confidence

    return omega
```

## 6. 参数选择

### 风险厌恶系数 δ
| 值 | 含义 | 适用场景 |
|----|------|----------|
| 1.0 | 低风险厌恶 | 进取型投资者 |
| 2.5 | 中等 | 一般投资者 |
| 5.0 | 高风险厌恶 | 保守型投资者 |

### Tau 参数
| 值 | 含义 | 效果 |
|----|------|------|
| 0.01 | 低不确定性 | 后验接近均衡 |
| 0.05 | 中等 | 常用 |
| 0.10 | 高不确定性 | 后验接近观点 |

## 7. 扩展

### 动态 Black-Litterman
- 时变协方差矩阵
- 观点强度随时间衰减
- 市场状态转换

### 多期 Black-Litterman
- 考虑再平衡
- 交易成本
- 税收

### 因子 Black-Litterman
- 观点基于因子而非个股
- 降低维度
- 提高稳定性

## 8. 实际应用

### 资产配置
```python
def strategic_asset_allocation(bl_model, economic_views):
    """
    战略资产配置
    """
    # 构建宏观观点
    P, Q = build_macro_views(economic_views)

    # 运行 BL 模型
    weights = bl_model.optimize(P, Q)

    return weights
```

### 行业配置
```python
def sector_allocation(sector_views):
    """
    行业配置
    """
    # 行业观点
    views = [
        {'type': 'relative', 'long': 'Technology', 'short': 'Utilities', 'return': 0.05},
        {'type': 'absolute', 'asset': 'Healthcare', 'return': 0.10}
    ]

    return black_litterman_portfolio(sector_data, views)
```

## 9. 注意事项

| 问题 | 说明 |
|------|------|
| 观点质量 | 观点的准确性直接影响结果 |
| 参数敏感性 | δ, τ, Ω 的选择影响结果 |
| 计算复杂 | 需要矩阵求逆 |
| 数据需求 | 需要可靠的协方差估计 |
