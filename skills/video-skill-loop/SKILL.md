---
name: video-skill-loop
description: Autonomous video skill learning loop for training-free VQA improvement. Checks job status, analyzes per-skill accuracy, induces routing rules, launches next iteration. Use when user says "check skill loop", "skill loop results", "run skill loop", "video skill learning", or wants to iterate the skill discovery pipeline.
argument-hint: "phase or focus area, e.g. check results / new iteration / submit job"
---

# Video Skill Learning Loop

**Goal**: Training-free video VQA improvement via autonomous skill discovery and routing.
**Model**: Qwen2.5-VL-7B-Instruct (parameters never modified)
**Context**: $ARGUMENTS

## Core Idea

Instead of post-training, we:
1. Try multiple video tool strategies (skills) on a discovery set with known ground truth
2. Learn **which questions benefit from which skill** via correctness signal + TF-IDF analysis
3. Build a routing policy: new question arrives → router selects skill → single inference → answer

No gradient updates. Only the routing policy is learned from data.

---

## Key Paths

```
PROJECT:    /data/DERI-Gong/jh015/lmms-eval
TOOLS:      skill_learning/tools/sampling.py   (6 sampling strategies)
            skill_learning/tools/temporal.py   (Claude API temporal grounding)
            skill_learning/tools/spatial.py    (Claude API spatial grounding)
EVAL LOOP:  skill_learning/eval_loop.py        (run all 9 tools × N samples)
ANALYZER:   skill_learning/analyze.py          (effective cases + routing rules)
SLURM:      run_skill_loop.sh                  (8h job, GPU)
LOGS:       logs/skill_loop_*/
DATA:       eval_deltaS_v2.jsonl (1602 samples)
VIDEOS:     /data/DERI-Gong/jh015/VideoZoomer/
```

---

## Workflow

### Step 1: Check Current State

```bash
# Job status
squeue -u acw652 -o "%i %j %t %M %l %R"

# Find latest skill loop log dir
ls -lt /data/DERI-Gong/jh015/lmms-eval/logs/ | grep skill_loop | head -5

# Check SLURM output for errors or progress
tail -50 /data/DERI-Gong/jh015/lmms-eval/slurm-<JOBID>.out

# Check checkpoint progress
wc -l /data/DERI-Gong/jh015/lmms-eval/logs/skill_loop_<TS>/results.json
```

Determine state:
- **Still running** → check how many samples done, report ETA
- **Crashed** → read error, diagnose, fix, resubmit
- **Results done** → run analyze.py → go to Step 2

---

### Step 2: Parse Results (Per-Tool Accuracy Matrix)

```bash
# Run analysis
/data/home/acw652/.conda/envs/verl-tool-env/bin/python \
    /data/DERI-Gong/jh015/lmms-eval/skill_learning/analyze.py \
    /data/DERI-Gong/jh015/lmms-eval/logs/skill_loop_<TS>/results.json

# Or read pre-saved analysis
cat /data/DERI-Gong/jh015/lmms-eval/logs/skill_loop_<TS>/analysis.json
```

Build accuracy table:
```
Tool                          Acc     Gain    Eff   Reg
uniform_32f (baseline)        XX.X%   —       —     —
uniform_16f                   XX.X%   +/-X.X% N     N
uniform_64f                   XX.X%   +/-X.X% N     N
motion_dense_32f              XX.X%   +/-X.X% N     N
keyframe_32f                  XX.X%   +/-X.X% N     N
first_last_32f                XX.X%   +/-X.X% N     N
temporal_grounding            XX.X%   +/-X.X% N     N
spatial_grounding             XX.X%   +/-X.X% N     N
spatio_temporal_grounding     XX.X%   +/-X.X% N     N
```

**Key signals**:
- Tools with gain > +3% AND effective_cases >= 10 → strong candidates for routing
- Tools with large regressions → avoid using broadly
- If NO tool beats baseline by >1% → skill space needs redesign (see Decision Gate)

---

### Step 3: Review Routing Rules from Analysis

```bash
cat /data/DERI-Gong/jh015/lmms-eval/logs/skill_loop_<TS>/analysis.json | python3 -c "
import json, sys
a = json.load(sys.stdin)
for rule in a['routing_rules']:
    print(f\"{rule['tool']}: gain={rule['gain']:+.1%} eff={rule['n_effective']} type_lift={rule['type_lift']}\")
    print(f\"  keywords: {rule['tfidf_keywords'][:6]}\")
"
```

For each routing rule, note:
- `type_lift`: which question types (temporal/spatial/detail/counting/action/causal) this tool helps
- `tfidf_keywords`: question words that predict this tool is effective
- `n_effective`: training samples supporting this rule

