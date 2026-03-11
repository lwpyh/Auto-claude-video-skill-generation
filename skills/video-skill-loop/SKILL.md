---
name: video-skill-loop
description: Autonomous video VQA skill discovery loop. Repeatedly designs new skills, submits SLURM experiments, analyzes results via Codex MCP review, and iterates until best skill gain >= +5% over baseline or MAX_ROUNDS reached. Use when user says "run skill loop", "video skill learning", "improve VQA", "skill loop results", or wants to iterate the skill discovery pipeline.
argument-hint: "phase or focus area, e.g. start new loop / check results / continue from round N"
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, Agent, Skill, mcp__codex__codex, mcp__codex__codex-reply
---

# Video VQA Skill Discovery Loop

Autonomously discover, implement, evaluate, and iterate video VQA skills for Qwen2.5-VL-7B — without any model fine-tuning.

**Context**: $ARGUMENTS

---

## Constants

- **MAX_ROUNDS** = 4
- **POSITIVE_THRESHOLD**: best skill gain ≥ +5% vs baseline on 100 samples, AND Codex verdict contains "sufficient" / "ready" / "converged"
- **REVIEW_DOC**: `VIDEO_SKILL_REVIEW.md` in `/data/DERI-Gong/jh015/lmms-eval/`
- **BASELINE**: `uniform_32_direct` (32 uniform frames, direct prompt)
- **PROJECT**: `/data/DERI-Gong/jh015/lmms-eval/`
- **SKILLS_FILE**: `skill_learning/skills.py`
- **SLURM_SCRIPT**: `run_skill_loop.sh`
- **LOG_BASE**: `logs/skill_loop_*/`

---

## Key File Paths

```
PROJECT:      /data/DERI-Gong/jh015/lmms-eval
SKILLS:       skill_learning/skills.py          ← add new skills here
LOOP:         skill_learning/loop.py            ← main eval loop
ANALYZER:     skill_learning/analyze.py         ← accuracy + routing rules
SLURM:        run_skill_loop.sh                 ← sbatch this
RESULTS:      logs/skill_loop_<TS>/results.json ← per-skill accuracy
ANALYSIS:     logs/skill_loop_<TS>/analysis.json
REVIEW_DOC:   VIDEO_SKILL_REVIEW.md
DATA:         eval_deltaS_v2.jsonl (1602 samples, MCQ A-E)
MODEL:        Qwen/Qwen2.5-VL-7B-Instruct (NEVER fine-tuned)
PYTHON:       /data/home/acw652/.conda/envs/verl-tool-env/bin/python
```

---

## Initialization

1. Read `VIDEO_SKILL_REVIEW.md` (if exists) for prior round state
2. Check for running/completed SLURM jobs:
   ```bash
   squeue -u acw652 -o "%i %j %t %M %R"
   ls -lt /data/DERI-Gong/jh015/lmms-eval/logs/ | grep skill_loop | head -5
   ```
3. Read current `skill_learning/skills.py` to understand what's already implemented
4. If latest results.json exists, invoke **analyze-results** skill to summarize current state
5. Initialize round counter = 1 (or resume from prior round)
6. Create/update `VIDEO_SKILL_REVIEW.md` with header

---

## Loop (repeat up to MAX_ROUNDS)

### Phase A: Codex Review

Gather full context, then send to Codex MCP:

**Context to collect before calling:**
```bash
# Current skill registry
cat /data/DERI-Gong/jh015/lmms-eval/skill_learning/skills.py | grep -E "^(def |FRAME|PROMPT|SKILL|Skill\()" | head -60

# Latest results (if any)
LATEST=$(ls -dt /data/DERI-Gong/jh015/lmms-eval/logs/skill_loop_*/ 2>/dev/null | head -1)
[ -n "$LATEST" ] && cat "$LATEST/analysis.json" 2>/dev/null | python3 -c "
import json,sys; a=json.load(sys.stdin)
print(f'Baseline: {a[\"baseline_acc\"]:.1%}')
for sk,s in sorted(a['skill_stats'].items(), key=lambda x:-x[1]['acc']):
    print(f'  {sk:<32} acc={s[\"acc\"]:.1%} gain={s[\"gain\"]:+.1%} eff={s[\"n_effective\"]} reg={s[\"n_regression\"]}')
print('Routing rules:', [r[\"skill\"]+':'+str(r[\"type_lift\"]) for r in a.get('routing_rules',[])])
"
```

