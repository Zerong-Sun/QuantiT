# 执行算法

## 1. 执行目标

### 最小化成本
$$\text{Execution Cost} = \text{Market Impact} + \text{Timing Cost} + \text{Spread Cost}$$

## 2. 基本算法

### TWAP（时间加权平均价格）
```python
def twap(quantity, duration, num_slices):
    slice_size = quantity / num_slices
    interval = duration / num_slices
    orders = []
    for i in range(num_slices):
        orders.append({'time': i * interval, 'quantity': slice_size})
    return orders
```

### VWAP（成交量加权平均价格）
```python
def vwap(quantity, volume_profile):
    total_volume = sum(volume_profile)
    orders = []
    for i, vol in enumerate(volume_profile):
        order_qty = quantity * (vol / total_volume)
        orders.append({'time': i, 'quantity': order_qty})
    return orders
```

### POV（成交量参与率）
```python
def pov(quantity, target_participation, volume_data):
    orders = []
    remaining = quantity
    for period_vol in volume_data:
        order_qty = min(remaining, period_vol * target_participation)
        orders.append({'quantity': order_qty, 'type': 'limit'})
        remaining -= order_qty
        if remaining <= 0:
            break
    return orders
```

## 3. 冲击模型

### Almgren-Chriss 最优轨迹
$$x_t^* = Q \cdot \frac{\sinh(\kappa(T-t))}{\sinh(\kappa T)}$$

### 实现
```python
def optimal_trajectory(Q, T, n_steps, kappa):
    trajectory = []
    for t in range(n_steps + 1):
        tau = T * t / n_steps
        x_t = Q * np.sinh(kappa * (T - tau)) / np.sinh(kappa * T)
        trajectory.append(x_t)
    return trajectory
```

## 4. 算法选择

| 算法 | 适用场景 | 优点 | 缺点 |
|------|----------|------|------|
| TWAP | 小订单 | 简单 | 不考虑市场条件 |
| VWAP | 跟踪基准 | 流动性友好 | 需要历史数据 |
| POV | 大订单 | 控制参与率 | 可能执行不完 |
| IS | 紧急订单 | 最小化差额 | 冲击大 |

## 5. 成本分析

### 交易成本分析（TCA）
```python
def transaction_cost_analysis(trades, benchmark):
    results = []
    for trade in trades:
        shortfall = trade['price'] - benchmark
        spread_cost = trade['spread'] / 2
        market_impact = trade['price'] - trade['arrival_price']
        results.append({
            'total_cost': shortfall,
            'spread_cost': spread_cost,
            'market_impact': market_impact
        })
    return results
```

## 6. 评估指标

| 指标 | 公式 | 含义 |
|------|------|------|
| VWAP 差距 | $(P_{avg} - P_{vwap}) / P_{vwap}$ | 相对基准表现 |
| 实现差额 | $P_{avg} - P_{arrival}$ | 执行质量 |
| 完成率 | Executed / Target | 执行完整性 |
