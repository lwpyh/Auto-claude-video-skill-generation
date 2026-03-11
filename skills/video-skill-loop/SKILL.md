---
name: video-skill-loop
description: Autonomous video VQA skill discovery loop. Designs new skills via Codex MCP review, delegates implementation/evaluation/analysis to sub-skills, iterates until best gain >= +5% or MAX_ROUNDS reached. Use when user says "run skill loop", "video skill learning", "improve VQA", or wants to iterate the skill discovery pipeline.
argument-hint: "e.g. start new loop / continue from round N / check results"
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, Agent, Skill, mcp__codex__codex, mcp__codex__codex-reply
---

# Video VQA Skill Discovery Loop (Orchestrator)

Autonomously discover and iterate video VQA skills for Qwen2.5-VL-7B — no fine-tuning.

**Context**: $ARGUMENTS

---

## Constants

- **MAX_ROUNDS** = 4
- **POSITIVE_THRESHOLD**: best skill gain ≥ +5% vs baseline AND Codex verdict = "sufficient" / "ready"
- **REVIEW_DOC**: `/data/DERI-Gong/jh015/lmms-eval/VIDEO_SKILL_REVIEW.md`
- **BASELINE**: `uniform_32_direct` (32 uniform frames, direct prompt)
- **PROJECT**: `/data/DERI-Gong/jh015/lmms-eval/`

---

## Sub-skills Used

| Sub-skill | When invoked |
|-----------|-------------|
| `video-skill-implement` | Phase C: write Codex-proposed skills into skills.py |
| `video-skill-run` | Phase D: sbatch submit + monitor until job done |
| `video-skill-analyze` | Phase E: parse results.json → accuracy table + routing rules |
| `research-lit` | Phase A: when Codex references a technique to look up |

---

## Initialization

1. Read `VIDEO_SKILL_REVIEW.md` for prior round state (if exists)
2. Check current SLURM jobs: `squeue -u acw652 -o "%i %j %t %M %R"`
3. Read current skill registry:
   ```bash
   grep -E "^(SKILL_REGISTRY|Skill\()" /data/DERI-Gong/jh015/lmms-eval/skill_learning/skills.py
   ```
4. Invoke `video-skill-analyze` to summarize latest results (if any log dir exists)
5. Create/update `VIDEO_SKILL_REVIEW.md` with header and timestamp
6. Set round = 1 (or resume)

---

## Loop (up to MAX_ROUNDS)

### Phase A — Codex Review

Collect context:
```bash
# Current skill registry summary
grep -E "Skill\(" /data/DERI-Gong/jh015/lmms-eval/skill_learning/skills.py

# Latest analysis summary (from video-skill-analyze output)
cat $(ls -dt /data/DERI-Gong/jh015/lmms-eval/logs/skill_loop_*/analysis.json 2>/dev/null | head -1) 2>/dev/null
```

If Codex references a paper/technique, first invoke:
```
Skill("research-lit", args="<technique> training-free video VQA improvement")
```

**Round 1 — new Codex thread:**
```
mcp__codex__codex:
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    [Round N/MAX_ROUNDS — Video VQA Skill Discovery]

    ## Goal
    Improve Qwen2.5-VL-7B video MCQ accuracy (A/B/C/D/E) without fine-tuning.
    A "skill" = (frame_strategy, prompt_strategy) preprocessing wrapper.

    ## Current Skills
    Frame strategies: uniform_16/32/64, motion_dense, keyframe, first_last, slow_fast
    Prompt strategies: direct (baseline), cot, temporal_cot, option_focus, desc_first

    ## Results (100 samples, eval_deltaS_v2.jsonl)
    [PASTE ACCURACY TABLE FROM video-skill-analyze]

    Routing rules learned:
    [PASTE ROUTING RULES]

    ## Task
    1. Score this skill design 1–10
    2. Identify which question types are still not handled
    3. Propose 3–5 new skills as Python code:
       - Frame fn: `(vpath: str) -> Tuple[List[PIL.Image], float]`
       - Prompt fn: `(frames, question: str, duration: float) -> list`
    4. Verdict: "not ready" / "almost" / "sufficient"
```

**Round 2+ — continue thread:**
```
mcp__codex__codex-reply:
  threadId: [saved from round 1]
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    [Round N update]

    Implemented: [list new skills]
    Updated results:
    [PASTE NEW ACCURACY TABLE]

    What worked / didn't: [brief analysis]

    Re-score. Propose next 3 skills. Same format.
```

**Save threadId** after round 1.

---

### Phase B — Parse Assessment

Save **full raw response** verbatim.

Extract:
- Score (1–10)
- Verdict ("not ready" / "almost" / "sufficient")
- Python code blocks for each proposed skill

**STOP** if score ≥ 6 AND gain ≥ +5% AND verdict = "sufficient".

---

### Phase C — Implement

Invoke sub-skill with extracted code blocks:
```
Skill("video-skill-implement", args="[paste Codex-proposed Python code blocks here]")
```

---

### Phase D — Run Experiment

Invoke sub-skill:
```
Skill("video-skill-run", args="submit and monitor skill_loop job")
```

---

### Phase E — Analyze & Document

Invoke sub-skill:
```
Skill("video-skill-analyze", args="latest skill_loop log directory")
```

Then append to `VIDEO_SKILL_REVIEW.md`:

```markdown
## Round N (YYYY-MM-DD HH:MM)

### Assessment
- Score: X/10  |  Verdict: [not ready / almost / sufficient]
- Key criticisms: ...

### Codex Full Response
<details><summary>expand</summary>
[FULL RAW RESPONSE — verbatim]
</details>

### Skills Implemented
| Name | Frame | Prompt | Rationale |
|------|-------|--------|-----------|

### Results
[paste table from video-skill-analyze]

### Status: continuing to Round N+1 / STOPPING
```

Increment round → back to Phase A.

---

## Termination

1. Write final summary to `VIDEO_SKILL_REVIEW.md`
2. Update MEMORY.md: best skill, gain, key routing rules
3. If max rounds without threshold: list blockers + recommend next steps

---

## Key Rules

- `config: {"model_reasoning_effort": "xhigh"}` always
- Save threadId, use `mcp__codex__codex-reply` for rounds 2+
- Implement BEFORE re-reviewing
- Metric = VQA accuracy (letter match), NOT delta_s
- Never fine-tune the model
