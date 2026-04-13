# Assembly Video Labeler — Instruction Guide

## Purpose

This document defines the labeling instruction for the first keyframe of an assembly video. The first frame typically shows all parts, screws, and tools laid out before assembly begins. The labeler should produce a structured **inventory** with spatial location info.

## Input

- **[Image #1]**: The first keyframe of the video (overview shot of all components on the table)

## Expected Output

The VLM should output a structured inventory in three sections:

### 1. Parts List

Identify all physical components (not screws, not tools) visible in the image. For each part:
- **name**: descriptive name (e.g. "carbon fiber frame arm", "flight controller PCB", "purple standoff")
- **quantity**: how many are visible
- **location**: spatial position in the image using a grid reference

Location grid (divide image into 3x3):
```
 top-left    | top-center    | top-right
 mid-left    | mid-center    | mid-right
 bottom-left | bottom-center | bottom-right
```

Example:
```
[PART] carbon fiber frame arm x6 @ top-left to top-center
[PART] purple aluminum standoff x3 @ mid-left
[PART] flight controller PCB x1 @ mid-left (below standoffs)
```

### 2. Screws / Fasteners List

Identify all screws, nuts, and fasteners. Use the whiteboard labels if visible. For each:
- **type**: screw specification (e.g. "M3 x 16mm socket head")
- **quantity**: count visible
- **location**: grid position OR reference to whiteboard section

Example:
```
[SCREW] M3 x 16mm socket head x2 @ whiteboard top-left section
[SCREW] M3 x 22mm pan head x4 @ whiteboard top-right section
[SCREW] M3 x 6mm pan head x1 @ whiteboard bottom-left section
[SCREW] M3 x 16mm pan head x4 @ whiteboard bottom-right section
[SCREW] small purple screws x8 @ mid-left (scattered between parts and standoffs)
```

### 3. Tools List

Identify all tools and consumable supplies visible. For each:
- **name**: tool name with size if visible (e.g. "hex screwdriver 2.5mm")
- **quantity**: count
- **location**: grid position

Example:
```
[TOOL] hex screwdriver (gold, 2.5mm) x1 @ bottom-center (top)
[TOOL] hex screwdriver (black, 2.0mm) x1 @ bottom-center (middle)
[TOOL] hex screwdriver (blue, 1.5mm) x1 @ bottom-center (bottom)
[TOOL] hex screwdriver (silver, 1.0mm) x1 @ bottom-center (bottom)
```

## Reference Image Analysis

For the reference image (seg000_frame000000.jpg from correct_assemble_v1.mp4):

```
Image layout (1920x1080):
┌─────────────────────────────────┬──────────────────────────────────┐
│ top-left                        │ top-right                        │
│ - Carbon fiber frame pieces x8  │ - Whiteboard with screw chart    │
│   (arms, plates, braces)        │   4 quadrants showing:           │
│                                 │   M3x16mm socket head            │
│                                 │   M3x22mm pan head               │
│ mid-left                        │   M3x6mm pan head                │
│ - Purple standoffs x3           │   M3x16mm pan head               │
│ - Small purple screws ~8        │                                  │
│ - Small black screws ~8         │                                  │
├─────────────────────────────────┼──────────────────────────────────┤
│ bottom-left                     │ bottom-center / bottom-right     │
│ (empty)                         │ - 4 hex screwdrivers             │
│                                 │   (gold 2.5mm, black 2.0mm,     │
│                                 │    blue 1.5mm, silver)           │
└─────────────────────────────────┴──────────────────────────────────┘
```

## Output Format

```json
{
  "parts": [
    {"name": "carbon fiber frame arm", "qty": 5, "location": "top-left"},
    {"name": "carbon fiber top plate", "qty": 1, "location": "top-left"},
    {"name": "carbon fiber base plate", "qty": 1, "location": "top-left"},
    {"name": "carbon fiber brace", "qty": 1, "location": "top-left"},
    {"name": "purple aluminum standoff", "qty": 3, "location": "mid-left"}
  ],
  "screws": [
    {"type": "M3 x 16mm socket head", "qty": 2, "location": "whiteboard top-left"},
    {"type": "M3 x 22mm pan head", "qty": 4, "location": "whiteboard top-right"},
    {"type": "M3 x 6mm pan head", "qty": 1, "location": "whiteboard bottom-left"},
    {"type": "M3 x 16mm pan head", "qty": 4, "location": "whiteboard bottom-right"},
    {"type": "small purple screw", "qty": 8, "location": "mid-left (scattered)"},
    {"type": "small black screw", "qty": 8, "location": "mid-left (row below parts)"}
  ],
  "tools": [
    {"name": "hex screwdriver 2.5mm (gold)", "qty": 1, "location": "bottom-center"},
    {"name": "hex screwdriver 2.0mm (black)", "qty": 1, "location": "bottom-center"},
    {"name": "hex screwdriver 1.5mm (blue)", "qty": 1, "location": "bottom-center"},
    {"name": "hex screwdriver (silver)", "qty": 1, "location": "bottom-center"}
  ]
}
```

## Usage

This instruction is designed for the **first frame only** (inventory shot). For subsequent frames during assembly, use the `assembly_structured` labeler which tracks Description + Tools + Parts per segment.

The JSON output can be used as the **ground truth parts/tools list** for the video, and cross-referenced with per-segment labeling to track which parts have been used at each step.
