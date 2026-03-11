---
name: video-skill-implement
description: Implement new video VQA skills from Codex-proposed Python code. Writes frame/prompt strategy functions into skills.py, registers them in SKILL_REGISTRY, and validates imports. Use when video-skill-loop says "implement proposed skills" or Codex has returned new skill code.
argument-hint: "Python code blocks from Codex review, or description of skills to add"
allowed-tools: Bash(*), Read, Write, Edit, Glob
---

# Video Skill Implement

Implement new skills from Codex proposals into the project skill registry.

**Input**: $ARGUMENTS (Python code blocks proposed by Codex)

---

## Workflow

### Step 1: Read Current skills.py

```bash
cat /data/DERI-Gong/jh015/lmms-eval/skill_learning/skills.py
```

Identify:
- What frame strategies already exist (`FRAME_STRATEGIES` dict)
- What prompt strategies already exist (`PROMPT_STRATEGIES` dict)
- What skills are already in `SKILL_REGISTRY`

### Step 2: Implement Proposed Code

For each proposed skill from the input:

**A. New frame strategy** — add before `FRAME_STRATEGIES` dict:
```python
def new_frame_fn(vpath: str, n: int) -> Tuple[List[Image.Image], float]:
    """[description]"""
    vr, fps, dur = _read_video(vpath)
    # ... implementation ...
    return frames, dur
```
Then add to `FRAME_STRATEGIES`:
```python
"new_key": lambda v: new_frame_fn(v, 32),
```

**B. New prompt strategy** — add before `PROMPT_STRATEGIES` dict:
```python
def new_prompt_fn(frames: List[Image.Image], question: str, duration: float) -> list:
    """[description]"""
    user = [_enc(f) for f in frames]
    user.append({"type": "text", "text": f"..."})
    return [{"role": "system", "content": _SYS}, {"role": "user", "content": user}]
```
Then add to `PROMPT_STRATEGIES`:
```python
"new_prompt_key": new_prompt_fn,
```

**C. New Skill combination** — add to `SKILL_REGISTRY`:
```python
SKILL_REGISTRY["frame_key_prompt_key"] = Skill(
    name="frame_key_prompt_key",
    frame_key="frame_key",
    prompt_key="prompt_key",
)
```

### Step 3: Validate

```bash
/data/home/acw652/.conda/envs/verl-tool-env/bin/python -c "
from skill_learning.skills import SKILL_REGISTRY, FRAME_STRATEGIES, PROMPT_STRATEGIES
print('Frame strategies:', list(FRAME_STRATEGIES.keys()))
print('Prompt strategies:', list(PROMPT_STRATEGIES.keys()))
print('Total skills:', len(SKILL_REGISTRY))
new_skills = [k for k in SKILL_REGISTRY if k not in [
    'uniform_32_direct','uniform_16_direct','uniform_64_direct',
    'motion_dense_direct','keyframe_direct','first_last_direct','slow_fast_direct',
    'uniform_32_cot','uniform_32_temporal','uniform_32_option','uniform_32_desc',
    'slow_fast_cot','keyframe_temporal','motion_dense_cot']]
print('New skills added:', new_skills)
" 2>&1
```

### Step 4: Quick Smoke Test (1 sample)

```bash
/data/home/acw652/.conda/envs/verl-tool-env/bin/python -c "
import json
from pathlib import Path
from skill_learning.skills import SKILL_REGISTRY

with open('/data/DERI-Gong/jh015/lmms-eval/eval_deltaS_v2.jsonl') as f:
    for line in f:
        d = json.loads(line)
        if d.get('videos'): break

rel = d['videos'][0]
p = Path(rel)
parts = p.parts
rel2 = Path(*parts[1:]) if parts and parts[0] in ('.','..') else p
vpath = str(Path('/data/DERI-Gong/jh015/VideoZoomer') / rel2)

for name in list(SKILL_REGISTRY.keys())[-3:]:  # test last 3 (newest)
    out = SKILL_REGISTRY[name].run(vpath, 'test question')
    print(f'{name}: {len(out[\"frames\"])} frames OK')
" 2>&1
```

### Step 5: Report

List all newly added skills with their frame_key and prompt_key.
If any validation fails, fix the code before reporting success.

---

## Key Rules

- Never remove existing skills — only add
- Keep function signatures exactly: `(vpath: str) -> Tuple[List[Image.Image], float]` for frames
- Keep prompt signature exactly: `(frames, question: str, duration: float) -> list`
- Use `_read_video`, `_get_frames`, `_enc` helpers already defined in skills.py
- If Codex code has errors, fix them (don't blindly paste broken code)
