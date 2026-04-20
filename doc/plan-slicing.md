# Plan: 智能分区 (Smart Partition) + 精确 Zoom 工具

> 2026-04-20

## Context

当前视频帧分区使用固定 9 宫格，语义边界不对齐。需要：
1. **动态分区工具 (tool)** — VLM 识别物体 → 语义聚类 → 生成区域
2. **精确 Zoom 工具 (tool)** — 基于 bbox 裁剪放大
3. **分区 Agent** — 编排 tool 调用，决定分区策略和 zoom 目标

目标场景：ProMQA-Assembly 类组装视频帧（零件、工具、说明书、操作区）。

---

## 架构设计

遵循现有 `core/interfaces.py` → `core/openrouter_labeler.py` → `task/assembly_video_labeler.py` 的三层模式，新增 `tools/` 和 `agents/` 层。

```
moonshot/code/
├── core/
│   ├── interfaces.py              # 已有: LabelerInterface, APILabelerInterface
│   └── openrouter_labeler.py      # 已有: OpenRouterLabeler
├── tools/                         # 新增: 可复用的视觉工具
│   ├── __init__.py
│   ├── smart_partition.py         # SmartPartitionTool(OpenRouterLabeler)
│   └── bbox_zoom.py              # BboxZoomTool (纯 cv2, 无需继承 Labeler)
├── agents/                        # 新增: 编排 tool 的 agent
│   ├── __init__.py
│   └── slicing_agent.py          # SlicingAgent — 分区+zoom 编排
├── config/
│   ├── tools/                     # 新增
│   │   └── smart_partition.yaml
│   └── agents/
│       └── slicing_agent.yaml
├── task/                          # 已有
├── processors/                    # 已有
└── doc/
    └── plan-slicing.md            # 本文档
```

---

## Tool 层设计

### Tool 1: SmartPartitionTool

**继承**: `OpenRouterLabeler` (复用 VLM API 调用、retry、JSON 解析)

**职责**: 输入图像 → 调 VLM → 输出语义分区列表

```python
# tools/smart_partition.py

@dataclass
class Zone:
    name: str                       # "parts_area", "tools_area", "instruction_board"
    bbox: tuple[float,float,float,float]  # (x1,y1,x2,y2) normalized 0-1
    objects: list[str]              # ["wrench", "carbon fiber plate"]
    description: str

class SmartPartitionTool(OpenRouterLabeler):
    """继承 OpenRouterLabeler, 复用 _make_api_call / _parse_api_response / _extract_json"""
    
    def __init__(self, name="smart_partition", model="google/gemini-2.5-flash", 
                 prompt_template=None, **kwargs):
        super().__init__(name=name, model=model, **kwargs)
        self.prompt_template = prompt_template or DEFAULT_PARTITION_PROMPT
    
    def partition(self, image_path: str, context: str = "") -> list[Zone]:
        """主入口: 图像路径 → Zone 列表"""
        # 1. 构造 LabelerInput (复用 interfaces.py)
        # 2. 调用 self.label(input_data) (继承自 OpenRouterLabeler)
        # 3. 解析 JSON → Zone 列表
    
    def visualize(self, image_path: str, zones: list[Zone], output_path: str) -> str:
        """画分区边界+标签, 保存到 output_path"""
    
    @classmethod
    def from_config(cls, config_dir, api_key=None):
        """工厂方法, 从 config/tools/smart_partition.yaml 加载"""
```

**VLM Prompt 设计**:
```
Analyze this image of an assembly workspace.
Identify all distinct functional zones where similar objects are grouped.

For each zone return:
- zone_name: short snake_case name
- bbox: [x1, y1, x2, y2] as normalized 0.0-1.0 coordinates
- objects: list of objects in this zone
- description: one-line description

{context}

Return a JSON array of zones. Example:
[{"zone_name": "parts_area", "bbox": [0.0, 0.0, 0.45, 0.35], 
  "objects": ["carbon plate", "wrench"], "description": "Drone frame parts"}]
```

### Tool 2: BboxZoomTool

**继承**: 无（纯 cv2 操作，不调 API）

**职责**: 给定 bbox → crop + margin + resize

