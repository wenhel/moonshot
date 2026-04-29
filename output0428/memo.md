# output0428 — 实验结果索引

2026-04-28 一天的成果。本文件是导航 memo，**作者方决策详情见原仓库
`code/doc/decision.md`**（不在本 mirror）。

---

## 📋 Master summary

来自 `code/doc/decision.md` 的 master summary 表，对应到本目录的 web 链接。

| Task ID | 任务描述 | 当前结果 | 结果目录 |
|---|---|---|---|
| **MR** | 手册图 ↔ 视频帧 跨域 part 检索 | ✅ Best = path (b) SAM 2 AMG + DINOv2，不完美但视觉确认最 usable | [path_b_sam2_amg_dinov2/](https://github.com/wenhel/moonshot/tree/master/output0428/sam3_image_to_video_retrieval/path_b_sam2_amg_dinov2) |
| **SBIR-1** | parts library 建库（21 个 drone 零件 reference） | ✅ Method F，21/21 part 全部定位 | [sbir/seg_ablation/F/](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/seg_ablation/F) |
| **SBIR-A** | 手册 step 页面 part 识别（6 张 step PNG） | ⚠ v2，50/53 = 94% 命中库 — **不理想，需视觉审查** | [sbir/task_a/v2/](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_a/v2) |
| **SBIR-B** | 视频帧 part 识别（5 个 keyframe） | ✅ v2 + mask-bg + sim≥0.35，20/24 confident | [sbir/task_b/v2/](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v2) |

**Status legend**: ✅ 当前最佳 · ⚠ 部分可用（有已知限制）

`YM` (step-matcher 优化) 任务不在本目录，结果在 `code/output0427/` 下未推送。

---

## MR — 手册图 ↔ 视频帧 跨域 part 检索

**问题**：给定 manual 上某零件的 line-art crop，在真实 drone 装配视频帧上找出同一零件。

**当前最佳路径**：(b) SAM 2 AMG + DINOv2 retrieval

**流水线**：
1. SAM 2.1 hiera-large `AutomaticMaskGenerator`（points_per_side=32）—— 每帧 ~28 个 class-agnostic mask 候选
2. DINOv2 vits14 编码 21 个 manual crop → (21, 384) L2 normalized
3. DINOv2 编码 142 个 mask bbox crop → (142, 384)
4. 余弦相似度 → 每个 part 的 top-K
5. OpenCV 拼图：每个 part 显示 [manual ‖ frame top-1 ‖ crop top-1 ‖ top-2 ‖ top-3]

**已知问题**：sim 平均 0.41；存在 "sticky proposal" 失败模式——7 个零件被 collapse 到同一个 mid-frame mask。**仅适用于近似 part-level 定位，不可作为 ground truth**。

**结果**：
- Best：[`path_b_sam2_amg_dinov2/`](https://github.com/wenhel/moonshot/tree/master/output0428/sam3_image_to_video_retrieval/path_b_sam2_amg_dinov2)
- Baselines（保留对比）：
  - [`path_c_siglip_zone/`](https://github.com/wenhel/moonshot/tree/master/output0428/sam3_image_to_video_retrieval/path_c_siglip_zone) — match bbox = zone bbox（zone routing 不是 part retrieval）
  - [`path_c_siglip_sw/`](https://github.com/wenhel/moonshot/tree/master/output0428/sam3_image_to_video_retrieval/path_c_siglip_sw) — sliding window
  - [`path_bc_amg_siglip/`](https://github.com/wenhel/moonshot/tree/master/output0428/sam3_image_to_video_retrieval/path_bc_amg_siglip) — AMG + SigLIP
- Raw frames：[`clip_000/`](https://github.com/wenhel/moonshot/tree/master/output0428/sam3_image_to_video_retrieval/clip_000)
- 方法对比：[`summary.md`](https://github.com/wenhel/moonshot/blob/master/output0428/sam3_image_to_video_retrieval/summary.md)

---

## SBIR-1 — parts library 建库（Stage 1）

**问题**：从 manual 的 parts page (`parts_page2.png`) 自动抠出每个零件的 crop + mask + bbox + 名字，建立可被下游 Task A/B 检索的 library。

**当前最佳方法**：Method F = Qwen2.5-VL drawing+caption sub-bbox + SAM3 box-prompt mask refine

**流水线**：
1. Qwen2.5-VL（`qwen/qwen2.5-vl-72b-instruct` via OpenRouter）一次性返回 21 个 cell 的 `drawing_bbox` + `caption_bbox` 像素坐标
2. crop 出 `drawing_bbox` 外扩 5% padding 的局部小图
3. SAM3 在该小图内 box-prompt 精修 mask（`detect_with_box_prompt`）
4. 输出 cell 完整 crop（drawing ∪ caption）+ 物体精确 mask

**结果（21/21 全部定位）**：
- 主目录：[`sbir/seg_ablation/F/`](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/seg_ablation/F)
- README + schema：[`F/README.md`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/seg_ablation/F/README.md)
- 21 parts metadata：[`parts_db.json`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/seg_ablation/F/parts_db.json)
- VLM 原始 bbox：[`vlm_bbox.json`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/seg_ablation/F/vlm_bbox.json)
- 模型记录：[`model-qwen-qwen2.5-vl-72b-instruct.json`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/seg_ablation/F/model-qwen-qwen2.5-vl-72b-instruct.json)
- 三张 overlay 验证图：
  - [`overlay_vlm.png`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/seg_ablation/F/overlay_vlm.png) — Qwen 给的 cell bbox
  - [`overlay_sam3.png`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/seg_ablation/F/overlay_sam3.png) — SAM3 精修 object bbox
  - [`overlay_merged.png`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/seg_ablation/F/overlay_merged.png) — 双色对比 + legend
- 21 个 part crops + masks：[`crops/`](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/seg_ablation/F/crops) / [`masks/`](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/seg_ablation/F/masks)

---

## SBIR-A — 手册 step 页面 part 识别（Task A）

**问题**：6 张 manual step PNG，每张找出可见零件的 bbox + 它对应 library 哪个 entry。

**两个版本对比**：
| 版本 | 方法 | 结果 |
|---|---|---|
| **v1** baseline | SAM3 detect (text prompt) + SigLIP cosine | 131 raw / 73 confident at sim≥0.7。**多噪声**，SAM3 会把 prompt 错配到视觉相似但语义错的物体（CLAUDE.md Domain Fact 1）|
| **v2** Best ⚠ | Qwen2.5-VL 直接看 step page + parts vocab，输出 `[{display_name, bbox_2d}]` | 53 returned / 50 = 94% 命中 library。**但 ⚠ 不理想——需视觉审查**，部分 step 上 Qwen 命名仍有偏差 |

**结果**：
- Winner：[`sbir/task_a/v2/`](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_a/v2)
- Baseline：[`sbir/task_a/v1/`](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_a/v1)
- 方法 README：[`task_a/README.md`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/task_a/README.md)
- Per-step 结果：每个 `step_NN/` 含 `detections.json` + `overlay.png` + `crops/`
  - [step_01](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_a/v2/step_01) · [step_02](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_a/v2/step_02) · [step_03](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_a/v2/step_03) · [step_04](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_a/v2/step_04) · [step_05](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_a/v2/step_05) · [step_06](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_a/v2/step_06)
- 汇总：[`v2/summary.json`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/task_a/v2/summary.json)

---

## SBIR-B — 视频帧 part 识别（Task B）

**问题**：5 个视频 keyframe，每帧找出可见零件的 bbox + 它对应 library 哪个 entry。

**两个版本对比**：
| 版本 | 方法 | 结果 |
|---|---|---|
| **v1** baseline | SAM3 detect (text prompt) + SigLIP cosine | **0/0 全部失败**。SAM3 文字 prompt 在 drone-domain + 真实视频帧上完全无法 ground（CLAUDE.md Facts 1+2 — drone parts 不在 vocab + 螺丝太小）|
| **v2** Best ✅ | Qwen2.5-VL 给候选 bbox（仅 `is_part_candidate` 过滤）→ DINOv2 retrieve（reference 用 SAM3 mask 去白底） | 24 candidate / **20 confident** at sim≥0.35。manual ↔ photo 跨域 cosine mean 0.435, max 0.65 |

**关键调参**：
- `mask-bg`: parts_library 的 reference 用 SAM3 mask 把背景设白，闭合 manual line-art ↔ real photo domain gap，sim 整体上移 0.05-0.10
- `sim_threshold=0.35`（不是默认 0.5）：跨域 cosine 分布偏低，0.5 过严

**D6 image-text rerank**（已尝试，**negative result**）：
- SigLIP 文本编码 21 个 library label vs SigLIP 图像编码 candidate crop → cosine
- **0/20 agreement**——SigLIP 没见过 drone 工业术语（`TOP PLATE`, `M3x22MM SCREWS`），text-image cosine 全 0.00-0.05 噪声水平
- 数据保留在 [`rerank_summary.json`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/task_b/v2/rerank_summary.json) 供后续 reference

**结果**：
- Winner：[`sbir/task_b/v2/`](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v2)
- Baseline (failed)：[`sbir/task_b/v1/`](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v1)
- 方法 README：[`task_b/README.md`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/task_b/README.md)
- 5 个 keyframe 抽帧：[`v2/frames/`](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v2/frames)
- Per-frame 结果（`detections.json` + `overlay.png` + `crops/`）：
  - [frame_t00.5s](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v2/frame_t00.5s) · [frame_t04.0s](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v2/frame_t04.0s) · [frame_t07.0s](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v2/frame_t07.0s) · [frame_t10.0s](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v2/frame_t10.0s) · [frame_t12.5s](https://github.com/wenhel/moonshot/tree/master/output0428/sbir/task_b/v2/frame_t12.5s)
- 汇总：[`v2/summary.json`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/task_b/v2/summary.json)
- 模型记录：[`model-qwen-qwen2.5-vl-72b-instruct.json`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/task_b/v2/model-qwen-qwen2.5-vl-72b-instruct.json)

---

## SBIR 跨方法对比

横向比较 Stage 1 ablation A-F + Task A/B v1-v2：[`sbir/compare.md`](https://github.com/wenhel/moonshot/blob/master/output0428/sbir/compare.md)

含决策树「何时用哪种方法」 + Cost summary（全部跑通约 $0.06 paid API）。

---

## 关键经验（适用于后续 SBIR-style 任务）

1. **CLAUDE.md `Domain facts` 是硬约束**：text-prompted SAM3 不能 ground domain-specific drone parts；视频帧上小螺丝直接返回 0 detection。架构必须**绕过**这点而不是对抗它。
2. **VLM 分工**：让 Qwen2.5-VL 做 grounding（开源 SOTA），DINOv2 做跨域 visual retrieval（self-supervised features 比 SigLIP 跨域更鲁棒）。**不要让 Qwen 命名 fine-grained 工业零件**。
3. **Reference background 影响跨域 retrieval**：用 parts_library 的 SAM3 mask 处理 reference 后再编码，cosine 上移 0.05-0.10。
4. **OpenRouter Qwen2.5-VL 输出绝对像素**（不是文档说的 0-1000 normalized）——必须实测验证编解码。
5. **Per-screw identity 不可能从视觉单独解决**（CLAUDE.md Fact 2）。M3x6 / M3x16 / M3x22 之分需要 manual context（哪个 step、哪个 subassembly）。
