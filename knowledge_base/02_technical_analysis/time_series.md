# 时间序列分析

## 1. 平稳性

### 定义
**弱平稳**（二阶平稳）：
1. $E[X_t] = \mu$（常数均值）
2. $\text{Var}(X_t) = \sigma^2$（常数方差）
3. $\text{Cov}(X_t, X_{t+h}) = \gamma(h)$（自协方差只依赖于滞后 $h$）

### 单位根检验

#### ADF 检验（Augmented Dickey-Fuller）
$$\Delta y_t = \alpha + \beta t + (\rho-1)y_{t-1} + \sum_{i=1}^p \gamma_i \Delta y_{t-i} + \epsilon_t$$

- $H_0$：$\rho = 1$（存在单位根，非平稳）
- $H_1$：$\rho < 1$（平稳）

#### KPSS 检验
- $H_0$：序列平稳
- $H_1$：序列非平稳

**建议**：结合 ADF 和 KPSS 使用，避免单一检验的偏差。

### 差分与趋势去除
- 一阶差分：$\Delta y_t = y_t - y_{t-1}$
- 二阶差分：$\Delta^2 y_t = \Delta y_t - \Delta y_{t-1}$
- 对数差分：$\ln(y_t/y_{t-1})$ ≈ 收益率

## 2. 自相关分析

### 自相关函数（ACF）
$$\rho_k = \frac{\gamma_k}{\gamma_0} = \frac{\text{Cov}(X_t, X_{t-k})}{\text{Var}(X_t)}$$

### 偏自相关函数（PACF）
PACF 是在控制中间滞后值后，$X_t$ 与 $X_{t-k}$ 的直接相关。

### 模型识别

| 模型 | ACF | PACF |
|------|-----|------|
| AR(p) | 拖尾 | p 阶截尾 |
| MA(q) | q 阶截尾 | 拖尾 |
| ARMA(p,q) | 拖尾 | 拖尾 |

## 3. ARMA 模型

### AR(p) 自回归模型
$$X_t = c + \phi_1 X_{t-1} + \phi_2 X_{t-2} + \cdots + \phi_p X_{t-p} + \epsilon_t$$

**平稳条件**：特征方程 $1 - \phi_1 z - \cdots - \phi_p z^p = 0$ 的根在单位圆外。

### MA(q) 移动平均模型
$$X_t = \mu + \epsilon_t + \theta_1 \epsilon_{t-1} + \cdots + \theta_q \epsilon_{t-q}$$

### ARIMA(p,d,q)
$$\phi(B)(1-B)^d X_t = \theta(B)\epsilon_t$$

其中 $B$ 是后移算子：$BX_t = X_{t-1}$

**建模步骤**：
1. 确定差分阶数 $d$（平稳化）
2. 通过 ACF/PACF 确定 $p, q$
3. 估计参数
4. 诊断检验（残差分析）

## 4. GARCH 模型

### 波动率聚集
金融收益率呈现波动率聚集：大波动后跟随大波动。

### GARCH(1,1)
$$\sigma_t^2 = \omega + \alpha \epsilon_{t-1}^2 + \beta \sigma_{t-1}^2$$

**约束**：$\omega > 0, \alpha \geq 0, \beta \geq 0, \alpha + \beta < 1$

**无条件方差**：$\sigma^2 = \frac{\omega}{1-\alpha-\beta}$

### EGARCH（指数 GARCH）
$$\ln(\sigma_t^2) = \omega + \alpha\left[\frac{|\epsilon_{t-1}|}{\sigma_{t-1}} - \sqrt{\frac{2}{\pi}}\right] + \gamma\frac{\epsilon_{t-1}}{\sigma_{t-1}} + \beta\ln(\sigma_{t-1}^2)$$

**优点**：
- 参数无约束
- $\gamma < 0$ 时捕捉杠杆效应

### GJR-GARCH
$$\sigma_t^2 = \omega + (\alpha + \gamma I_{t-1})\epsilon_{t-1}^2 + \beta\sigma_{t-1}^2$$

其中 $I_{t-1} = 1$ 当 $\epsilon_{t-1} < 0$

## 5. 协整与误差修正模型

### 协整定义
若 $X_t \sim I(1)$，$Y_t \sim I(1)$，但存在 $\beta$ 使：
$$Z_t = Y_t - \beta X_t \sim I(0)$$
则称 $X_t, Y_t$ 协整。

### Engle-Granger 两步法
1. 回归 $Y_t = \alpha + \beta X_t + \epsilon_t$
2. 检验残差 $\hat{\epsilon}_t$ 的平稳性

### 向量误差修正模型（VECM）
$$\Delta Y_t = \alpha \beta' Y_{t-1} + \sum_{i=1}^{p-1} \Gamma_i \Delta Y_{t-i} + \epsilon_t$$

- $\beta$：协整向量（长期关系）
- $\alpha$：调整速度（短期修正）

## 6. 状态空间模型与卡尔曼滤波

### 卡尔曼滤波
$$状态方程：x_t = F_t x_{t-1} + w_t, \quad w_t \sim N(0, Q_t)$$
$$观测方程：y_t = H_t x_t + v_t, \quad v_t \sim N(0, R_t)$$

**预测步骤**：
$$\hat{x}_{t|t-1} = F_t \hat{x}_{t-1|t-1}$$

**更新步骤**：
$$K_t = P_{t|t-1} H_t' (H_t P_{t|t-1} H_t' + R_t)^{-1}$$
$$\hat{x}_{t|t} = \hat{x}_{t|t-1} + K_t (y_t - H_t \hat{x}_{t|t-1})$$

**应用**：
- 时变参数模型
- 隐波动率估计
- 动态因子模型

## 7. 预测评估

### 误差指标
| 指标 | 公式 | 特点 |
|------|------|------|
| MAE | $\frac{1}{n}\sum\|e_t\|$ | 稳健 |
| RMSE | $\sqrt{\frac{1}{n}\sum e_t^2}$ | 惩罚大误差 |
| MAPE | $\frac{100}{n}\sum\|\frac{e_t}{y_t}\|$ | 百分比误差 |
| Theil U | $\frac{RMSE_{model}}{RMSE_{naive}}$ | 相对基准 |
