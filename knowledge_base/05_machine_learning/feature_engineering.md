# 特征工程

## 1. 特征类型

### 技术指标特征

#### 动量类
| 特征 | 公式 | 说明 |
|------|------|------|
| Returns | $P_t/P_{t-1} - 1$ | 日收益率 |
| Log Returns | $\ln(P_t/P_{t-1})$ | 对数收益率 |
| ROC | $(P_t - P_{t-n})/P_{t-n}$ | 变化率 |
| Momentum | $P_t - P_{t-n}$ | 动量 |

#### 波动率类
| 特征 | 公式 | 说明 |
|------|------|------|
| Volatility | $\sigma$ (rolling) | 滚动波动率 |
| ATR | Average True Range | 真实波幅 |
| Bollinger Width | $(Upper-Lower)/Middle$ | 布林带宽度 |

#### 趋势类
| 特征 | 公式 | 说明 |
|------|------|------|
| SMA Cross | $SMA_{short}/SMA_{long}$ | 均线比值 |
| MACD Histogram | $MACD - Signal$ | MACD柱 |
| ADX | Average Directional Index | 趋势强度 |

### 基本面特征

#### 估值
```python
def valuation_features(df):
    features = {}
    features['pe_ratio'] = df['price'] / df['eps']
    features['pb_ratio'] = df['price'] / df['book_value']
    features['ps_ratio'] = df['price'] / df['revenue']
    features['pcf_ratio'] = df['price'] / df['cash_flow']
    return features
```

#### 盈利能力
```python
def profitability_features(df):
    features = {}
    features['roe'] = df['net_income'] / df['equity']
    features['roa'] = df['net_income'] / df['assets']
    features['gross_margin'] = df['gross_profit'] / df['revenue']
    features['operating_margin'] = df['operating_income'] / df['revenue']
    return features
```

#### 成长性
```python
def growth_features(df):
    features = {}
    features['revenue_growth'] = df['revenue'].pct_change(4)
    features['earnings_growth'] = df['eps'].pct_change(4)
    features['asset_growth'] = df['assets'].pct_change(4)
    return features
```

## 2. 特征构造方法

### 交叉特征
```python
def cross_features(df):
    """交叉特征"""
    features = {}
    features['price_vol_ratio'] = df['close'] / df['volume']
    features['return_vol'] = df['returns'] / df['volatility']
    features['momentum_value'] = df['momentum'] * df['pe_ratio']
    return features
```

### 分组统计特征
```python
def group_features(df, group_col, value_col):
    """分组统计特征"""
    features = {}
    features['group_mean'] = df.groupby(group_col)[value_col].transform('mean')
    features['group_std'] = df.groupby(group_col)[value_col].transform('std')
    features['group_rank'] = df.groupby(group_col)[value_col].rank(pct=True)
    return features
```

### 时间特征
```python
def time_features(df):
    """时间特征"""
    features = {}
    features['day_of_week'] = df.index.dayofweek
    features['month'] = df.index.month
    features['quarter'] = df.index.quarter
    features['is_month_end'] = df.index.is_month_end
    features['is_quarter_end'] = df.index.is_quarter_end
    return features
```

## 3. 特征处理

### 缺失值处理
```python
def handle_missing(df, method='forward'):
    if method == 'forward':
        return df.fillna(method='ffill')
    elif method == 'interpolate':
        return df.interpolate(method='time')
    elif method == 'drop':
        return df.dropna()
```

### 异常值处理
```python
def handle_outliers(df, method='clip', n_std=3):
    if method == 'clip':
        return df.clip(lower=df.mean() - n_std*df.std(),
                       upper=df.mean() + n_std*df.std())
    elif method == 'winsorize':
        from scipy.stats.mstats import winsorize
        return df.apply(lambda x: winsorize(x, limits=[0.05, 0.05]))
```

### 标准化
```python
def normalize(df, method='zscore'):
    if method == 'zscore':
        return (df - df.mean()) / df.std()
    elif method == 'minmax':
        return (df - df.min()) / (df.max() - df.min())
    elif method == 'rank':
        return df.rank(pct=True)
```

## 4. 特征选择

### 过滤法
```python
from sklearn.feature_selection import mutual_info_regression

def filter_features(X, y, threshold=0.01):
    """基于互信息的特征选择"""
    mi_scores = mutual_info_regression(X, y)
    selected = X.columns[mi_scores > threshold]
    return selected
```

### 包装法
```python
from sklearn.feature_selection import RFE
from sklearn.ensemble import RandomForestRegressor

def wrapper_features(X, y, n_features=10):
    """递归特征消除"""
    estimator = RandomForestRegressor(n_estimators=100)
    selector = RFE(estimator, n_features_to_select=n_features)
    selector.fit(X, y)
    return X.columns[selector.support_]
```

### 嵌入法
```python
def embedded_features(X, y):
    """基于模型的特征选择"""
    from sklearn.ensemble import GradientBoostingRegressor
    model = GradientBoostingRegressor()
    model.fit(X, y)
    importances = model.feature_importances_
    return X.columns[importances > np.median(importances)]
```

## 5. 特征重要性

### 基于模型
```python
def feature_importance(model, feature_names):
    """特征重要性"""
    if hasattr(model, 'feature_importances_'):
        return pd.Series(model.feature_importances_, index=feature_names)
    elif hasattr(model, 'coef_'):
        return pd.Series(np.abs(model.coef_), index=feature_names)
```

### Permutation Importance
```python
from sklearn.inspection import permutation_importance

def perm_importance(model, X, y):
    """排列重要性"""
    result = permutation_importance(model, X, y, n_repeats=10)
    return pd.Series(result.importances_mean, index=X.columns)
```

### SHAP
```python
import shap

def shap_importance(model, X):
    """SHAP 值"""
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)
    return pd.DataFrame(shap_values, columns=X.columns)
```

## 6. 金融特征工程最佳实践

| 实践 | 说明 |
|------|------|
| 避免前视偏差 | 特征只能用过去数据 |
| 考虑交易成本 | 特征应覆盖交易成本 |
| 中性化 | 行业/市值中性化减少暴露 |
| 稳定性 | 选择在不同市场环境下稳定的特征 |
| 低相关性 | 特征间相关性低增加信息量 |
| 可解释性 | 优先选择有经济学意义的特征 |
