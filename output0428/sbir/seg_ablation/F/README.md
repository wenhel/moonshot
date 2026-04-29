# SBIR `parts_library` (Stage 1 winner — Method F)

This directory **is** the parts library used downstream by Task A and Task B.
Built once from `parts_page2.png` of a drone-frame assembly manual.

---

## Method (F = Qwen2.5-VL bbox + SAM3 mask refine)

For each distinct part on the parts page:
1. Qwen2.5-VL (`qwen/qwen2.5-vl-72b-instruct` via OpenRouter) returns a
   tight `drawing_bbox` and `caption_bbox` in absolute pixel coords.
2. The page is cropped around `drawing_bbox` (5% padding) and SAM3
   (`detect_with_box_prompt`) refines an object-only mask within that
   crop.
3. The full cell (drawing ∪ caption bbox union) is saved as `crops/part_NN.png`,
   the SAM3 object mask as `masks/part_NN.png`.

Driver: `tests/extra/test_sbir_seg_ablation.py` `--method F`
Provenance: `model-qwen-qwen2.5-vl-72b-instruct.json` (this dir)
Decision history: `doc/decision.md` 2026-04-28 12:01 entry.

---

## File layout

```
F/
├── parts_db.json                       21-part library (top-level dict; see schema below)
├── vlm_bbox.json                       raw Qwen output (drawing+caption bbox per part)
├── crops/part_NN.png                   per-part cropped image (cell = drawing ∪ caption)
├── masks/part_NN.png                   per-part object mask (SAM3 refined; 255 = object, 0 = bg)
├── overlay_vlm.png                     parts page + cell bboxes (yellow) only
├── overlay_sam3.png                    parts page + SAM3 refined object bboxes (colored) only
├── overlay_merged.png                  parts page + both, with legend
└── model-qwen-qwen2.5-vl-72b-instruct.json   model id, params, timestamp
```

`crops/part_NN.png` and `masks/part_NN.png` are **spatially aligned** —
same width × height. The mask is `255` only where the SAM3 object lies;
the caption text region inside the crop is mask=0.

---

## `parts_db.json` schema

Top-level shape:
```json
{
  "_meta": {"method": "F", "vlm_model_id": "qwen/qwen2.5-vl-72b-instruct",
            "parts_page": "...parts_page2.png", "n_parts": 21},
  "parts": [...]
}
```

Each entry in `parts` has these fields (per `tests/extra/test_sbir_seg_ablation.py::method_f_vlm_bbox_sam3_refine`):

| Field | Meaning |
|---|---|
| `id` | Integer index 0..20 |
| `label` | Display name as printed on the page (`"TOP PLATE"`, `"M3x22MM SCREWS"`) |
| `sam3_prompt` | Always `"(crop+box-prompt)"` — SAM3 was geometric-prompted, no text |
| `bbox_xyxy` | `[x0, y0, x1, y1]` — full cell bbox = drawing ∪ caption (use this for crop/display) |
| `vlm_bbox_xyxy` | Same as `bbox_xyxy` (legacy alias kept for back-compat) |
| `drawing_bbox_xyxy` | Tight bbox around the drawing only (no caption) |
| `caption_bbox_xyxy` | Tight bbox around the printed caption text only |
| `sam3_bbox_xyxy` | SAM3 refined tight bbox around the object pixels |
| `score` | SAM3 confidence (0..1) |
| `spec` | Quantity marker as printed (`"X1"`, `"X4"`, `"X13"`) |
| `crop_path` | Path (project-relative) to `crops/part_NN.png` |
| `mask_path` | Path to `masks/part_NN.png` |
| `source` | `"vlm_cell+sam3_object_mask"` |

---

## The 21 parts

| id | label | spec | cell bbox `[x0,y0,x1,y1]` |
|---|---|---|---|
| 0 | TOP PLATE | X1 | [56, 154, 156, 456] |
| 1 | SPLIT PLATE FRONT | X1 | [216, 225, 326, 481] |
| 2 | SPLIT PLATE REAR | X1 | [390, 223, 500, 483] |
| 3 | 5 INCH ARM | X4 | [558, 214, 622, 480] |
| 4 | BATTERY PAD | X1 | [678, 251, 758, 480] |
| 5 | FPV CAMERA MOUNT LEFT | X1 | [810, 146, 928, 283] |
| 6 | FPV CAMERA MOUNT RIGHT | X1 | [810, 338, 930, 477] |
| 7 | SPACER PLATE | X1 | [978, 154, 1052, 280] |
| 8 | X-LOCK ARM WEDGE | X2 | [965, 361, 1078, 477] |
| 9 | BATTERY STRAP | X1 | [1093, 170, 1206, 275] |
| 10 | X-LOCK FC ISOLATOR | X1 | [1099, 338, 1194, 474] |
| 11 | M2x4MM SCREWS | X4 | [48, 644, 138, 742] |
| 12 | M3x8MM SCREWS | X16 | [172, 627, 260, 740] |
| 13 | M3x16MM SCREWS | X2 | [294, 603, 386, 740] |
| 14 | M3x8MM SCREWS | X4 | [413, 637, 502, 740] |
| 15 | M3x6MM SCREWS | X1 | [529, 632, 618, 740] |
| 16 | M3x6MM SCREWS | X13 | [650, 638, 738, 740] |
| 17 | M3x16MM SCREWS | X4 | [777, 606, 872, 740] |
| 18 | M3x22MM SCREWS | X4 | [897, 585, 990, 738] |
| 19 | 20MM STANDOFF | X6 | [1044, 579, 1120, 732] |
| 20 | GOPRO MOUNT | X1 | [1145, 630, 1213, 728] |

Note: M3x8 / M3x16 / M3x6 each appear twice as separate entries — they are
the same physical screw type drawn in two cells of the parts page (the
manual lists them grouped by usage). Downstream consumers should consider
entries with the same `label` as visually equivalent.

---

## How to read each overlay

| Overlay | What's shown |
|---|---|
| `overlay_vlm.png` | Yellow boxes = full cell bbox (drawing ∪ caption) returned by Qwen, with `#NN <label>` |
| `overlay_sam3.png` | Colored boxes = SAM3 refined object bbox, tight to the drawing pixels only |
| `overlay_merged.png` | Yellow (VLM cell) + green (SAM3 object) on the same page, with a legend in the top-left |

`overlay_vlm.png` shows whether Qwen located each cell correctly.
`overlay_sam3.png` shows whether SAM3 refined the boundary cleanly within
each cell. `overlay_merged.png` lets you see VLM coarse → SAM3 fine in one
view.

---

## Downstream consumption

`tests/extra/_sbir_embed.py::load_parts_library(library_dir)` reads this
directory and returns a dict with `parts`, `crop_paths`, `mask_paths`,
`labels`. Used by `test_sbir_task_a_v1.py`, `test_sbir_task_a_v2.py`,
`test_sbir_task_b_v2.py`.

For Task B v2 retrieval, callers should apply
`_sbir_embed.apply_mask_white_bg(crop_path, mask_path)` before encoding,
which composites the object onto a white background so DINOv2 features
focus on the part not the manual page background.

---

## Reproduce

```bash
python -m tests.extra.test_sbir_seg_ablation \
    --method F --device cuda:0 --crop-pad 0.05
```

The script `shutil.rmtree`s this directory at start, so re-runs produce
clean outputs.
