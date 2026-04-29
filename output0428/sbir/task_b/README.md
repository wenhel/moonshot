# SBIR Task B — Detect + identify parts on real-world video keyframes

**Goal**: For 5 keyframes sampled from a 13-second drone-assembly video clip,
locate every visible drone part with a bbox and identify which `parts_library`
entry it corresponds to.

**Input**:
- Video: `output0427/hierarchical-video-splitter/pen_0.5/seg_000/L2_000_t0.0-13.0.mp4`
  (13s, fps=30, 390 frames)
- 5 keyframes sampled at t = 0.5, 4.0, 7.0, 10.0, 12.5 seconds → saved as
  PNGs under `v{N}/frames/`
- Same `parts_library` as Task A: `output0428/sbir/seg_ablation/F/`
  (21 parts built by Method F = Qwen2.5-VL bbox + SAM3 mask refine).

**Output structure (per version)**:
```
v{N}/
├── frames/                       # extracted keyframes
│   └── frame_t<XX.X>s.png
├── frame_t<XX.X>s/
│   ├── detections.json           # {bbox, top1_part_id, top3, sim, ...} per detection
│   ├── overlay.png               # frame + bboxes + retrieved label
│   └── crops/det_MM.png          # one crop per detection
├── summary.json                  # per-frame counts
└── model-<vlm-id>.json           # (v2 only) which VLM produced the bboxes
```

---

## v1 — SAM3 detect + SigLIP retrieve (plan0428 baseline)

Same recipe as Task A v1: build a prompt vocabulary from
`parts_library.display_name`, run SAM3 text-prompted detection on each
frame, embed each crop with SigLIP, cosine-match against library.

**Pipeline**:
1. Extract 5 keyframes from L2_000 mp4.
2. SAM3 prompt vocabulary = 18 unique library names.
3. Per frame: run `Sam3DetectorTracker.detect_in_image(text=<each prompt>)`.
4. SigLIP embed each crop → cosine vs library → top-1 + threshold ≥ 0.7.

**Script**: `tests/extra/test_sbir_task_b_v1.py`

**Result**:

| Frame | raw | kept | confident |
|---|---|---|---|
| t=0.5s | **0** | 0 | 0 |
| t=4.0s | **0** | 0 | 0 |
| t=7.0s | **0** | 0 | 0 |
| t=10.0s | **0** | 0 | 0 |
| t=12.5s | **0** | 0 | 0 |

**All 5 frames return 0 SAM3 detections** for all 18 prompts. This exactly
matches the prediction in CLAUDE.md "Domain facts":
- **Fact 1**: drone-specific parts (top plate, X-Lock, FPV mount) are not
  in SAM3's open-vocab vision vocabulary — text prompts don't ground.
- **Fact 2**: M3 screws on a video frame are too small (5-10 px wide on
  this video's resolution) for full-frame SAM3 to detect.

This v1 exists to **document the documented failure mode**, not as a
working pipeline. Use v2 for actual results.

---

## v2 — Qwen2.5-VL candidate bbox + DINOv2 retrieve (plan 3b)

Splits the task by what each model is good at:
- **Qwen2.5-VL** locates candidate objects on the frame and filters out
  hands / tools / table (it's good at general scene understanding).
- **DINOv2** matches each cropped candidate to the manual's library by
  visual similarity (it's good at self-supervised cross-domain matching,
  i.e. real-world photo ↔ manual line-art reference).

Why DINOv2 not SigLIP: parts_library reference crops are isometric drawings,
keyframes are real-world photos. Self-supervised DINOv2 features tend to be
more domain-robust than SigLIP's text-aligned image space (per [Manual-PA
ICCV 2025](https://openaccess.thecvf.com/content/ICCV2025/papers/Zhang_Manual-PA_Learning_3D_Part_Assembly_from_Instruction_Diagrams_ICCV_2025_paper.pdf)
which uses DINO-style features for manual ↔ part-cloud retrieval).

**Pipeline**:
1. Extract 5 keyframes (same as v1).
2. DINOv2 (`facebookresearch/dinov2_vits14`) embed library crops →
   `(21, 384)` matrix.
3. Per frame: feed to Qwen via `config/labeler/frame_object_bbox.yaml` →
   `[{description, bbox_2d, is_part_candidate}]`.
4. Filter `is_part_candidate=true` (drop hands/tools).
5. DINOv2 embed each remaining crop → cosine vs library → top-1 + top-3.
6. Threshold sim ≥ 0.5 → confident (lower than v1's 0.7 because of the
   manual ↔ photo domain gap).

**Script**: `tests/extra/test_sbir_task_b_v2.py`
**VLM**: `qwen/qwen2.5-vl-72b-instruct` (OpenRouter)

**Result**:

| Frame | Qwen returned | candidates | kept | confident (sim ≥ 0.5) |
|---|---|---|---|---|
| t=0.5s | 4 | 4 | 4 | 1 |
| t=4.0s | 6 | 6 | 6 | 2 |
| t=7.0s | 4 | 4 | 4 | 1 |
| t=10.0s | 5 | 5 | 5 | 2 |
| t=12.5s | 5 | 5 | 5 | 1 |

Total: 24 candidate bboxes, 7 confident retrievals. Real output (vs v1's
0) — to be human-reviewed via overlay PNGs to assess actual precision.

---

## How to interpret each `detections.json`

Each entry:
- `bbox_xyxy`: pixel `[x0, y0, x1, y1]` in the frame.
- `qwen_description` (v2 only): Qwen's natural-language description of the
  object (helpful when `top1_label = "unknown"` — tells you what was there).
- `top1_part_id` + `top1_label`: best library match (or "unknown" if
  cosine below threshold).
- `top1_sim`: cosine similarity in [0, 1].
- `top3`: runner-up library matches with their sims (useful for debugging
  ambiguous cases).
- `crop_path`: cropped image of the detection (saved under `crops/`).

---

## How to re-run

```bash
# v1 — expected to produce all-zero output (documents the failure mode)
python -m tests.extra.test_sbir_task_b_v1 --device cuda:0

# v2 (requires OPENROUTER_API_KEY in code/.env)
python -m tests.extra.test_sbir_task_b_v2 --device cuda:0
```

Both scripts `shutil.rmtree(out_root)` at start. Adjust keyframe sampling
with `--timestamps "t1,t2,t3,..."` (default `0.5,4.0,7.0,10.0,12.5`).

---

## Known limitations

- **v2 confidence is calibration-dependent**: sim threshold 0.5 is a
  heuristic. Real precision/recall needs ground-truth annotation on a few
  frames.
- **Per-screw identity is not solvable here**: per CLAUDE.md Fact 2,
  M3x6 vs M3x16 vs M3x22 cannot be distinguished from vision alone in
  these video frames. Any "M3 screw" retrieval should be treated as
  "screw type X (one of three)" not as a confident exact match.
- **Domain gap**: manual reference images are clean isometric drawings;
  real frames have shadows, occlusion, motion blur, perspective. DINOv2
  helps but does not fully bridge this gap. Top-3 retrieval inspection is
  recommended over blind top-1 acceptance.
- **Qwen sometimes truncates output** when frames are very busy
  (max_tokens=8192 in yaml; if hit, reduce expected entries via the
  prompt's "under 30 entries per frame" hint).
