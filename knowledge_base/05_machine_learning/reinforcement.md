# 强化学习

## 1. 基本框架

### 马尔可夫决策过程（MDP）
$$MDP = (S, A, P, R, \gamma)$$

- $S$：状态空间
- $A$：动作空间
- $P(s'|s,a)$：状态转移概率
- $R(s,a)$：奖励函数
- $\gamma \in [0,1)$：折扣因子

### 目标函数
$$J(\pi) = E_{\pi}\left[\sum_{t=0}^{\infty} \gamma^t R(s_t, a_t)\right]$$

## 2. 核心概念

### 状态值函数
$$V^\pi(s) = E_{\pi}\left[\sum_{t=0}^{\infty} \gamma^t R(s_t, a_t) | s_0 = s\right]$$

### 动作值函数
$$Q^\pi(s, a) = E_{\pi}\left[\sum_{t=0}^{\infty} \gamma^t R(s_t, a_t) | s_0 = s, a_0 = a\right]$$

### Bellman 方程
$$V^\pi(s) = \sum_{a} \pi(a|s) \sum_{s'} P(s'|s,a)[R(s,a,s') + \gamma V^\pi(s')]$$

### 最优策略
$$\pi^*(s) = \arg\max_a Q^*(s, a)$$

## 3. 动态规划

### 策略评估
$$V_{k+1}(s) = \sum_{a} \pi(a|s) \sum_{s'} P(s'|s,a)[R(s,a,s') + \gamma V_k(s')]$$

### 策略改进
$$\pi_{k+1}(s) = \arg\max_a \sum_{s'} P(s'|s,a)[R(s,a,s') + \gamma V_k(s')]$$

### 值迭代
$$V_{k+1}(s) = \max_a \sum_{s'} P(s'|s,a)[R(s,a,s') + \gamma V_k(s')]$$

## 4. 蒙特卡洛方法

### 首次访问 MC
```python
def mc_policy_evaluation(env, policy, num_episodes, gamma=0.99):
    V = defaultdict(float)
    returns = defaultdict(list)

    for _ in range(num_episodes):
        episode = generate_episode(env, policy)
        G = 0
        visited = set()

        for t in reversed(range(len(episode))):
            s, a, r = episode[t]
            G = gamma * G + r
            if s not in visited:
                returns[s].append(G)
                V[s] = np.mean(returns[s])
                visited.add(s)
    return V
```

## 5. 时序差分学习

### TD(0)
$$V(s) \leftarrow V(s) + \alpha [R + \gamma V(s') - V(s)]$$

### Q-Learning（Off-Policy）
```python
def q_learning(env, num_episodes, alpha=0.1, gamma=0.99, epsilon=0.1):
    Q = defaultdict(lambda: np.zeros(env.action_space.n))

    for _ in range(num_episodes):
        state = env.reset()
        done = False

        while not done:
            # ε-greedy 策略
            if np.random.random() < epsilon:
                action = env.action_space.sample()
            else:
                action = np.argmax(Q[state])

            next_state, reward, done, _ = env.step(action)

            # Q-Learning 更新
            best_next = np.max(Q[next_state])
            Q[state][action] += alpha * (reward + gamma * best_next - Q[state][action])

            state = next_state
    return Q
```

### SARSA（On-Policy）
$$Q(s,a) \leftarrow Q(s,a) + \alpha [R + \gamma Q(s',a') - Q(s,a)]$$

## 6. 深度强化学习

### DQN（Deep Q-Network）
```python
class DQN(nn.Module):
    def __init__(self, state_dim, action_dim):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(state_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 128),
            nn.ReLU(),
            nn.Linear(128, action_dim)
        )

    def forward(self, x):
        return self.network(x)
```

### Actor-Critic
- **Actor**：策略网络 $\pi_\theta(a|s)$
- **Critic**：值函数网络 $V_\phi(s)$

### PPO（Proximal Policy Optimization）
$$L^{CLIP}(\theta) = E_t[\min(r_t(\theta)A_t, \text{clip}(r_t(\theta), 1-\epsilon, 1+\epsilon)A_t)]$$

## 7. 金融 RL 应用

### 状态设计
```python
def get_state portfolio, market_data):
    """构建状态向量"""
    return {
        'positions': portfolio.positions,
        'cash': portfolio.cash,
        'prices': market_data.prices,
        'indicators': market_data.technical_indicators,
        'volatility': market_data.volatility
    }
```

### 动作空间
- **离散**：买入/卖出/持有
- **连续**：交易比例 [-1, 1]

### 奖励函数
```python
def reward_function(portfolio_value, prev_value, risk_penalty=0.1):
    """风险调整收益"""
    returns = (portfolio_value - prev_value) / prev_value
    # Sharpe-like reward
    return returns - risk_penalty * max(0, returns)
```

### 训练环境
```python
import gym

class TradingEnv(gym.Env):
    def __init__(self, prices, features, initial_cash=100000):
        self.prices = prices
        self.features = features
        self.initial_cash = initial_cash
        self.action_space = gym.spaces.Discrete(3)  # buy, hold, sell
        self.observation_space = gym.spaces.Box(
            low=-np.inf, high=np.inf, shape=(len(features[0])+2,)
        )

    def step(self, action):
        # 执行交易
        # 计算奖励
        # 更新状态
        return next_state, reward, done, info
```

## 8. 挑战与解决方案

| 挑战 | 说明 | 解决方案 |
|------|------|----------|
| 非平稳性 | 市场环境不断变化 | 在线学习、元学习 |
| 稀疏奖励 | 交易信号稀疏 | 奖励塑形、课程学习 |
| 样本效率 | 金融数据有限 | 模型-based RL、迁移学习 |
| 过拟合 | 历史数据有限 | 正则化、数据增强 |
| 信用分配 | 长期回报归因 | 蒙特卡洛方法、GAE |

## 9. 实践建议

| 建议 | 说明 |
|------|------|
| 从简单环境开始 | 先在合成数据上验证 |
| 奖励设计很重要 | 直接影响学习到的策略 |
| 课程学习 | 从简单到复杂逐步训练 |
| 多次随机种子 | RL 训练方差大 |
| 与传统方法结合 | RL 作为信号之一，非唯一 |
