# 方案五：代码+AI混合流水线架构

## 1. 方案概述

**架构名称**: Hybrid Code-AI Pipeline (HCAP)

**核心理念**: 将筛选流程分为"可编程阶段"和"需AI判断阶段"，用代码处理确定性规则（关键词匹配、去重、格式化），用AI处理需要理解和推理的部分，实现效率与智能的最佳组合。

**一句话描述**: 代码做粗筛、AI做精选，各取所长、分层处理。

---

## 2. 差异化维度

| 维度 | 本方案选择 | 与其他方案对比 |
|------|-----------|--------------|
| **架构形态** | 代码+AI混合 (Code+AI Hybrid) | Python预处理+AI精选 |
| **筛选逻辑** | 淘汰制 (Elimination-based) | 层层过滤，漏斗式缩减 |
| 处理顺序 | 内容优先（代码阶段） | - |
| 价值权重 | 显性优先型 | - |
| 推理深度 | 浅度（代码）+ 中度（AI） | - |

---

## 3. 架构流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Stage 0: 输入准备                                    │
│  ┌───────────────────┐         ┌───────────────────┐                    │
│  │ user_profile.txt  │ ──────▶ │ 提取用户关键词    │ ──▶ keywords.json  │
│  └───────────────────┘  (Code) └───────────────────┘                    │
│                                                                          │
│  ┌───────────────────┐         ┌───────────────────┐                    │
│  │ news_list.json    │ ──────▶ │ 解析新闻数据      │ ──▶ parsed_news[]  │
│  └───────────────────┘  (Code) └───────────────────┘                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Stage 1: 代码快速过滤 (Code Layer)                   │
│                                                                          │
│  输入: 438条新闻                                                         │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Filter 1.1: 关键词匹配过滤                                       │    │
│  │ - 基于用户画像提取的关键词列表                                   │    │
│  │ - 匹配规则: 标题或内容包含任一关键词                             │    │
│  │ - 输出: 命中关键词的新闻 + 匹配关键词标记                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                         │                                                │
│                         ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Filter 1.2: 排斥词过滤                                           │    │
│  │ - 基于用户画像提取的排斥词列表                                   │    │
│  │ - 过滤规则: 包含排斥词的新闻直接淘汰                             │    │
│  │ - 例：User 001排斥"新手教程"、"纯宏观分析"                       │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                         │                                                │
│                         ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Filter 1.3: 内容去重                                             │    │
│  │ - 基于内容相似度(Jaccard/编辑距离)识别重复新闻                   │    │
│  │ - 保留每组重复中最长/来源最优的一条                              │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                         │                                                │
│                         ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Filter 1.4: 来源优先级排序                                       │    │
│  │ - 按来源可信度打分: The Block > Coindesk > Twitter               │    │
│  │ - 为每条新闻添加来源分数                                         │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  输出: ~100-150条候选新闻 (含关键词匹配分、来源分)                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Stage 2: AI智能精选 (AI Layer)                       │
│                                                                          │
│  输入: ~100-150条候选新闻 + 用户画像                                     │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ AI Task 2.1: 语义相关性评估                                      │    │
│  │ - 超越关键词匹配，理解语义关联                                   │    │
│  │ - 评估新闻与用户需求的深层相关性                                 │    │
│  │ - 输出: 语义相关分 (0-100)                                       │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                         │                                                │
│                         ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ AI Task 2.2: 三层价值评估                                        │    │
│  │ - 显性价值: 直接匹配用户明确需求                                 │    │
│  │ - 隐性价值: 逻辑关联但非直接匹配                                 │    │
│  │ - 盲区价值: 用户可能忽视但重要的信息                             │    │
│  │ - 输出: 三层得分 + 加权总分                                      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                         │                                                │
│                         ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ AI Task 2.3: 排序与选择                                          │    │
│  │ - 按加权总分排序                                                 │    │
│  │ - 选出Top 20                                                     │    │
│  │ - 生成推荐理由                                                   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  输出: 20条最终推荐 + 评分明细 + 推荐理由                               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Stage 3: 结果输出                                    │
│                                                                          │
│  格式化输出最终结果                                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 核心实现

### 4.1 代码层实现 (Python)

