---
name: video-skill-loop
description: Autonomous video skill learning loop for training-free VQA improvement. Checks job status, analyzes per-skill accuracy, induces routing rules, launches next iteration. Use when user says "check skill loop", "skill loop results", "run skill loop", "video skill learning", or wants to iterate the skill discovery pipeline.
argument-hint: [phase or focus area, e.g. "check results" / "new iteration" / "phase1"]
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, Agent
---

# Video Skill Learning Loop

**Goal**: Training-free video VQA improvement via autonomous skill discovery and routing.
**Model**: Qwen2.5-VL-7B-Instruct (parameters never modified)
**Context**: $ARGUMENTS

## Core Idea

Instead of post-training, we:
1. Try multiple video sampling strategies (skills) on a discovery set with known ground truth
2. Learn **which questions benefit from which skill** via correctness signal + TF-IDF + LLM rule induction
3. Build a routing policy: new question arrives → router selects skill → single inference → answer

No gradient updates. Only the routing policy is learned from data.

---

## Key Paths

```
PROJECT:    /data/DERI-Gong/jh015/lmms-eval
SKILLS:     skill_learning/skills.py        (10 skill variants)
INDUCER:    skill_learning/inducer.py       (TF-IDF + Qwen2.5-7B rule synthesis)
ROUTER:     skill_learning/router.py        (routing logic)
LOOP:       skill_learning/loop.py          (Phase 1/2/3 orchestration)
SLURM:      run_skill_loop.sh               (8h job)
LOGS:       logs/skill_loop_*/
DATA:       eval_deltaS_v2.jsonl (1602 samples)
VIDEOS:     /data/DERI-Gong/jh015/VideoZoomer/General_Video/
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
```

Determine state:
- **Still running** → check progress (how many samples done in Phase 1), report ETA
- **Crashed** → read error, diagnose, fix, resubmit
- **Phase 1 done, awaiting Phase 2** → run induction manually if needed
- **All phases done** → go to Step 2

---

### Step 2: Parse Phase 1 Results (Per-Skill Accuracy Matrix)

```bash
cat /data/DERI-Gong/jh015/lmms-eval/logs/skill_loop_<TS>/phase1_results.json
```

Build accuracy table:
```
Skill               Acc    vs Baseline   Effective Cases   Regressions
uniform_32f         XX.X%  (baseline)    —                 —
uniform_16f         XX.X%  +/-X.X%       N                 N
uniform_64f         XX.X%  +/-X.X%       N                 N
pipeline_16_16      XX.X%  +/-X.X%       N                 N
motion_zoom_32f     XX.X%  +/-X.X%       N                 N
keyframe_32f        XX.X%  +/-X.X%       N                 N
first_last_32f      XX.X%  +/-X.X%       N                 N
coarse8_fine24      XX.X%  +/-X.X%       N                 N
multi_zoom_2segs    XX.X%  +/-X.X%       N                 N
spatial_zoom_32f    XX.X%  +/-X.X%       N                 N
```

**Key signals**:
- Skills with gain > +3% AND effective_cases >= 10 → strong candidates for routing
- Skills with large regressions → avoid using broadly
- If NO skill beats baseline by >1% → loop needs redesign (see Decision Gate)

---

### Step 3: Parse Phase 2 Rules

```bash
cat /data/DERI-Gong/jh015/lmms-eval/logs/skill_loop_<TS>/phase2_rules.json
```

For each rule, note:
- `routing_condition`: what question types / keywords trigger it
- `gain`: expected accuracy improvement
- `llm_rule`: human-readable rule from Qwen2.5-7B
- `n_effective`: how many training samples support the rule

Evaluate rule quality:
- **Good rule**: n_effective >= 8, gain > 0.03, routing_condition is specific and interpretable
- **Weak rule**: n_effective < 5 or routing_condition is empty
- **Conflicting rules**: two skills both claim the same question type → check which has higher precision

---

### Step 4: Parse Phase 3 Router Evaluation

```bash
cat /data/DERI-Gong/jh015/lmms-eval/logs/skill_loop_<TS>/final_summary.json
cat /data/DERI-Gong/jh015/lmms-eval/logs/skill_loop_<TS>/phase3_routing_log.json
```