```python
# tools/bbox_zoom.py

@dataclass
class ZoomResult:
    zoomed_image: np.ndarray
    source_bbox: tuple[float,float,float,float]  # normalized
    pixel_bbox: tuple[int,int,int,int]            # 实际像素坐标 (含 margin)

class BboxZoomTool:
    def __init__(self, default_margin: float = 0.1):
        self.default_margin = default_margin
    
    def zoom(self, image: np.ndarray, bbox: tuple, margin: float = None) -> ZoomResult:
        """核心: bbox crop + margin + resize 到原图大小"""
        # 1. normalized → pixel coords
        # 2. expand by margin
        # 3. clamp to image bounds
        # 4. crop → cv2.resize(crop, (orig_w, orig_h))
    
    def zoom_from_path(self, image_path: str, bbox: tuple, 
                       margin: float = None, save_path: str = None) -> ZoomResult:
        """便捷方法: 从文件读 → zoom → 可选保存"""
    
    def multi_zoom(self, image: np.ndarray, bboxes: list[tuple], 
                   margin: float = None) -> list[ZoomResult]:
        """多目标 zoom, 返回每个 bbox 的 zoom 结果"""
```

---

## Agent 层设计

### SlicingAgent

**职责**: 编排 SmartPartitionTool + BboxZoomTool，决策逻辑

```python
# agents/slicing_agent.py

class SlicingAgent:
    def __init__(self, partition_tool: SmartPartitionTool, 
                 zoom_tool: BboxZoomTool, vlm_client=None):
        self.partition_tool = partition_tool
        self.zoom_tool = zoom_tool
        self.vlm = vlm_client  # 用于 query→zone 匹配
    
    def analyze_frame(self, image_path: str, context: str = "") -> dict:
        """完整分析: 分区 + 返回结构化结果"""
        zones = self.partition_tool.partition(image_path, context)
        return {"zones": zones, "image_path": image_path}
    
    def zoom_by_query(self, image_path: str, query: str, 
                      zones: list[Zone] = None) -> ZoomResult:
        """query-driven zoom: 
        1. 如果没有 zones, 先调 partition
        2. 用 VLM/embedding 匹配 query → best zone
        3. 调 zoom_tool.zoom(image, best_zone.bbox)
        """
    
    def zoom_by_zone_name(self, image_path: str, zone_name: str,
                          zones: list[Zone] = None) -> ZoomResult:
        """直接按 zone name zoom"""
```

---

## 配置文件

```yaml
# config/tools/smart_partition.yaml
tool_info:
  name: smart_partition
  class_name: SmartPartitionTool
  base_class: OpenRouterLabeler

model_config_ref: model/openrouter.yaml

generation_config:
  temperature: 0.2
  max_tokens: 800

prompt:
  template: |
    Analyze this image of an assembly workspace.
    Identify all distinct functional zones where similar objects are grouped.
    For each zone return:
    - zone_name: short snake_case name
    - bbox: [x1, y1, x2, y2] as normalized 0.0-1.0 coordinates  
    - objects: list of objects in this zone
    - description: one-line description
    {context}
    Return ONLY a JSON array.
```

---

## 实现步骤

1. `moonshot/code/tools/__init__.py` + `tools/bbox_zoom.py` — BboxZoomTool (纯 cv2, 无依赖)
2. `moonshot/code/tools/smart_partition.py` — SmartPartitionTool(OpenRouterLabeler)
3. `moonshot/code/config/tools/smart_partition.yaml`
4. `moonshot/code/agents/__init__.py` + `agents/slicing_agent.py` — SlicingAgent
5. 测试脚本: 用组装图片验证分区+zoom

## 验证

1. SmartPartitionTool: 输入组装图 → 应输出 ~4 区 (零件/说明书+螺丝/操作区/工具)
2. BboxZoomTool: 给定 bbox → 输出放大图
3. SlicingAgent: query="screwdrivers" → 自动定位工具区 → zoom
4. visualize: 画出分区边界检查对齐

## 依赖

- `opencv-python` — crop/resize/visualize
- `openrouter_labeler.py` (已有) — VLM API
- 无需本地模型