```python
"""
Hybrid Code-AI Pipeline - Code Layer
Stage 1: 代码快速过滤
"""
import json
import re
from collections import defaultdict
from difflib import SequenceMatcher

class CodeFilterPipeline:
    """代码层过滤流水线"""

    def __init__(self, user_profile_path: str, news_list_path: str):
        self.user_profile = self._load_user_profile(user_profile_path)
        self.news_list = self._load_news_list(news_list_path)
        self.keywords = []
        self.exclusions = []
        self.source_priority = {
            "The Block Beats": 5,
            "Cointelegraph": 5,
            "CoinDesk": 5,
            "DeFi Rate": 4,
            "Event Horizon": 3,
            "Prediction News": 3,
            "@Twitter Bundle 1": 2,
            "@Twitter Bundle 2": 2,
        }

    def _load_user_profile(self, path: str) -> str:
        """加载用户画像"""
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def _load_news_list(self, path: str) -> list:
        """加载新闻列表"""
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def extract_keywords_from_profile(self) -> dict:
        """
        从用户画像中提取关键词和排斥词
        注意: 这个方法可以用AI辅助，也可以用规则提取
        返回: {"keywords": [...], "exclusions": [...]}
        """
        # 示例关键词提取规则 (可根据实际用户画像调整)
        # 实际使用时建议用AI一次性提取

        profile_lower = self.user_profile.lower()

        # 通用加密货币关键词
        crypto_keywords = [
            "polymarket", "kalshi", "prediction market", "预测市场",
            "arbitrage", "套利", "价差", "spread",
            "defi", "uniswap", "aave", "compound",
            "ethereum", "eth", "solana", "sol", "btc", "bitcoin",
            "layer2", "l2", "rollup", "zk",
            "nft", "opensea", "blur",
            "stablecoin", "usdt", "usdc", "dai",
            "tvl", "apy", "yield", "收益",
            "hack", "exploit", "漏洞", "攻击",
            "sec", "cftc", "监管", "regulation",
            "liquidity", "流动性", "做市",
            "oracle", "chainlink", "预言机",
            "bridge", "跨链",
        ]

        # 根据用户画像筛选相关关键词
        self.keywords = [kw for kw in crypto_keywords
                        if kw in profile_lower or self._is_related_to_profile(kw)]

        # 排斥词 (从用户画像的"不喜欢"部分提取)
        self.exclusions = []
        if "新手" in self.user_profile or "教程" in self.user_profile:
            self.exclusions.extend(["新手教程", "入门指南", "beginner"])

        return {
            "keywords": self.keywords,
            "exclusions": self.exclusions
        }

    def _is_related_to_profile(self, keyword: str) -> bool:
        """判断关键词是否与用户画像相关 (简单规则)"""
        # 这里可以添加更复杂的关联规则
        return False

    def filter_by_keywords(self, news_list: list) -> list:
        """
        Filter 1.1: 关键词匹配过滤
        返回匹配任一关键词的新闻，并标记匹配的关键词
        """
        filtered = []
        for news in news_list:
            text = news.get('t', '').lower()
            matched_keywords = [kw for kw in self.keywords if kw.lower() in text]
            if matched_keywords:
                news['_matched_keywords'] = matched_keywords
                news['_keyword_score'] = len(matched_keywords) * 10  # 每个关键词10分
                filtered.append(news)
        return filtered

    def filter_by_exclusions(self, news_list: list) -> list:
        """
        Filter 1.2: 排斥词过滤
        排除包含排斥词的新闻
        """
        filtered = []
        for news in news_list:
            text = news.get('t', '').lower()
            has_exclusion = any(exc.lower() in text for exc in self.exclusions)
            if not has_exclusion:
                filtered.append(news)
        return filtered

    def deduplicate(self, news_list: list, threshold: float = 0.8) -> list:
        """
        Filter 1.3: 内容去重
        使用Jaccard相似度识别重复内容
        """
        if not news_list:
            return []

        # 按来源优先级排序，保证优先保留高质量来源
        sorted_news = sorted(news_list,
                           key=lambda x: self.source_priority.get(x.get('src', ''), 1),
                           reverse=True)

        kept = []
        seen_texts = []

        for news in sorted_news:
            text = news.get('t', '')
            is_duplicate = False

            for seen in seen_texts:
                similarity = SequenceMatcher(None, text, seen).ratio()
                if similarity > threshold:
                    is_duplicate = True
                    break

            if not is_duplicate:
                kept.append(news)
                seen_texts.append(text)

        return kept

    def add_source_scores(self, news_list: list) -> list:
        """
        Filter 1.4: 添加来源分数
        """
        for news in news_list:
            source = news.get('src', '')
            news['_source_score'] = self.source_priority.get(source, 1)
        return news_list

    def run_code_layer(self) -> dict:
        """
        执行完整的代码层过滤流水线
        返回过滤后的候选新闻和统计信息
        """
        # 提取关键词
        keywords_info = self.extract_keywords_from_profile()

        # 执行过滤流水线
        step1 = self.filter_by_keywords(self.news_list)
        step2 = self.filter_by_exclusions(step1)
        step3 = self.deduplicate(step2)
        step4 = self.add_source_scores(step3)

        # 按预计算分数排序
        candidates = sorted(step4,
                          key=lambda x: x.get('_keyword_score', 0) + x.get('_source_score', 0),
                          reverse=True)

        return {
            "keywords_extracted": keywords_info,
            "pipeline_stats": {
                "input_count": len(self.news_list),
                "after_keyword_filter": len(step1),
                "after_exclusion_filter": len(step2),
                "after_dedup": len(step3),
                "final_candidates": len(candidates)
            },
            "candidates": candidates
        }


# 使用示例
if __name__ == "__main__":
    pipeline = CodeFilterPipeline(
        user_profile_path="user/user_001.txt",
        news_list_path="news test data/2026-01-18_compact.json"
    )
    result = pipeline.run_code_layer()
    print(f"从 {result['pipeline_stats']['input_count']} 条新闻筛选出 "
          f"{result['pipeline_stats']['final_candidates']} 条候选")
```

