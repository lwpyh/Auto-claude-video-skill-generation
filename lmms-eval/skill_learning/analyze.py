"""
Analyze results.json → per-skill accuracy + question-type lift + reflection proposals.

Reflection logic (coordinate descent in frame × prompt space):
  1. Rank frame strategies by average accuracy across all skills using that frame key
  2. Rank prompt strategies by average accuracy across all skills using that prompt key
  3. Propose top-3 frame × top-3 prompt combos not yet in SKILL_REGISTRY
  4. Targeted proposals: if a question type is systematically weak, boost relevant skills

Output: analysis.json with keys:
  baseline_acc, skill_stats, routing_rules, new_candidates
"""

from __future__ import annotations
import json, re
from pathlib import Path
from typing import Dict, List
from collections import defaultdict


BASELINE = "uniform_32_direct"

QUESTION_TYPES = {
    "temporal":  r"\b(when|before|after|first|last|then|sequence|order|earlier|later|step|stage|finally)\b",
    "spatial":   r"\b(where|position|location|left|right|top|bottom|side|corner|center|front|back|above|below)\b",
    "detail":    r"\b(text|read|sign|label|number|digit|color|written|display|brand|name|title|caption)\b",
    "counting":  r"\b(how many|count|number of|total|times|once|twice)\b",
    "action":    r"\b(what (is|are|does|do|was|were)|doing|happening|action|activity|perform|demonstrate)\b",
    "causal":    r"\b(why|because|reason|cause|result|effect|purpose|goal)\b",
}


def classify_q(q: str) -> List[str]:
    return [t for t, p in QUESTION_TYPES.items() if re.search(p, q, re.I)]