Evaluate rule quality:
- **Good rule**: n_effective >= 8, gain > 0.03, type_lift has entries > 1.5×
- **Weak rule**: n_effective < 5 or no type_lift signal

---

### Step 4: Decision Gate

#### If best_tool_gain > +3% (meaningful):
→ **Build simple routing policy**
- Temporal questions → `temporal_grounding`
- Spatial questions → `spatial_grounding`
- Complex questions → `spatio_temporal_grounding`
- Others → `uniform_32f` (baseline)
- Update PROGRESS.md, consider VideoMME eval

#### If 0% < gain <= 3% (marginal):
→ **Iterate: add more targeted skills**
- Check which question types no tool handles well
- Add new skill variant (e.g., CLIP-based retrieval, question-guided zoom)
- Re-run eval with `--tools <new_tool>` (checkpoint resumes existing tools)

#### If gain <= 0% (no improvement):
→ **Diagnose: check improvable samples**
```python
# Load results.json and check
import json
results = json.load(open("results.json"))
tools = list(results.keys())
all_ids = list(results["uniform_32f"].keys())
improvable = [sid for sid in all_ids
              if any(results[t][sid]["correct"] for t in tools
                     if not results["uniform_32f"][sid]["correct"])]
print(f"Improvable: {len(improvable)} / {len(all_ids)} = {len(improvable)/len(all_ids):.1%}")
```
If < 15% improvable → skill space fundamentally insufficient

---

### Step 5: Submit Job

```bash
# Check ANTHROPIC_API_KEY is set
echo $ANTHROPIC_API_KEY

# Export key and submit
export ANTHROPIC_API_KEY=<key>
sbatch /data/DERI-Gong/jh015/lmms-eval/run_skill_loop.sh
```

The SLURM script runs `eval_loop.py` which:
- Checkpoints every 10 samples to `results.json`
- Resumes automatically if resubmitted
- Runs all 9 tools × N samples

---

### Step 6: Update PROGRESS.md

```bash
# After each iteration
cat >> /data/DERI-Gong/jh015/lmms-eval/PROGRESS.md << 'EOF'

### Skill Loop Iteration N (Job XXXXXX, logs/skill_loop_<TS>)

| Tool                         | Acc   | vs Baseline |
|------------------------------|-------|-------------|
| uniform_32f (baseline)       | XX.X% | —           |
| temporal_grounding           | XX.X% | +X.X%       |
| spatial_grounding            | XX.X% | +X.X%       |
| spatio_temporal_grounding    | XX.X% | +X.X%       |

**Top Routing Rules**: [summary from analysis.json]
**Decision**: [proceed to VideoMME / iterate / redesign]
EOF
```

---

## Key Rules

- Baseline is always `uniform_32f` (32 uniform frames, no tools)
- VQA metric = answer letter match (A/B/C/D/E), **not delta_s** (delta_s is IGNORED)
- Never modify model parameters
- A "tool" = function `(video_path, question) → {"frames": [...], "meta": {...}}`
- Grounding tools use **Anthropic Claude API** (claude-haiku-4-5-20251001) — no local HuggingFace models
- `results.json` checkpointed every 10 samples — safe to resume after crash
- Analysis → `analysis.json` in same log dir

---

## Current Tool Registry (9 tools)

### Category 1: Sampling Tools (question-agnostic, no API)

| Tool | Description |
|------|-------------|
| `uniform_16f` | 16 uniformly-spaced frames |
| `uniform_32f` | **32 uniformly-spaced frames (BASELINE)** |
| `uniform_64f` | 64 uniformly-spaced frames |
| `motion_dense_32f` | 32 frames from highest-motion 3s window |
| `keyframe_32f` | 32 histogram-diff keyframes |
| `first_last_32f` | 16 first + 16 last frames |

### Category 2: Temporal Grounding (Claude API)

| Tool | Description |
|------|-------------|
| `temporal_grounding` | **Pass 1**: send 8 overview frames + question to Claude API → parse `TIME: Xs to Ys` → **Pass 2**: extract 24 dense frames from predicted interval. Fallback: motion-dense window. |

### Category 3: Spatial Grounding (Claude API)

| Tool | Description |
|------|-------------|
| `spatial_grounding` | **Pass 1**: send highest-motion frame + question to Claude API → parse `REGION: x1=A y1=B x2=C y2=D` (normalised 0-1) → **Pass 2**: crop+magnify that region from 32 uniform frames. Fallback: center crop. |
| `spatio_temporal_grounding` | Temporal first → spatial on those frames. 2 API calls. Most targeted. |

**API model**: `claude-haiku-4-5-20251001` (fast + cheap, vision-capable)
**Response formats**:
- Temporal: `TIME: 12.0s to 28.5s`
- Spatial:  `REGION: x1=0.10 y1=0.05 x2=0.55 y2=0.60`
