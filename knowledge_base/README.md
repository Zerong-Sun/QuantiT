# 量化交易理论知识库

本知识库系统性地整理量化交易领域的核心理论、模型和策略，作为 QuantiT 项目的理论基础参考。

## 知识库结构

```
knowledge_base/
├── 01_foundations/           # 金融数学基础
│   ├── probability.md       # 概率论与随机过程
│   ├── stochastic.md        # 随机微积分
│   └── statistics.md        # 统计推断
├── 02_technical_analysis/   # 技术分析
│   ├── indicators.md        # 技术指标
│   ├── patterns.md          # K线形态与图表形态
│   └── time_series.md       # 时间序列分析
├── 03_factor_investing/     # 因子投资
│   ├── capm.md              # 资本资产定价模型
│   ├── fama_french.md       # Fama-French 多因子模型
│   ├── alpha_models.md      # Alpha 模型构建
│   └── factor_zoo.md        # 因子动物园
├── 04_statistical_arbitrage/# 统计套利
│   ├── pairs_trading.md     # 配对交易
│   ├── cointegration.md     # 协整理论
│   └── mean_reversion.md    # 均值回复
├── 05_machine_learning/     # 机器学习
│   ├── ml_fundamentals.md   # ML 基础与金融应用
│   ├── deep_learning.md     # 深度学习
│   ├── reinforcement.md     # 强化学习
│   └── feature_engineering.md # 特征工程
├── 06_risk_management/      # 风险管理
│   ├── var_models.md        # VaR 模型
│   ├── risk_factors.md      # 风险因子
│   └── hedging.md           # 对冲策略
├── 07_portfolio_theory/     # 投资组合理论
│   ├── modern_portfolio.md  # 现代投资组合理论
│   ├── black_litterman.md   # Black-Litterman 模型
│   └── risk_parity.md       # 风险平价
├── 08_market_microstructure/# 市场微观结构
│   ├── order_book.md        # 订单簿与流动性
│   ├── market_making.md     # 做市策略
│   └── execution.md         # 执行算法
├── 09_behavioral_finance/   # 行为金融
│   ├── biases.md            # 认知偏差
│   └── anomalies.md         # 市场异象
└── 10_hong_kong/            # 港股长线（恒生科技主题轮动）
    ├── market_structure.md  # HKEX、联系汇率、港股通、印花税
    ├── supply_demand.md     # 成交额、汇率流动性、南向资金代理
    ├── policy_regimes.md    # 政策体制日历（非新闻情绪）
    ├── international.md     # 美元、美债、纳指、人民币传导
    └── hstech_rotation.md   # 月频主题权重
```

## 使用方式

1. 每个理论包含：**定义 → 数学公式 → 直觉解释 → 实际应用 → 局限性**
2. 代码实现参考 `quantit/` 目录中的对应模块
3. 文档与代码保持同步更新

## 参考文献

- Hull, J.C. *Options, Futures, and Other Derivatives*
- Shreve, S.E. *Stochastic Calculus for Finance*
- De Prado, M.L. *Advances in Financial Machine Learning*
- López de Prado, M. *Machine Learning for Asset Managers*
- Erb, C.B. & Harvey, C.R. *The Golden Dilemma*