Report:
```
Baseline accuracy (uniform_32f):  XX.X%
Router accuracy:                  XX.X%
Gain:                             +X.X%

Routing breakdown:
  Skill X selected N times → accuracy Y%
  Skill Y selected N times → accuracy Y%
  Fallback (baseline) N times
```

---

### Step 5: Decision Gate

#### If router_accuracy > baseline + 2% (meaningful gain):
→ **Proceed to VideoMME**
- Update PROGRESS.md with results
- Submit VideoMME eval job:
  ```bash
  # (to be designed — use router as the model wrapper in lmms-eval)
  ```

#### If 0% < gain <= 2% (marginal):
→ **Iterate: refine rules or add new skills**
- Identify which question categories the router is mis-routing
- Add new skill variant targeting that category
- Re-run Phase 1 (can reuse cached results, only run new skill)

#### If gain <= 0% (no improvement):
→ **Redesign: skills are not diverse enough or routing signal is weak**

Diagnose by checking:
```python
# What fraction of samples have ANY skill that beats baseline?
n_improvable = count samples where max(all_skills) > baseline
```

If n_improvable < 20% of training set → the skill space needs fundamentally new approaches.

**New skill ideas to try** (implement in `skill_learning/skills.py`):
- `clip_frame_retrieval`: CLIP cosine similarity between question text and video frames
- `question_guided_zoom`: extract nouns from question, find frames where those objects appear (requires OWL-ViT or similar)
- `temporal_segment_reasoning`: divide video into 4 equal segments, run 8f per segment, combine
- `reverse_chronological`: sample frames in reverse order (emphasizes ending)

---

### Step 6: If Iterating — Add New Skill and Re-run

1. Implement new skill in `skill_learning/skills.py`, add to `SKILL_REGISTRY`
2. If reusing Phase 1 cache, just run Phase 1 for the new skill only:
   ```bash
   # Modify run_skill_loop.sh to --skills <new_skill_name> and --phase 1
   # Then merge results with existing phase1_results.json
   ```
3. Re-run Phase 2 (induction) on merged results
4. Re-run Phase 3 (router evaluation)

Increment loop counter. Document each iteration in PROGRESS.md.

---

### Step 7: Update PROGRESS.md

After each loop iteration, append to PROGRESS.md under a new Exp section:

```markdown
### Skill Loop Iteration N (Job XXXXXX, logs/skill_loop_<TS>)

| Skill                | Train Acc | vs Baseline |
|----------------------|-----------|-------------|
| uniform_32f (base)   | XX.X%     | —           |
| best_skill           | XX.X%     | +X.X%       |
| ...                  |           |             |

**Induced Rules**: [summary]
**Router Val Acc**: XX.X% vs Baseline XX.X% (Gain: +X.X%)
**Decision**: [proceed to VideoMME / iterate with new skills / redesign]
```

---

## Key Rules

- Baseline is always `uniform_32f` (32 uniform frames, no tools)
- VQA metric = answer letter match (A/B/C/D/E), not delta_s
- delta_s signal is IGNORED — correctness is the only signal
- Never modify model parameters
- Skills are purely video preprocessing + frame selection strategies
- A "skill" = a function (video_path, question) → framing strategy for the model
- LLM (Qwen2.5-7B) used only for rule synthesis in Phase 2, never for routing at inference time
- Phase 1 results are cached in `phase1_results.json` — don't re-run unless skills change
- If a SLURM job crashes mid-Phase-1, re-run with `--phase 1`; it will resume from checkpoint

## Current Skill Registry (10 skills)

| ID | Skill | Description |
|----|-------|-------------|
| 1 | `uniform_32f` | 32 uniform frames (baseline) |
| 2 | `uniform_16f` | 16 uniform frames |
| 3 | `uniform_64f` | 64 uniform frames |
| 4 | `pipeline_16_16` | 16f overview + motion-dense zoom 16f |
| 5 | `motion_zoom_32f` | 32f all in most-active segment |
| 6 | `keyframe_32f` | 32 histogram-diff keyframes |
| 7 | `first_last_32f` | 16 first + 16 last frames |
| 8 | `coarse8_fine24` | 8f sparse + 24f dense motion zoom |
| 9 | `multi_zoom_2segs` | 16f overview + top-2 motion segments zoom |
| 10 | `spatial_zoom_32f` | motion zoom + 2× center crop magnification |
