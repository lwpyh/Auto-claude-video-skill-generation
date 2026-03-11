---
name: video-skill-analyze
description: Analyze video VQA skill experiment results. Parses results.json, computes per-skill accuracy vs baseline, question-type lift, and routing rules. Use when video-skill-loop needs to analyze results, or user says "analyze skill results", "what's the accuracy", "which skill is best".
argument-hint: "log directory path, or 'latest' to use most recent"
allowed-tools: Bash(*), Read, Glob
---

# Video Skill Analyze

Parse and summarize skill evaluation results for the video VQA loop.

**Target**: $ARGUMENTS (log dir path, or "latest")

---

## Workflow

### Step 1: Locate Results

```bash
# Find target log dir
if [ "$ARGUMENTS" = "latest" ] || [ -z "$ARGUMENTS" ]; then
    LOGDIR=$(ls -dt /data/DERI-Gong/jh015/lmms-eval/logs/skill_loop_*/ 2>/dev/null | head -1)
else
    LOGDIR="$ARGUMENTS"
fi
echo "Analyzing: $LOGDIR"
ls "$LOGDIR/"
```

### Step 2: Run Project Analyzer

```bash
PYTHON=/data/home/acw652/.conda/envs/verl-tool-env/bin/python
$PYTHON /data/DERI-Gong/jh015/lmms-eval/skill_learning/analyze.py \
    "$LOGDIR/results.json" 2>&1
```

### Step 3: Parse analysis.json and Report

```bash
python3 -c "
import json

a = json.load(open('$LOGDIR/analysis.json'))
n = a['n']
base = a['baseline_acc']

print(f'=== Skill Accuracy Table (n={n}, baseline={base:.1%}) ===')
print(f'{\"Skill\":<34} {\"Acc\":>6}  {\"Gain\":>8}  {\"Eff\":>5}  {\"Reg\":>5}')
print('-'*65)
for sk, s in sorted(a['skill_stats'].items(), key=lambda x: -x[1]['acc']):
    mark = ' ← BASELINE' if sk == a['baseline'] else ''
    print(f'  {sk:<32} {s[\"acc\"]:>5.1%}  {s[\"gain\"]:>+7.1%}  {s[\"n_effective\"]:>5}  {s[\"n_regression\"]:>5}{mark}')

print()
print('=== Routing Rules ===')
for r in a.get('routing_rules', []):
    print(f'  {r[\"skill\"]}: gain={r[\"gain\"]:+.1%}  eff={r[\"n_effective\"]}  type_lift={r[\"type_lift\"]}')

print()
print('=== Reflection Candidates ===')
for c in a.get('new_candidates', []):
    print(f'  {c[\"name\"]}  ({c[\"reason\"]})')

print()
best = max(a['skill_stats'].items(), key=lambda x: x[1]['acc'])
print(f'BEST: {best[0]}  acc={best[1][\"acc\"]:.1%}  gain={best[1][\"gain\"]:+.1%}')
print(f'THRESHOLD MET: {best[1][\"gain\"] >= 0.05}  (need gain >= 5%)')
" 2>/dev/null
```

### Step 4: Question-Type Breakdown (if available)

```bash
python3 -c "
import json, re

results = json.load(open('$LOGDIR/results.json'))
QTYPES = {
    'temporal':  r'\b(when|before|after|first|last|sequence|order|step)\b',
    'spatial':   r'\b(where|left|right|top|bottom|position|location)\b',
    'counting':  r'\b(how many|count|number of|total)\b',
    'causal':    r'\b(why|because|reason|cause|result)\b',
    'detail':    r'\b(text|read|sign|color|number|digit|written)\b',
}
base = results.get('uniform_32_direct', {})
print('Question type accuracy (baseline vs best skill):')
for qtype, pat in QTYPES.items():
    ids = [sid for sid, v in base.items()
           if re.search(pat, v.get('meta',{}).get('question',''), re.I)]
    if len(ids) < 3: continue
    base_acc = sum(base[sid]['correct'] for sid in ids) / len(ids)
    best_sk, best_acc = 'baseline', base_acc
    for sk, r in results.items():
        if sk == 'uniform_32_direct': continue
        acc = sum(r.get(sid,{}).get('correct',False) for sid in ids) / len(ids)
        if acc > best_acc:
            best_acc, best_sk = acc, sk
    print(f'  {qtype:<12} n={len(ids):>3}  base={base_acc:.0%}  best={best_sk}({best_acc:.0%})')
" 2>/dev/null
```

### Step 5: Output for video-skill-loop

Return a structured summary suitable for pasting into the Codex review prompt:
- Full accuracy table
- Routing rules (question type → best skill)
- Reflection candidates from analyze.py
- Whether positive threshold (gain ≥ +5%) is met

---

## Key Rules

- Always compare against `uniform_32_direct` as baseline
- Report both gain AND regressions (a skill that helps 10 but hurts 12 is net negative)
- Flag if n_samples < 100 (results are preliminary)
- Note if any skill had errors (acc = 0% is a bug, not a real result)
