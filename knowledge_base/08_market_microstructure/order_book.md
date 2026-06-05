# 订单簿与流动性

## 1. 订单簿结构

### 基本组成
```
卖盘 (Asks)                买盘 (Bids)
─────────────────────────────────────
Price  | Volume            Price  | Volume
─────────────────────────────────────
$10.05 | 500               $10.00 | 800
$10.04 | 1000              $9.99  | 1200
$10.03 | 800               $9.98  | 600
$10.02 | 1500              $9.97  | 2000
$10.01 | 2000              $9.96  | 1500
─────────────────────────────────────
```

### 关键指标
| 指标 | 定义 | 含义 |
|------|------|------|
| Bid-Ask Spread | $P_{ask} - P_{bid}$ | 流动性成本 |
| Mid Price | $(P_{ask} + P_{bid})/2$ | 公允价格 |
| Best Bid/Offer | 最高买价/最低卖价 | 最优执行价格 |
| Depth | 各价位挂单量 | 市场深度 |

## 2. 流动性度量

### 买卖价差
$$\text{Spread} = P_{ask} - P_{bid}$$

### Amihud 非流动性
$$\text{Amihud} = \frac{1}{T} \sum_{t=1}^T \frac{|r_t|}{Volume_t}$$

### Roll 模型
$$\text{Spread} = 2\sqrt{-\text{Cov}(r_t, r_{t-1})}$$

## 3. 市场冲击模型

### 平方根模型（Almgren-Chriss）
$$\text{Impact} = \eta \cdot \sigma \cdot \sqrt{\frac{Q}{V}} + \gamma \cdot \frac{Q}{V}$$

- $\eta \sigma \sqrt{Q/V}$：暂时冲击
- $\gamma Q/V$：永久冲击

### 学术模型

| 模型 | 公式 | 特点 |
|------|------|------|
| Kyle (1985) | $\Delta P = \lambda \cdot Q$ | 线性冲击 |
| Glosten-Milgrom | 做市商学习 | 信息不对称 |
| Hasbrouck | 信息份额 | 价格发现 |

## 4. 订单类型

### 基本订单类型
| 类型 | 描述 | 特点 |
|------|------|------|
| Market Order | 市价单 | 立即执行，价格不确定 |
| Limit Order | 限价单 | 价格确定，可能不执行 |
| Stop Order | 止损单 | 触发后变市价单 |
| IOC | 立即成交否则取消 | 部分成交 |
| FOK | 全部成交否则取消 | 全部或无 |

## 5. 高频数据特征

### 微观结构噪声
- 买卖价差反弹
- 离散价格变动
- 非同步交易

### 已实现波动率
$$RV = \sum_{i=1}^n r_i^2$$

## 6. 订单簿分析

### 订单簿不平衡
$$\text{OBI} = \frac{V_{bid} - V_{ask}}{V_{bid} + V_{ask}}$$

### VPIN（知情交易概率）
$$VPIN = \frac{|V^+ - V^-|}{V}$$

## 7. 数据处理

### 构建订单簿
```python
def build_orderbook(ticks, depth=10):
    bids = ticks[ticks['side'] == 'buy'].groupby('price')['volume'].sum()
    asks = ticks[ticks['side'] == 'sell'].groupby('price')['volume'].sum()
    bids = bids.sort_index(ascending=False).head(depth)
    asks = asks.sort_index().head(depth)
    return {'bids': bids, 'asks': asks}
```
