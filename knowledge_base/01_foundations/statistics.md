# 统计推断

## 1. 参数估计

### 点估计

#### 最大似然估计（MLE）
$$\hat{\theta}_{MLE} = \arg\max_\theta \prod_{i=1}^n f(x_i; \theta)$$

**性质**：一致性、渐近正态性、渐近有效性（在正则条件下）

#### 矩估计（MoM）
令样本矩等于总体矩：$\frac{1}{n}\sum_{i=1}^n X_i^k = E[X^k]$

**优点**：不依赖分布假设，计算简单

### 区间估计

**置信区间**：
$$CI_{1-\alpha} = \left[\hat{\theta} - z_{\alpha/2} \cdot SE(\hat{\theta}), \quad \hat{\theta} + z_{\alpha/2} \cdot SE(\hat{\theta})\right]$$

**金融应用**：
- 收置信区间
- 波动率估计的不确定性
- 因子收益的统计显著性

## 2. 假设检验

### 框架
- $H_0$：原假设（如 $\beta = 0$，因子无 alpha）
- $H_1$：备择假设（如 $\beta \neq 0$）

### 常用检验

| 检验 | 应用 | 统计量 |
|------|------|--------|
| t 检验 | 因子收益显著性 | $t = \frac{\hat{\beta}}{SE(\hat{\beta})}$ |
| F 检验 | 模型整体显著性 | $F = \frac{SSR/k}{SSE/(n-k-1)}$ |
| ADF 检验 | 单位根/平稳性 | 基于 OLS 回归的 t 统计量 |
| Jarque-Bera | 正态性检验 | 基于偏度和峰度 |
| Chow 检验 | 结构断点 | $F = \frac{(RSS_r - RSS_u)/k}{RSS_u/(n-2k)}$ |

### 多重检验问题

在因子研究中同时检验大量假设时：
- **Bonferroni 校正**：$\alpha_{adj} = \alpha / m$
- **False Discovery Rate（FDR）**：控制错误发现率
- **Bootstrap 方法**：经验性地确定阈值

## 3. 回归分析

### OLS 回归
$$y_t = \alpha + \beta x_t + \epsilon_t, \quad \epsilon_t \sim (0, \sigma^2)$$

**估计量**：
$$\hat{\beta} = \frac{\text{Cov}(x, y)}{\text{Var}(x)} = \frac{\sum (x_i - \bar{x})(y_i - \bar{y})}{\sum (x_i - \bar{x})^2}$$

### 时间序列回归的特殊问题

#### 自相关
**Durbin-Watson 检验**：$DW = \frac{\sum_{t=2}^T (e_t - e_{t-1})^2}{\sum_{t=1}^T e_t^2}$

**Newey-West HAC 标准误**（异方差自相关稳健）：
$$\hat{V}_{NW} = \hat{V}_{OLS} + \sum_{l=1}^{L} w_l \sum_{t=l+1}^T e_t e_{t-l} (x_t x_{t-l}' + x_{t-l} x_t')$$

#### 多重共线性
- **方差膨胀因子**：$VIF_j = \frac{1}{1-R_j^2}$
- **岭回归**：引入惩罚项 $\hat{\beta}_{ridge} = (X'X + \lambda I)^{-1}X'Y$
- **LASSO**：$\hat{\beta}_{LASSO} = \arg\min \|Y - X\beta\|^2 + \lambda\|\beta\|_1$

### Panel Data 模型
$$y_{it} = \alpha_i + \beta x_{it} + \epsilon_{it}$$

- 固定效应：$\alpha_i$ 为固定参数
- 随机效应：$\alpha_i \sim (0, \sigma_\alpha^2)$

## 4. 非参数方法

### 核密度估计
$$\hat{f}(x) = \frac{1}{nh} \sum_{i=1}^n K\left(\frac{x - X_i}{h}\right)$$

**常用核**：
- 高斯核：$K(u) = \frac{1}{\sqrt{2\pi}} e^{-u^2/2}$
- Epanechnikov 核：$K(u) = \frac{3}{4}(1-u^2) \mathbf{1}_{|u| \leq 1}$

**带宽选择**：$h_{opt} \propto n^{-1/5}$（MSE 最优）

### 非参数回归（LOWESS）
局部加权回归，适合捕捉非线性关系。

## 5. Bootstrap 方法

### 基本思想
从数据中有放回地重采样，用经验分布替代理论分布。

### 应用
- **置信区间**：百分位 Bootstrap
- **标准误估计**：$SE_{boot} = \sqrt{\frac{1}{B-1}\sum_{b=1}^B (\hat{\theta}^*_b - \bar{\hat{\theta}^*})^2}$
- **假设检验**：置换检验（Permutation Test）

### Block Bootstrap（时间序列）
保持时间序列的序列相关性，对连续块进行重采样。

## 6. 量化交易中的统计陷阱

| 陷阱 | 描述 | 解决方案 |
|------|------|----------|
| 过拟合 | 模型对历史数据拟合过好 | 交叉验证、样本外测试 |
| 数据窥探 | 反复测试直到找到"显著"结果 | 调整 p 值、Bonferroni 校正 |
| 幸存者偏差 | 只看存活公司 | 包含退市股票数据 |
| 前视偏差 | 使用未来信息 | 严格的事件时间框架 |
| 回测过拟合 | 策略参数对历史数据过度优化 | Walk-forward 优化 |
