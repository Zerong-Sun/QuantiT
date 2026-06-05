# VaR 模型

## 1. VaR 定义

### 基本概念
Value at Risk (VaR) 衡量在给定置信水平下，未来特定时期内的最大潜在损失。

$$P(L > VaR_{\alpha}) = 1 - \alpha$$

### 示例
- 1-day 95% VaR = $1M
- 含义：有 5% 的概率，明天损失超过 $1M

### 变体
| 类型 | 定义 | 公式 |
|------|------|------|
| 绝对 VaR | 相对于零 | $VaR = -\mu + z_\alpha \sigma$ |
| 相对 VaR | 相对于均值 | $VaR = z_\alpha \sigma$ |

## 2. 参数法

### 正态分布假设
$$VaR_{\alpha} = \mu + z_{\alpha} \sigma$$

其中 $z_{\alpha}$ 是标准正态分位数（95% 对应 1.645）

### t 分布假设
$$VaR_{\alpha} = \mu + t_{\alpha,\nu} \sigma$$

t 分布更好地捕捉厚尾

### 风险因子建模
$$r_t = \sum_{k=1}^K \beta_k f_{k,t} + \epsilon_t$$

其中 $f_{k,t}$ 是风险因子收益率

## 3. 历史模拟法

### 基本步骤
1. 收集历史收益率
2. 排序收益率
3. 找到对应分位数

```python
def historical_var(returns, confidence=0.95, holding_period=1):
    """
    历史模拟法 VaR
    """
    sorted_returns = np.sort(returns)
    index = int((1 - confidence) * len(sorted_returns))
    var_1day = -sorted_returns[index]
    return var_1day * np.sqrt(holding_period)
```

### 优缺点
**优点**：
- 不需要分布假设
- 捕捉非线性风险
- 简单易懂

**缺点**：
- 依赖历史数据
- 假设历史会重演
- 对极端事件估计不准确

## 4. Monte Carlo 模拟

### 基本步骤
1. 建立价格模型
2. 模拟大量路径
3. 计算损益分布
4. 确定 VaR

```python
def monte_carlo_var(prices, confidence=0.95, n_simulations=10000, 
                     holding_period=5):
    """
    Monte Carlo VaR
    """
    # 计算历史参数
    returns = np.log(prices / prices.shift(1)).dropna()
    mu = returns.mean()
    sigma = returns.std()

    # 模拟路径
    simulated_returns = np.random.normal(
        mu, sigma, (n_simulations, holding_period)
    )

    # 计算累积收益
    cumulative_returns = np.sum(simulated_returns, axis=1)

    # 计算 VaR
    var = -np.percentile(cumulative_returns, (1 - confidence) * 100)
    return var
```

### 常用模型
- GBM（几何布朗运动）
- GARCH 模型
- 跳跃扩散模型

## 5. 条件 VaR (CVaR/Expected Shortfall)

### 定义
$$CVaR_{\alpha} = E[L | L > VaR_{\alpha}]$$

CVaR 衡量超过 VaR 时的平均损失

### 计算
```python
def cvar(returns, confidence=0.95):
    """
    条件 VaR (Expected Shortfall)
    """
    var = np.percentile(returns, (1 - confidence) * 100)
    return -np.mean(returns[returns <= var])
```

### 优点
- 一致性风险度量（满足次可加性）
- 更好地捕捉尾部风险
- Basle III 推荐使用

## 6. 回测

### Kupiec 检验
检验 VaR 模型的准确性：

$$LR_{uc} = -2\ln\left[\frac{(1-p)^{T-n} p^n}{(1-\hat{p})^{T-n} \hat{p}^n}\right] \sim \chi^2(1)$$

其中 $p$ 是模型预测的失败率，$\hat{p} = n/T$ 是实际失败率

### Christoffersen 检验
检验失败是否独立：

$$LR_{ind} = -2\ln\left[\frac{p_{12}^{n_{01}+n_{11}} (1-p_{12})^{n_{00}+n_{10}}}{p_1^{n_{01}} (1-p_1)^{n_{00}} p_2^{n_{11}} (1-p_2)^{n_{10}}}\right]$$

### 回测框架
```python
def backtest_var(prices, var_predictions, confidence=0.95):
    """
    VaR 回测
    """
    returns = prices.pct_change().dropna()
    exceptions = returns < -var_predictions

    # 计算失败率
    failure_rate = exceptions.mean()

    # Kupiec 检验
    n_exceptions = exceptions.sum()
    T = len(returns)
    p = 1 - confidence
    p_hat = n_exceptions / T

    lr_uc = -2 * (
        np.log((1-p)**(T-n_exceptions) * p**n_exceptions) -
        np.log((1-p_hat)**(T-n_exceptions) * p_hat**n_exceptions)
    )

    return {
        'failure_rate': failure_rate,
        'n_exceptions': n_exceptions,
        'kupiec_pvalue': 1 - chi2.cdf(lr_uc, 1)
    }
```

## 7. 实际考虑

| 问题 | 说明 |
|------|------|
| 尾部风险 | VaR 可能低估极端损失 |
| 模型风险 | 不同模型给出不同结果 |
| 参数不确定性 | 参数估计有误差 |
| 非流动性 | VaR 假设可以立即平仓 |
| 相关性变化 | 危机时相关性上升 |
| 时变波动率 | 需要动态模型 |

## 8. 监管要求

### Basel III 要求
- 使用 99% VaR
- 10 天持有期
- 乘以 3 作为资本要求
- 推荐使用 CVaR

### 内部模型
- 定期回测
- 压力测试
- 模型验证
