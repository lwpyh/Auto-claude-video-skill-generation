# Auto-claude-video-skill-generation

[English](README.md) | 中文版

> 🎬 **Video VQA Skill 自主发现** —— Claude Code 自主探索帧采样策略与 Prompt 策略的最优组合，无需微调模型即可提升视频问答准确率。

基于 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 的自定义 Skills，用于自主发现视频 VQA 的最优输入策略。

---

## 🎬 Video VQA Skill 自主发现

> **"自动找出让视频问答模型准确率最高的帧采样 + Prompt 策略组合。"**

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
│   停止条件：最优 skill 增益 ≥ +5% AND Codex 评分为"sufficient"  │
└─────────────────────────────────────────────────────────────────┘
```

**什么是"Skill"：**
- 一个（帧策略, Prompt 策略）组合 —— 纯预处理，零微调
- **帧策略**：均匀采样、运动密集、关键帧、Slow-Fast、首尾采样……
- **Prompt 策略**：直接回答、思维链（CoT）、时序 CoT、逐选项分析、先描述再回答……
- Codex 每轮提出新的 Python 实现，agent 直接写入代码

**使用的模型：** Qwen2.5-VL-7B-Instruct（从不修改参数——只改输入）

---

## 🧰 Skills

| Skill | 功能 | 需要 Codex MCP？ |
|-------|------|--------------------|
| 🎬 [`video-skill-loop`](skills/video-skill-loop/SKILL.md) | 主协调器：Codex 评审 skill 设计，循环直到增益 ≥ +5% | 是 |
| 🔧 [`video-skill-implement`](skills/video-skill-implement/SKILL.md) | 把 Codex 提出的 Python 代码写入 skills.py 并验证 | 否 |
| 🚀 [`video-skill-run`](skills/video-skill-run/SKILL.md) | 提交 SLURM job + 监控进度 + 检测完成 | 否 |
| 📈 [`video-skill-analyze`](skills/video-skill-analyze/SKILL.md) | 解析 results.json → 准确率表、路由规则、反思候选 | 否 |

---

## ⚙️ 安装

### 前置条件

1. 安装 [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
2. 安装 [Codex CLI](https://github.com/openai/codex) 并配置为 MCP server：
   ```bash
   npm install -g @openai/codex
   claude mcp add codex -s user -- codex mcp-server
   ```
3. 有 SLURM 集群 + GPU + Qwen2.5-VL-7B-Instruct 模型缓存

### 安装 Skills

```bash
git clone https://github.com/lwpyh/Auto-claude-video-skill-generation.git
cd Auto-claude-video-skill-generation

cp -r skills/video-skill-loop ~/.claude/skills/
cp -r skills/video-skill-implement ~/.claude/skills/
cp -r skills/video-skill-run ~/.claude/skills/
cp -r skills/video-skill-analyze ~/.claude/skills/
```

### 用法

```
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

**Claude Code 负责执行**（读文件、写代码、提交任务、收结果），**外部 LLM 负责评估**（打分、找弱点、提出新实现）。两个模型互不评自己的作业，形成真实的反馈循环。

## 🎛️ 自定义

Skills 就是普通的 Markdown 文件，fork 后随意改：

- **`MAX_ROUNDS`** — 增加轮数上限（默认 4）
- **`POSITIVE_THRESHOLD`** — 调整停止条件（默认：增益 ≥ 5%）
- **帧/Prompt 策略** — 向 `lmms-eval/skill_learning/skills.py` 添加新策略函数
- **`allowed-tools`** — 限制或扩展每个 skill 可用的工具

## 📋 Roadmap

- [x] **Video VQA Skill 自主发现** — 无训练 VQA 提升，帧+Prompt 策略搜索
- [ ] **VideoMME 评估** — 在标准 benchmark 上验证最优 skill
- [ ] 更多 VLM backbone（LLaVA-Video、InternVL 等）

## License

MIT
