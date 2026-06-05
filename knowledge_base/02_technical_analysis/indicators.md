# 技术指标

## 1. 趋势指标

### 移动平均线（MA）

#### 简单移动平均（SMA）
$$SMA_t = \frac{1}{n} \sum_{i=0}^{n-1} P_{t-i}$$

#### 指数移动平均（EMA）
$$EMA_t = \alpha \cdot P_t + (1-\alpha) \cdot EMA_{t-1}$$
其中 $\alpha = \frac{2}{n+1}$ 是平滑因子。

**特性比较**：
| 特性 | SMA | EMA |
|------|-----|-----|
| 权重分配 | 等权重 | 指数衰减 |
| 对新数据反应 | 慢 | 快 |
| 滞后性 | 高 | 低 |
| 适用场景 | 长期趋势 | 短期信号 |

### MACD（Moving Average Convergence Divergence）
$$MACD = EMA_{12} - EMA_{26}$$
$$Signal = EMA_9(MACD)$$
$$Histogram = MACD - Signal$$

**交易信号**：
- 金叉：MACD 上穿 Signal → 买入
- 死叉：MACD 下穿 Signal → 卖出
- 柱状图背离：趋势反转信号

### ADX（Average Directional Index）
$$ADX = \frac{1}{n} \sum_{i=0}^{n-1} DX_i$$
其中 $DX = \frac{+DI - |-DI|}{+DI + |-DI|}$

**解读**：
- ADX > 25：强趋势
- ADX < 20：无趋势/震荡
- +DI > -DI：上升趋势；-DI > +DI：下降趋势

## 2. 动量指标

### RSI（Relative Strength Index）
$$RSI = 100 - \frac{100}{1 + RS}$$
$$RS = \frac{\text{平均涨幅}}{\text{平均跌幅}}$$

**交易信号**：
- RSI > 70：超买（可能回调）
- RSI < 30：超卖（可能反弹）
- 背离：价格创新高但 RSI 未创新高 → 顶背离

### Stochastic Oscillator
$$\%K = \frac{C - L_n}{H_n - L_n} \times 100$$
$$\%D = SMA_3(\%K)$$

其中 $C$ 是当前收盘价，$H_n, L_n$ 是 n 日最高价和最低价。

### CCI（Commodity Channel Index）
$$CCI = \frac{TP - SMA(TP)}{0.015 \times MD}$$
$$TP = \frac{H + L + C}{3}$$

## 3. 波动率指标

### ATR（Average True Range）
$$TR = \max(H-L, |H-C_{prev}|, |L-C_{prev}|)$$
$$ATR = SMA_n(TR)$$

**应用**：
- 止损设置：$Stop = Entry \pm k \times ATR$
- 仓位管理：$Position Size = \frac{Account \times Risk\%}{ATR \times Point Value}$
- 波动率归一化

### Bollinger Bands
$$Middle = SMA_{20}$$
$$Upper = Middle + 2\sigma$$
$$Lower = Middle - 2\sigma$$

**交易信号**：
- 价格触及上轨：超买
- 价格触及下轨：超卖
- 带宽收窄后扩张：波动率突破

### Keltner Channel
$$Middle = EMA_{20}$$
$$Upper = Middle + 2 \times ATR$$
$$Lower = Middle - 2 \times ATR$$

**与布林带的区别**：用 ATR 替代标准差，对波动率变化更稳定。

## 4. 成交量指标

### OBV（On-Balance Volume）
$$OBV_t = OBV_{t-1} + \begin{cases} V_t & \text{if } C_t > C_{t-1} \\ -V_t & \text{if } C_t < C_{t-1} \\ 0 & \text{otherwise} \end{cases}$$

**解读**：OBV 趋势与价格趋势一致 → 趋势确认；不一致 → 可能反转

### VWAP（Volume Weighted Average Price）
$$VWAP = \frac{\sum (TP_i \times V_i)}{\sum V_i}$$

**机构交易基准**：日内交易者常用 VWAP 作为执行基准。

### CMF（Chaikin Money Flow）
$$CMF = \frac{\sum_{i=n}^{} MFI_i}{\sum_{i=n}^{} V_i}$$
$$MFI = [(C-L)-(H-C)]/(H-L) \times V$$

- CMF > 0：买入压力
- CMF < 0：卖出压力

## 5. 指标组合与过滤

### 多时间框架分析
- 月线：确定大趋势方向
- 周线：确定中期趋势
- 日线：寻找入场时机
- 4H/1H：精确入场点

### 指标过滤系统
```
趋势过滤：EMA_50 > EMA_200（上升趋势）
动量确认：RSI 在 40-70 区间（健康回调）
波动率过滤：ATR > 阈值（足够流动性）
成交量确认：Volume > 1.5 × SMA_20(Volume)
```

## 6. 指标的数学本质

### 滤波器视角
技术指标本质上是信号滤波器：
- **低通滤波器**：移动平均（平滑噪声）
- **带通滤波器**：MACD（提取特定频率的趋势）
- **高通滤波器**：RSI 的超买超卖（提取极端值）

### 谱分析
将价格序列分解为不同频率的周期分量，识别主导周期。

## 7. 实战注意事项

| 问题 | 应对策略 |
|------|----------|
| 滞后性 | 结合领先指标（如 RSI）；使用更短周期 |
| 假信号 | 多指标确认；等待回调入场 |
| 震荡市失效 | ADX 过滤；识别市场状态 |
| 过度拟合 | 样本外测试；简单参数 |
| 交易成本 | 考虑滑点、佣金对信号频率的影响 |
