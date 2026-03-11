"""
Skill Registry for Video VQA.

A Skill = (frame_strategy, prompt_strategy).
  frame_strategy: (vpath: str) -> (frames: List[PIL.Image], duration: float)
  prompt_strategy: (frames, question, duration) -> messages list (Qwen2.5-VL format)

Baseline: uniform_32f + direct prompt.

Frame strategies (local, no API):
  uniform_16 / uniform_32 / uniform_64
  motion_dense   — densest frames in highest-motion window
  keyframe       — scene-boundary frames via histogram diff
  first_last     — emphasise temporal boundaries
  slow_fast      — 1/4 sparse overview + 3/4 from motion peak (Slow-Fast, arxiv 2601.11359)

Prompt strategies (zero-shot, no fine-tuning):
  direct         — baseline: "Answer with the letter only."
  cot            — chain-of-thought before answering
  temporal_cot   — inject frame timestamps + temporal reasoning cue
  option_focus   — systematically evaluate each option
  desc_first     — describe video content then answer
"""

from __future__ import annotations
import numpy as np
import base64, io, re
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Callable
from PIL import Image


MAX_PIXELS = 602112
MIN_PIXELS = 256 * 28 * 28
BASELINE   = "uniform_32_direct"


# ─────────────────────────────────────────────
# Frame strategies
# ─────────────────────────────────────────────

def _read_video(vpath: str):
    import decord
    vr = decord.VideoReader(vpath, ctx=decord.cpu(0), num_threads=4)
    fps = vr.get_avg_fps()
    dur = len(vr) / max(fps, 1e-6)
    return vr, fps, dur


def _get_frames(vr, indices: List[int]) -> List[Image.Image]:
    indices = [min(max(0, i), len(vr) - 1) for i in indices]
    arr = vr.get_batch(indices).asnumpy()
    return [Image.fromarray(f.astype("uint8"), "RGB") for f in arr]


def uniform(vpath: str, n: int) -> Tuple[List[Image.Image], float]:
    vr, fps, dur = _read_video(vpath)
    idx = np.linspace(0, len(vr) - 1, n, dtype=int).tolist()
    return _get_frames(vr, idx), dur


