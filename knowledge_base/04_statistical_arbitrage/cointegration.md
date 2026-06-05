# 协整理论

## 1. 协整的定义

### 非平稳时间序列
若时间序列 $X_t$ 经过 d 次差分后平稳，则称 $X_t$ 为 d 阶单整，记为 $X_t \sim I(d)$。

### 协整定义
设有 $k$ 个 $I(1)$ 序列 $X_1, X_2, \ldots, X_k$，如果存在向量 $\beta = (\beta_1, \beta_2, \ldots, \beta_k)'$，使得：
$$Z_t = \beta' X_t = \sum_{i=1}^k \beta_i X_{i,t} \sim I(0)$$
则称 $X_1, X_2, \ldots, X_k$ 具有协整关系，$\beta$ 为协整向量。

### 直觉
- 虽然各价格序列都是随机游走（不平稳）
- 但它们之间存在长期均衡关系
- 短期偏离会回复到均衡

## 2. 两变量协整

### Engle-Granger 两步法

**第一步**：OLS 回归
$$Y_t = \alpha + \beta X_t + \epsilon_t$$

**第二步**：检验残差 $\hat{\epsilon}_t$ 的平稳性
$$\Delta \hat{\epsilon}_t = \rho \hat{\epsilon}_{t-1} + \sum_{i=1}^p \gamma_i \Delta \hat{\epsilon}_{t-i} + u_t$$

检验 $H_0: \rho = 0$（非平稳）vs $H_1: \rho < 0$（平稳）

### 检验统计量
- **ADF 统计量**：检验残差是否有单位根
- **临界值**：需要特殊临界值（不使用标准 ADF 临界值）

### 估计量性质
- $\hat{\beta}$ 是超一致估计量：$\hat{\beta} \xrightarrow{p} \beta$
- 收敛速度为 $T$（而非 $T^{1/2}$）
- $\sqrt{T}(\hat{\beta} - \beta)$ 有非标准分布

## 3. 多变量协整

### Johansen 检验

**向量误差修正模型（VECM）**：
$$\Delta Y_t = \alpha \beta' Y_{t-1} + \sum_{i=1}^{p-1} \Gamma_i \Delta Y_{t-i} + \epsilon_t$$

其中：
- $\beta$：协整向量矩阵（$k \times r$，$r$ 为协整秩）
- $\alpha$：调整系数矩阵（$k \times r$）
- $\Gamma_i$：短期动态系数

### 协整秩检验

**迹检验（Trace Test）**：
$$\lambda_{trace}(r) = -T \sum_{i=r+1}^k \ln(1 - \hat{\lambda}_i)$$

**最大特征值检验**：
$$\lambda_{max}(r, r+1) = -T \ln(1 - \hat{\lambda}_{r+1})$$

### 模型选择

| 模型 | 确定性趋势 | 协整向量 |
|------|------------|----------|
| Model 1 | 无趋势，无截距 | 无常数项 |
| Model 2 | 无趋势，有截距 | 有常数项 |
| Model 3 | 线性趋势，有截距 | 有趋势项 |
| Model 4 | 二次趋势 | 有趋势项 |

## 4. 误差修正模型（ECM）

### Granger 表示定理
如果 $Y_t, X_t$ 协整，则存在 ECM：
$$\Delta Y_t = \alpha (Y_{t-1} - \beta X_{t-1}) + \sum_{i=1}^p \gamma_i \Delta Y_{t-i} + \sum_{i=0}^q \delta_i \Delta X_{t-i} + \epsilon_t$$

### 参数解释
- $\alpha$：调整速度（$\alpha < 0$ 表示均值回复）
- $\beta$：长期均衡关系
- $\gamma_i, \delta_i$：短期动态

### 序列相关修正
使用 Newey-West HAC 标准误处理残差自相关。

## 5. 协整检验的步骤

### 完整流程
```
1. 单位根检验（ADF/KPSS）
   ↓
2. 确定单整阶数
   ↓
3. 协整检验（Engle-Granger 或 Johansen）
   ↓
4. 估计协整向量
   ↓
5. 建立 VECM 模型
   ↓
6. 模型诊断（残差分析）
```

### 代码实现
```python
import statsmodels.api as sm
from statsmodels.tsa.vector_ar.vecm import coint_johansen

def cointegration_analysis(data, det_order=-1, k_ar_diff=1):
    """
    Johansen 协整检验
    """
    result = coint_johansen(data, det_order, k_ar_diff)
    
    # 迹检验
    trace_stat = result.lr1
    trace_crit = result.cvt  # 90%, 95%, 99% 临界值
    
    # 最大特征值检验
    max_stat = result.lr2
    max_crit = result.cvm
    
    # 协整向量
    evec = result.evec
    
    return {
        'trace_stat': trace_stat,
        'trace_crit': trace_crit,
        'max_stat': max_stat,
        'max_crit': max_crit,
        'eigenvectors': evec
    }
```

## 6. 协整与配对交易

### 配对交易的协整框架
1. **选择配对**：基于协整检验
2. **估计均衡**：$\hat{\beta}$（对冲比率）
3. **生成信号**：基于价差偏离
4. **风险管理**：考虑协整关系破裂

### 动态对冲比率
使用滚动窗口或卡尔曼滤波更新 $\beta$。

### 协整关系的稳定性
- 定期重新检验
- 监控调整速度 $\alpha$
- 注意结构性变化

## 7. 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 伪协整 | 结构性断点 | 断点检验，分段协整 |
| 多重协整 | 多个均衡关系 | Johansen 检验 |
| 非线性协整 | 阈值效应 | Threshold ECM |
| 结构变化 | 制度变迁 | 时变参数模型 |

## 8. 扩展

### 非线性协整
**TVECM（Threshold VECM）**：
$$\Delta Y_t = \begin{cases}
\alpha_1 \beta' Y_{t-1} + \cdots & \text{if } z_t \leq \gamma \\
\alpha_2 \beta' Y_{t-1} + \cdots & \text{if } z_t > \gamma
\end{cases}$$

### 面板协整
使用多个时间序列的信息提高检验功效。
- Pedroni 检验
- Kao 检验
