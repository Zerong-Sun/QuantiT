# 因子动物园

## 1. 因子发现的历史

### 里程碑研究
| 年份 | 研究 | 发现 |
|------|------|------|
| 1976 | Black, Jensen, Scholes | CAPM 实证检验 |
| 1981 | Banz | 规模效应 |
| 1983 | Stattman | 价值效应 |
| 1987 | De Bondt, Thaler | 过度反应/反转 |
| 1990 | Jegadeesh, Titman | 动量效应 |
| 1992 | Fama, French | 三因子模型 |
| 1996 | Carhart | 四因子模型（+动量） |
| 2015 | Fama, French | 五因子模型 |

### 因子数量增长
- 1990年代：约 10 个主要因子
- 2000年代：约 100 个因子
- 2010年代：超过 400 个因子
- 2020年代：超过 600+ 个因子

## 2. 主要因子分类

### 经典因子（已被广泛验证）

#### 价值因子
| 指标 | 公式 | 经济逻辑 |
|------|------|----------|
| B/M | 账面值/市值 | 困境公司被低估 |
| E/P | 盈利/市值 | 增长预期修正 |
| CF/P | 现金流/市值 | 真实盈利能力 |
| D/P | 股息/市值 | 收入需求 |

#### 规模因子
- 小公司溢价
- 分析师覆盖不足
- 流动性较差

#### 动量因子
- 短期反转（1个月）
- 中期动量（3-12个月）
- 长期反转（3-5年）

#### 质量因子
- ROE、Gross Profitability
- 低应计项目
- 盈利稳定性

#### 低波动因子
- 低波动股票风险调整后收益更高
- 与 CAPM 矛盾

### 新兴因子

#### 情绪因子
- 分析师情绪变化
- 社交媒体情绪
- 新闻情绪

#### 技术因子
- 价格模式
- 订单簿不平衡
- 高频数据特征

#### ESG 因子
- 环境（E）：碳排放、能源效率
- 社会（S）：员工满意度、多元化
- 治理（G）：董事会独立性、薪酬结构

## 3. 因子动物园问题

### 过度拟合风险
**Harvey, Liu & Zhu (2016)**：
- 发现 316 个因子
- t 统计量阈值应提高到 3.0+（而非 1.96）
- 建议进行多重检验校正

### 数据窥探（Data Snooping）
- 在大量资产上测试大量因子
- 即使随机策略也可能产生"显著"结果
- **White's Reality Check**: Adjusted p-value

### 发表偏差
- 显著结果更容易发表
- 阴性结果被忽略
- 导致因子效果被高估

## 4. 因子验证方法

### 样本外测试
```
时间轴：
|-----训练期-----|-----测试期-----|
    (70%)            (30%)
```

### Walk-Forward 优化
```python
def walk_forward(data, window, step):
    """滚动窗口验证"""
    results = []
    for i in range(0, len(data) - window - step, step):
        train = data[i:i+window]
        test = data[i+window:i+window+step]
        model = train_model(train)
        results.append(evaluate(model, test))
    return results
```

### 多重检验校正
- **Bonferroni**: $p_{adj} = p \times m$
- **Holm-Bonferroni**: 逐步校正
- **Benjamini-Hochberg**: 控制 FDR

### Bootstrap 方法
```python
def bootstrap_factor_test(returns, n_bootstrap=1000):
    """Bootstrap 检验因子显著性"""
    observed_sharpe = returns.mean() / returns.std()
    null_sharpees = []
    for _ in range(n_bootstrap):
        shuffled = np.random.permutation(returns)
        null_sharpees.append(shuffled.mean() / shuffled.std())
    p_value = np.mean([s >= observed_sharpe for s in null_sharpees])
    return p_value
```

## 5. 因子聚类

### 因子层级
```
市场因子
├── 价值类
│   ├── B/M
│   ├── E/P
│   └── CF/P
├── 成长类
│   ├── 盈利增长
│   └── 销售增长
├── 质量类
│   ├── ROE
│   ├── 盈利稳定性
│   └── 低应计
└── 动量类
    ├── 横截面动量
    └── 时间序列动量
```

## 6. 因子生命周期

| 阶段 | 特征 | 应对 |
|------|------|------|
| 发现阶段 | 学术研究发现异象 | 深入研究 |
| 传播阶段 | 论文发表、媒体关注 | 跟踪验证 |
| 拥挤阶段 | 大量资本涌入 | 控制风险 |
| 崩溃阶段 | 因子拥挤导致踩踏 | 及时退出 |
| 稳定阶段 | 拥挤程度降低 | 重新配置 |

## 7. 实践建议

### 因子选择准则
1. **样本外显著**：至少 30% 数据未参与训练
2. **经济学意义**：有合理的风险补偿或行为解释
3. **跨市场有效**：在不同国家/地区有效
4. **低相关性**：与现有因子相关性 < 0.5
5. **高容量**：可管理较大规模资金

### 组合构建
- **因子分散**：至少 5-10 个独立因子
- **风险控制**：单因子暴露 < 30%
- **再平衡**：月度/季度
- **成本控制**：换手率 < 100%/年