def motion_dense(vpath: str, n: int) -> Tuple[List[Image.Image], float]:
    """n frames concentrated in highest-motion 3-second window."""
    vr, fps, dur = _read_video(vpath)
    total  = len(vr)
    stride = max(1, int(fps / 4))
    probe  = list(range(0, total, stride))
    arr    = vr.get_batch(probe).asnumpy().astype(np.float32)
    diffs  = np.mean(np.abs(arr[1:] - arr[:-1]), axis=(1, 2, 3)) if len(probe) > 1 else np.zeros(1)
    win    = max(1, int(3.0 * fps / stride))
    scores = np.convolve(diffs, np.ones(win) / win, mode="same")
    peak   = int(np.argmax(scores))
    s = max(0, probe[max(0, peak - win // 2)])
    e = min(total - 1, probe[min(len(probe) - 1, peak + win // 2)])
    idx = np.linspace(s, e, n, dtype=int).tolist()
    return _get_frames(vr, idx), dur


def keyframe(vpath: str, n: int) -> Tuple[List[Image.Image], float]:
    """n scene-boundary keyframes via colour-histogram diff."""
    vr, fps, dur = _read_video(vpath)
    total  = len(vr)
    stride = max(1, int(fps / 2))
    probe  = list(range(0, total, stride))
    arr    = vr.get_batch(probe).asnumpy()
    diffs, prev = [0.0], None
    for a in arr:
        h = np.histogram(a, bins=64, range=(0, 255))[0].astype(np.float32)
        h /= h.sum() + 1e-8
        diffs.append(float(np.abs(h - prev).sum()) if prev is not None else 0.0)
        prev = h
    diffs  = np.array(diffs[1:])
    if len(diffs) < n:
        return uniform(vpath, n)
    gap    = max(1, len(diffs) // (n * 2))
    sel    = [0]
    for idx in np.argsort(diffs)[::-1]:
        if all(abs(idx - s) >= gap for s in sel):
            sel.append(idx)
        if len(sel) >= n:
            break
    vidx = sorted([probe[min(i, len(probe) - 1)] for i in sel])
    return _get_frames(vr, vidx), dur


def first_last(vpath: str, n: int) -> Tuple[List[Image.Image], float]:
    """n//2 frames from first half + n//2 from second half."""
    vr, fps, dur = _read_video(vpath)
    total = len(vr)
    h     = n // 2
    fi    = np.linspace(0, total // 2 - 1, h, dtype=int).tolist()
    li    = np.linspace(total // 2, total - 1, n - h, dtype=int).tolist()
    return _get_frames(vr, fi + li), dur


def slow_fast(vpath: str, n: int) -> Tuple[List[Image.Image], float]:
    """Slow-Fast: n//4 uniform 'slow' overview + 3n//4 from motion peak 'fast' window."""
    vr, fps, dur = _read_video(vpath)
    total   = len(vr)
    n_slow  = max(1, n // 4)
    n_fast  = n - n_slow
    slow_idx = np.linspace(0, total - 1, n_slow, dtype=int).tolist()
    # motion window
    stride = max(1, int(fps / 4))
    probe  = list(range(0, total, stride))
    arr    = vr.get_batch(probe).asnumpy().astype(np.float32)
    diffs  = np.mean(np.abs(arr[1:] - arr[:-1]), axis=(1, 2, 3)) if len(probe) > 1 else np.zeros(1)
    win    = max(1, int(3.0 * fps / stride))
    scores = np.convolve(diffs, np.ones(win) / win, mode="same")
    peak   = int(np.argmax(scores))
    s = max(0, probe[max(0, peak - win // 2)])
    e = min(total - 1, probe[min(len(probe) - 1, peak + win // 2)])
    fast_idx = np.linspace(s, e, n_fast, dtype=int).tolist()
    all_idx  = sorted(set(slow_idx + fast_idx))[:n]
    return _get_frames(vr, all_idx), dur


FRAME_STRATEGIES: Dict[str, Callable] = {
    "uniform_16":   lambda v: uniform(v, 16),
    "uniform_32":   lambda v: uniform(v, 32),
    "uniform_64":   lambda v: uniform(v, 64),
    "motion_dense": lambda v: motion_dense(v, 32),
    "keyframe":     lambda v: keyframe(v, 32),
    "first_last":   lambda v: first_last(v, 32),
    "slow_fast":    lambda v: slow_fast(v, 32),
}


# ─────────────────────────────────────────────
# Prompt strategies
# ─────────────────────────────────────────────

_SYS = "You are a helpful assistant analyzing video frames to answer questions accurately."


def _enc(img: Image.Image) -> dict:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return {
        "type": "image",
        "image": f"data:image/jpeg;base64,{b64}",
        "max_pixels": MAX_PIXELS, "min_pixels": MIN_PIXELS,
    }


def direct(frames: List[Image.Image], question: str, duration: float) -> list:
    """Baseline: show frames + answer with letter only."""
    user = [_enc(f) for f in frames]
    user.append({"type": "text",
                 "text": f"Question: {question}\nAnswer with the letter only (A/B/C/D/E)."})
    return [{"role": "system", "content": _SYS}, {"role": "user", "content": user}]


def cot(frames: List[Image.Image], question: str, duration: float) -> list:
    """Chain-of-Thought: reason step-by-step before answering."""
    user = [_enc(f) for f in frames]
    user.append({"type": "text", "text": (
        f"Question: {question}\n\n"
        f"Think step by step:\n"
        f"1. Describe the key visual evidence across the frames.\n"
        f"2. Identify which option is supported by what you see.\n"
        f"3. State your final answer as a single letter (A/B/C/D/E)."
    )})
    return [{"role": "system", "content": _SYS}, {"role": "user", "content": user}]


def temporal_cot(frames: List[Image.Image], question: str, duration: float) -> list:
    """Temporal CoT: inject per-frame timestamps, encourage temporal reasoning."""
    n   = len(frames)
    tss = "  ".join(f"[{round(i/(max(n-1,1))*duration, 1)}s]" for i in range(n))
    user = [_enc(f) for f in frames]
    user.append({"type": "text", "text": (
        f"These {n} frames span {duration:.1f}s. Frame timestamps: {tss}\n\n"
        f"Question: {question}\n\n"
        f"Consider the temporal order and progression. Think step by step, "
        f"then give your final answer as a single letter (A/B/C/D/E)."
    )})
    return [{"role": "system", "content": _SYS}, {"role": "user", "content": user}]


def option_focus(frames: List[Image.Image], question: str, duration: float) -> list:
    """Option-by-option evaluation, then select best."""
    user = [_enc(f) for f in frames]
    user.append({"type": "text", "text": (
        f"Question: {question}\n\n"
        f"Carefully evaluate each answer option against the visual evidence. "
        f"Eliminate wrong options, then state your final answer as a single letter (A/B/C/D/E)."
    )})
    return [{"role": "system", "content": _SYS}, {"role": "user", "content": user}]


def desc_first(frames: List[Image.Image], question: str, duration: float) -> list:
    """Describe video content first, then answer the question."""
    user = [_enc(f) for f in frames]
    user.append({"type": "text", "text": (
        f"First briefly describe the key events and objects visible across these frames. "
        f"Then answer: {question}\n"
        f"Final answer (letter only): "
    )})
    return [{"role": "system", "content": _SYS}, {"role": "user", "content": user}]


PROMPT_STRATEGIES: Dict[str, Callable] = {
    "direct":       direct,
    "cot":          cot,
    "temporal_cot": temporal_cot,
    "option_focus": option_focus,
    "desc_first":   desc_first,
}


# ─────────────────────────────────────────────
# Skill definition
# ─────────────────────────────────────────────

@dataclass
class Skill:
    name:       str
    frame_key:  str
    prompt_key: str
    tags:       List[str] = field(default_factory=list)

    def run(self, vpath: str, question: str) -> dict:
        frames, duration = FRAME_STRATEGIES[self.frame_key](vpath)
        messages = PROMPT_STRATEGIES[self.prompt_key](frames, question, duration)
        return {
            "frames":   frames,
            "messages": messages,
            "duration": duration,
            "meta": {
                "skill":     self.name,
                "frame_key": self.frame_key,
                "prompt_key":self.prompt_key,
                "n_frames":  len(frames),
                "question":  question,
            },
        }


# ─────────────────────────────────────────────
# Initial skill registry
# ─────────────────────────────────────────────
# Design: key frame strategies × key prompt strategies
# Keep initial set ≤ 14 to fit in 8-hour SLURM job (100 samples)

_INITIAL: List[Skill] = [
    # ── Baseline ──
    Skill("uniform_32_direct",      "uniform_32",   "direct",       ["baseline"]),

    # ── Frame variants (direct prompt — isolates frame effect) ──
    Skill("uniform_16_direct",      "uniform_16",   "direct"),
    Skill("uniform_64_direct",      "uniform_64",   "direct"),
    Skill("motion_dense_direct",    "motion_dense", "direct"),
    Skill("keyframe_direct",        "keyframe",     "direct"),
    Skill("first_last_direct",      "first_last",   "direct"),
    Skill("slow_fast_direct",       "slow_fast",    "direct"),

    # ── Prompt variants (uniform_32 frames — isolates prompt effect) ──
    Skill("uniform_32_cot",         "uniform_32",   "cot"),
    Skill("uniform_32_temporal",    "uniform_32",   "temporal_cot"),
    Skill("uniform_32_option",      "uniform_32",   "option_focus"),
    Skill("uniform_32_desc",        "uniform_32",   "desc_first"),

    # ── Best-guess combos ──
    Skill("slow_fast_cot",          "slow_fast",    "cot"),
    Skill("keyframe_temporal",      "keyframe",     "temporal_cot"),
    Skill("motion_dense_cot",       "motion_dense", "cot"),
]

SKILL_REGISTRY: Dict[str, Skill] = {s.name: s for s in _INITIAL}
