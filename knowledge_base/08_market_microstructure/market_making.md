# 做市策略

## 1. 做市基础

### 盈利来源
$$\text{Profit} = \text{Spread} \times \text{Volume} - \text{Adverse Selection} - \text{Inventory Cost}$$

### 做市商角色
- 提供流动性
- 缩小买卖价差
- 促进价格发现
- 承担库存风险

## 2. Avellaneda-Stoikov 模型

### 最优报价
$$\text{Optimal Bid} = S - \frac{1}{2}\gamma\sigma^2 T - \frac{1}{\gamma}\ln\left(1 + \frac{\gamma}{\kappa}\right)$$
$$\text{Optimal Ask} = S + \frac{1}{2}\gamma\sigma^2 T + \frac{1}{\gamma}\ln\left(1 + \frac{\gamma}{\kappa}\right)$$

### 参数含义
| 参数 | 含义 | 影响 |
|------|------|------|
| $\gamma$ | 风险厌恶系数 | 越大价差越大 |
| $\sigma$ | 波动率 | 越大价差越大 |
| $\kappa$ | 订单到达率 | 越高价差越小 |

### 实现
```python
class AvellanedaStoikov:
    def __init__(self, gamma, sigma, kappa):
        self.gamma = gamma
        self.sigma = sigma
        self.kappa = kappa

    def optimal_quotes(self, S, T, q=0):
        reservation = S - q * self.gamma * self.sigma**2 * T
        spread = (self.gamma * self.sigma**2 * T +
                 (2/self.gamma) * np.log(1 + self.gamma/self.kappa))
        bid = reservation - spread/2
        ask = reservation + spread/2
        return bid, ask
```

## 3. 库存管理

### 库存控制
```python
class InventoryController:
    def __init__(self, target_inventory=0, max_inventory=1000):
        self.target = target_inventory
        self.max = max_inventory

    def adjust_quotes(self, bid, ask, current_inventory):
        inventory_skew = (current_inventory - self.target) / self.max
        adjusted_bid = bid * (1 - 0.1 * inventory_skew)
        adjusted_ask = ask * (1 + 0.1 * inventory_skew)
        return adjusted_bid, adjusted_ask
```

## 4. 风险管理

### 止损规则
```python
def check_stop_loss(daily_pnl, max_loss):
    if daily_pnl < -max_loss:
        return True
    return False
```

### 风险限额
| 风险类型 | 限额 |
|----------|------|
| 单日亏损 | -0.5% |
| 库存限额 | ±1000手 |
| 价差限额 | 最大 0.5% |

## 5. 评估指标

| 指标 | 含义 |
|------|------|
| 日均收益 | 盈利能力 |
| 夏普比率 | 风险调整收益 |
| 最大回撤 | 下行风险 |
| 成交量份额 | 市场参与度 |
| 报价命中率 | 执行效率 |
