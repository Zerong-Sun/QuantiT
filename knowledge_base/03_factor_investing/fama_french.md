# Fama-French 多因子模型

## 1. 三因子模型 (1993)

### 模型定义
$$R_{i,t} - R_{f,t} = \alpha_i + \beta_{i,MKT} MKT_t + \beta_{i,SMB} SMB_t + \beta_{i,HML} HML_t + \epsilon_{i,t}$$

### 因子构造

#### MKT（市场因子）
$$MKT_t = R_{m,t} - R_{f,t}$$

#### SMB（Small Minus Big，规模因子）
- **Small**：市值最小的 50% 股票等权组合
- **Big**：市值最大的 50% 股票等权组合
$$SMB_t = \frac{1}{3}(S_{LV} + S_{SV} + S_{N}) - \frac{1}{3}(B_{LV} + B_{SV} + B_{N})$$

#### HML（High Minus Low，价值因子）
- **High**：B/M 最高的 30% 股票
- **Low**：B/M 最低的 30% 股票
$$HML_t = \frac{1}{2}(S_{HV} + B_{HV}) - \frac{1}{2}(S_{LV} + B_{LV})$$

### 分组方法（2×3）
按市值（S/B）和 B/M（H/M/L）交叉分组：
- 6 个组合
- 确保因子捕捉独立的维度

## 2. 五因子模型 (2015)

### 新增因子

#### RMW（Robust Minus Weak，盈利因子）
$$RMW_t = R_{Robust} - R_{Weak}$$

- **Robust**：营业利润/权益账面值最高的 30%
- **Weak**：最低的 30%

#### CMA（Conservative Minus Aggressive，投资因子）
$$CMA_t = R_{Conservative} - R_{Aggressive}$$

- **Conservative**：总资产年增长率最低的 30%
- **Aggressive**：最高的 30%

### 五因子模型
$$R_{i,t} - R_{f,t} = \alpha_i + \beta_{i,MKT} MKT_t + \beta_{i,SMB} SMB_t + \beta_{i,HML} HML_t + \beta_{i,RMW} RMW_t + \beta_{i,CMA} CMA_t + \epsilon_{i,t}$$

### 发现
- HML 在加入 RMW 和 CMA 后变得冗余
- 价值溢价可以由盈利和投资因子解释
- 但在某些样本期 HML 仍有独立贡献

## 3. Momentum 因子 (1993, 2018)

### UMD（Up Minus Down）
$$UMD_t = R_{Winners} - R_{Losers}$$

- **Winners**：过去 12 个月收益率最高的 30%
- **Losers**：过去 12 个月收益率最低的 30%
- 跳过最近 1 个月（短期反转）

### 动量异象
- **横截面动量**：过去赢家继续赢
- **时间序列动量**：绝对收益持续
- **动量崩溃**：2009 年 3 月等极端情况

## 4. 因子投资的理论解释

### 风险补偿假说
因子溢价是对系统性风险的补偿：
- 价值：财务困境风险
- 规模：流动性风险
- 动量：趋势崩溃风险
- 盈利：商业模式脆弱性
- 投资：增长不可持续风险

### 行为金融假说
- 价值：投资者过度外推成长股业绩
- 动量：反应不足 → 逐步调整
- 规模：分析师覆盖不足，信息不对称

### 制度摩擦
- 做空限制
- 杠杆约束
- 流动性约束

## 5. 因子构建细节

### 价值因子的替代指标

| 指标 | 公式 | 特点 |
|------|------|------|
| B/M | 账面值/市值 | 经典 |
| E/P | 盈利/市值 | 剔除亏损公司 |
| CF/P | 现金流/市值 | 更稳定 |
| D/P | 股息/市值 | 仅适用于分红公司 |
| Sales/P | 销售额/市值 | 适用于成长股 |

### 盈利因子的替代指标

| 指标 | 公式 | 特点 |
|------|------|------|
| ROE | 净利润/权益 | 经典 |
| Gross Profitability | 毛利/总资产 | Novy-Marx (2013) |
| Operating Profitability | 营业利润/权益 | FF5 标准 |
| Accruals | 应计项目/资产 | 质量因子 |

## 6. 因子择时

### 宏观经济变量
- 信贷利差（Baa - Aaa）
- 期限利差（10Y - 3M）
- 通货膨胀率
- 工业产出增长率

### 估值信号
- 因子估值差（因子的 B/M 比率）
- 因子动量（因子自身收益率）

### 经济周期
| 周期阶段 | 表现好的因子 |
|----------|--------------|
| 复苏 | 价值、规模、动量 |
| 扩张 | 动量、质量 |
| 过热 | 盈利、投资 |
| 衰退 | 低波动、质量 |

## 7. 因子动物园问题

### 过度拟合风险
- 大量因子被发现但样本外失效
- 数据窥探（data snooping）
- 发表偏差（publication bias）

### 解决方案
1. **经济理论**：因子必须有合理的经济解释
2. **样本外测试**：walk-forward 验证
3. **多重检验校正**：Bonferroni, FDR
4. **预注册研究**：事前指定检验计划

### 健康因子的标准
- 有经济学直觉
- 在不同市场/时期有效
- 不能被其他因子完全解释
- 承担成本后仍有收益

## 8. 实际应用

### 因子组合构建
```python
# 简化版因子组合
def factor_portfolio(returns, factor_exposures, weights='equal'):
    """
    构建因子组合
    """
    if weights == 'equal':
        w = np.ones(len(factor_exposures)) / len(factor_exposures)
    elif weights == 'optimized':
        # 均值-方差优化
        from scipy.optimize import minimize
        # ...
    return returns @ w
```

### Smart Beta ETF
| 因子 | 代表产品 | 费率 |
|------|----------|------|
| 价值 | iShares MSCI Value | 0.04% |
| 规模 | iShares MSCI Small-Cap | 0.04% |
| 动量 | iShares MSCI Momentum | 0.04% |
| 质量 | iShares MSCI Quality | 0.04% |
| 低波动 | iShares MSCI Min Vol | 0.04% |
