# Web3 信息降噪系统 (Web3 Info Denoise)

> AI 驱动的 Web3 个性化信息聚合服务

每天自动抓取并筛选 Web3 信息，通过 AI 生成符合你偏好的个性化简报，节省 2+ 小时阅读时间。

---

## 核心特性

### AI 个性化筛选
- 3 轮 AI 对话式注册，深度理解用户偏好
- 两步处理流程：筛选（英文 prompt）→ 翻译（语言适配）
- 4 层内容分级：必读事件 / 行业大局 / 用户推荐 / 其他更新
- 跨源内容去重 + 来源多样性保证

### 智能反馈闭环
- 整体反馈（有帮助/没帮助）
- 单条反馈（👍/不感兴趣 按钮）
- 动态更新用户画像，用户越用越精准

### 多信息源聚合
- Twitter 账号监控（通过 RSS 转换）
- 网站 RSS 订阅（支持自动检测）
- 每用户独立信息源配置

---

## 项目结构

```
web3_info_denoise/
├── bot/                          # Telegram Bot 核心代码
│   ├── main.py                   # 入口 + 定时任务
│   ├── config.py                 # 环境变量配置
│   ├── handlers/                 # 用户交互层
│   ├── services/                 # 业务逻辑层
│   ├── prompts/                  # Prompt 模板
│   └── utils/                    # 工具层
│
├── test_data/                    # 实验数据样本
├── TECHNICAL_APPENDIX_FOR_HACKATHON.md   # 技术验证文档
├── EXPERIMENT_REPORT.md          # 详细实验报告
├── 产品需求文档_PRD_Final.md       # 产品需求文档
├── 测试用例与验收标准_Test_Cases.md # 测试用例
└── docker-compose.yml            # Docker 部署配置
```

---

## 技术亮点

我们不是简单的"套壳"产品。通过 **75组科学实验**，我们验证并优化了 AI 信息筛选能力：

| 指标 | 效果 |
|------|------|
| 位置偏差 | 降低 **80%** |
| 有价值信息发现率 | 提升 **192%** |
| 价值提取效率 | **76.91%** |

详见 [技术验证文档](./TECHNICAL_APPENDIX_FOR_HACKATHON.md)

---

## 技术栈

| 技术层 | 选型 | 说明 |
|--------|------|------|
| **LLM 引擎** | Gemini / OpenAI | 支持多 LLM 提供商 |
| **Bot 框架** | python-telegram-bot v22.0 | 官方推荐库 |
| **RSS 抓取** | feedparser + httpx | 异步抓取 + 自动去重 |
| **部署** | Docker Compose | 一键部署 |

---

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/justDance-everybody/web3_info_denoise.git
cd web3_info_denoise
```

### 2. 配置环境变量

```bash
cp bot/.env.example bot/.env
# 编辑 bot/.env，填写必要配置
```

### 3. Docker 部署

```bash
docker compose up -d
```

---

## 文档索引

| 文档 | 说明 |
|------|------|
| [TECHNICAL_APPENDIX_FOR_HACKATHON.md](./TECHNICAL_APPENDIX_FOR_HACKATHON.md) | **技术验证文档**（面向评委） |
| [EXPERIMENT_REPORT.md](./EXPERIMENT_REPORT.md) | 详细实验报告 |
| [test_data/](./test_data/) | 实验数据样本 |
| [产品需求文档_PRD_Final.md](./产品需求文档_PRD_Final.md) | 产品需求文档 |
| [测试用例与验收标准_Test_Cases.md](./测试用例与验收标准_Test_Cases.md) | 测试用例 |

---

## 核心数据流

```
用户注册 → AI 对话收集偏好 → 配置信息源
                                    ↓
                            【每小时】预抓取 + 去重缓存
                                    ↓
                            【09:00】AI 筛选 + 语言适配
                                    ↓
                            Telegram 推送简报
                                    ↓
    用户反馈 → 每日更新画像 ──────────┘
```

---

## License

MIT
