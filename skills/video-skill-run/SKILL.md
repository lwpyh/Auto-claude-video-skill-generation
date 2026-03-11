---
name: video-skill-run
description: Submit the video skill evaluation SLURM job and monitor until completion. Handles sbatch submission, progress polling, and checkpoint reading. Use when video-skill-loop says "run experiment", "submit job", or "wait for results".
argument-hint: "submit and monitor / just monitor job <JOBID> / check progress"
allowed-tools: Bash(*), Read
---

# Video Skill Run

Submit and monitor the skill evaluation SLURM job.

**Context**: $ARGUMENTS

---

## Workflow

### Step 1: Check for Already-Running Jobs

```bash
squeue -u acw652 -o "%i %j %t %M %l %R" | grep skill_loop
```

- If a skill_loop job is already running → skip submission, go to Step 3
- If no job running → proceed to Step 2

### Step 2: Submit Job

```bash
cd /data/DERI-Gong/jh015/lmms-eval
sbatch run_skill_loop.sh
```

Note the **job ID** from output (`Submitted batch job XXXXXX`).

### Step 3: Monitor Progress

Check every few minutes. Report progress table:

```bash
# Job status
squeue -u acw652 -o "%i %j %t %M %l %R" | grep -E "skill_loop|JOBID"

# Latest log dir
LATEST=$(ls -dt /data/DERI-Gong/jh015/lmms-eval/logs/skill_loop_*/ 2>/dev/null | head -1)
echo "Log dir: $LATEST"

# Checkpoint progress
[ -n "$LATEST" ] && python3 -c "
import json, os
rpath = '$LATEST/results.json'
if not os.path.exists(rpath):
    print('No checkpoint yet')
else:
    r = json.load(open(rpath))
    skills = list(r.keys())
    counts = {sk: len(r[sk]) for sk in skills}
    n_done = max(counts.values()) if counts else 0
    print(f'Progress: {n_done}/100 samples done, {len(skills)} skills')
    base = r.get('uniform_32_direct', {})
    base_acc = sum(v[\"correct\"] for v in base.values()) / max(len(base), 1)
    print(f'Baseline so far: {base_acc:.1%}')
    for sk in sorted(skills, key=lambda s: -sum(v[\"correct\"] for v in r[s].values())/max(len(r[s]),1)):
        acc = sum(v[\"correct\"] for v in r[sk].values()) / max(len(r[sk]), 1)
        gain = acc - base_acc
        print(f'  {sk:<32} {acc:.1%}  {gain:+.1%}  ({len(r[sk])} samples)')
" 2>/dev/null

# Tail SLURM output for errors
ls /data/DERI-Gong/jh015/lmms-eval/slurm-*.out 2>/dev/null | sort -t- -k2 -n | tail -1 | xargs -I{} tail -20 {}
```

### Step 4: Detect Completion

Job is done when:
- `squeue` no longer shows the job, OR
- Checkpoint shows 100/100 samples done for all skills

### Step 5: Report

```bash
LATEST=$(ls -dt /data/DERI-Gong/jh015/lmms-eval/logs/skill_loop_*/ 2>/dev/null | head -1)
echo "Results at: $LATEST"
ls -la "$LATEST/"
```

Return: log directory path + final sample count for use by `video-skill-analyze`.

---

## Key Rules

- Do NOT re-submit if a job is already running (checkpoint resumes automatically)
- The loop runs `--max_iters 3` internally — it may submit multiple SLURM iterations on its own
- If job crashes mid-run: re-submit same script; checkpoint in `results.json` resumes from last saved point
- Estimated wall time: ~7h for 14 skills × 100 samples on A100
