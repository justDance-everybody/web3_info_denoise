# Web3 信息降噪系统 - 技术验证文档

> AI-Native Information Filtering System for Web3

本仓库包含我们信息筛选系统的**技术验证文档**和**实验数据**，展示了我们如何通过系统性实验优化AI信息筛选能力。

---

## 核心亮点

- **75组科学实验**：5种筛选架构 × 5个用户画像 × 3天数据
- **2,373条真实数据**：基于真实Web3信息流的验证
- **量化效果验证**：
  - 位置偏差降低 **80%**
  - 有价值信息发现率提升 **192%**
  - 最优方案价值提取效率达 **76.91%**

---

## 文档结构

| 文件 | 说明 |
|------|------|
| [TECHNICAL_APPENDIX_FOR_HACKATHON.md](./TECHNICAL_APPENDIX_FOR_HACKATHON.md) | **主文档** - 面向非技术读者的技术介绍 |
| [EXPERIMENT_REPORT.md](./EXPERIMENT_REPORT.md) | 详细技术报告 |
| [test_data/](./test_data/) | 实验数据样本（可验证） |

---

## 技术架构概览

```
用户需求 → 多阶段流水线架构 → 高价值信息输出
              │
              ├─ 阶段0: 去偏差预处理 (Debiasing)
              ├─ 阶段1: 粗筛过滤 (400→80条)
              ├─ 阶段2: 多维度评分 (显性/隐性/盲区价值)
              └─ 阶段3: 多样性调整
```

---

## 关键技术

- **Multi-Stage Pipeline Architecture** - 多阶段流水线架构
- **Three-dimensional Value Assessment** - 三维价值评估模型
- **Systematic Bias Elimination** - 系统性偏差消除
- **Multi-hop Reasoning** - 多跳推理发现隐藏价值
- **Multi-Agent Collaboration** - 多智能体协作

---

## 快速了解

1. 阅读 [TECHNICAL_APPENDIX_FOR_HACKATHON.md](./TECHNICAL_APPENDIX_FOR_HACKATHON.md) 了解我们的方法
2. 查看 [test_data/](./test_data/) 验证数据真实性
3. 深入阅读 [EXPERIMENT_REPORT.md](./EXPERIMENT_REPORT.md) 了解技术细节

---

*本项目所有实验由 AI 协助完成，体现 Human-AI 协作范式*
