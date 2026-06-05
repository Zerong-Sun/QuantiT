# 风险平价

## 1. 基本概念

### 传统等权重的问题
- 等权重组合在风险贡献上不平等
- 高波动资产主导组合风险

### 风险平价的目标
使每个资产对组合总风险的贡献相等

### 风险贡献定义
$$RC_i = w_i \frac{\partial \sigma_p}{\partial w_i} = w_i \frac{(\Sigma w)_i}{\sigma_p}$$

其中：
- $RC_i$：资产 i 的风险贡献
- $\sigma_p$：组合波动率
- $(\Sigma w)_i$：组合收益对资产 i 的边际贡献

## 2. 数学框架

### 总风险分解
$$\sigma_p^2 = \sum_{i=1}^n \sum_{j=1}^n w_i w_j \sigma_{ij} = w' \Sigma w$$

### 风险贡献
$$RC_i = w_i (\Sigma w)_i / \sigma_p$$

### 风险平价条件
$$RC_1 = RC_2 = \cdots = RC_n = \sigma_p / n$$

## 3. 优化问题

### 基本形式
$$\min_w \sum_{i=1}^n \sum_{j=1}^n \left(\frac{RC_i}{\sigma_p} - \frac{RC_j}{\sigma_p}\right)^2$$
$$s.t. \quad w' \mathbf{1} = 1$$
$$\quad \quad w \geq 0$$