### 4.2 AI层Prompt

```markdown
# 角色定义
你是一位精准的信息价值评估专家。你将收到经过代码预筛选的候选新闻列表（已过滤明显无关内容），你的任务是进行精细化评估并选出最终的20条推荐。

# 背景
这些候选新闻已经通过代码层的以下过滤：
- 关键词匹配：包含与用户相关的关键词
- 排斥词过滤：不包含用户明确排斥的内容
- 内容去重：已移除重复或高度相似的新闻
- 来源评分：已标记来源可信度

现在需要你进行语义级别的深度评估。

# 输入

## 用户画像
<用户画像>
{user_profile}
</用户画像>

## 预筛选结果
<代码层筛选统计>
{pipeline_stats}
</代码层筛选统计>

## 候选新闻列表
以下新闻已包含代码层添加的元数据：
- _matched_keywords: 匹配的关键词列表
- _keyword_score: 关键词匹配分数
- _source_score: 来源可信度分数

<候选新闻>
{candidates}
</候选新闻>

# 任务

## Step 1: 语义相关性评估
对每条候选新闻，评估其与用户需求的语义相关性：
- 不仅看关键词匹配，还要理解语义含义
- 考虑新闻的实际内容是否对用户有价值
- 语义相关分: 0-100

## Step 2: 三层价值评估
对每条候选新闻评估三层价值：

### 显性价值 (0-100)
- 直接匹配用户明确表述的需求
- 用户主动寻找的信息类型
- 可直接指导用户决策或行动

### 隐性价值 (0-100)
- 与用户需求有逻辑关联但非直接匹配
- 上下游依赖关系带来的价值
- 需要一步推理才能发现的关联

### 盲区价值 (0-100)
- 用户可能忽视但实际重要的信息
- 规则改变者、风险预警、新兴机会
- 用户不知道自己需要知道的

### 加权总分计算
```
总分 = 语义相关分 × 0.20 + 显性价值 × 0.35 + 隐性价值 × 0.25 + 盲区价值 × 0.20
```

## Step 3: 排序与选择
1. 按加权总分降序排列
2. 选出分数最高的20条
3. 确保选择多样性（不要过度集中在某一主题）

# 输出格式

```json
{
  "evaluation_summary": {
    "candidates_evaluated": 评估的候选数,
    "avg_semantic_score": 平均语义相关分,
    "high_value_count": 高价值新闻数(总分>70)
  },

  "detailed_evaluation": [
    {
      "n": 新闻编号,
      "code_layer_scores": {
        "keyword_score": 来自代码层,
        "source_score": 来自代码层
      },
      "ai_layer_scores": {
        "semantic_relevance": 语义相关分,
        "explicit_value": 显性价值分,
        "implicit_value": 隐性价值分,
        "blindspot_value": 盲区价值分,
        "total": 加权总分
      },
      "selected": true/false
    },
    ...
  ],

  "final_selection": [
    {
      "rank": 排名,
      "n": 新闻编号,
      "total_score": 总分,
      "primary_value_type": "explicit/implicit/blindspot",
      "recommendation_reason": "推荐理由（2-3句话）"
    },
    ...
  ],

  "diversity_check": {
    "topics_covered": ["主题1", "主题2", ...],
    "value_type_distribution": {
      "explicit_heavy": 数量,
      "implicit_heavy": 数量,
      "blindspot_heavy": 数量
    }
  }
}
```
```

