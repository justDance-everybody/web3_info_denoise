# 实验数据样本 (Test Data Sample)

本文件夹包含信息筛选实验的**精简数据样本**，用于验证技术附录中数据的真实性。

---

## 文件结构

```
test_data/
├── data/
│   ├── users/                    # 用户画像示例
│   │   ├── user_001.txt         # 预测市场套利交易者
│   │   └── user_003.txt         # 以太坊/Solana研究者
│   └── news/
│       └── 2026-01-18_compact.json   # 单日信息流（400+条）
│
├── schemes/                      # 筛选方案设计文档
│   ├── scheme_01_user_centric_deep_analysis.md
│   ├── scheme_03_blindspot_hunter.md
│   └── scheme_05_hybrid_code_ai_pipeline.md
│
└── experiments/
    ├── analysis/                 # 分析报告
    │   ├── comparison_report.md  # 方案对比报告
    │   └── efficiency_report.md  # 效率评估报告
    │
    └── results/                  # 实验结果示例（JSON）
        ├── scheme_1/user_001_2026-01-18.json
        ├── scheme_3/user_001_2026-01-18.json
        └── scheme_5/user_001_2026-01-18.json
```

---

## 数据说明

| 文件类型 | 数量 | 说明 |
|---------|------|------|
| 用户画像 | 2个 | 完整实验包含5个用户画像 |
| 原始信息 | 1天 | 完整实验包含3天数据（共2,373条）|
| 方案文档 | 3个 | 完整实验包含5种方案 |
| 实验结果 | 3个 | 完整实验包含75组结果 |

---

## 完整数据

完整实验数据位于项目根目录：
- 用户画像：`/data/users/` (5个)
- 信息数据：`/data/news/` (3天)
- 方案设计：`/schemes/` (5种)
- 实验结果：`/experiments/v3_cursor_lab/main/results/` (75组)

---

*本样本数据与技术附录 (TECHNICAL_APPENDIX_FOR_HACKATHON.md) 配套使用*
