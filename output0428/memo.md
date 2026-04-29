# output0428 — experiment results index

A day's work from 2026-04-28. This file is a navigation memo;
**full decision narrative lives in `code/doc/decision.md`** in the
upstream repo (not in this mirror). 中文版见 [memo-chn.md](memo-chn.md).

---

## Three core tasks (T1 / T2 / T3)

Every entry in `decision.md` falls into one of three categories. Each row
in the master summary table below is tagged `[T1]` / `[T2]` / `[T3]`.

### [T1] Build a parts library from the manual
Cut every distinct part out of the manual's parts page once, building the
**gallery shared by downstream T2 + T3**. Each entry contains: cell crop,
object mask, bbox, display_name.

Input: `parts_page2.png` (one manual page)
Output: 21 part entries

### [T2] Retrieve manual parts on **manual step pages**
Given 6 step PNGs (manual's step diagrams), for each page locate every
visible part bbox and identify which T1 library entry it matches.

Input: 6 step PNGs (other pages of the same manual)
Output: per-step bbox + label per part

### [T3] Retrieve manual parts on **real video frames**
Given keyframes sampled from a real assembly video, for each frame locate
every visible part bbox and identify which T1 library entry it matches.
**This is cross-domain retrieval (manual line-art ↔ real photo) — the
hardest task.**

Input: 5 video keyframes (from `L2_000_t0.0-13.0.mp4`)
Output: per-frame bbox + label per part

> T3 appears as two `decision.md` entries (`MR` and `SBIR-B`) — **same
> task, two parallel approaches**. Different bbox candidate sources (VLM
> grounding vs SAM2 AMG); both use DINOv2 for retrieval.

---

## 📋 Master summary

Mirrors `code/doc/decision.md`'s master summary table, with `[T*]` tags
prepended and result paths converted to github web links.

| Task ID | Task description | Current result | Result dir |
|---|---|---|---|
| **`[T3]`** **MR** | manual ↔ video-frame cross-domain part retrieval (approach: SAM2 AMG + DINOv2) | ✅ Best = path (b) SAM 2 AMG + DINOv2; imperfect but most usable per visual review | [path_b_sam2_amg_dinov2/](https://github.com/wenhel/moonshot/tree/master/output0428/sam3_image_to_video_retrieval/path_b_sam2_amg_dinov2) |
| **`[T1]`** **SBIR-1** | parts library construction (21 drone-part references) | ✅ Method F, 21/21 parts located | [sbir/seg_ablation/F/](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/seg_ablation/F) |
| **`[T2]`** **SBIR-A** | part identification on manual step pages (6 step PNGs) | ⚠ v2, 50/53 = 94% library match — **suboptimal, needs visual review** | [sbir/task_a/v2/](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_a/v2) |
| **`[T3]`** **SBIR-B** | part identification on video keyframes (5 keyframes) (approach: VLM bbox + DINOv2) | ✅ v2 + mask-bg + sim≥0.35, 20/24 confident | [sbir/task_b/v2/](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v2) |

**Status legend**: ✅ current best · ⚠ partially usable (with known limitations)

> **Overlap note**: `MR` and `SBIR-B` are both `[T3]` — same problem, two
> parallel approaches. See [T3: MR vs SBIR-B flow & model comparison](#t3-mr-vs-sbir-b)
> below for the side-by-side.

`YM` (step-matcher optimisation) is not part of this directory; its
results live under `code/output0427/` and are not mirrored here.

---

## <a id="t3-mr-vs-sbir-b"></a>[T3] MR vs SBIR-B — flow & model comparison

Both paths share the same goal: parts_library (T1 output) is the query,
video keyframes are the gallery, do cross-domain part retrieval. The
differences are entirely in **how candidate bboxes are produced** and
**how reference is preprocessed**; the retrieval encoder (DINOv2) is shared.

### Flow comparison

|  | **MR** ([path_b_sam2_amg_dinov2/](https://github.com/wenhel/moonshot/tree/master/output0428/sam3_image_to_video_retrieval/path_b_sam2_amg_dinov2)) | **SBIR-B** ([sbir/task_b/v2/](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v2)) |
|---|---|---|
| Input video | same (L2_000_t0.0-13.0.mp4) | same |
| Keyframe timestamps | same (t = 0.5, 4, 7, 10, 12.5 s) | same |
| Reference source | same (parts_library/F, 21 parts) | same |
| **Reference preprocessing** | **none**: raw cell crop (with caption + white background) encoded directly | **`apply_mask_white_bg`**: SAM3 mask paints non-object pixels white before encoding |
| **Bbox candidate model** | **SAM 2.1 hiera-large AMG**<br>local 898 MB checkpoint<br>class-agnostic, points_per_side=32 | **Qwen2.5-VL 72B Instruct**<br>OpenRouter API call<br>VLM grounding; per frame returns `[{bbox_2d, description, is_part_candidate}]` |
| **Bbox geometric filter** | `pred_iou_thresh=0.7`, `stability_score_thresh=0.85`, `min_mask_region_area=64` | bbox validity check only (x2>x1, y2>y1) |
| **Bbox semantic filter** | **none** | **`is_part_candidate=true`** (VLM-tagged; drops hands / tools / table) |
| **Total candidates over 5 frames** | **142** mask proposals (includes background / hands / tools) | **24** candidates (post VLM filter) |
| Encoder | DINOv2 vits14, 384-dim L2-normalized | same |
| **Retrieval direction** | per-**part** top-3 (gallery-side: top-3 video proposals per library part) | per-**candidate** top-1 (query-side: top-1 library part per detected object) |
| **Confidence threshold** | sim ≥ 0.45 (for visual review) | sim ≥ 0.35 (cross-domain, lower than the usual 0.5) |
| top-1 sim mean | 0.41 | **0.435** (mask-bg boost) |
| top-1 sim max | ~0.50 | **0.65** |
| Confident count | sim≥0.45 considered confident (see [retrieval.json](https://github.com/wenhel/moonshot/blob/master/output0428/sam3_image_to_video_retrieval/path_b_sam2_amg_dinov2/retrieval.json)) | **20/24** at sim≥0.35 |
| API cost | $0 (fully local) | ~$0.025 (5 Qwen calls; cached after first run) |
| Failure mode | **Sticky proposal**: ~7 parts collapse to one mid-frame mask | **SPLIT PLATE bias**: post mask-bg, the hole-pattern feature dominates and most "metal-with-holes" candidates retrieve to SPLIT PLATE |
| Detail README | [path_b/README.md](https://github.com/wenhel/moonshot/blob/master/output0428/sam3_image_to_video_retrieval/path_b_sam2_amg_dinov2/README.md) | [task_b/README.md](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/task_b/README.md) |

### When to pick which

| Scenario | Recommendation |
|---|---|
| "Does this part appear in the video? Roughly where?" (gallery-driven recall) | **MR**: per-part top-K, higher recall |
| "Which library part does this video object correspond to?" (query-driven naming) | **SBIR-B**: per-candidate top-1, VLM has filtered non-parts |
| Need pixel-tight bbox (mask boundary on object) | **MR**: SAM 2 AMG gives mask boundary |
| Need semantically clean candidates (no hands / tools / table) | **SBIR-B**: `is_part_candidate` already filtered |
| Offline / no API budget | **MR**: fully local |
| Want highest cosine numbers (mask-bg suite boost) | **SBIR-B**: mean 0.435, max 0.65 |

### Shared root limitations

Both approaches are bound by the CLAUDE.md `Domain facts`:
- **Fact 1**: drone-specific parts are not in any vision foundation model's vocabulary — SBIR-B routes around it via VLM candidate-level descriptions; MR routes around it via class-agnostic SAM 2 AMG.
- **Fact 2**: per-screw identity (M3x6 vs M3x16 vs M3x22) is not visually separable. Neither approach can resolve this — any "M3 screw" retrieval result should be treated at "screw class" granularity, not at exact-spec granularity.

Full decision record: see `code/doc/decision.md` 2026-04-29 07:13 entry.

---

## MR — manual ↔ video-frame cross-domain part retrieval

**Problem**: given a manual line-art crop of a drone part, locate the
same part in a real-world drone-assembly video frame.

**Current best path**: (b) SAM 2 AMG + DINOv2 retrieval

**Pipeline**:
1. SAM 2.1 hiera-large `AutomaticMaskGenerator` (points_per_side=32) — ~28 class-agnostic mask candidates per frame
2. DINOv2 vits14 encodes 21 manual crops → (21, 384) L2-normalized
3. DINOv2 encodes 142 mask bbox crops → (142, 384)
4. Cosine similarity → per-part top-K
5. OpenCV panels: per part [manual ‖ frame top-1 ‖ crop top-1 ‖ top-2 ‖ top-3]

**Known issues**: sim mean 0.41; "sticky proposal" failure mode where 7 parts collapse to the same mid-frame mask. **Suitable for approximate part-level localisation only — not ground truth**.

**Results**:
- Best: [`path_b_sam2_amg_dinov2/`](https://github.com/wenhel/moonshot/tree/master/output0428/sam3_image_to_video_retrieval/path_b_sam2_amg_dinov2)
- Baselines (kept for comparison):
  - [`path_c_siglip_zone/`](https://github.com/wenhel/moonshot/tree/master/output0428/sam3_image_to_video_retrieval/path_c_siglip_zone) — match bbox = zone bbox (zone routing, not part retrieval)
  - [`path_c_siglip_sw/`](https://github.com/wenhel/moonshot/tree/master/output0428/sam3_image_to_video_retrieval/path_c_siglip_sw) — sliding window
  - [`path_bc_amg_siglip/`](https://github.com/wenhel/moonshot/tree/master/output0428/sam3_image_to_video_retrieval/path_bc_amg_siglip) — AMG + SigLIP
- Raw frames: [`clip_000/`](https://github.com/wenhel/moonshot/tree/master/output0428/sam3_image_to_video_retrieval/clip_000)
- Method comparison: [`summary.md`](https://github.com/wenhel/moonshot/blob/master/output0428/sam3_image_to_video_retrieval/summary.md)

---

## SBIR-1 — parts library construction (Stage 1)

**Problem**: from the manual's parts page (`parts_page2.png`), automatically extract each part's crop + mask + bbox + name to build a library that downstream Task A/B can retrieve against.

**Current best method**: Method F = Qwen2.5-VL drawing+caption sub-bbox + SAM3 box-prompt mask refine

**Pipeline**:
1. Qwen2.5-VL (`qwen/qwen2.5-vl-72b-instruct` via OpenRouter) returns 21 cell `drawing_bbox` + `caption_bbox` pixel coordinates in one call
2. Crop a local patch at `drawing_bbox` expanded by 5% padding
3. SAM3 box-prompt within that patch refines the mask (`detect_with_box_prompt`)
4. Save full cell crop (drawing ∪ caption) + precise object mask

**Results (21/21 located)**:
- Main dir: [`sbir/seg_ablation/F/`](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/seg_ablation/F)
- README + schema: [`F/README.md`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/seg_ablation/F/README.md)
- 21-part metadata: [`parts_db.json`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/seg_ablation/F/parts_db.json)
- Raw VLM bboxes: [`vlm_bbox.json`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/seg_ablation/F/vlm_bbox.json)
- Model record: [`model-qwen-qwen2.5-vl-72b-instruct.json`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/seg_ablation/F/model-qwen-qwen2.5-vl-72b-instruct.json)
- Three overlay verification PNGs:
  - [`overlay_vlm.png`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/seg_ablation/F/overlay_vlm.png) — Qwen-supplied cell bboxes
  - [`overlay_sam3.png`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/seg_ablation/F/overlay_sam3.png) — SAM3-refined object bboxes
  - [`overlay_merged.png`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/seg_ablation/F/overlay_merged.png) — two-colour overlay + legend
- 21 part crops + masks: [`crops/`](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/seg_ablation/F/crops) / [`masks/`](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/seg_ablation/F/masks)

---

## SBIR-A — part identification on manual step pages (Task A)

**Problem**: 6 manual step PNGs; for each, locate every visible part bbox and identify which library entry it matches.

**Two versions**:

| Version | Method | Result |
|---|---|---|
| **v1** baseline | SAM3 detect (text prompt) + SigLIP cosine | 131 raw / 73 confident at sim≥0.7. **Noisy** — SAM3 maps prompts to visually similar but semantically wrong objects (CLAUDE.md Domain Fact 1). |
| **v2** Best ⚠ | Qwen2.5-VL given step page + parts vocab, returns `[{display_name, bbox_2d}]` directly | 53 returned / 50 = 94% library match. **But ⚠ suboptimal — needs visual review**; some Qwen names are still off on certain steps. |

**Results**:
- Winner: [`sbir/task_a/v2/`](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_a/v2)
- Baseline: [`sbir/task_a/v1/`](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_a/v1)
- Method README: [`task_a/README.md`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/task_a/README.md)
- Per-step results (each `step_NN/` contains `detections.json` + `overlay.png` + `crops/`):
  - [step_01](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_a/v2/step_01) · [step_02](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_a/v2/step_02) · [step_03](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_a/v2/step_03) · [step_04](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_a/v2/step_04) · [step_05](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_a/v2/step_05) · [step_06](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_a/v2/step_06)
- Summary: [`v2/summary.json`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/task_a/v2/summary.json)

---

## SBIR-B — part identification on video keyframes (Task B)

**Problem**: 5 video keyframes; for each, locate every visible part bbox and identify which library entry it matches.

**Two versions**:

| Version | Method | Result |
|---|---|---|
| **v1** baseline | SAM3 detect (text prompt) + SigLIP cosine | **0/0 across all 5 frames**. SAM3 text prompts cannot ground drone-domain parts on real-world frames at all (CLAUDE.md Facts 1+2 — drone parts not in vocab + screws too small). |
| **v2** Best ✅ | Qwen2.5-VL gives candidate bboxes (with `is_part_candidate` filter) → DINOv2 retrieve (reference uses SAM3 mask → white background) | 24 candidates / **20 confident** at sim≥0.35. Manual ↔ photo cross-domain cosine: mean 0.435, max 0.65. |

**Key tuning**:
- `mask-bg`: applying parts_library SAM3 masks to references (paint background white) closes the manual line-art ↔ real photo domain gap; cosine shifts up by 0.05-0.10
- `sim_threshold=0.35` (not the default 0.5): cross-domain cosine distribution is lower; 0.5 is too strict

**D6 image-text rerank** (attempted, **negative result**):
- SigLIP encodes 21 library labels (text) vs candidate crops (image) → cosine
- **0/20 agreement** — SigLIP has no exposure to drone industrial vocabulary (`TOP PLATE`, `M3x22MM SCREWS`); text-image cosine sits at 0.00-0.05 (noise floor)
- Retained at [`rerank_summary.json`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/task_b/v2/rerank_summary.json) for future reference

**Results**:
- Winner: [`sbir/task_b/v2/`](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v2)
- Baseline (failed): [`sbir/task_b/v1/`](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v1)
- Method README: [`task_b/README.md`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/task_b/README.md)
- 5 extracted keyframes: [`v2/frames/`](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v2/frames)
- Per-frame results (`detections.json` + `overlay.png` + `crops/`):
  - [frame_t00.5s](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v2/frame_t00.5s) · [frame_t04.0s](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v2/frame_t04.0s) · [frame_t07.0s](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v2/frame_t07.0s) · [frame_t10.0s](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v2/frame_t10.0s) · [frame_t12.5s](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v2/frame_t12.5s)
- Summary: [`v2/summary.json`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/task_b/v2/summary.json)
- Model record: [`model-qwen-qwen2.5-vl-72b-instruct.json`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/task_b/v2/model-qwen-qwen2.5-vl-72b-instruct.json)

---

## SBIR cross-method comparison

Horizontal comparison of Stage 1 ablation A-F + Task A/B v1-v2: [`sbir/compare.md`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/compare.md)

Includes a "when to use which" decision tree + cost summary (full reproduction ~$0.06 in paid API).

---

## Key takeaways (for future SBIR-style tasks)

1. **CLAUDE.md `Domain facts` are binding**: text-prompted SAM3 cannot ground domain-specific drone parts; small screws on video frames return 0 detections. Architecture must work around this, not fight it.
2. **VLM specialisation principle**: split tasks by what each model is best at. Let Qwen2.5-VL do grounding (open-source SOTA), let DINOv2 do cross-domain visual retrieval (self-supervised features cross domains better than SigLIP image-text shared space). **Do not let Qwen name fine-grained industrial parts**.
3. **Reference background matters for cross-domain retrieval**: applying parts_library SAM3 masks before encoding shifts DINOv2 cosine up by 0.05-0.10. Always strip non-object pixels from manual reference before matching against real-world photos.
4. **OpenRouter Qwen2.5-VL outputs absolute pixels** (not 0-1000 normalized as upstream docs claim) — verify experimentally before writing the decoder.
5. **Per-screw identity is not solvable from vision alone** (CLAUDE.md Fact 2). Distinguishing M3x6 / M3x16 / M3x22 requires manual context (which step, which subassembly).