---

## 5. 方案特点

### 优势
1. **效率优化**：代码层快速过滤掉明显无关新闻，减少AI处理量
2. **成本控制**：AI只处理约1/3-1/4的新闻，降低API调用成本
3. **确定性保证**：关键词匹配、去重等确定性规则由代码保证
4. **可调试性强**：代码层问题可以精确定位和修复
5. **分层优化**：代码层和AI层可以独立优化

### 局限
1. **关键词覆盖限制**：过度依赖关键词可能遗漏语义相关但词汇不同的新闻
2. **两阶段延迟**：需要先完成代码层才能开始AI层
3. **代码维护成本**：需要维护关键词列表和过滤规则
4. **漏斗过度收紧风险**：代码层过滤过于激进可能导致漏选

### 适用场景
- 新闻量大、需要高效处理的场景
- 成本敏感的生产环境
- 有明确关键词列表的用户
- 需要可审计、可调试的筛选流程

---

## 6. 评估指标

| 指标 | 预期表现 | 测量方法 |
|------|---------|---------|
| 代码层过滤率 | 60-75% | 过滤掉的新闻占比 |
| 候选质量 | >80% | 候选中最终入选的比例 |
| AI调用成本节省 | >60% | 相比全量AI处理的成本减少 |
| 漏选率 | <5% | 被代码层错误过滤的高价值新闻 |
| 端到端延迟 | 中低 | 完整处理一批新闻的时间 |

---

## 7. 流水线配置选项

```python
# 流水线配置示例
PIPELINE_CONFIG = {
    # 代码层配置
    "code_layer": {
        "keyword_min_match": 1,          # 最少匹配关键词数
        "dedup_threshold": 0.8,          # 去重相似度阈值
        "max_candidates": 150,           # 最多传递给AI层的候选数
        "source_boost": True,            # 是否启用来源加分
    },

    # AI层配置
    "ai_layer": {
        "model": "claude-3-opus",        # 使用的模型
        "temperature": 0.3,              # 生成温度
        "value_weights": {               # 价值权重
            "semantic": 0.20,
            "explicit": 0.35,
            "implicit": 0.25,
            "blindspot": 0.20
        },
        "min_score_threshold": 40,       # 最低入选分数
        "output_count": 20,              # 最终输出数量
    },

    # 关键词配置
    "keywords": {
        "extraction_method": "ai",       # "ai" 或 "rule"
        "update_frequency": "daily",     # 关键词更新频率
        "include_synonyms": True,        # 是否包含同义词
    }
}
```

---

## 8. 变体与调优建议

1. **关键词动态更新**：用AI定期分析用户反馈，更新关键词列表
2. **软过滤模式**：代码层不直接淘汰，而是给低分，让AI做最终决定
3. **并行处理**：代码层分批处理，边处理边传递给AI层
4. **缓存优化**：缓存新闻分类结果，对同一新闻只做一次分类
5. **A/B测试**：对比纯AI方案和混合方案的效果，找到最优配置
