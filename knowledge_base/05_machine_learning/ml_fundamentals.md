# ML 基础与金融应用

## 1. 监督学习

### 线性模型

#### OLS 回归
$$\hat{\beta} = (X'X)^{-1}X'Y$$

#### 岭回归（L2 正则化）
$$\hat{\beta}_{ridge} = (X'X + \lambda I)^{-1}X'Y$$

#### LASSO（L1 正则化）
$$\hat{\beta}_{LASSO} = \arg\min \|Y - X\beta\|^2 + \lambda\|\beta\|_1$$

**特点**：产生稀疏解，自动特征选择

#### Elastic Net
$$\hat{\beta}_{EN} = \arg\min \|Y - X\beta\|^2 + \lambda_1\|\beta\|_1 + \lambda_2\|\beta\|_2^2$$

### 树模型

#### 决策树
- **分裂准则**：信息增益、基尼指数
- **剪枝**：防止过拟合

#### 随机森林
```python
from sklearn.ensemble import RandomForestRegressor

rf = RandomForestRegressor(
    n_estimators=100,
    max_depth=5,
    min_samples_leaf=20,
    random_state=42
)
rf.fit(X_train, y_train)
```

#### 梯度提升树
```python
import lightgbm as lgb

params = {
    'objective': 'regression',
    'metric': 'rmse',
    'num_leaves': 31,
    'learning_rate': 0.05,
    'feature_fraction': 0.8,
    'bagging_fraction': 0.8,
    'bagging_freq': 5,
    'verbose': -1
}

train_data = lgb.Dataset(X_train, label=y_train)
model = lgb.train(params, train_data, num_boost_round=100)
```

### 支持向量机（SVM）
$$\min \frac{1}{2}\|w\|^2 + C\sum_{i=1}^n \xi_i$$
$$s.t. \quad y_i(w'x_i + b) \geq 1 - \xi_i, \quad \xi_i \geq 0$$

## 2. 无监督学习

### 聚类

#### K-Means
```python
from sklearn.cluster import KMeans

kmeans = KMeans(n_clusters=5, random_state=42)
labels = kmeans.fit_predict(X)
```

#### 层次聚类
```python
from scipy.cluster.hierarchy import linkage, fcluster

Z = linkage(X, method='ward')
labels = fcluster(Z, t=5, criterion='maxclust')
```

### 降维

#### PCA
```python
from sklearn.decomposition import PCA

pca = PCA(n_components=10)
X_reduced = pca.fit_transform(X)
```

#### t-SNE（可视化）
```python
from sklearn.manifold import TSNE

tsne = TSNE(n_components=2, random_state=42)
X_2d = tsne.fit_transform(X)
```

## 3. 金融中的特殊问题

### 标签构建

#### 三重屏障法（Triple Barrier Method）
```python
def triple_barrier(prices, lookforward, upper_pct, lower_pct):
    """
    三重屏障法生成标签
    """
    labels = []
    for i in range(len(prices)):
        # 未来收益
        future_ret = prices[i+lookforward] / prices[i] - 1

        if future_ret > upper_pct:
            labels.append(1)  # 盈利
        elif future_ret < -lower_pct:
            labels.append(-1)  # 亏损
        else:
            labels.append(0)  # 中性
    return labels
```

#### Meta-Labeling
```python
def meta_labeling(primary_model, X, y):
    """
    Meta-Labeling：预测primary_model的信号是否正确
    """
    primary_signals = primary_model.predict(X)
    meta_y = (primary_signals == y).astype(int)
    meta_model = RandomForestClassifier()
    meta_model.fit(X, meta_y)
    return meta_model
```

### 特征工程

#### 技术指标特征
```python
def add_technical_features(df):
    """添加技术指标特征"""
    df['returns_1d'] = df['close'].pct_change(1)
    df['returns_5d'] = df['close'].pct_change(5)
    df['returns_20d'] = df['close'].pct_change(20)
    df['volatility_20d'] = df['returns_1d'].rolling(20).std()
    df['rsi_14'] = compute_rsi(df['close'], 14)
    df['macd'], df['macd_signal'] = compute_macd(df['close'])
    return df
```

### 交叉验证

#### 时间序列交叉验证
```python
def time_series_cv(X, y, n_splits=5):
    """时间序列交叉验证"""
    tscv = TimeSeriesSplit(n_splits=n_splits)
    scores = []
    for train_idx, val_idx in tscv.split(X):
        X_train, X_val = X[train_idx], X[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        model = train_model(X_train, y_train)
        score = evaluate(model, X_val, y_val)
        scores.append(score)
    return scores
```

## 4. 模型评估

### 回归指标
| 指标 | 公式 | 特点 |
|------|------|------|
| MSE | $\frac{1}{n}\sum(y_i - \hat{y}_i)^2$ | 惩罚大误差 |
| MAE | $\frac{1}{n}\sum|y_i - \hat{y}_i|$ | 稳健 |
| R² | $1 - \frac{SS_{res}}{SS_{tot}}$ | 解释方差比例 |

### 分类指标
| 指标 | 公式 | 特点 |
|------|------|------|
| Accuracy | $\frac{TP+TN}{TP+TN+FP+FN}$ | 整体准确率 |
| Precision | $\frac{TP}{TP+FP}$ | 预测为正的准确率 |
| Recall | $\frac{TP}{TP+FN}$ | 正样本的覆盖率 |
| F1 | $2\frac{Precision \times Recall}{Precision + Recall}$ | 平衡指标 |
| AUC | ROC曲线下面积 | 不依赖阈值 |

### 金融指标
| 指标 | 说明 |
|------|------|
| IC（信息系数） | 预测值与真实值的相关系数 |
| IR（信息比率） | IC的均值/IC的标准差 |
| 分组收益 | 按预测值分组后的收益差异 |
| 换手率 | 组合调整频率 |

## 5. 防止过拟合

### 正则化
- L1/L2 正则化
- Dropout（神经网络）
- Early Stopping

### 交叉验证
- 时间序列分割
- Purged K-Fold
- Embargo

### 特征选择
- 递归特征消除（RFE）
- 基于模型的特征重要性
- Boruta 算法

### 集成方法
- Bagging：降低方差
- Boosting：降低偏差
- Stacking：组合多个模型

## 6. 实践建议

| 建议 | 说明 |
|------|------|
| 从简单模型开始 | 线性模型 → 树模型 → 神经网络 |
| 重视特征工程 | 好的特征比复杂的模型更重要 |
| 样本外测试 | 至少30%数据用于验证 |
| 扣除交易成本 | 收益需覆盖交易成本 |
| 监控模型衰减 | 定期重新训练 |
| 记录实验 | 使用MLflow等工具跟踪 |
