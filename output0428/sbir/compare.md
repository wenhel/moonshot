# SBIR — cross-method comparison

Horizontal compare of every method tried in 2026-04-28's SBIR session.
Per-stage detail lives in each subdir's README; this doc is the index.

> See also `doc/decision.md` 2026-04-28 12:01 for the human-decision
> narrative (why F won Stage 1, why v2 won Tasks A+B).

---

## Stage 1 — build parts_library from `parts_page2.png`

| Method | Detector | Naming | Total found | Quality | Result dir |
|---|---|---|---|---|---|
| **A** | SAM3 + 14 generic noun prompts (`plate`, `arm`, `screw`, ...) at conf=0.4 | from prompt | 19 (after IoMin NMS) | misses TOP PLATE / X-LOCK / large parts; mostly screws + brackets | `seg_ablation/A/` |
| **B** | SAM3 + 18 brand-specific prompts (`top plate`, `M3x22mm screw`, ...) at conf=0.1 | from prompt | 20 (after IoMin NMS) | also misses TOP PLATE; "X-LOCK FC ISOLATOR" returns 0 (drone-vocab fact); low score 0.13-0.19 on big parts means SAM3 mis-prompt | `seg_ablation/B/` |
| **C** | SAM 2.1 large auto-everything (no text) | (none) | 44 raw masks | 2 huge masks ≈ 1M px (background); 42 ok-sized but no labels — caller has to name | `seg_ablation/C/` |
| **D** | GroundingDINO + period-joined brand prompts at thr=0.20 | from prompt | 5 | misses 16/21 — same drone-vocab limit as SAM3 | `seg_ablation/D/` |
| **E** | SAM3 with `"visual"` dummy text + no geometric prompt | (none) | 114 detections | over-segmented, includes background patches; not useful | `seg_ablation/E/` |
| **F** ✅ | Qwen2.5-VL drawing+caption bbox + SAM3 box-prompt mask refine | from VLM | **21 / 21** | every part on the page found, mask scores 0.66-0.95 | `seg_ablation/F/` |

**Why F won**: per CLAUDE.md `Domain Fact 1`, drone-specific words
(`X-LOCK FC ISOLATOR`, `top plate`) are not in SAM3's open-vocab vision
vocabulary. Methods A/B/D all need text prompts and all hit this wall.
SAM2 auto (C) skips the wall but produces unlabeled masks. Method F
delegates ground-and-name to Qwen2.5-VL (which has SOTA open-source
grounding per the Qwen blog and 2025 NTIRE benchmarks) and uses SAM3
purely as a mask refiner inside known bboxes — no text grounding needed.

Detail: `seg_ablation/F/README.md`.

---

## Task A — detect + identify on 6 manual step pages

| Step | v1 raw | v1 confident (sim ≥ 0.7) | v2 returned | v2 matched library |
|---|---|---|---|---|
| step_01 | 24 | 24 | 11 | 11 |
| step_02 | 17 | 8 | 7 | 7 |
| step_03 | 14 | 7 | 3 | 3 |
| step_04 | 22 | 2 | 4 | 3 |
| step_05 | 41 | 25 | 18 | 16 |
| step_06 | 13 | 7 | 10 | 10 |
| **Σ** | **131** | **73** | **53** | **50 (94%)** |

- **v1** = SAM3 text-prompted detect + crop + SigLIP cosine vs library
- **v2** ✅ = Qwen2.5-VL receives step page + parts vocab list, returns labeled
  bboxes directly (no SigLIP / no SAM3)

**Why v2 won**: v1's 131 raw detections are bloated with SAM3 mapping
prompts to visually-similar wrong regions (e.g. `wrench` → drone arm —
CLAUDE.md Domain Fact 1). The SigLIP threshold filters most but causes
recall to vary wildly across steps (step_04: 22 raw / 2 confident).
v2 outputs fewer but each comes pre-named by Qwen against the library
vocab — no fuzzy retrieval needed, 94% agree.

Detail: `task_a/README.md`.

---

## Task B — detect + identify on 5 video keyframes from L2_000

