# Path (b) — SAM 2 AMG + DINOv2 retrieval

Manual line-art crop → real-world video frame retrieval.

> Image-as-prompt cross-domain retrieval：parts library 用 manual 上的零件
> isometric line-art crop 当 query，去 video keyframe 上找到对应的真实物体。
> 完全绕过 SAM 3 文字 prompt（CLAUDE.md Domain Fact 1：drone-specific 词
> 不在 SAM 3 vocabulary 里）。

**Driver**: `tests/extra/test_path_b_sam2_amg_dinov2_retrieval.py`
**Decision context**: see `code/doc/decision.md` 2026-04-28 11:51 entry +
`code/doc/memo_sam3_zone_crop.md` §9.6.

---

## 流程

```
manual parts_library (21 个零件 line-art crop, 已 SAM3 mask 去背景)
                                  │
                                  │  DINOv2 vits14 encoder
                                  ▼
                          (21, 384) library embeddings
                                  │
                                  │
                                  │
video (L2_000_t0.0-13.0.mp4)      │
       │                          │
       │  抽 5 个 keyframe         │
       │  t = {0.5, 4, 7, 10, 12.5}s
       │                          │
       ▼                          │
  5 个 frame PNG                   │
       │                          │
       │  SAM 2.1 hiera-large      │
       │  AutomaticMaskGenerator   │
       │  (points_per_side=32)     │
       ▼                          │
  142 个 class-agnostic            │
  mask proposals                   │
  (每个有 bbox + IoU + stability)  │
       │                          │
       │  crop bbox + 4px padding  │
       │  DINOv2 encode            │
       ▼                          │
  (142, 384) proposal embeddings   │
                                  │
                                  ▼
                      cosine: (21, 384) × (142, 384)ᵀ → (21, 142)
                                  │
                                  ▼
                每个 part 取 top-3 最相似的 (frame, mask proposal)
                                  │
                                  ▼
                     retrieval.json + overlays + viz
```

---

## 模型与参数

| 阶段 | 工具 | 模型 / 参数 | 来源 |
|---|---|---|---|
| Mask proposal | `SAM2AutomaticMaskGenerator` | `sam2.1_hiera_large.pt` (898 MB)<br>`points_per_side=32` (1024 候选点)<br>`points_per_batch=64`<br>`pred_iou_thresh=0.7`<br>`stability_score_thresh=0.85`<br>`min_mask_region_area=64` | facebookresearch/sam2 |
| Library + proposal embedding | `Dinov2ImageEncoder` | `facebookresearch/dinov2_vits14`<br>518×518 input, L2 normalized<br>384-dim CLS token | `tests/extra/_sbir_embed.py` |
| Retrieval | numpy cosine | `embeds @ embeds.T` | inline |
| Per-part top-K | argsort | `topk=3` | inline |
| Overlay | OpenCV | green if `sim ≥ 0.45` 否则 red | inline `render_overlay` |
| Per-part panel viz | `_viz_path_bc.py` | 5 列 strip per part: manual ‖ frame top-1 (full + bbox) ‖ crop top-1 ‖ crop top-2 ‖ crop top-3 | `tests/extra/_viz_path_bc.py` |

**关键决策**：
- **不用 SAM 3 文字 prompt**：CLAUDE.md Domain Fact 1 已记录 SAM 3
  on `"top plate" / "X-LOCK FC ISOLATOR"` 等 drone 词汇返回 0 detection；
  SAM 2 AMG 是 class-agnostic，靠 grid 撒点不依赖词汇。
- **DINOv2 不是 SigLIP**：reference 是 manual line-art，query 是真实
  photo，self-supervised DINOv2 features 比 SigLIP image-text shared
  space 跨域更鲁棒（Manual-PA ICCV 2025 也是 DINO 系特征）。
- **不是 D6 文字 rerank**：之前 SBIR Task B v2 D6 用 SigLIP 文字-图像 rerank
  失败（SigLIP 没见过 drone 工业术语），所以这里直接 image-image cosine。

---

## 输入

| 资源 | 路径（相对 code/）|
|---|---|
| 视频 | `output0427/hierarchical-video-splitter/pen_0.5/seg_000/L2_000_t0.0-13.0.mp4` (13 s, 30 fps, 480×270) |
| Keyframes | t = {0.5, 4.0, 7.0, 10.0, 12.5} 秒 → 5 帧 |
| Parts library | `output0428/sbir/seg_ablation/F/` (21 entries, 见该目录 `README.md`) |
| Library crops | `output0428/sbir/seg_ablation/F/crops/part_000.png` ... `part_020.png` |
| SAM 2 weights | `agentbuild0427/sam2_weights/sam2.1_hiera_large.pt` (gitignored) |

---

## 输出文件

```
path_b_sam2_amg_dinov2/
├── README.md                      ← 本文件
├── retrieval.json                 主结果（schema 见下文）
├── frames/                        5 个 keyframe PNG (480×270)
│   └── frame_t<XX.X>s.png
├── proposals/                     SAM 2 AMG 生成的 142 个 mask bbox crop
│   └── frame_t<XX.X>s_p<NNN>.png
├── overlays/                      每帧画上所有 mask 的 top-1 part 标签
│   └── frame_t<XX.X>s_top1.png
└── viz/                           per-part 检索面板
    ├── all_parts_grid.png         21 个 part 拼成的总览图（无标题）
    ├── all_parts_grid_titled.png  同上 + 标题
    └── per_part/                  21 个 part 各自一张面板
        └── part_<NN>_<label>.png  (manual ‖ frame full ‖ top-1 ‖ top-2 ‖ top-3)
```

---

## `retrieval.json` schema

