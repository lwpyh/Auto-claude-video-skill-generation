# Auto-claude-video-skill-generation

[中文版 README](README_CN.md) | English

> 🎬 **Video VQA Skill Discovery** — Claude Code autonomously discovers frame sampling + prompting strategies that improve video QA accuracy, with zero model fine-tuning.

Custom [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skills for autonomous video VQA improvement. Claude Code drives the skill search while an external LLM (via [Codex MCP](https://github.com/openai/codex)) acts as a critical reviewer proposing new implementations each round.

---

## 🎬 Video VQA Skill Discovery

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

**What a "skill" is:**
- A (frame_strategy, prompt_strategy) pair — pure preprocessing, zero fine-tuning
- **Frame strategies**: uniform sampling, motion-dense, keyframe, slow-fast, first-last, ...
- **Prompt strategies**: direct, chain-of-thought, temporal CoT, option-focus, describe-first, ...
- Codex proposes new Python implementations each round; agent writes them directly into code

**Model:** Qwen2.5-VL-7B-Instruct (never modified — only the input changes)

---

## 🧰 Skills

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
2. [Codex CLI](https://github.com/openai/codex) installed and configured as MCP server:
   ```bash
   npm install -g @openai/codex
   claude mcp add codex -s user -- codex mcp-server
   ```
3. SLURM cluster with GPU + Qwen2.5-VL-7B-Instruct in HuggingFace cache

### Install Skills

```bash
git clone https://github.com/lwpyh/Auto-claude-video-skill-generation.git
cd Auto-claude-video-skill-generation

cp -r skills/video-skill-loop ~/.claude/skills/
cp -r skills/video-skill-implement ~/.claude/skills/
cp -r skills/video-skill-run ~/.claude/skills/
cp -r skills/video-skill-analyze ~/.claude/skills/
```

### Usage

```
> /video-skill-loop start new loop
> /video-skill-analyze latest
> /video-skill-run submit and monitor
```

### 🌙 Auto-Allow for Overnight Runs (Optional)

Add to `.claude/settings.local.json`:

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

**Claude Code handles execution** (writing code, submitting jobs, collecting results) while **Codex handles evaluation** (scoring skill design, proposing new implementations). Neither model grades its own work.

## 🎛️ Customization

Skills are plain Markdown files — fork and customize:

- **`MAX_ROUNDS`** — iteration limit (default: 4)
- **`POSITIVE_THRESHOLD`** — stop condition (default: gain ≥ +5%)
- **Frame/prompt strategies** — add new functions to `lmms-eval/skill_learning/skills.py`
- **`allowed-tools`** — restrict or expand what each skill can do

## 📋 Roadmap

- [x] Video VQA Skill Discovery — training-free improvement via frame+prompt skill search
- [ ] VideoMME evaluation — validate best skills on standard benchmark
- [ ] More VLM backbones (LLaVA-Video, InternVL, etc.)

## License

MIT
