"""
电气网络拓扑 + 通信图

电气网络: 基于导纳矩阵构建加权 Laplacian 矩阵 L (Eq. 3)
通信网络: 环形拓扑, 支持随机链路故障
"""

import numpy as np


def build_laplacian(B, V):
    """
    构建加权 Laplacian 矩阵 L (论文 Eq. 3).

    L[i,j] = -V_i * V_j * B[i,j]   (i ≠ j)
    L[i,i] = Σ_j V_i * V_j * B[i,j]

    Parameters
    ----------
    B : np.ndarray, shape (N, N)
        导纳矩阵 (对称, 对角为0)
    V : np.ndarray, shape (N,)
        母线电压幅值 (标幺值)

    Returns
    -------
    L : np.ndarray, shape (N, N)
        加权 Laplacian 矩阵
    """
    N = len(V)
    L = np.zeros((N, N))
    for i in range(N):
        row_sum = 0.0
        for j in range(N):
            if i != j:
                w = V[i] * V[j] * B[i, j]
                L[i, j] = -w
                row_sum += w
        L[i, i] = row_sum
    return L


class CommunicationGraph:
    """通信网络管理器, 支持随机链路故障."""

    def __init__(self, adjacency, fail_prob=0.1):
        """
        Parameters
        ----------
        adjacency : dict[int, list[int]]
            邻居列表, 如 {0:[1,3], 1:[0,2], 2:[1,3], 3:[2,0]}
        fail_prob : float
            每条链路每 episode 故障概率
        """
        self.adjacency = adjacency
        self.fail_prob = fail_prob
        self.N = len(adjacency)
        # 链路状态: eta[(i,j)] = 1 (正常) 或 0 (故障)
        self.eta = {}
        self.reset()

    def reset(self, rng=None):
        """重置链路状态, 随机生成故障."""
        if rng is None:
            rng = np.random.default_rng()
        self.eta = {}
        for i, neighbors in self.adjacency.items():
            for j in neighbors:
                # 对称链路: 如果 (j,i) 已设置, 复用
                if (j, i) in self.eta:
                    self.eta[(i, j)] = self.eta[(j, i)]
                else:
                    self.eta[(i, j)] = 0 if rng.random() < self.fail_prob else 1

    def reset_no_failure(self):
        """重置为所有链路正常 (用于测试)."""
        self.eta = {}
        for i, neighbors in self.adjacency.items():
            for j in neighbors:
                self.eta[(i, j)] = 1

    def get_neighbors(self, agent_i):
        """返回 agent_i 的邻居列表."""
        return self.adjacency[agent_i]

    def is_link_active(self, i, j):
        """检查链路 (i,j) 是否正常."""
        return self.eta.get((i, j), 0) == 1

    def get_active_neighbor_count(self, agent_i):
        """返回 agent_i 的活跃邻居数."""
        return sum(self.is_link_active(agent_i, j)
                   for j in self.adjacency[agent_i])