顶层 dict，3 个字段：

### `_meta`
```json
{
  "method": "path_b_sam2_amg_dinov2",
  "video": "output0427/hierarchical-video-splitter/pen_0.5/seg_000/L2_000_t0.0-13.0.mp4",
  "library_dir": "output0428/sbir/seg_ablation/F",
  "timestamps_sec": [0.5, 4.0, 7.0, 10.0, 12.5],
  "n_frames": 5,
  "n_proposals": 142,
  "n_parts": 21,
  "topk": 3,
  "amg_points_per_side": 32
}
```

### `per_part_topk`
长度 21，每个 entry 是「这个 part 在视频里 top-3 像」：
```json
{
  "part_id": 0,
  "label": "TOP PLATE",
  "library_crop": "<absolute path to library crop>",
  "topk": [
    {
      "rank": 1,
      "sim": 0.4993,
      "frame_id": "frame_t00.5s",
      "t_sec": 0.5,
      "bbox_xyxy_px": [47, 122, 81, 179],
      "proposal_path": "proposals/frame_t00.5s_p005.png",
      "predicted_iou": 0.95,
      "area": 924
    },
    { "rank": 2, ... },
    { "rank": 3, ... }
  ]
}
```

### `per_proposal_top1_part`
长度 142，每个 entry 是「这个 mask 候选最像哪个 part」：
```json
{
  "global_idx": 0,
  "frame_id": "frame_t00.5s",
  "t_sec": 0.5,
  "frame_path": "frames/frame_t00.5s.png",
  "proposal_path": "proposals/frame_t00.5s_p000.png",
  "bbox_xyxy_px": [0, 0, 460, 270],
  "predicted_iou": 0.99,
  "stability_score": 0.91,
  "area": 91685,
  "best_part_id": 3,
  "best_label": "5 INCH ARM",
  "best_sim": 0.27
}
```

---

## 如何审查结果

1. **快速看效果**：`viz/all_parts_grid_titled.png` —— 21 个 part 拼成一张图，每行展示 manual ↔ video 上 top-1 mask 的对应关系。绿框 = sim≥0.45，红框 = 低 sim。
2. **逐个 part 详查**：`viz/per_part/part_<NN>_<label>.png` —— 每张包含 manual reference + frame 全图（标了 top-1 bbox）+ top-1/2/3 crop。
3. **逐个 frame 详查**：`overlays/frame_t<XX.X>s_top1.png` —— 一帧上所有 mask（每个 mask 框出来 + 标 top-1 part 名 + sim）。
4. **数值排查**：`retrieval.json::per_part_topk[i].topk[0].sim` ——
   sim 全表均值 0.41，max ~0.50，远低于 SBIR Task B v2 用 mask-bg reference 的 0.65。

---

## 已知限制

| 现象 | 原因 | 影响 |
|---|---|---|
| sim 平均 0.41 偏低 | manual line-art ↔ real photo 跨域 + reference 没用 mask 去背景（Task B v2 用了 mask-bg 的 trick 这里没用）| 需要手工设阈值审查，不能盲信 top-1 |
| **Sticky proposal 失败模式** | SAM 2 AMG 在某些区域生成大 mask，多个 part 的 top-1 collapse 到同一个 mask（约 7 个 part 都指向 frame 中央那块） | top-1 retrieval 不能用作 ground truth |
| 142 个 proposal 多冗余 | `points_per_side=32` 撒得密，多 mask 高度重叠 | 后续可加 NMS 过滤；目前保留全部 |
| Per-screw identity 不可解 | CLAUDE.md Fact 2：M3x6/M3x16/M3x22 视觉无法区分 | 螺丝 retrieval 只能视为「类」级别，不可作型号鉴别 |

**Status**: MVP 可接受，**视觉确认最 usable** 的非文字 prompt 路线，但 sim 偏低 + sticky proposal → 仅用于「大致 part 定位」，**不可用作 ground truth**。

---

## 复现

```bash
cd <code dir>
python -m tests.extra.test_path_b_sam2_amg_dinov2_retrieval \
  --video output0427/hierarchical-video-splitter/pen_0.5/seg_000/L2_000_t0.0-13.0.mp4 \
  --library-dir output0428/sbir/seg_ablation/F \
  --out-root output0428/sam3_image_to_video_retrieval/path_b_sam2_amg_dinov2 \
  --device cuda:0

# 重新生成 viz（已有 retrieval.json 时）
python -m tests.extra._viz_path_bc \
  --retrieval-json output0428/sam3_image_to_video_retrieval/path_b_sam2_amg_dinov2/retrieval.json \
  --out-dir       output0428/sam3_image_to_video_retrieval/path_b_sam2_amg_dinov2/viz
```

依赖：`facebookresearch/sam2` 和 `dinov2`（torch.hub），SAM 2 weights 需手动下到
`agentbuild0427/sam2_weights/sam2.1_hiera_large.pt`。

---

## 相关方案对比

跟 SBIR Task B v2 是同一目标的两种解法（详见 `output0428/sbir/compare.md` +
`code/doc/decision.md` 2026-04-28 11:51 entry）：

| 路径 | bbox 来源 | retrieval | 性质 |
|---|---|---|---|
| **path (b)（本路径）** | SAM 2 AMG class-agnostic | DINOv2 image-image | 完全自动，bbox-precision proposals |
| Task B v2 (`output0428/sbir/task_b/v2/`) | Qwen2.5-VL VLM grounding | DINOv2 + mask-bg reference | VLM 提供语义过滤 (`is_part_candidate`)，sim 上移到 0.65 |

两种路径的 strength 不一样：path (b) bbox 更精，Task B v2 sim 更高且语义过滤更干净。
