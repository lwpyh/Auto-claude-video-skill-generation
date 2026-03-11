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

    ## Skill Design Space (read carefully before proposing)

    Skills are NOT limited to Frame × Prompt. Three categories allowed:

    **Category 1 — Frame + Prompt**: simple (frame_strategy, prompt_strategy) pair.

    **Category 2 — Two-Stage Grounding** (preferred next step):
    Use Qwen's own grounding ability. Stage 1: ask Qwen with 8–16 frames
    "which time range / region is relevant for answering [question]?" →
    parse timestamp [t1,t2] or bbox [x1,y1,x2,y2] → validate (t1<t2, within
    duration; bbox area >5%, within frame) → if invalid, fallback to
    pipeline_16_16. Stage 2: dense-sample from [t1,t2] or crop+zoom bbox →
    run actual VQA. Every grounding skill MUST have validation + fallback.

    **Category 3 — Local CV** (no GPU): opencv optical flow, scenedetect,
    pytesseract OCR — all local, no external model APIs.

    Hard constraints:
    - No external model APIs (Anthropic/OpenAI/Gemini forbidden)
    - Only Qwen2.5-VL-7B for any inference step
    - Fallback = pipeline_16_16 (current best, +11%)

    ## Task
    1. Score this skill design 1–10
    2. Identify which question types are still not handled (esp. longvideo-reason 32% of dataset)
    3. Propose 3–5 new skills as Python code. For Category 2, include both
       grounding stage and validation logic. Signature:
       - Frame fn: `(vpath: str) -> Tuple[List[PIL.Image], float]`
       - Prompt fn: `(frames, question: str, duration: float) -> list`
       - Or full skill fn: `(vpath: str, question: str) -> dict` for two-stage
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

## Skill Design Space & Principles

### What a skill CAN be (not limited to Frame × Prompt)

Skills are any **pure preprocessing wrapper** `(vpath, question) → messages` that changes what the model sees. Three categories:

**Category 1 — Frame + Prompt (existing)**
Simple (frame_strategy, prompt_strategy) combinations. Fast, one inference per sample.

**Category 2 — Two-Stage Grounding (preferred next frontier)**
Use Qwen's native grounding ability to find *where/when* to look, then run real VQA on the refined input.

```
Stage 1 (grounding inference, lightweight):
  Ask Qwen with 8–16 uniform frames:
    Temporal: "For answering [question], which time range in the video is most relevant? Answer in seconds."
    Spatial:  "For answering [question], which region of the frame is most relevant? Answer as bbox."
  Parse timestamp [t1, t2] or bbox [x1,y1,x2,y2] from output.

Stage 2 (refined VQA inference):
  Temporal: dense-sample frames from [t1, t2], then ask the actual question.
  Spatial:  crop + 2× zoom to bbox region from sampled frames, then ask.
  Both:     temporal slice + spatial crop.
```

**Category 3 — Local CV Augmentation (no GPU needed)**
Traditional CV as preprocessing before feeding frames to Qwen:
- `scenedetect` / frame-difference → shot boundary detection
- `opencv` optical flow → precise motion magnitude per pixel
- `pytesseract` OCR → extract on-screen text for detail questions

### Grounding Validation (mandatory for Category 2 skills)

Qwen's grounding is imperfect. Every Category 2 skill MUST include:

```python
def _validate_grounding(result: str, duration: float, frame_w: int, frame_h: int) -> bool:
    # Temporal: timestamps parseable AND t1 < t2 AND both within [0, duration]
    # Spatial:  bbox parseable AND area > 5% of frame AND within frame bounds
    # Returns False if grounding looks hallucinated or unparseable

def grounding_skill(vpath, question):
    grounding_result = run_grounding_inference(vpath, question)
    if not _validate_grounding(grounding_result, ...):
        return SKILL_REGISTRY["pipeline_16_16"].run(vpath, question)  # fallback
    return run_refined_vqa(vpath, question, grounding_result)
```

### Self-Reflection for Grounding Skills (optional, for high-stakes cases)

When grounded answer and fallback answer conflict:
```
Third inference: show Qwen both answers + reasoning, ask it to choose.
```
Only add this when a simpler validation pass proves insufficient.

### Hard Constraints

- **No external model APIs** — no Anthropic, OpenAI, Gemini, etc. calls during skill execution
- **Qwen2.5-VL-7B only** — grounding is done by the same model being evaluated (no unfair external help)
- **Local CV libraries are fine** — opencv, scenedetect, pytesseract, etc. are fair game
- **Never fine-tune** — model weights are always frozen
- **Fallback is `pipeline_16_16`** — currently best known skill (+11%), use as safety net
- **Metric = VQA accuracy (letter match A/B/C/D/E), NOT delta_s**

### When Proposing New Skills (instruct Codex)

Prefer skills that address question types where current routing fails:
- `longvideo-reason` questions (32% of dataset) → temporal grounding most useful
- spatial/detail questions → spatial grounding or OCR
- counting/causal questions → multi-step prompt decomposition

---

## Key Rules

- `config: {"model_reasoning_effort": "xhigh"}` always
- Save threadId, use `mcp__codex__codex-reply` for rounds 2+
- Implement BEFORE re-reviewing
- Metric = VQA accuracy (letter match), NOT delta_s
- Never fine-tune the model
- Codex prompt MUST include the Skill Design Space & Principles section above when asking for new skill proposals
