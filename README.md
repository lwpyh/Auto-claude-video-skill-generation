# Auto-claude-video-skill-generation

[中文版 README](README_CN.md) | English

> 🎬 **Video VQA Skill Discovery** — Claude Code autonomously discovers frame sampling + prompting strategies that improve video QA accuracy, with zero model fine-tuning.
>
> 🌙 **Auto Research Loop** — Let Claude Code review your paper, fix weaknesses, and iterate overnight via Codex MCP.

Custom [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skills for autonomous ML research workflows. These skills orchestrate **cross-model collaboration** — Claude Code drives the research while an external LLM (via [Codex MCP](https://github.com/openai/codex)) acts as a critical reviewer.

---

## 🔄 Workflows

### Workflow 1: Auto Research Loop 🔁 (sleep & wake up to results)

> **"Review my paper, fix what's wrong, repeat until it's good."**

```
┌─────────────────────────────────────────────────────────────┐
│                    Auto Review Loop                          │
│                                                              │
│   /research-review          /auto-review-loop                │
│   (single deep review)      (autonomous loop)                │
│         │                         │                          │
│         ▼                         ▼                          │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐               │
│   │ External  │──▶│ Implement│──▶│ Monitor  │──▶ repeat     │
│   │ LLM      │   │ fixes    │   │ results  │    until       │
│   │ reviews  │   │ & run    │   │          │    score ≥ 6   │
│   └──────────┘   │ experiments│  └──────────┘               │
│                   └──────────┘                               │
│   Supporting skills:                                         │
│   /analyze-results  — interpret experiment outputs           │
│   /monitor-experiment — check progress, collect results      │
└─────────────────────────────────────────────────────────────┘
```

**Skills involved:** `auto-review-loop` + `research-review` + `analyze-results` + `monitor-experiment`

**🛡️ Key safety features:**

- 🔒 **MAX_ROUNDS = 4** — prevents infinite loops; stops early if score threshold is met
- ⏱️ **> 4 GPU-hour experiments skipped** — won't launch massive jobs; flags them for manual follow-up
- 🧠 **Prefer reframing over new experiments** — when both can address a weakness, chooses the cheaper path
- 🪞 **No hiding weaknesses** — explicit rule: "Do NOT hide weaknesses to game a positive score"
- 🔧 **Fix before re-review** — must actually implement fixes before resubmitting; no empty promises

### Workflow 2: Literature & Idea Discovery 🔍

> **"What's the state of the art? Where are the gaps?"**

```
1. /research-lit "training-free video VQA improvement"   ← search & survey
2. Read landscape, spot a gap
3. /research-review "my idea to fix X using Y"           ← external LLM critiques
4. Iterate on the idea with critical feedback
```

**Skills involved:** `research-lit` + `research-review`

### Workflow 3: Video VQA Skill Discovery 🎬

> **"Find which video sampling + prompting strategies improve my VLM's accuracy — automatically."**

```
┌─────────────────────────────────────────────────────────────────┐
│                  Video Skill Discovery Loop                      │
│                                                                  │
│   /video-skill-loop  (orchestrator, uses Codex MCP)             │
│         │                                                        │
│         ├──▶ /video-skill-implement  (write new skills.py code) │
│         ├──▶ /video-skill-run        (sbatch + monitor SLURM)   │
│         └──▶ /video-skill-analyze    (accuracy table + routing) │
│                                                                  │
│   Each round:                                                    │
│   Codex reviews skill design + results                          │
│       → proposes Python implementations of new strategies        │
│       → agent writes code, submits GPU job, collects results     │
│       → feeds results back to Codex for next round              │
│                                                                  │
│   Stops when: best skill gain ≥ +5% vs baseline                 │
│               AND Codex verdict = "sufficient"                   │
└─────────────────────────────────────────────────────────────────┘
```

**Skills involved:** `video-skill-loop` + `video-skill-implement` + `video-skill-run` + `video-skill-analyze`

**What a "skill" is:**
- A (frame_strategy, prompt_strategy) pair — pure preprocessing, zero fine-tuning
- Frame strategies: uniform sampling, motion-dense, keyframe, slow-fast, first-last, ...
- Prompt strategies: direct, chain-of-thought, temporal CoT, option-focus, describe-first, ...
- Codex proposes new Python implementations each round; agent writes them directly into code

**Model used:** Qwen2.5-VL-7B-Instruct (never modified — only the input changes)

**Experiment results (job 816672, 100 samples):**

| Skill | Acc | vs Baseline |
|-------|-----|-------------|
| uniform_32f (baseline) | 70% | — |
| **pipeline_16_16** | **81%** | **+11%** |
| spatial_zoom_32f | 80% | +10% |
| multi_zoom_2segs | 78% | +8% |
| keyframe_32f | 0% | -70% ⚠️ (bug) |

---

## 🧰 All Skills

### General Research Skills

| Skill | Description | Needs Codex MCP? |
|-------|-------------|-----------------|
| 🔬 [`research-review`](skills/research-review/SKILL.md) | Single-round deep review from external LLM (xhigh reasoning) | Yes |
| 🔁 [`auto-review-loop`](skills/auto-review-loop/SKILL.md) | Autonomous multi-round review→fix→re-review loop (max 4 rounds) | Yes |
| 📚 [`research-lit`](skills/research-lit/SKILL.md) | Search papers, analyze related work, find research gaps | No |
| 📊 [`analyze-results`](skills/analyze-results/SKILL.md) | Analyze experiment results, compute statistics, generate insights | No |
| 👀 [`monitor-experiment`](skills/monitor-experiment/SKILL.md) | Monitor running experiments, check progress, collect results | No |

### Video VQA Skills *(New)*

| Skill | Description | Needs Codex MCP? |
|-------|-------------|-----------------|
| 🎬 [`video-skill-loop`](skills/video-skill-loop/SKILL.md) | Orchestrator: Codex reviews skill design, iterates until gain ≥ +5% | Yes |
| 🔧 [`video-skill-implement`](skills/video-skill-implement/SKILL.md) | Write Codex-proposed Python skill code into skills.py + validate | No |
| 🚀 [`video-skill-run`](skills/video-skill-run/SKILL.md) | Submit SLURM job + monitor progress + detect completion | No |
| 📈 [`video-skill-analyze`](skills/video-skill-analyze/SKILL.md) | Parse results.json → accuracy table, routing rules, reflection candidates | No |

---

## ⚙️ Setup

### Prerequisites

1. [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed
2. (For review skills) [Codex CLI](https://github.com/openai/codex) installed and configured as MCP server:
   ```bash
   npm install -g @openai/codex
   claude mcp add codex -s user -- codex mcp-server
   ```
3. (For video skills) SLURM cluster with GPU + Qwen2.5-VL-7B-Instruct in HuggingFace cache

### Install Skills

```bash
git clone https://github.com/lwpyh/Auto-claude-video-skill-generation.git
cd Auto-claude-video-skill-generation

# Install all skills globally
cp -r skills/* ~/.claude/skills/

# Or install only video VQA skills
cp -r skills/video-skill-loop ~/.claude/skills/
cp -r skills/video-skill-implement ~/.claude/skills/
cp -r skills/video-skill-run ~/.claude/skills/
cp -r skills/video-skill-analyze ~/.claude/skills/
```

### Usage

```
# General research
> /research-lit discrete diffusion language models
> /research-review my paper on training dynamics in D-LLMs
> /auto-review-loop ML paper on factorized gap diagnosis
> /analyze-results figures/*.json
> /monitor-experiment server5

# Video VQA skill discovery
> /video-skill-loop start new loop
> /video-skill-analyze latest
> /video-skill-run submit and monitor
```

### 🌙 Auto-Allow for Overnight Runs (Optional)

To run loops without clicking permission prompts, add to `.claude/settings.local.json`:

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

## 🏗️ How It Works

```
┌─────────────────────────────────────────────────┐
│                 Claude Code                      │
│                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐   │
│  │  Read     │    │  Write   │    │  Submit  │   │
│  │  results  │───▶│  new     │───▶│  SLURM   │   │
│  │  + code   │    │  skills  │    │  job     │   │
│  └──────────┘    └──────────┘    └──────────┘   │
│       │                               │          │
│       ▼                               ▼          │
│  ┌──────────────────────────────────────────┐    │
│  │         Codex MCP (External LLM)         │    │
│  │                                          │    │
│  │  Round 1: "Score 4/10. Add CoT prompts"  │    │
│  │  Round 2: "Score 6/10. Try slow-fast"    │    │
│  │  Round 3: "Score 7/10. Sufficient." ✅   │    │
│  └──────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

The key insight: **Claude Code handles execution** (reading files, writing code, submitting jobs, collecting results) while **the external LLM handles evaluation** (scoring, identifying weaknesses, proposing new implementations). Neither model grades its own work.

## 🎛️ Customization

Skills are plain Markdown files. Fork and customize:

- **`MAX_ROUNDS`** — increase for more thorough iteration (default: 4)
- **`POSITIVE_THRESHOLD`** — adjust stop condition (default: gain ≥ +5% for video, score ≥ 6 for paper review)
- **Frame/prompt strategies** — add new strategies to `lmms-eval/skill_learning/skills.py`
- **`allowed-tools`** — restrict or expand what each skill can do
- **Prompt templates** — tailor the Codex review persona and evaluation criteria

## 📋 Roadmap

- [x] **Video VQA Skill Discovery** — training-free improvement via frame+prompt skill search
- [ ] **VideoMME evaluation** — validate best skills on standard benchmark
- [ ] **GLM-5 (executor) + Minimax-2.1 (reviewer)** — alternative cross-model pair
- [ ] More executor × reviewer combinations (Gemini, DeepSeek, etc.)

## License

MIT