**Codex MCP call (round 1):**
```
mcp__codex__codex:
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    [Round N/MAX_ROUNDS — Video VQA Skill Discovery Loop]

    ## Project Goal
    Improve Qwen2.5-VL-7B video VQA accuracy (MCQ A-E) WITHOUT any fine-tuning.
    A "skill" = (frame_strategy, prompt_strategy): a function that preprocesses video
    frames and formats the question before single-pass VQA inference.

    ## Current Skill Design
    Frame strategies implemented: uniform_16/32/64, motion_dense, keyframe, first_last, slow_fast
    Prompt strategies implemented: direct, cot, temporal_cot, option_focus, desc_first
    Total skills = frame × prompt combinations (14 initial skills)

    ## Current Experimental Results (100 samples, eval_deltaS_v2.jsonl)
    [PASTE ACCURACY TABLE HERE]

    Routing rules learned:
    [PASTE ROUTING RULES HERE]

    ## Key observations from prior rounds (if any)
    [PASTE PRIOR ROUND FINDINGS]

    ## Your Task
    Act as an expert in video understanding and VLM inference-time optimization.

    1. **Score** this skill design 1–10 for effectiveness (10 = best possible training-free VQA improvement)
    2. **Diagnose** which question types or video characteristics are still not handled
    3. **Propose 3–5 new skills** as concrete Python implementations:
       - New frame strategies (functions matching signature: `(vpath: str) -> (List[PIL.Image], float)`)
       - New prompt strategies (functions matching signature: `(frames, question, duration) -> list`)
       - Or new frame×prompt combinations
    4. **Predict** which question types each proposed skill would help (with reasoning)
    5. **Verdict**: "not ready" / "almost" / "sufficient" — is +5% gain over baseline achievable?

    Format proposed skill code as Python, ready to paste into skills.py.
    Be specific and implementable — no vague suggestions.
```

**For round 2+**, use `mcp__codex__codex-reply` with saved `threadId`:
```
mcp__codex__codex-reply:
  threadId: [saved from round 1]
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    [Round N update]

    Since your last review, we implemented: [list new skills]
    New results:
    [PASTE UPDATED ACCURACY TABLE]

    Key changes:
    - [Skill X]: acc=YY% gain=+Z% (expected: ...)
    - [Skill Y]: acc=YY% gain=+Z% (expected: ...)

    Routing rules now: [updated]

    Re-score and re-assess. Which proposals worked? Which didn't, and why?
    Propose the next round of skills using same format.
    Same output format: Score, Verdict, 3–5 new skill implementations.
```

---

### Phase B: Parse Codex Response

**CRITICAL: Save the FULL raw response verbatim** (for VIDEO_SKILL_REVIEW.md Phase E).

Extract:
- **Score** (numeric 1–10)
- **Verdict** ("not ready" / "almost" / "sufficient")
- **Proposed skills** (Python code blocks — extract each one)
- **Predicted question types** for each proposed skill

**STOP CONDITION**: score ≥ 6 AND best_gain ≥ +5% AND verdict contains "sufficient" or "ready" → stop loop.

Also invoke **research-lit** skill if Codex references a technique you haven't seen:
```
Skill("research-lit", args="<technique name> video VQA inference-time improvement")
```

---

### Phase C: Implement New Skills

For each proposed skill from Codex:

1. **Add frame strategy** (if new) to `skill_learning/skills.py` in `FRAME_STRATEGIES` dict:
   ```python
   # Example addition
   def new_strategy(vpath: str, n: int) -> Tuple[List[Image.Image], float]:
       ...

   FRAME_STRATEGIES["new_strategy"] = lambda v: new_strategy(v, 32)
   ```

2. **Add prompt strategy** (if new) to `PROMPT_STRATEGIES` dict:
   ```python
   def new_prompt(frames, question, duration) -> list:
       ...

   PROMPT_STRATEGIES["new_prompt"] = new_prompt
   ```

3. **Register new Skill combinations** in `SKILL_REGISTRY`:
   ```python
   SKILL_REGISTRY["new_frame_new_prompt"] = Skill(
       "new_frame_new_prompt", "new_frame_key", "new_prompt_key")
   ```

4. **Validate** imports work:
   ```bash
   /data/home/acw652/.conda/envs/verl-tool-env/bin/python -c "
   from skill_learning.skills import SKILL_REGISTRY
   print(list(SKILL_REGISTRY.keys()))"
   ```

5. **Submit SLURM job** (only evaluates new skills, checkpoints resume existing results):
   ```bash
   cd /data/DERI-Gong/jh015/lmms-eval
   sbatch run_skill_loop.sh
   # Note the job ID
   ```

---

### Phase D: Monitor Job

Poll SLURM until job completes (check every few minutes during conversation):

```bash
# Check job status
squeue -u acw652 -o "%i %j %t %M %l %R" | grep skill_loop

# Check progress in output file
tail -30 /data/DERI-Gong/jh015/lmms-eval/slurm-<JOBID>.out

# Check checkpoint (how many samples done)
LATEST=$(ls -dt /data/DERI-Gong/jh015/lmms-eval/logs/skill_loop_*/ | head -1)
python3 -c "
import json
r = json.load(open('$LATEST/results.json'))
skills = list(r.keys())
n = max(len(v) for v in r.values())
print(f'Progress: {n}/100 samples, {len(skills)} skills')
for sk in sorted(skills, key=lambda s: -sum(v[\"correct\"] for v in r[s].values())/max(len(r[s]),1)):
    acc = sum(v[\"correct\"] for v in r[sk].values()) / max(len(r[sk]),1)
    print(f'  {sk:<32} {acc:.1%} ({len(r[sk])} samples)')
"
```

Invoke **monitor-experiment** skill if job is long-running and user needs a status update:
```
Skill("monitor-experiment", args="SLURM job <JOBID> skill_loop")
```

