# Auto-claude-video-skill-generation

[English](README.md) | 中文版

![分数曲线](auto_review_score_curve.png)

> 🌙 **让 Claude Code 在你睡觉时做科研。** 醒来发现论文已被打分、弱点已被定位、实验已跑完、叙事已重写——全自动。
>
> 🎬 **新增：Video VQA Skill 自主发现** —— Claude Code 自主探索帧采样策略与 Prompt 策略的最优组合，无需微调模型即可提升视频问答准确率。

基于 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 的自定义 Skills，用于自主 ML 科研工作流。核心机制是**跨模型协作**——Claude Code 负责执行（读文件、写代码、跑实验、收结果），外部 LLM（通过 [Codex MCP](https://github.com/openai/codex)）负责评审（打分、找弱点、建议修复）。两个模型互不评自己的作业，形成真正的反馈循环。

## 📈 真实运行效果

某 ML 研究项目上的 4 轮自动循环，从 borderline reject 到可投稿：

| 轮次 | 分数 | 发生了什么 |
|------|------|-----------|
| 初始 | 5.0/10 | Borderline reject |
| 第 1 轮 | 6.5/10 | 补了标准指标，发现指标脱钩 |
| 第 2 轮 | 6.8/10 | 核心声明不可复现，转换叙事 |
| 第 3 轮 | 7.0/10 | 大规模 seed 研究推翻了主要改善声明 |
| 第 4 轮 | **7.5/10** ✅ | 诊断证据确立，**可以投稿** |

循环自主跑了 **20+ 个 GPU 实验**，重写了论文叙事框架，杀掉了经不住检验的声明——全程无人干预。

---

## 🔄 三种工作流

### 工作流 1：自动科研循环 🔁（睡一觉醒来看结果）

> "帮我 review 论文，修复问题，循环到通过为止。"

**涉及 Skills：** `auto-review-loop` + `research-review` + `analyze-results` + `monitor-experiment`

```
外部 LLM 评审 → Claude Code 实现修复 → 跑实验 → 收结果 → 再评审 → 循环
```

用法：
```
> /auto-review-loop 我的 diffusion model 论文
```

**🛡️ 关键安全机制：**

- 🔒 **MAX_ROUNDS = 4** — 防止无限循环；达到分数阈值时提前停止
- ⏱️ **> 4 GPU-hour 的实验自动跳过** — 不会启动超大实验，标记为"需人工跟进"
- 🧠 **优先改叙事而非跑新实验** — 同样能解决问题时，选择成本更低的路径
- 🪞 **不隐藏弱点** — 明确规则："不要隐藏弱点来骗高分"
- 🔧 **先修后审** — 必须实现修复后再重新 review，不能只承诺修

📝 **博客：** [开源 | 睡觉 Claude 自动跑实验改文](http://xhslink.com/o/5cBMTDigNXz)

### 工作流 2：文献调研与找 Idea 🔍

> "这个领域最新进展是什么？哪里有 gap？"

**涉及 Skills：** `research-lit` + `research-review`

```
1. /research-lit "training-free video VQA improvement"  ← 搜论文，整理全景
2. 读完全景，发现一个 gap
3. /research-review "我的 idea 是用 X 来解决 Y"         ← 让外部 LLM 批判你的想法
4. 根据反馈迭代
```

📝 **博客：** [Claude Code 两月 NeurIPS 指北](http://xhslink.com/o/7IvAJQ41IBA)

### 工作流 3：Video VQA Skill 自主发现 🎬 *（新增）*

> "自动找出让视频问答模型准确率最高的帧采样 + Prompt 策略组合。"

```
┌─────────────────────────────────────────────────────────────────┐
│                  Video Skill 发现循环                            │
│                                                                  │
│   /video-skill-loop  （主协调器，调用 Codex MCP）                │
│         │                                                        │
│         ├──▶ /video-skill-implement  （把 Codex 提出的代码写入） │
│         ├──▶ /video-skill-run        （sbatch 提交 + 监控）      │
│         └──▶ /video-skill-analyze    （准确率表 + 路由规则）     │
│                                                                  │
│   每一轮：                                                        │
│   Codex 评审当前 skill 设计 + 实验结果                           │
│       → 提出新策略的 Python 实现代码                              │
│       → agent 写代码、提交 GPU job、收结果                        │
│       → 带新结果回 Codex 继续下一轮                               │
│                                                                  │
│   停止条件：最优 skill 增益 ≥ +5% AND Codex 评分 ≥ 6            │
└─────────────────────────────────────────────────────────────────┘
```

**涉及 Skills：** `video-skill-loop` + `video-skill-implement` + `video-skill-run` + `video-skill-analyze`

**什么是"Skill"：**
- 一个（帧策略, Prompt 策略）组合 —— 纯预处理，零微调
- **帧策略**：均匀采样、运动密集、关键帧、Slow-Fast、首尾采样……
- **Prompt 策略**：直接回答、思维链（CoT）、时序 CoT、逐选项分析、先描述再回答……
- Codex 每轮提出新的 Python 实现，agent 直接写入代码

**使用的模型：** Qwen2.5-VL-7B-Instruct（从不修改参数——只改输入）

**实验结果（job 816672，100 samples）：**

| Skill | 准确率 | vs 基线 |
|-------|--------|---------|
| uniform_32f（基线） | 70% | — |
| **pipeline_16_16** | **81%** | **+11%** |
| spatial_zoom_32f | 80% | +10% |
| multi_zoom_2segs | 78% | +8% |
| keyframe_32f | 0% | -70% ⚠️（Bug） |

---

## 🧰 全部 Skills

### 通用科研 Skills

| Skill | 功能 | 需要 Codex MCP？ |
|-------|------|-----------------|
| 🔬 [`research-review`](skills/research-review/SKILL.md) | 单轮深度评审（外部 LLM，xhigh 推理） | 是 |
| 🔁 [`auto-review-loop`](skills/auto-review-loop/SKILL.md) | 多轮自动 review→修复→再 review 循环（最多 4 轮） | 是 |
| 📚 [`research-lit`](skills/research-lit/SKILL.md) | 搜论文、分析相关工作、找研究空白 | 否 |
| 📊 [`analyze-results`](skills/analyze-results/SKILL.md) | 分析实验结果、统计、生成对比表 | 否 |
| 👀 [`monitor-experiment`](skills/monitor-experiment/SKILL.md) | 监控实验进度、收集结果 | 否 |

### Video VQA Skills *（新增）*

| Skill | 功能 | 需要 Codex MCP？ |
|-------|------|-----------------|
| 🎬 [`video-skill-loop`](skills/video-skill-loop/SKILL.md) | 主协调器：Codex 评审 skill 设计，循环直到增益 ≥ +5% | 是 |
| 🔧 [`video-skill-implement`](skills/video-skill-implement/SKILL.md) | 把 Codex 提出的 Python 代码写入 skills.py 并验证 | 否 |
| 🚀 [`video-skill-run`](skills/video-skill-run/SKILL.md) | 提交 SLURM job + 监控进度 + 检测完成 | 否 |
| 📈 [`video-skill-analyze`](skills/video-skill-analyze/SKILL.md) | 解析 results.json → 准确率表、路由规则、反思候选 | 否 |

---

## ⚙️ 安装

### 前置条件

1. 安装 [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
2. （仅 review 类 skill 需要）安装 [Codex CLI](https://github.com/openai/codex) 并配置为 MCP server：
   ```bash
   npm install -g @openai/codex
   claude mcp add codex -s user -- codex mcp-server
   ```
3. （仅 video skill 需要）有 SLURM 集群 + GPU + Qwen2.5-VL-7B-Instruct 模型缓存

### 安装 Skills

```bash
git clone https://github.com/lwpyh/Auto-claude-video-skill-generation.git
cd Auto-claude-video-skill-generation

# 安装全部 skills（全局可用）
cp -r skills/* ~/.claude/skills/

# 或只安装 Video VQA skills
cp -r skills/video-skill-loop ~/.claude/skills/
cp -r skills/video-skill-implement ~/.claude/skills/
cp -r skills/video-skill-run ~/.claude/skills/
cp -r skills/video-skill-analyze ~/.claude/skills/
```

### 用法

```
# 通用科研
> /research-lit discrete diffusion language models
> /auto-review-loop 我的 ML 论文
> /analyze-results figures/*.json

# Video VQA skill 发现
> /video-skill-loop start new loop
> /video-skill-analyze latest
> /video-skill-run submit and monitor
```

### 🌙 过夜自动运行的免确认配置（可选）

在 `.claude/settings.local.json` 中添加：

```json
{
  "permissions": {
    "allow": [
      "mcp__codex__codex",
      "mcp__codex__codex-reply",
      "Write",
      "Edit",
      "Bash(*)",
      "Skill(auto-review-loop)",
      "Skill(video-skill-loop)",
      "Skill(video-skill-implement)",
      "Skill(video-skill-run)",
      "Skill(video-skill-analyze)"
    ]
  }
}
```

## 🏗️ 运行原理

```
┌─────────────────────────────────────────────────┐
│                 Claude Code                      │
│                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐   │
│  │  读取结果  │    │  写新的  │    │  提交    │   │
│  │  和代码   │───▶│  skill  │───▶│  SLURM  │   │
│  │          │    │  代码    │    │  job    │   │
│  └──────────┘    └──────────┘    └──────────┘   │
│       │                               │          │
│       ▼                               ▼          │
│  ┌──────────────────────────────────────────┐    │
│  │         Codex MCP（外部 LLM）             │    │
│  │                                          │    │
│  │  第 1 轮："评分 4/10，建议加 CoT Prompt"  │    │
│  │  第 2 轮："评分 6/10，试试 Slow-Fast"    │    │
│  │  第 3 轮："评分 7/10，已足够。" ✅        │    │
│  └──────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

核心洞察：**Claude Code 负责执行**（读文件、写代码、提交任务、收结果），**外部 LLM 负责评估**（打分、找弱点、提出新实现）。两个模型互不评自己的作业，形成真实的反馈循环。

## 🎛️ 自定义

Skills 就是普通的 Markdown 文件，fork 后随意改：

- **`MAX_ROUNDS`** — 增加轮数上限（默认 4）
- **`POSITIVE_THRESHOLD`** — 调整停止条件（视频任务：增益 ≥ 5%；论文审稿：评分 ≥ 6）
- **帧/Prompt 策略** — 向 `lmms-eval/skill_learning/skills.py` 添加新策略函数
- **`allowed-tools`** — 限制或扩展每个 skill 可用的工具
- **Prompt 模板** — 定制 Codex 的评审人格和评估标准

## 📋 Roadmap

- [x] **Video VQA Skill 自主发现** — 无训练 VQA 提升，帧+Prompt 策略搜索
- [ ] **VideoMME 评估** — 在标准 benchmark 上验证最优 skill
- [ ] **GLM-5（执行者）+ Minimax-2.1（评审者）** — 与 Claude Code + Codex 平行的跨模型组合
- [ ] 更多执行者 × 评审者组合（Gemini、DeepSeek 等）

## 💬 交流群

欢迎加入微信群，交流 Claude Code + AI 科研工作流：

<img src="wechat_group.jpg" alt="微信交流群二维码" width="300">

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=lwpyh/Auto-claude-video-skill-generation&type=Date)](https://star-history.com/#lwpyh/Auto-claude-video-skill-generation&Date)

## License

MIT
