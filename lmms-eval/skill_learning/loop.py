"""
Autonomous Skill Discovery Loop

Flow (single SLURM job, model loaded once):
  Iteration 1: evaluate all initial skills (14 skills × N samples)
  Analyze → routing rules + reflection candidates
  Iteration 2: evaluate new skill candidates (coordinate descent)
  Analyze → updated routing rules
  ... repeat up to max_iters

Stopping: no new candidates OR max_iters reached.

Usage:
  python -m skill_learning.loop --n 100 --max_iters 3 --log_dir <path>
"""

from __future__ import annotations
import os, json, argparse
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from skill_learning.skills   import SKILL_REGISTRY, FRAME_STRATEGIES, PROMPT_STRATEGIES, Skill, BASELINE
from skill_learning.eval_loop import load_samples, load_model, run_eval
from skill_learning.analyze  import analyze


def _register_new(candidates: list) -> list:
    """Add candidates to SKILL_REGISTRY; return names of newly added."""
    added = []
    for c in candidates:
        nm = c["name"]
        if nm in SKILL_REGISTRY:
            continue
        fk, pk = c["frame_key"], c["prompt_key"]
        if fk not in FRAME_STRATEGIES or pk not in PROMPT_STRATEGIES:
            print(f"  [skip] {nm}: unknown frame={fk} or prompt={pk}")
            continue
        SKILL_REGISTRY[nm] = Skill(nm, fk, pk, tags=["reflection"])
        added.append(nm)
    return added


def run_loop(n: int, log_dir: str, max_iters: int = 3):
    os.makedirs(log_dir, exist_ok=True)
    results_path = str(Path(log_dir) / "results.json")

    print(f"\n{'='*60}")
    print(f"Skill Discovery Loop")
    print(f"  n={n}  max_iters={max_iters}  log={log_dir}")
    print(f"  initial skills: {len(SKILL_REGISTRY)}")
    print(f"{'='*60}")

    samples = load_samples(n)
    print(f"Loaded {len(samples)} samples.\n")

    # Load model ONCE for the entire loop
    model, processor, tokenizer = load_model()

    history        = []
    evaluated_set  = set()     # skills already in results.json
    pending        = list(SKILL_REGISTRY.keys())   # initial batch

    for iteration in range(1, max_iters + 1):
        print(f"\n{'#'*60}")
        print(f"# ITERATION {iteration}  |  pending={len(pending)} skills")
        print(f"{'#'*60}")

        if not pending:
            print("Nothing new to evaluate — stopping.")
            break

        run_eval(samples, pending, log_dir, model, processor, tokenizer)
        evaluated_set.update(pending)

        # Analyze
        analysis = analyze(results_path)
        best_sk  = max(analysis["skill_stats"].items(), key=lambda x: x[1]["acc"])
        history.append({
            "iteration":    iteration,
            "n_skills":     len(evaluated_set),
            "baseline_acc": analysis["baseline_acc"],
            "best_skill":   best_sk[0],
            "best_acc":     best_sk[1]["acc"],
            "best_gain":    best_sk[1]["gain"],
            "new_candidates": [c["name"] for c in analysis["new_candidates"]],
        })

        print(f"\n  ── Iteration {iteration} summary ──")
        print(f"  Baseline:  {BASELINE}  acc={analysis['baseline_acc']:.1%}")
        print(f"  Best:      {best_sk[0]}  acc={best_sk[1]['acc']:.1%}"
              f"  gain={best_sk[1]['gain']:+.1%}")

        # Register and schedule new candidates
        added   = _register_new(analysis["new_candidates"])
        pending = added

        if not added:
            print("  No new candidates to add — converged.")
            break
        print(f"  Added {len(added)} new skills: {added}")

    # ── Final report ─────────────────────────────────────────
    print(f"\n{'='*60}")
    print("LOOP COMPLETE")
    print(f"{'='*60}")
    for h in history:
        print(f"  Iter {h['iteration']}: best={h['best_skill']}"
              f"  acc={h['best_acc']:.1%}  gain={h['best_gain']:+.1%}"
              f"  total_skills={h['n_skills']}")

    # Final analysis (all skills)
    if evaluated_set:
        print("\n── Final routing rules ──")
        with open(str(Path(log_dir) / "analysis.json")) as f:
            final = json.load(f)
        for rule in final.get("routing_rules", [])[:8]:
            print(f"  {rule['skill']}: gain={rule['gain']:+.1%}  "
                  f"eff={rule['n_effective']}  type_lift={rule['type_lift']}")

    # Save loop history
    hist_path = str(Path(log_dir) / "loop_history.json")
    with open(hist_path, "w") as f:
        json.dump(history, f, indent=2)
    print(f"\nLoop history → {hist_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n",         type=int, default=100,
                        help="Number of samples from discovery set")
    parser.add_argument("--max_iters", type=int, default=3,
                        help="Max reflection iterations")
    parser.add_argument("--log_dir",   type=str, default=None,
                        help="Directory for results/checkpoints")
    args = parser.parse_args()

    if args.log_dir is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.log_dir = f"/data/DERI-Gong/jh015/lmms-eval/logs/skill_loop_{ts}"

    run_loop(args.n, args.log_dir, args.max_iters)


if __name__ == "__main__":
    main()