---

### Phase E: Analyze and Document

Once job completes, invoke **analyze-results** skill:
```
Skill("analyze-results", args="skill_loop results at <LATEST_LOG_DIR>")
```

Then run the project analyzer:
```bash
LATEST=$(ls -dt /data/DERI-Gong/jh015/lmms-eval/logs/skill_loop_*/ | head -1)
/data/home/acw652/.conda/envs/verl-tool-env/bin/python \
    /data/DERI-Gong/jh015/lmms-eval/skill_learning/analyze.py \
    "$LATEST/results.json"
```

Append to `VIDEO_SKILL_REVIEW.md`:

```markdown
## Round N (YYYY-MM-DD HH:MM)

### Assessment Summary
- Codex Score: X/10
- Verdict: [not ready / almost / sufficient]
- Key criticisms: [bullet list from Codex]

### Codex Full Response
<details>
<summary>Click to expand full Codex response</summary>

[PASTE COMPLETE RAW CODEX RESPONSE — verbatim, unedited]

</details>

### Skills Implemented This Round
| Skill Name | Frame Key | Prompt Key | Rationale |
|------------|-----------|------------|-----------|
| new_skill_1 | frame_x | prompt_y | Codex proposal: ... |

### Experimental Results
| Skill | Acc | Gain vs Baseline | Eff | Reg |
|-------|-----|-----------------|-----|-----|
| uniform_32_direct (baseline) | XX% | — | — | — |
| best_new_skill | XX% | +X% | N | N |
| ... | | | | |

### Routing Rules Learned
- [skill_name]: helps [question_types] with lift [X×] (n_effective=N)

### Key Findings
1. [Observation + interpretation + implication]
2. ...

### Status
- Continuing to Round N+1 / STOPPING (positive threshold reached)
- Next round will focus on: [...]
```

Increment round counter → back to Phase A.

---

## Termination

When loop ends:

1. Write final summary to `VIDEO_SKILL_REVIEW.md`
2. Update `/data/home/acw652/.claude/projects/-data-home-acw652/memory/MEMORY.md` with:
   - Best skill found and its gain
   - Key routing rules (question type → skill)
   - Remaining gaps
3. If stopped at max rounds without positive threshold:
   - List remaining blockers with estimated effort
   - Suggest whether to (a) continue with more rounds, (b) pivot to different skill types, or (c) use best-found skill as final answer
4. Report final routing policy for production use

---

## Key Rules

- **ALWAYS** use `config: {"model_reasoning_effort": "xhigh"}` for Codex calls
- **Save threadId** from first call, use `mcp__codex__codex-reply` for all subsequent rounds
- **Implement BEFORE re-reviewing** — never promise fixes without writing the code
- **Checkpoint resume**: `results.json` saves every 10 samples; re-submitting a job continues from where it stopped
- **Never fine-tune the model** — skills are purely preprocessing + prompt wrappers
- **Baseline is sacred**: `uniform_32_direct` (32 uniform frames, direct prompt) — always report gain vs this
- **Metric is VQA accuracy** (answer letter A/B/C/D/E match) — NOT delta_s or any proxy
- **Be honest**: include regressions, not just gains. A skill that helps 10 but hurts 12 is net negative
- If Codex proposes a skill requiring external API/model, implement the **local fallback version** instead

---

## Codex Review Prompt Template (Round 2+)

```
[Round N/MAX_ROUNDS update]

Implemented since last round:
1. [skill_name] (frame=[X], prompt=[Y]): acc=ZZ%, gain=+A% — [as expected / better / worse than predicted]
2. ...

Full updated accuracy table:
[TABLE]

Routing rules learned:
[RULES]

Failed proposals and why:
- [skill that didn't work]: predicted +X%, actual +Y% — likely because [hypothesis]

Question: Which of the remaining weak question types should we attack next?
Propose the next 3 skills. Same format as before.
Score / Verdict / Implementations.
```

---

## Current Skill Space Reference

### Frame Strategies (keys for FRAME_STRATEGIES dict)
| Key | Description |
|-----|-------------|
| `uniform_16/32/64` | N uniform frames |
| `motion_dense` | 32f from highest-motion 3s window |
| `keyframe` | 32 scene-boundary frames (histogram diff) |
| `first_last` | 16f first half + 16f second half |
| `slow_fast` | n//4 uniform + 3n//4 motion-dense |

### Prompt Strategies (keys for PROMPT_STRATEGIES dict)
| Key | Description |
|-----|-------------|
| `direct` | **BASELINE**: "Answer with the letter only." |
| `cot` | Chain-of-thought: describe → reason → answer |
| `temporal_cot` | Inject frame timestamps + temporal reasoning |
| `option_focus` | Evaluate each option, eliminate, select |
| `desc_first` | Describe video content first, then answer |

### Skill Registration
```python
# In skill_learning/skills.py
SKILL_REGISTRY["frame_key_prompt_key"] = Skill(
    name="frame_key_prompt_key",
    frame_key="frame_key",
    prompt_key="prompt_key",
)
```