def analyze(results_path: str) -> Dict:
    with open(results_path) as f:
        results = json.load(f)

    from skill_learning.skills import SKILL_REGISTRY, FRAME_STRATEGIES, PROMPT_STRATEGIES, Skill

    skills   = list(results.keys())
    all_ids  = list(results.get(BASELINE, {}).keys())
    n        = len(all_ids)
    base_r   = results.get(BASELINE, {})
    base_acc = sum(v["correct"] for v in base_r.values()) / max(n, 1)

    # ── Per-skill stats ──────────────────────────────────────
    stats: Dict[str, dict] = {}
    for sk in skills:
        r    = results[sk]
        acc  = sum(v["correct"] for v in r.values()) / max(len(r), 1)
        eff  = [sid for sid in all_ids
                if r.get(sid, {}).get("correct") and not base_r.get(sid, {}).get("correct")]
        reg  = [sid for sid in all_ids
                if not r.get(sid, {}).get("correct") and base_r.get(sid, {}).get("correct")]
        stats[sk] = {"acc": acc, "gain": acc - base_acc, "eff": eff, "reg": reg}

    print(f"\n{'='*68}")
    print(f"{'Skill':<34} {'Acc':>6}  {'Gain':>8}  {'Eff':>5}  {'Reg':>5}")
    print(f"{'='*68}")
    for sk, s in sorted(stats.items(), key=lambda x: -x[1]["acc"]):
        mark = " ← baseline" if sk == BASELINE else ""
        print(f"  {sk:<32} {s['acc']:>5.1%}  {s['gain']:>+7.1%}"
              f"  {len(s['eff']):>5}  {len(s['reg']):>5}{mark}")

    # ── Question-type lift per skill ─────────────────────────
    routing_rules = []
    for sk, s in stats.items():
        if sk == BASELINE or s["gain"] <= 0 or len(s["eff"]) < 3:
            continue
        base_rate = len(s["eff"]) / max(n, 1)
        type_lift = {}
        for qtype, pat in QUESTION_TYPES.items():
            n_type = sum(1 for sid in all_ids
                         if re.search(pat, results[sk].get(sid, {})
                                      .get("meta", {}).get("question", ""), re.I))
            n_eff  = sum(1 for sid in s["eff"]
                         if re.search(pat, results[sk].get(sid, {})
                                      .get("meta", {}).get("question", ""), re.I))
            if n_type >= 3 and base_rate > 0 and (n_eff / n_type) / base_rate > 1.2:
                type_lift[qtype] = round((n_eff / n_type) / base_rate, 2)
        routing_rules.append({
            "skill":       sk,
            "gain":        round(s["gain"], 4),
            "n_effective": len(s["eff"]),
            "n_regression":len(s["reg"]),
            "type_lift":   type_lift,
        })
    routing_rules.sort(key=lambda r: -r["gain"])

    if routing_rules:
        print(f"\n── Routing rules ──")
        for r in routing_rules[:5]:
            print(f"  {r['skill']}: gain={r['gain']:+.1%}  eff={r['n_effective']}"
                  f"  type_lift={r['type_lift']}")

    # ── Reflection: coordinate descent in frame × prompt space ──
    frame_accs  = defaultdict(list)
    prompt_accs = defaultdict(list)
    for sk, s in stats.items():
        skill_obj = SKILL_REGISTRY.get(sk)
        if skill_obj:
            frame_accs[skill_obj.frame_key].append(s["acc"])
            prompt_accs[skill_obj.prompt_key].append(s["acc"])

    def mean(lst): return sum(lst) / len(lst) if lst else 0

    top_frames  = sorted(frame_accs,  key=lambda k: -mean(frame_accs[k]))[:3]
    top_prompts = sorted(prompt_accs, key=lambda k: -mean(prompt_accs[k]))[:3]

    new_candidates = []
    for fk in top_frames:
        for pk in top_prompts:
            cname = f"{fk}_{pk}"
            if cname not in SKILL_REGISTRY:
                new_candidates.append({
                    "name":       cname,
                    "frame_key":  fk,
                    "prompt_key": pk,
                    "reason":     f"reflection: top frame={fk}  top prompt={pk}",
                })

    # Targeted: for question types where no skill has lift > 1.5×,
    # try frame=slow_fast (good for temporal) and frame=uniform_64 (more detail)
    covered_types = set()
    for r in routing_rules:
        covered_types.update(r["type_lift"].keys())
    weak_types = set(QUESTION_TYPES) - covered_types

    targeted_map = {
        "temporal":  ("slow_fast",   "temporal_cot"),
        "spatial":   ("uniform_64",  "option_focus"),
        "detail":    ("uniform_64",  "desc_first"),
        "counting":  ("keyframe",    "cot"),
        "causal":    ("first_last",  "cot"),
        "action":    ("motion_dense","cot"),
    }
    for wt in weak_types:
        if wt in targeted_map:
            fk, pk = targeted_map[wt]
            cname  = f"{fk}_{pk}"
            if cname not in SKILL_REGISTRY and not any(c["name"] == cname for c in new_candidates):
                new_candidates.append({
                    "name":       cname,
                    "frame_key":  fk,
                    "prompt_key": pk,
                    "reason":     f"targeted: weak type={wt}",
                })

    print(f"\n── Reflection proposals ({len(new_candidates)} new candidates) ──")
    for c in new_candidates:
        print(f"  {c['name']}  ({c['reason']})")

    # ── Save ────────────────────────────────────────────────
    log_dir  = str(Path(results_path).parent)
    analysis = {
        "n":              n,
        "baseline":       BASELINE,
        "baseline_acc":   round(base_acc, 4),
        "skill_stats":    {sk: {"acc": round(s["acc"], 4), "gain": round(s["gain"], 4),
                                "n_effective": len(s["eff"]), "n_regression": len(s["reg"])}
                           for sk, s in stats.items()},
        "routing_rules":  routing_rules,
        "new_candidates": new_candidates,
        "top_frames":     top_frames,
        "top_prompts":    top_prompts,
    }
    out = str(Path(log_dir) / "analysis.json")
    with open(out, "w") as f:
        json.dump(analysis, f, indent=2)
    print(f"\nAnalysis saved → {out}")
    return analysis


if __name__ == "__main__":
    import sys
    analyze(sys.argv[1])
