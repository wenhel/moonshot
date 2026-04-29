# SBIR Task A — Detect + identify parts on manual step pages

**Goal**: For each of the 6 drone-assembly manual step pages, locate every
visible part with a bbox and identify which `parts_library` entry it
corresponds to (top-1 retrieval).

**Input**:
- 6 step PNGs at
  `output/manual_parsed_v2/steps-from-page-countfirst-gemini25-flash-image/steps/step_0[1-6].png`
- Stage 1 `parts_library` at `output0428/sbir/seg_ablation/F/`
  (21 part entries built by Method F = Qwen2.5-VL bbox + SAM3 mask refine).

**Output structure (per version)**:
```
v{N}/
├── step_NN/
│   ├── detections.json    # {bbox, score, top1_part_id, top3, sim} per detection
│   ├── overlay.png        # step PNG + colored bboxes + labels
│   └── crops/det_MM.png   # one crop per detection
├── summary.json           # per-step counts
└── model-<vlm-id>.json    # (v2 only) which VLM produced the bboxes
```

---

## v1 — SAM3 detect + SigLIP retrieve (plan0428 baseline)

Per the original `plan0428-SBIR.md` design.

**Pipeline**:
1. Build prompt vocabulary from `parts_library` `display_name` list (18 unique).
2. For each step PNG: run `Sam3DetectorTracker.detect_in_image(text=<each prompt>)`
   → collect all bboxes (across all prompts).
3. Per detection: crop → SigLIP image embedding (`google/siglip-base-patch16-224`).
4. Cosine similarity vs library SigLIP embeddings → top-1 + top-3.
5. Threshold sim ≥ 0.7 → confident match, else "unknown".

**Script**: `tests/extra/test_sbir_task_a_v1.py`

**Results**: high recall (13–41 raw detections per step) but low precision —
SAM3 doesn't have a learned visual concept for drone-specific parts (top
plate, X-Lock, etc., per CLAUDE.md Domain Fact 1), so most "detections" are
SAM3 matching the text prompt to the wrong visual region; SigLIP cosine
threshold then filters out the noise. step_04 collapses to 2/22 confident.

| Step | raw | kept | confident (sim ≥ 0.7) |
|---|---|---|---|
| step_01 | 24 | 24 | 24 |
| step_02 | 17 | 17 | 8 |
| step_03 | 14 | 14 | 7 |
| step_04 | 22 | 22 | 2 |
| step_05 | 41 | 41 | 25 |
| step_06 | 13 | 13 | 7 |

---

## v2 — Qwen2.5-VL direct labeling (plan 3a)

Bypasses SAM3's vocabulary limitation by relying on Qwen2.5-VL's grounding
ability to locate AND name parts in one shot.

**Pipeline**:
1. Build vocabulary from `parts_library` `display_name` list.
2. For each step PNG: feed page + vocab list to Qwen via
   `config/labeler/step_page_label.yaml` → JSON
   `[{display_name, bbox_2d, note}]`.
3. Match `display_name` against library vocab (verbatim) → `part_id`. If no
   match, `display_name` is "unknown".
4. Save bbox + crop + part_id.

**Script**: `tests/extra/test_sbir_task_a_v2.py`
**VLM**: `qwen/qwen2.5-vl-72b-instruct` (OpenRouter)

**Results**: fewer detections than v1 but each one is directly named by
Qwen — no fuzzy retrieval step needed.

| Step | returned | kept | matched library |
|---|---|---|---|
| step_01 | 11 | 11 | 11 |
| step_02 | 7  | 7  | 7  |
| step_03 | 3  | 3  | 3  |
| step_04 | 4  | 4  | 3  |
| step_05 | 18 | 18 | 16 |
| step_06 | 10 | 10 | 10 |

---

## How to interpret each `detections.json`

Each entry has:
- `bbox_xyxy`: pixel `[x0, y0, x1, y1]` in the step PNG
- `top1_part_id` + `top1_label`: best library match (v1 via SigLIP; v2
  directly from VLM)
- `top1_sim` (v1 only): cosine similarity in [0, 1]
- `top3` (v1 only): runner-up candidates
- `sam3_prompt` (v1 only): which prompt produced this raw detection

For v2 entries, `label == "unknown"` means Qwen saw something at that bbox
that doesn't correspond to any library part (e.g. assembled subassembly).

---

## How to re-run

```bash
# v1
python -m tests.extra.test_sbir_task_a_v1 --device cuda:0

# v2 (requires OPENROUTER_API_KEY in code/.env)
python -m tests.extra.test_sbir_task_a_v2
```

Both scripts call `shutil.rmtree(out_root)` at start, so re-runs produce
clean outputs (no leftovers from prior runs).

---

## Known limitations

- **v1**: SAM3 text prompts unreliable for drone parts (CLAUDE.md Fact 1).
  Many low-confidence detections are SAM3 mapping the prompt to a
  visually-similar generic object (e.g. "wrench" → drone arm). The SigLIP
  cosine threshold filters most but not all of these.
- **v2**: Qwen's pixel-bbox precision is good for manual pages (drawings on
  white background) but not pixel-perfect. Bboxes may be a few px loose.
- Neither version distinguishes between visually-identical parts in the
  same library (e.g. M3x8 vs M3x16 screws). Per CLAUDE.md Fact 2, this
  fine-grained identity cannot be recovered from vision alone — it
  requires manual context (which step, which subassembly).
