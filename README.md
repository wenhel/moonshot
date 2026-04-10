# Moonshot Video Report Pipeline

Video keyframe extraction + VLM labeling -> structured markdown report.

## Setup

```bash
conda env create -f environment.yml
conda activate moonshot
```

API key is auto-loaded from `moonshot/code/.env` (`OPENROUTER_API_KEY=...`).

All commands run from `moonshot/code/`:
```bash
cd moonshot/code
```

## Usage

### Check config
```bash
python -m task.video_report_pipeline --config-dryrun
```

### Extract only (no API key needed)
```bash
python -m task.video_report_pipeline VIDEO --steps extract --out OUTPUT_DIR
```

### Dryrun (extract + 1 VLM call to verify wiring)
```bash
python -m task.video_report_pipeline VIDEO --dryrun --out OUTPUT_DIR --max-sec 30
```

### Full run (extract + label + report)
```bash
python -m task.video_report_pipeline VIDEO --out OUTPUT_DIR
```

### Split steps: extract once, label with different labelers
```bash
# Extract
python -m task.video_report_pipeline VIDEO --steps extract --out OUTPUT_DIR

# Label with assembly_structured (default)
python -m task.video_report_pipeline --steps label --out OUTPUT_DIR

# Same keyframes, different labeler
python -m task.video_report_pipeline --steps label --out OUTPUT_DIR \
    --labeler assembly_tools --report-name report_tools.md

# Generic description
python -m task.video_report_pipeline --steps label --out OUTPUT_DIR \
    --labeler generic_describe --report-name report_generic.md
```

### Switch extractor
```bash
# Fixed interval (default)
python -m task.video_report_pipeline VIDEO --extractor fixed-keyframe --out OUTPUT_DIR

# Scene detection for fixed-camera footage
python -m task.video_report_pipeline VIDEO --extractor scene_fixedcam --out OUTPUT_DIR

# Scene detection for hard-cut videos
python -m task.video_report_pipeline VIDEO --extractor scene_defined --out OUTPUT_DIR
```

### CLI parameter overrides
```bash
# Override segment length and keyframe interval
python -m task.video_report_pipeline VIDEO --interval 10 --keyframe-interval 2 --out OUTPUT_DIR

# Override max frames per segment
python -m task.video_report_pipeline VIDEO --max-frames 5 --out OUTPUT_DIR

# Limit video duration
python -m task.video_report_pipeline VIDEO --max-sec 120 --out OUTPUT_DIR
```

## Project Structure

```
moonshot/code/
├── config/
│   ├── defaults/pipeline.yaml          # Default extractor/labeler params + extractor presets
│   ├── labeler/
│   │   ├── assembly_structured.yaml                  # Description + Tools + Parts
│   │   ├── assembly_structured-with-instruction.yaml  # + spatial grid location
│   │   ├── assembly_tools.yaml                        # Description + Tools
│   │   ├── generic_describe.yaml                      # Generic description
│   │   └── instruction.md                             # Labeling instruction guide
│   └── model/
│       └── openrouter.yaml             # OpenRouter API config (copied from project)
├── core/                               # Layer 1-2 (copied from stance/)
│   ├── interfaces.py                   # LabelerInterface, LabelerInput/Output
│   └── openrouter_labeler.py           # OpenRouterLabeler — HTTP/retry/JSON
├── processors/                         # Copied from stance/processors + src/data
│   ├── keyframe_extractor.py           # KeyFrameExtractor
│   └── scene_detector.py              # SceneDetector
├── task/                               # Business logic
│   ├── assembly_video_labeler.py       # Layer 3: AssemblyVideoLabeler
│   ├── video_report_pipeline.py        # CLI + orchestrator
│   ├── report_writer.py                # Markdown/JSON report generation
│   ├── segment_video_original.py       # Original reference code
│   └── srt2segment_original.py         # Original reference code
├── environment.yml
└── plan.md
```

## Four Labelers

| Name | Output | Use case |
|---|---|---|
| `assembly_structured` | Description + Tools + Parts | Full analysis (default) |
| `assembly_structured-with-instruction` | Description + Tools + Parts with 3x3 grid location | Spatial-aware analysis |
| `assembly_tools` | Description + Tools | Tool identification |
| `generic_describe` | Description only | No domain assumptions |

## Three Extractors

| Name | Mode | Use case |
|---|---|---|
| `fixed-keyframe` | fixed | General purpose (default: 30s segments, 5s keyframe interval) |
| `scene_fixedcam` | scene_detect | Fixed camera footage (1s compare interval, threshold=10) |
| `scene_defined` | scene_detect | Videos with hard cuts (consecutive frame compare, threshold=25) |

## Output Structure

```
OUTPUT_DIR/
├── segments.json
├── keyframes/
│   ├── seg000_frame000000.jpg
│   └── ...
└── report.md
```

## Config

Labeler configs follow the project convention (`config/labeler/*.yaml`):
```yaml
labeler_info:
  name: "assembly_structured"
  class_name: "AssemblyVideoLabeler"
model_config_ref: "model/openrouter.yaml"
task_config:
  task_type: "assembly_video_structured"
  instruction_type: "assembly_structured"
generation_config:
  temperature: 0.2
  max_tokens: 600
instructions:
  assembly_structured:
    template: |
      Your prompt with {time_range} and {transcript_hint} placeholders.
```

To add a new labeler: create `config/labeler/my_labeler.yaml`, then `--labeler my_labeler`.
