# Seg30 Movement Description 对比实验

> Segment 30: 900.0s - 929.8s (frame #22500 - #23246)
> 实际动作（人工标注）: 拿蓝色螺丝刀 → 拧螺丝（松） → 放回螺丝刀 → 翻转/替换零件 → 再拿螺丝刀准备下一步

---

## 实验条件

| 条件 | 输入 | 模型 | API |
|---|---|---|---|
| A: 6帧 (原始) | 6 张 keyframes (间隔 125 帧) | gemini-2.5-flash | OpenRouter |
| B: 30帧 (密集) | 30 张 keyframes (间隔 25 帧, 1fps) | gemini-2.5-flash | OpenRouter |
| C: 原始视频 | 30秒 mp4 视频文件 | gemini-2.5-flash | Google GenAI SDK 直接视频输入 |

---

## 条件 A: 6 帧 (原始 pipeline)

**输入**: seg030_frame022500, 022625, 022750, 022875, 023000, 023125

**Movement**:
```
[PART: frame arm @ parts -> workspace] and attaches it to the main frame. (x4 重复)
```

**Description**: The person is assembling the drone frame by attaching the top plate to the bottom plate. They carefully align the two frame components and secure them together using screws. This step forms the basic structure of the drone's body.

**Movement (完整)**:
```
[PART: top plate @ parts -> workspace]
[PART: bottom plate @ workspace]
[PART: top plate @ workspace]
[PART: M3x6mm pan head screws @ screws_board -> workspace]
```

**Zone States**:
- workspace: The drone frame, consisting of the bottom plate and top plate, is assembled and held by the person.
- tools: All four hex drivers are present.
- parts: The long carbon fiber plate and two small purple parts remain.
- screws_board: The M3x6mm pan head screws have been removed from the board.

**问题**:
- 完全 hallucinate — 视频里没有 "picks up frame arm" 或 "attaching top plate" 这些动作
- Movement 重复且缺乏具体性
- 没有检测到蓝色螺丝刀的使用
- 没有检测到拧螺丝动作
- Zone States 声称 "all four hex drivers are present" 但实际蓝色螺丝刀被使用了

**评分**: 0/5 (完全不对)

---

## 条件 B: 30 帧 (密集采样)

**输入**: frame022500 到 frame023225, 每 25 帧一张 (30 张)

**Description**: The person assembles the drone frame by attaching the bottom plate to the arms using screws. They then remove the assembled frame from the workspace.

**Movement** (完整):
```
[MOVE] #22525-#22550 | blue screwdriver | tools -> workspace | The person picks up the blue screwdriver from the tools zone.
[MOVE] #22550-#22575 | bottom plate | parts -> workspace | The person picks up the bottom plate from the parts zone and places it on the workspace.
[MOVE] #22575-#22600 | right hand | workspace -> workspace | The person uses their right hand to hold the bottom plate in place.
[MOVE] #22600-#22625 | blue screwdriver | workspace -> tools | The person places the blue screwdriver back into the tools zone.
[MOVE] #22625-#22650 | left hand | workspace -> workspace | The person uses their left hand to hold the bottom plate.
[MOVE] #22650-#22675 | right hand | workspace -> workspace | The person uses their right hand to adjust the bottom plate.
[MOVE] #22675-#22700 | left hand | workspace -> workspace | The person uses their left hand to hold the bottom plate.
[MOVE] #22700-#22725 | right hand | workspace -> workspace | The person uses their right hand to adjust the bottom plate.
[MOVE] #22725-#22750 | left hand | workspace -> workspace | The person uses their left hand to hold the bottom plate.
[MOVE] #22750-#22775 | right hand | workspace -> workspace | The person uses their right hand to adjust the bottom plate.
[MOVE] #22775-#22800 | left hand | workspace -> workspace | The person uses their left hand to hold the bottom plate.
[MOVE] #22800-#22825 | right hand | workspace -> workspace | The person uses their right hand to adjust the bottom plate.
[MOVE] #22825-#22850 | left hand | workspace -> workspace | The person uses their left hand to hold the bottom plate.
[MOVE] #22850-#22875 | right hand | workspace -> workspace | The person uses their right hand to adjust the bottom plate.
[MOVE] #22875-#22900 | left hand | workspace -> workspace | The person uses their left hand to hold the bottom plate.
[MOVE] #22900-#22925 | right hand | workspace -> workspace | The person uses their right hand to adjust the bottom plate.
[MOVE] #22925-#22950 | left hand | workspace -> workspace | The person uses their left hand to hold the bottom plate.
[MOVE] #22950-#22975 | right hand | workspace -> workspace | The person uses their right hand to adjust the bottom plate.
[MOVE] #22975-#23000 | left hand | workspace -> workspace | The person uses their left hand to hold the bottom plate.
[MOVE] #23000-#23025 | right hand | workspace -> workspace | The person uses their right hand to adjust the bottom plate.
[MOVE] #23025-#23050 | left hand | workspace -> workspace | The person uses their left hand to hold the bottom plate.
[MOVE] #23050-#23075 | right hand | workspace -> workspace | The person uses their right hand to adjust the bottom plate.
[MOVE] #23075-#23100 | left hand | workspace -> workspace | The person uses their left hand to hold the bottom plate.
[MOVE] #23100-#23125 | right hand | workspace -> workspace | The person uses their right hand to adjust the bottom plate.
[MOVE] #23125-#23150 | left hand | workspace -> workspace | The person uses their left hand to hold the bottom plate.
[MOVE] #23150-#23175 | right hand | workspace -> workspace | The person uses their right hand to adjust the bottom plate.
[MOVE] #23175-#23200 | left hand | workspace -> workspace | The person uses their left hand to hold the bottom plate.
[MOVE] #23200-#23225 | right hand | workspace -> workspace | The person uses their right hand to adjust the bottom plate.
```

**Zone States**:
- tools: blue screwdriver
- parts: empty
- screws_board: M3 x 16mm socket head, M3 x 22mm pan head, M3 x 6mm pan head, M3 x 16mm pan head
- workspace: assembled drone frame

**改善**:
- ✅ 检测到蓝色螺丝刀 pick up 和放回
- ✅ 有 frame number 标注

**仍有问题**:
- ❌ 没有检测到 "拧螺丝" 动作 (只说 "adjust")
- ❌ 没有检测到零件翻转/替换
- ❌ workspace->workspace 的 hand movement 重复 20+ 次，信噪比极低
- ❌ 把每帧都编了一个 "adjust" 动作

**评分**: 2/5 (部分对，但噪声太多)

---

## 条件 C: 原始视频 (Gemini 直接视频输入)

**输入**: seg030_clip.mp4 (30 秒, 746 帧)

**Movement**:
```
[MOVE] ~1s-2s  | Blue screwdriver | tools -> right_hand
[ACTION] ~3s-7s | Blue screwdriver & Silver drone frame | workspace | loosen a screw, turning counter-clockwise
[MOVE] ~7s-8s  | Blue screwdriver | right_hand -> tools
[MOVE] ~8s-9s  | Silver drone frame | workspace -> off_camera
[MOVE] ~9s-10s | Black drone frame | off_camera -> workspace
[IDLE] ~10s-21s | Black drone frame | workspace
[MOVE] ~21s-22s | Black drone frame | workspace -> off_camera
[MOVE] ~24s-25s | Blue screwdriver | tools -> right_hand
[MOVE] ~25s-27s | Black frame arm | parts -> workspace
[ACTION] ~27s-29s | Blue screwdriver & Black frame arm | workspace | ready to work
```

**Zone States**:
```
- workspace: Left hand holds black frame arm; right hand holds blue screwdriver
- tools: 3 screwdrivers remain (gold, black, silver). Blue is held.
- parts: One arm missing from pile. Pink parts and screws still present.
- screws_board: Unchanged.
```

**改善**:
- ✅ 检测到蓝色螺丝刀 pick up 和放回 (2 次)
- ✅ 检测到 "loosen a screw, turning counter-clockwise" — 精确到旋转方向
- ✅ 检测到零件替换 (silver frame out, black frame in)
- ✅ 区分了 MOVE / ACTION / IDLE 三种状态
- ✅ 时间戳准确
- ✅ Zone state 描述准确（蓝色螺丝刀不在 tools 区）
- ✅ 无重复/hallucination

**评分**: 4.5/5 (高度准确, 仅缺少少量细节)

---

## Token Cost & 延迟

| 条件 | 延迟 | 输入 tokens (est) | 输出 tokens (est) | 成本 (Gemini Flash) |
|---|---|---|---|---|
| A: 6 帧 | **2.2s** | ~1,565 | ~110 | $0.00030 |
| B: 30 帧 | **3.5s** | ~7,757 | ~156 | $0.00126 |
| C: 视频 | **17.6s** (upload 1.4s + gen 12.9s) | ~7,865 | ~508 | $0.00148 |

- Token 估算: 图片 ~258 tok/张, 视频 ~263 tok/秒 (Gemini 标准)
- 价格: Gemini 2.5 Flash $0.15/M input, $0.60/M output
- B 和 C 的输入 token 接近 (~7.8k)，但 C 的输出丰富 3x (508 vs 156 tok)
- C 延迟最高 (17.6s) 主要因为视频上传和处理，但**单位 token 信息密度远高**
- 31 个 segment 全跑: A ~$0.009, B ~$0.039, C ~$0.046 — 差距不大

---

## 结论

| 维度 | A: 6帧 | B: 30帧 | C: 视频 |
|---|---|---|---|
| **螺丝刀检测** | ❌ | ✅ (pick up/放回) | ✅ (pick up/使用/放回, 2轮) |
| **拧螺丝动作** | ❌ | ❌ (只说adjust) | ✅ (loosen screw, counter-clockwise) |
| **零件替换** | ❌ | ❌ | ✅ (silver out, black in) |
| **时间精度** | 无 | frame level | 秒级 |
| **Hallucination** | 严重 (4x重复假动作) | 中 (20x adjust) | 无 |
| **信噪比** | 极低 | 低 | 高 |
| **总评** | 0/5 | 2/5 | 4.5/5 |

**关键发现**: Gemini 的**原生视频理解**远优于图片序列输入。视频输入能理解连续动作（拧螺丝的旋转方向）、物体的进出场（off_camera 概念）、以及 idle 状态，这些在静态图片中很难判断。

**建议**: 对于 movement 描述任务，应优先使用 Gemini 视频输入而非图片序列。图片序列更适合 zone state 描述（zoom crop 能看到细节）。