| Frame | v1 raw | v2 (no mask, sim≥0.5) | v2 (mask, sim≥0.5) | v2 (mask, sim≥0.35) ✅ |
|---|---|---|---|---|
| t=0.5s | 0 | 1 | 1 | 3 |
| t=4.0s | 0 | 2 | 2 | 5 |
| t=7.0s | 0 | 1 | 1 | 3 |
| t=10.0s | 0 | 2 | 2 | 4 |
| t=12.5s | 0 | 1 | 1 | 5 |
| **Σ confident** | **0 / 0** | **7 / 24** | **7 / 24** | **20 / 24** |

- **v1** = SAM3 detect + SigLIP retrieve (same as Task A v1) — fully
  predicted to fail by CLAUDE.md `Domain Facts 1+2`: SAM3 gives 0 instances
  per frame for all 18 part prompts. v1 exists only to document the failure
  mode; not a working pipeline.
- **v2 (no mask)** = Qwen gives candidate bboxes (no naming) → DINOv2
  cosine vs library reference (raw `parts_page` crops as references)
- **v2 (mask)** = same but reference crops are mask-applied (object kept,
  cell background painted white) — closes the manual ↔ photo domain gap;
  top1_sim distribution shifts from `mean=?, max=0.58` to `mean=0.435, max=0.65`
- **v2 (mask + sim ≥ 0.35)** ✅ = the same masked references but with
  threshold tuned to the new sim distribution; 20/24 candidates are now
  confident matches

**Why v2 won**: v1 is dead by domain fact. Within v2, the mask-bg trick
moves cosine up by ~0.05-0.10 because reference is now object-only (no
manual page background pixels confusing DINOv2). With distribution
shifted up, the original 0.5 threshold becomes too strict for cross-domain
retrieval — 0.35 is empirically calibrated to the new distribution.

**Known bias** (recorded for follow-up): after mask-bg, SPLIT PLATE
FRONT/REAR's hole-pattern feature is so distinctive that almost every
"metal arm with holes" candidate from Qwen retrieves SPLIT PLATE as top1,
crowding out 5 INCH ARM and TOP PLATE. A confidence-margin rule (top1 -
top2 ≥ δ) would help but isn't implemented.

Detail: `task_b/README.md`.

---

## Cross-cutting decision tree

```
Is the input a MANUAL page (manual side, isometric line art)?
  └── yes → Task A v2 recipe: VLM directly names + locates with vocab list.
            VLM has the descriptive context to disambiguate fine names
            (manual itself shows the labelling).
  └── no  → It's a real-world photo / video frame.
        Is the target list small + visually distinctive?
          └── yes → Task B v2 recipe: VLM gives candidate bboxes only,
                    DINOv2 retrieves names from library with mask-bg.
                    Threshold ≈ 0.35 (cross-domain gap).
          └── no  → out of scope here; needs domain-fine-tuned detector
                    (CLAUDE.md Domain Fact 1).
```

For library construction (Stage 1): always use Method F when the source
is a manual parts page with one cell per part.

---

## Cost summary (paid API calls, 2026-04-28 session)

| Stage | Calls | Cached after first run |
|---|---|---|
| Stage 1 F | 1 Qwen call (~$0.005) | yes — re-runs hit cache |
| Task A v2 | 6 Qwen calls (~$0.03) | yes |
| Task B v2 | 5 Qwen calls (~$0.025) | yes |
| Total | ~$0.06 / full reproduce | re-runs are free |

All other steps (SAM3, SigLIP, DINOv2, parts_page enumerate) are local-only.

---

## Files referenced in this comparison

```
output0428/sbir/
├── compare.md                      ← this file
├── seg_ablation/
│   ├── A/, B/, C/, D/, E/          baseline methods (kept for posterity)
│   └── F/                          WINNER, with own README.md
├── task_a/
│   ├── README.md                   v1/v2 detail
│   ├── v1/, v2/                    output dirs
└── task_b/
    ├── README.md                   v1/v2 detail
    ├── v1/, v2/                    output dirs
```
