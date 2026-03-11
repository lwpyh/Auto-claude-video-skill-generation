"""
Evaluation loop: run skill × sample → correctness matrix → results.json

Results are checkpointed every 10 samples and support resuming.
Model is loaded externally and passed in to avoid repeated loading.
"""

from __future__ import annotations
import os, re, json, time
from pathlib import Path
from typing import List, Dict, Optional

DATA_FILE  = "/data/DERI-Gong/jh015/lmms-eval/eval_deltaS_v2.jsonl"
VIDEO_ROOT = "/data/DERI-Gong/jh015/VideoZoomer"
HF_HOME    = "/data/home/acw652/.cache/huggingface"
MODEL_PATH = "Qwen/Qwen2.5-VL-7B-Instruct"
MAX_NEW    = 256


# ── Data ────────────────────────────────────────────────────

def load_samples(n: int, offset: int = 0) -> List[Dict]:
    samples, count = [], 0
    with open(DATA_FILE) as f:
        for line in f:
            d = json.loads(line.strip())
            if not d.get("videos"):
                continue
            rel   = d["videos"][0]
            p     = Path(rel)
            parts = p.parts
            rel2  = Path(*parts[1:]) if parts and parts[0] in (".", "..") else p
            vpath = str(Path(VIDEO_ROOT) / rel2)
            if not os.path.exists(vpath):
                continue
            count += 1
            if count > offset:
                d["_video_path"] = vpath
                d["_id"]         = count
                samples.append(d)
            if len(samples) >= n:
                break
    return samples


def get_gt(sample: Dict) -> str:
    m = re.search(r"<answer>(.*?)</answer>", sample.get("solution", ""))
    return m.group(1).strip() if m else sample.get("solution", "").strip()


def extract_answer(text: str) -> str:
    for pat in [r"\(([A-E])\)", r"answer is\s+([A-E])\b",
                r"^([A-E])[.\s]", r"\b([A-E])\b"]:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).upper()
    return ""


# ── Model ────────────────────────────────────────────────────

def load_model():
    import torch
    from transformers import AutoProcessor, AutoTokenizer, Qwen2_5_VLForConditionalGeneration
    os.environ["HF_HOME"]              = HF_HOME
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    print("Loading Qwen2.5-VL-7B-Instruct ...")
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        MODEL_PATH, torch_dtype=torch.bfloat16,
        device_map="auto", attn_implementation="flash_attention_2",
    ).eval()
    from skill_learning.skills import MAX_PIXELS, MIN_PIXELS
    processor = AutoProcessor.from_pretrained(
        MODEL_PATH, max_pixels=MAX_PIXELS, min_pixels=MIN_PIXELS)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    print("Model loaded.")
    return model, processor, tokenizer


def run_vqa(messages: list, model, processor, tokenizer) -> str:
    import torch
    from qwen_vl_utils import process_vision_info
    text  = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    imgs, vids = process_vision_info(messages)
    inputs = processor(text=[text], images=imgs, videos=vids,
                       padding=True, return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=MAX_NEW, do_sample=False,
            temperature=None, top_p=None, use_cache=True,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.pad_token_id,
        )
    seq = out[0][inputs.input_ids.shape[1]:]
    return processor.decode(seq, skip_special_tokens=True)


# ── Eval loop ────────────────────────────────────────────────

def run_eval(
    samples:     List[Dict],
    skill_names: List[str],
    log_dir:     str,
    model=None, processor=None, tokenizer=None,
) -> Dict:
    """
    Evaluate skill_names × samples → results dict.
    Checkpoints every 10 samples. Resumes automatically from existing results.json.
    If model/processor/tokenizer are None, loads them internally.
    """
    from skill_learning.skills import SKILL_REGISTRY, BASELINE

    results_path = os.path.join(log_dir, "results.json")
    os.makedirs(log_dir, exist_ok=True)

    # Resume
    if os.path.exists(results_path):
        with open(results_path) as f:
            results = json.load(f)
        done_ids = set.union(*[set(r.keys()) for r in results.values()]) if results else set()
        print(f"Resuming — {len(done_ids)} sample-slots done.")
    else:
        results  = {}
        done_ids = set()

    # Ensure all skill keys exist
    for sn in skill_names:
        if sn not in results:
            results[sn] = {}

    _own_model = model is None
    if _own_model:
        model, processor, tokenizer = load_model()

    n = len(samples)
    for i, sample in enumerate(samples):
        sid = str(sample["_id"])
        # skip only if ALL skills have this sample done
        if all(sid in results.get(sn, {}) for sn in skill_names):
            continue

        vpath    = sample["_video_path"]
        question = sample["problem"]
        gt       = get_gt(sample)
        print(f"\n[{i+1}/{n}] GT={gt}  {Path(vpath).name[:45]}")

        for sn in skill_names:
            if sid in results[sn]:
                continue          # already done for this skill
            t0 = time.time()
            try:
                skill   = SKILL_REGISTRY[sn]
                out     = skill.run(vpath, question)
                resp    = run_vqa(out["messages"], model, processor, tokenizer)
                pred    = extract_answer(resp)
                correct = (pred == gt)
                meta    = out["meta"]
            except Exception as e:
                pred, correct = "", False
                meta = {"error": str(e), "question": question}
            elapsed = time.time() - t0

            results[sn][sid] = {
                "correct": correct,
                "pred":    pred,
                "gt":      gt,
                "meta":    meta,
            }
            mark = "✓" if correct else "✗"
            print(f"  [{sn:<30}] {pred} {mark}  ({elapsed:.1f}s)")

        if (i + 1) % 10 == 0:
            _save(results, results_path)
            print("  [checkpoint]")

    _save(results, results_path)
    _print_summary(results, skill_names, BASELINE)
    return results


def _save(results, path):
    with open(path, "w") as f:
        json.dump(results, f, indent=2)


def _print_summary(results, skill_names, baseline):
    base_acc = None
    rows = []
    for sn in skill_names:
        r   = results.get(sn, {})
        acc = sum(v["correct"] for v in r.values()) / max(len(r), 1)
        rows.append((sn, acc))
        if sn == baseline:
            base_acc = acc
    print(f"\n{'='*60}")
    print(f"{'Skill':<32} {'Acc':>6}  {'vs baseline':>12}")
    print(f"{'='*60}")
    for sn, acc in sorted(rows, key=lambda x: -x[1]):
        delta  = f"{acc - base_acc:+.1%}" if base_acc is not None and sn != baseline else "—"
        marker = " ← baseline" if sn == baseline else ""
        print(f"  {sn:<30} {acc:>5.1%}  {delta:>12}{marker}")
