# Alpha 模型构建

## 1. Alpha 的定义

### 传统定义
$$\alpha_i = R_{i,t} - [R_{f,t} + \beta_{i,t}(R_{m,t} - R_{f,t})]$$

### 广义 Alpha
Alpha 是超过风险因子补偿的超额收益：
$$\text{Alpha} = \text{实际收益} - \text{风险补偿}$$

### Alpha 的来源
1. **信息优势**：私人信息或更快处理公开信息
2. **分析优势**：更好的模型或数据处理能力
3. **执行优势**：更低的交易成本
4. **结构优势**：市场摩擦造成的持续定价偏差

## 2. Alpha 研究流程

### 研究步骤
```
1. 假设生成 → 2. 数据收集 → 3. 特征工程 → 4. 模型构建
→ 5. 回测验证 → 6. 风险分析 → 7. 实盘部署
```

### 假设来源
- 学术文献
- 市场异象
- 交易经验
- 替代数据
- 机器学习发现

## 3. Alpha 因子类型

### 基于价格/成交量
| 因子 | 公式 | 逻辑 |
|------|------|------|
| 短期反转 | 过去 1-5 日收益率 | 过度反应 |
| 中期动量 | 过去 6-12 月收益率 | 反应不足 |
| 波动率 | 收益率标准差 | 波动率溢价 |
| 流动性 | Amihud 指标 | 流动性溢价 |
| 量价背离 | 价格与成交量方向不一致 | 趋势衰竭 |

### 基于基本面
| 因子 | 公式 | 逻辑 |
|------|------|------|
| 盈利质量 | 应计项目/利润 | 盈利持续性 |
| 意外盈余 | (实际EPS - 预期EPS) / 价格 | 盈余公告后漂移 |
| 分析师修正 | 预期EPS变化 | 信息传递 |
| 内部人交易 | 内部人买卖比率 | 信息优势 |

### 基于另类数据
| 数据类型 | Alpha 信号 |
|----------|------------|
| 卫星图像 | 停车场车辆数 → 零售销售 |
| 社交媒体 | 情绪分析 → 需求预测 |
| 信用卡交易 | 消费数据 → 公司业绩 |
| 供应链数据 | 供应商出货 → 客户收入 |
| 专利数据 | 创新能力 → 长期价值 |

## 4. 因子构建方法

### 线性因子
$$\text{Factor}_t = \sum_{i=1}^{N} w_i X_{i,t}$$

### 排序因子（Rank-based）
```python
def rank_factor(series, pct=True):
    """百分位排序因子"""
    if pct:
        return series.rank(pct=True)
    return series.rank()
```

### Z-Score 标准化
$$Z_t = \frac{X_t - \mu_t}{\sigma_t}$$

### 中性化
```python
def neutralize(factor, industry, market_cap):
    """行业中性化 + 市值中性化"""
    from sklearn.linear_model import LinearRegression
    reg = LinearRegression()
    X = pd.get_dummies(industry)
    X['log_mcap'] = np.log(market_cap)
    reg.fit(X, factor)
    return factor - reg.predict(X)  # 残差即中性化因子
```

## 5. Alpha 衰减分析

### 半衰期
$$\text{Alpha}_t = \text{Alpha}_0 \cdot e^{-\lambda t}$$
半衰期 $t_{1/2} = \frac{\ln 2}{\lambda}$

### 信号衰减曲线
```
持有期收益 (HPR)
│
│  ╲
│    ╲
│      ╲____
│           ╲____
│                 ╲____
└────────────────────────→ 持有期
```

### 容量分析
$$\text{Capacity} = \frac{\text{日均成交量} \times \text{参与率}}{\text{换手率要求}}$$

**参与率**：通常 5-20%（取决于市场冲击）

## 6. Alpha 组合

### 因子加权
$$\text{Alpha}_i = \sum_{f} w_f \cdot \text{Factor}_{f,i}$$

### 机器学习组合
- 线性回归
- 随机森林
- 梯度提升树
- 神经网络

### 因子时变权重
$$w_{f,t} = w_{f,t-1} + \eta \cdot \frac{\partial \text{Sharpe}}{\partial w_f}$$

## 7. Alpha 与风险的关系

### 风险调整 Alpha
$$\text{Sharpe Ratio} = \frac{E[\text{Alpha}]}{\sigma(\text{Alpha})}$$

### Alpha 的风险分解
$$\sigma^2(\text{Alpha}) = \underbrace{\sigma^2_{\text{idiosyncratic}}}_{\text{个股风险}} + \underbrace{\sigma^2_{\text{factor}}}_{\text{因子风险}} + \underbrace{\sigma^2_{\text{timing}}}_{\text{择时风险}}$$

### Alpha 的可持续性
| Alpha 来源 | 可持续性 | 容量 |
|------------|----------|------|
| 信息优势 | 低（会扩散） | 低 |
| 执行优势 | 中（技术提升） | 中 |
| 行为偏差 | 高（心理稳定） | 高 |
| 结构摩擦 | 高（监管持续） | 中 |

## 8. 实践建议

### Alpha 研究准则
1. **简单优先**：先测试简单因子
2. **经济学意义**：每个 Alpha 必须有解释
3. **样本外验证**：至少 30% 数据用于验证
4. **交易成本**：扣费后仍有收益
5. **容量评估**：考虑市场冲击

### 常见错误
| 错误 | 后果 | 解决 |
|------|------|------|
| 过拟合 | 样本外失效 | 交叉验证 |
| 前视偏差 | 未来数据泄露 | 严格时间框架 |
| 幸存者偏差 | 高估收益 | 包含退市股票 |
| 忽略成本 | 低估损耗 | 扣除交易成本 |
| 过度交易 | 增加成本 | 降低换手率 |
