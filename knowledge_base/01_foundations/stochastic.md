# 随机微积分

## 1. Itô 积分

### 为什么不是普通积分？

对于随机过程 $f(W_t)$，传统微积分的链式法则不适用，因为布朗运动的路径处处不可微且变差无限。

### Itô 积分定义
$$\int_0^t f(W_s) dW_s = \lim_{|\pi| \to 0} \sum_{i} f(W_{t_i})(W_{t_{i+1}} - W_{t_i})$$

### Itô 引理（核心工具）

若 $X_t$ 满足 $dX_t = \mu_t dt + \sigma_t dW_t$，则对光滑函数 $f(t, x)$：
$$df(t, X_t) = \left(\frac{\partial f}{\partial t} + \mu_t \frac{\partial f}{\partial x} + \frac{1}{2}\sigma_t^2 \frac{\partial^2 f}{\partial x^2}\right)dt + \sigma_t \frac{\partial f}{\partial x} dW_t$$

**关键区别**：多出的 $\frac{1}{2}\sigma_t^2 \frac{\partial^2 f}{\partial x^2}$ 项（Itô 修正项）来自 $(dW_t)^2 = dt$。

## 2. 随机微分方程（SDE）

### 几何布朗运动（GBM）
$$dS_t = \mu S_t dt + \sigma S_t dW_t$$

**解**：
$$S_t = S_0 \exp\left[\left(\mu - \frac{\sigma^2}{2}\right)t + \sigma W_t\right]$$

**特征**：
- 对数收益率服从正态分布：$\ln(S_t/S_0) \sim N\left((\mu-\sigma^2/2)t, \sigma^2 t\right)$
- 期望：$E[S_t] = S_0 e^{\mu t}$
- 中位数：$S_0 e^{(\mu - \sigma^2/2)t}$（低于期望）

### Ornstein-Uhlenbeck 过程（均值回复）
$$dX_t = \theta(\mu - X_t)dt + \sigma dW_t$$

**解**：
$$X_t = X_0 e^{-\theta t} + \mu(1 - e^{-\theta t}) + \sigma \int_0^t e^{-\theta(t-s)} dW_s$$

**特征**：
- 长期均值 $\mu$，回复速度 $\theta$
- 方差：$\text{Var}(X_t) = \frac{\sigma^2}{2\theta}(1 - e^{-2\theta t})$
- 稳态方差：$\frac{\sigma^2}{2\theta}$

### CIR 过程（Cox-Ingersoll-Ross）
$$dX_t = \theta(\mu - X_t)dt + \sigma \sqrt{X_t} dW_t$$

**特征**：
- 方差与 $X_t$ 成正比（波动率随水平变化）
- 若 $2\theta\mu > \sigma^2$，过程永不触及零
- 用于利率建模（Vasicek 模型的改进）

### 跳跃扩散模型（Merton）
$$dS_t = \mu S_t dt + \sigma S_t dW_t + S_{t^-} (e^J - 1) dN_t$$

其中 $J \sim N(\mu_J, \sigma_J^2)$，$N_t$ 是强度为 $\lambda$ 的泊松过程。

**用途**：捕捉资产价格的突然跳变（财报、黑天鹅事件）

## 3. Girsanov 定理

### 物理测度 → 风险中性测度

若在物理测度 $P$ 下：$dS_t = \mu S_t dt + \sigma S_t dW_t^P$

则存在等价鞅测度 $Q$，使得：$dS_t = r S_t dt + \sigma S_t dW_t^Q$

**变换关系**：
$$dW_t^Q = dW_t^P + \frac{\mu - r}{\sigma} dt$$

**含义**：
- 风险溢价 $\mu - r$ 被"吸收"到测度变换中
- 在 $Q$ 下，所有资产的期望收益率都是无风险利率 $r$
- 这是衍生品定价的基础

### Radon-Nikodym 导数
$$\frac{dQ}{dP}\bigg|_{\mathcal{F}_t} = \exp\left(-\frac{\mu - r}{\sigma} W_t - \frac{1}{2}\left(\frac{\mu - r}{\sigma}\right)^2 t\right)$$

## 4. Feynman-Kac 公式

连接 PDE 与期望：

若 $V(t,x)$ 满足 PDE：
$$\frac{\partial V}{\partial t} + \mu(x)\frac{\partial V}{\partial x} + \frac{1}{2}\sigma^2(x)\frac{\partial^2 V}{\partial x^2} - rV = 0$$

则：
$$V(t,x) = e^{-r(T-t)} E^Q\left[h(X_T) \mid X_t = x\right]$$

**应用**：Black-Scholes PDE 的解就是期权的风险中性期望价格。

## 5. 量化交易应用

| 工具 | 应用 |
|------|------|
| GBM | 股票价格建模、期权定价基础 |
| OU 过程 | 配对交易、均值回复策略 |
| CIR 过程 | 利率建模、固定收益定价 |
| 跳跃扩散 | 尾部风险定价、信用风险模型 |
| Girsanov 定理 | 期权定价、Greeks 计算 |
| Feynman-Kac | 衍生品定价、PDE 数值解 |
| Itô 引理 | 推导 Greeks、构建对冲策略 |