### 目标函数（偏差平方和）
$$\min_w \sum_{i=1}^n \left(w_i \frac{(\Sigma w)_i}{w' \Sigma w} - \frac{1}{n}\right)^2$$

## 4. 求解方法

### Spinu (2013) 算法
```python
def risk_parity(cov_matrix, risk_budget=None):
    """
    风险平价组合求解
    """
    n = len(cov_matrix)

    if risk_budget is None:
        risk_budget = np.ones(n) / n

    def objective(w):
        portfolio_vol = np.sqrt(w @ cov_matrix @ w)
        marginal_contrib = cov_matrix @ w
        risk_contrib = w * marginal_contrib / portfolio_vol

        target_contrib = risk_budget * portfolio_vol
        return np.sum((risk_contrib - target_contrib)**2)

    constraints = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}
    bounds = tuple((0, 1) for _ in range(n))

    result = minimize(objective, np.ones(n)/n, method='SLSQP',
                     bounds=bounds, constraints=constraints)
    return result.x
```

### 梯度下降法
```python
def risk_parity_gradient(cov_matrix, risk_budget, lr=0.01, max_iter=1000):
    """
    梯度下降求解风险平价
    """
    n = len(cov_matrix)
    w = np.ones(n) / n

    for _ in range(max_iter):
        portfolio_vol = np.sqrt(w @ cov_matrix @ w)
        marginal_contrib = cov_matrix @ w
        risk_contrib = w * marginal_contrib / portfolio_vol

        target_contrib = risk_budget * portfolio_vol
        gradient = 2 * (risk_contrib - target_contrib)

        w = w - lr * gradient
        w = np.maximum(w, 0)  # 非负约束
        w = w / np.sum(w)  # 归一化

    return w
```

## 5. 逆方差加权

### 简化版本
$$w_i = \frac{1/\sigma_i^2}{\sum_{j=1}^n 1/\sigma_j^2}$$

### 实现
```python
def inverse_variance_weights(cov_matrix):
    """
    逆方差加权
    """
    variances = np.diag(cov_matrix)
    inv_var = 1 / variances
    return inv_var / np.sum(inv_var)
```

## 6. 层次风险平价（HRP）

### 基本步骤
1. 基于相关性进行层次聚类
2. 通过准对角化重排协方差矩阵
3. 递归二分配置权重

### 实现
```python
import scipy.cluster.hierarchy as sch

def hierarchical_risk_parity(cov_matrix, returns):
    """
    层次风险平价
    """
    # 计算相关性距离
    corr = returns.corr()
    dist = np.sqrt(0.5 * (1 - corr))
    linkage = sch.linkage(dist, method='single')

    # 准对角化
    quasi_diag = quasi_diagonal(linkage)

    # 递归二分
    w = recursive_bisection(cov_matrix, quasi_diag)

    return w

def recursive_bisection(cov_matrix, sorted_indices):
    """递归二分配置"""
    if len(sorted_indices) == 1:
        return {sorted_indices[0]: 1}

    # 分成两组
    mid = len(sorted_indices) // 2
    left = sorted_indices[:mid]
    right = sorted_indices[mid:]

    # 计算各组方差
    var_left = compute_cluster_variance(cov_matrix, left)
    var_right = compute_cluster_variance(cov_matrix, right)

    # 配置权重
    alpha = 1 - var_left / (var_left + var_right)

    # 递归
    weights = {}
    weights.update({k: alpha * v for k, v in recursive_bisection(cov_matrix, left).items()})
    weights.update({k: (1-alpha) * v for k, v in recursive_bisection(cov_matrix, right).items()})

    return weights
```

## 7. 等风险贡献（ERC）

### 与风险平价的关系
- **风险平价**：所有资产风险贡献相等
- **ERC**：风险贡献与目标比例匹配

### 目标风险预算
```python
def equal_risk_contribution(cov_matrix, target_risk_budget=None):
    """
    等风险贡献组合
    """
    n = len(cov_matrix)

    if target_risk_budget is None:
        target_risk_budget = np.ones(n) / n

    def objective(w):
        portfolio_vol = np.sqrt(w @ cov_matrix @ w)
        marginal_contrib = cov_matrix @ w
        risk_contrib = w * marginal_contrib / portfolio_vol

        # 风险贡献比例
        risk_contrib_pct = risk_contrib / portfolio_vol

        # 与目标的偏差
        return np.sum((risk_contrib_pct - target_risk_budget)**2)

    constraints = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}
    bounds = tuple((0, 1) for _ in range(n))

    result = minimize(objective, np.ones(n)/n, method='SLSQP',
                     bounds=bounds, constraints=constraints)
    return result.x
```

## 8. 实际应用

### 资产类别配置
```python
def asset_class_allocation(asset_returns, asset_classes):
    """
    基于风险平价的资产类别配置
    """
    # 计算协方差矩阵
    cov_matrix = asset_returns.cov() * 252

    # 风险平价权重
    weights = risk_parity(cov_matrix.values)

    # 转换为资产类别权重
    class_weights = {}
    for i, asset_class in enumerate(asset_classes):
        class_weights[asset_class] = weights[i]

    return class_weights
```

### 因子风险平价
```python
def factor_risk_parity(factor_returns, factor_exposures):
    """
    因子风险平价
    """
    # 因子协方差
    factor_cov = factor_returns.cov()

    # 因子风险平价权重
    factor_weights = risk_parity(factor_cov.values)

    # 转换为股票权重
    stock_weights = factor_exposures @ factor_weights

    return stock_weights / np.sum(stock_weights)
```

## 9. 优缺点

### 优点
| 优点 | 说明 |
|------|------|
| 分散化 | 真正的风险分散 |
| 稳定性 | 不依赖收益预测 |
| 透明性 | 逻辑清晰易理解 |
| 低成本 | 换手率较低 |

### 缺点
| 缺点 | 说明 |
|------|------|
| 协方差敏感 | 依赖协方差估计 |
| 无收益预期 | 不考虑预期收益 |
| 杠杆需求 | 可能需要杠杆达到目标风险 |
| 尾部风险 | 不捕捉极端风险 |

## 10. 与传统方法比较

| 方法 | 目标 | 依赖 | 风险分散 |
|------|------|------|----------|
| 等权重 | 简单 | 无 | 低 |
| 市值加权 | 代表市场 | 无 | 低 |
| 均值方差 | 最优风险收益 | 收益预测 | 中 |
| 风险平价 | 等风险贡献 | 协方差 | 高 |
