# 深度学习

## 1. 神经网络基础

### 感知机
$$y = f\left(\sum_{i=1}^n w_i x_i + b\right) = f(W'x + b)$$

### 激活函数

| 函数 | 公式 | 特点 |
|------|------|------|
| Sigmoid | $\sigma(x) = \frac{1}{1+e^{-x}}$ | 输出(0,1)，梯度消失 |
| Tanh | $\tanh(x)$ | 输出(-1,1)，零中心 |
| ReLU | $\max(0, x)$ | 计算简单，稀疏激活 |
| GELU | $x \cdot \Phi(x)$ | Transformer常用 |

## 2. 循环神经网络（RNN）

### LSTM（长短期记忆）

**门控机制**：
$$f_t = \sigma(W_f[h_{t-1}, x_t] + b_f) \quad \text{（遗忘门）}$$
$$i_t = \sigma(W_i[h_{t-1}, x_t] + b_i) \quad \text{（输入门）}$$
$$C_t = f_t \odot C_{t-1} + i_t \odot \tanh(W_C[h_{t-1}, x_t] + b_C)$$
$$o_t = \sigma(W_o[h_{t-1}, x_t] + b_o) \quad \text{（输出门）}$$
$$h_t = o_t \odot \tanh(C_t)$$

### GRU（门控循环单元）
$$z_t = \sigma(W_z[h_{t-1}, x_t]) \quad \text{（更新门）}$$
$$r_t = \sigma(W_r[h_{t-1}, x_t]) \quad \text{（重置门）}$$
$$h_t = (1-z_t) \odot h_{t-1} + z_t \odot \tanh(W[r_t \odot h_{t-1}, x_t])$$

## 3. Transformer

### 自注意力机制
$$\text{Attention}(Q, K, V) = \text{softmax}\left(\frac{QK'}{\sqrt{d_k}}\right)V$$

### 多头注意力
$$\text{MultiHead}(Q, K, V) = \text{Concat}(\text{head}_1, \ldots, \text{head}_h)W^O$$

### 位置编码
$$PE_{(pos, 2i)} = \sin(pos / 10000^{2i/d_{model}})$$
$$PE_{(pos, 2i+1)} = \cos(pos / 10000^{2i/d_{model}})$$

### 金融 Transformer 实现
```python
class FinancialTransformer(nn.Module):
    def __init__(self, input_dim, d_model, nhead, num_layers, output_dim):
        super().__init__()
        self.input_projection = nn.Linear(input_dim, d_model)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=256
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.output_layer = nn.Linear(d_model, output_dim)

    def forward(self, x):
        x = self.input_projection(x)
        x = self.transformer(x)
        return self.output_layer(x[:, -1, :])
```

## 4. CNN 在金融中的应用

### 1D CNN 提取时序特征
```python
class TimeSeriesCNN(nn.Module):
    def __init__(self, input_channels, num_classes):
        super().__init__()
        self.conv1 = nn.Conv1d(input_channels, 64, kernel_size=3, padding=1)
        self.conv2 = nn.Conv1d(64, 128, kernel_size=3, padding=1)
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.fc = nn.Linear(128, num_classes)

    def forward(self, x):
        x = torch.relu(self.conv1(x))
        x = torch.relu(self.conv2(x))
        x = self.pool(x).squeeze(-1)
        return self.fc(x)
```

## 5. 自编码器（Autoencoder）

### 基本结构
$$\text{Encoder}: z = f_\phi(x)$$
$$\text{Decoder}: \hat{x} = g_\theta(z)$$

### 金融应用
- 异常检测（欺诈、极端事件）
- 因子提取
- 数据增强

## 6. 训练技巧

### 数据预处理
```python
def normalize_features(df, method='zscore'):
    if method == 'zscore':
        return (df - df.mean()) / df.std()
    elif method == 'robust':
        return (df - df.median()) / (df.quantile(0.75) - df.quantile(0.25))
```

### 学习率调度
```python
scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=100)
```

### 正则化
- Dropout
- Weight Decay
- Early Stopping

## 7. 深度学习 vs 传统 ML

| 方面 | 传统 ML | 深度学习 |
|------|---------|----------|
| 数据需求 | 中等 | 大量 |
| 可解释性 | 高 | 低 |
| 特征工程 | 需要 | 自动 |
| 训练速度 | 快 | 慢 |
| 适用场景 | 结构化数据 | 序列/图像/文本 |

## 8. 实践建议

| 建议 | 说明 |
|------|------|
| 从简单模型开始 | 先用线性模型/树模型做baseline |
| 重视数据质量 | 噪声数据会毁掉任何模型 |
| 过拟合是主要敌人 | 金融数据信噪比低 |
| 考虑推理成本 | 实盘需要快速预测 |
| 集成学习 | 结合多个模型提升稳定性 |
