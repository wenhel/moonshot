# Moonshot Video-Report Pipeline — Design & Coding Plan

**Created:** 2026-04-09
**Author:** refactor of `moonshot/demo/segment_video.py` into a reusable class-based pipeline

---

## 1. Goal

Extract the **keyframe extractor** and **VLM labeler** parts from `moonshot/demo/segment_video.py`, standardize them into a single-file class-based pipeline, and generate reports with **the same structure** as `moonshot/demo/output/report-5s-v2.md` for arbitrary input videos.

Scope:
- Reuse existing OpenCV keyframe logic and OpenRouter (Gemini VLM) labeler HTTP code verbatim.
- Replace hardcoded labeler prompt with **YAML-controlled** prompts, so multiple labeler variants can be instantiated without code changes.
- Keep SRT-based semantic segmenter (`srt2segment.py`) untouched for now; future work: TTS-based transcript for narration-less clips.
- Single file, no package — easy to iterate.

Out of scope (future work):
- TTS / Whisper-based transcript generation for narration-less videos
- Packaging into `moonshot/pipeline/`
- Integration with `assembly_instructions-*.yml` specs

---

## 2. File Layout

```
moonshot/
├── code/
│   └── plan.md                     # this file
├── video_report_pipeline.py        # NEW: all classes + CLI in one file
├── labelers.yaml                   # NEW: labeler prompt configs
└── demo/                           # unchanged (old scripts kept for reference)
    ├── segment_video.py
    ├── srt2segment.py
    └── output/report-5s-v2.md      # target report format
```

---

## 3. Reuse vs New Code

<details><summary>Full component-level mapping (click to expand)</summary>

| Component | Source | Change |
|---|---|---|
| `parse_srt()` | copy from `segment_video.py:48-78` | verbatim |
| `get_transcript_for_range()` | copy from `segment_video.py:81-92` | verbatim |
| `class SrtAligner` shell | NEW | wraps above two functions; TODO comment for TTS provider |
| `get_video_info()` | copy from `segment_video.py:99-114` | returns `VideoInfo` dataclass instead of dict |
| `detect_scene_boundaries()` | copy from `segment_video.py:117-144` | verbatim |
| `build_segments_from_boundaries()` | copy from `segment_video.py:147-159` | verbatim |
| `build_segments_fixed()` | copy from `segment_video.py:162-180` | verbatim |
| `load_semantic_segments()` | copy from `segment_video.py:243-268` | verbatim |
| `extract_keyframes_for_segments()` | copy from `segment_video.py:187-236` | verbatim |
| `class KeyframeExtractor` shell | NEW | groups the five functions above as methods |
| `encode_image_base64()` | copy from `segment_video.py:275-277` | verbatim |
| `describe_segment_vlm()` HTTP body | copy from `segment_video.py:280-348` | **modified:** prompt text loaded from YAML, `time_range` / `transcript_hint` as `.format()` placeholders; `model` / `max_tokens` / `temperature` from YAML |
| `describe_all_segments()` batch loop | copy from `segment_video.py:351-359` | verbatim |
| `class VLMLabeler` + `from_yaml()` | NEW | constructs instance by name from `labelers.yaml` |
| `fmt_time()` | copy from `segment_video.py:366-368` | verbatim |
| `save_results()` JSON + Markdown | copy from `segment_video.py:371-421` | verbatim (md template 1:1 preserved) |
| `class ReportWriter` shell | NEW | thin wrapper |
| `@dataclass Segment` | copy from `segment_video.py:31-41` | verbatim |
| `@dataclass VideoInfo` | NEW | dict → dataclass |
| `class VideoReportPipeline` | NEW | orchestrator composing the classes above |
| `main()` CLI | NEW (references `segment_video.py:428-545` flow) | argparse now takes labeler name + yaml path |
| `labelers.yaml` | NEW | original prompt from `segment_video.py:305-316` lifted as entry `assembly_tools`; adds `generic_describe` and `assembly_step_only` variants |
| `srt2segment.py` | unchanged | deferred |

**Principle:** 100% verbatim copy of core algorithms (OpenCV keyframe logic, OpenRouter HTTP payload, markdown template). "NEW" is only class shells, YAML loading, pipeline orchestration, and new prompt variants. Behaviour under `assembly_tools` labeler should be **identical** to the original `segment_video.py`.

</details>

---

## 4. Class Design

<details><summary>Class signatures (click to expand)</summary>

```python
# ---------- data ----------
@dataclass
class Segment:
    index: int
    start_sec: float
    end_sec: float
    start_frame: int
    end_frame: int
    title: str = ""
    keyframe_paths: List[str] = field(default_factory=list)
    transcript: str = ""
    vlm_description: str = ""

@dataclass
class VideoInfo:
    fps: float
    frame_count: int
    duration: float
    width: int
    height: int

    @classmethod
    def probe(cls, video_path: str) -> "VideoInfo": ...


# ---------- transcript ----------
class SrtAligner:
    """Parse SRT and align subtitle ranges to segments.

    TODO(future): swap this out for a TTS/Whisper-based transcript provider
    so narration-less clips (e.g. videos/correct_assemble_v*.mp4) can still
    get a transcript. Keep the same .transcript_for_range(start, end) surface.
    """
    def __init__(self, srt_path: Optional[str] = None): ...
    def transcript_for_range(self, start_sec: float, end_sec: float) -> str: ...


# ---------- keyframes / segmentation ----------
class KeyframeExtractor:
    def __init__(self, video_info: VideoInfo): ...

    # three segmentation strategies
    def segments_fixed(self, interval_sec: float, max_sec: float = 0.0) -> List[Segment]: ...
    def segments_scene_detect(self, video_path: str, threshold: float = 25.0,
                               min_scene_sec: float = 2.0, max_sec: float = 0.0) -> List[Segment]: ...
    def segments_from_json(self, json_path: str, max_sec: float = 0.0) -> List[Segment]: ...

    # keyframe extraction on a finished segment list
    def extract(self, video_path: str, segments: List[Segment], out_dir: str,
                frames_per_segment: int = 2, keyframe_interval_sec: float = 0.0) -> None: ...


# ---------- VLM labeler ----------
class VLMLabeler:
    def __init__(self, name: str, model: str, prompt_template: str,
                 max_tokens: int, temperature: float, api_key: str): ...

    @classmethod
    def from_yaml(cls, yaml_path: str, name: str, api_key: str) -> "VLMLabeler": ...

    def label(self, segment: Segment) -> str: ...       # single segment
    def label_all(self, segments: List[Segment], rate_sleep_sec: float = 0.5) -> None: ...


# ---------- report ----------
class ReportWriter:
    def write(self, segments: List[Segment], out_dir: str, video_info: VideoInfo,
              report_name: str = "report.md") -> Tuple[str, str]: ...


# ---------- pipeline orchestrator ----------
class VideoReportPipeline:
    def __init__(self,
                 extractor: KeyframeExtractor,
                 labeler: Optional[VLMLabeler],
                 aligner: Optional[SrtAligner],
                 writer: ReportWriter): ...

    def run(self,
            video_path: str,
            out_dir: str,
            *,
            mode: str,                   # "fixed" | "scene_detect" | "semantic"
            segments_json: Optional[str] = None,
            frames_per_seg: int = 2,
            keyframe_interval_sec: float = 0.0,
            interval_sec: float = 5.0,
            scene_threshold: float = 25.0,
            min_scene_sec: float = 2.0,
            max_sec: float = 0.0,
            dryrun: bool = False) -> None: ...
```

`dryrun=True` means: do segmentation + keyframe extraction as usual, but only call VLM on the **first segment** (to verify wiring + API auth), then stop without writing `report.md`. It still hits the real API — exactly what the user asked for ("必须调用").

</details>

---

## 5. YAML Config Format

`moonshot/labelers.yaml`:

```yaml
# Each labeler defines one prompt variant. Select by --labeler <name>.
# Prompt placeholders: {time_range}, {transcript_hint}
labelers:
  - name: assembly_tools
    model: google/gemini-2.5-flash
    max_tokens: 500
    temperature: 0.3
    prompt: |
      These are keyframes from a hardware assembly video segment ({time_range}).{transcript_hint}
      Provide TWO sections:
      1. **Description**: Describe what is happening in 2-3 sentences. Focus on the main action,
         components being assembled, and any text visible on screen.
      2. **Tools**: List ONLY the tools and consumable supplies the person is USING ...
         Format each as [TOOL: name]. If no tools are visible or mentioned, write [TOOL: none].

  - name: generic_describe
    model: google/gemini-2.5-flash
    max_tokens: 300
    temperature: 0.3
    prompt: |
      These are keyframes from a video segment ({time_range}).{transcript_hint}
      Describe what is happening in 2-3 sentences. Focus on the main action and any visible
      text or objects.

  - name: assembly_step_only
    model: google/gemini-2.5-flash
    max_tokens: 300
    temperature: 0.3
    prompt: |
      These are keyframes from an assembly video segment ({time_range}).{transcript_hint}
      Describe the assembly step being performed in 1-2 sentences. Name the specific
      parts / components involved.
```

`transcript_hint` is set by the labeler at call time to either empty string (no SRT) or `'\nNarration during this segment: "…"'` — same as the original.

---

## 6. CLI

```
python moonshot/video_report_pipeline.py VIDEO [options]

  --out PATH              output directory (default: ./output)
  --mode {fixed,scene_detect,semantic}   segmentation mode (default: fixed)
  --segments-json PATH    pre-computed segments (implies --mode semantic)
  --srt PATH              SRT for transcript alignment (auto-detected if omitted)
  --labelers-yaml PATH    path to labelers.yaml (default: ./labelers.yaml)
  --labeler NAME          which labeler entry to use (default: assembly_tools)
  --frames-per-seg N      uniform N frames per segment (default: 2)
  --keyframe-interval S   or extract one frame every S seconds (overrides --frames-per-seg)
  --interval S            segment length for fixed mode (default: 5)
  --threshold F           scene-detect threshold (default: 25.0)
  --min-scene S           min scene duration (default: 2.0)
  --max-sec S             only process up to S seconds (default: 0 = full video)
  --dryrun                real API call on first segment only, then stop
```

Note: no `--no-vlm` flag. The user explicitly wants VLM to be invoked.

---

## 7. Output Layout (identical to demo/output/)

```
<out_dir>/
├── segments.json
├── keyframes/
│   ├── seg000_frame000000.jpg
│   ├── seg000_frame000299.jpg
│   └── ...
└── report.md
```

`report.md` matches `demo/output/report-5s-v2.md` 1:1:

- Header: `**Duration** | **Resolution** | **FPS** | **Segments**`
- Per segment:
  - `## Segment N [mm:ss.SS - mm:ss.SS] — <title>`
  - Horizontal keyframe thumbnails in `<div style="overflow-x:auto;...">`
  - `**Visual:** <vlm description>`
  - `<details><summary>Transcript</summary>...</details>` (if present)

---

## 8. Validation Strategy

No smoke test with full VLM run. Two dryrun steps only:

1. **Config dryrun** — load `labelers.yaml`, print each labeler's `name`, `model`, and first 100 chars of prompt. Verifies YAML parsing and class construction.
2. **Wiring dryrun** — run `VideoReportPipeline.run(video="demo/videos/correct_assemble_v1.mp4", …, dryrun=True)`:
   - probe video info
   - run `fixed` segmentation (interval 5s)
   - extract keyframes for all segments
   - call `VLMLabeler.label()` **on segment 0 only** (real OpenRouter API call)
   - print the returned description
   - stop (no report.md written)

If both dryruns pass, the pipeline is wired end-to-end. Full-video runs are user-triggered afterwards.

---

## 9. Coding Steps

1. Create `moonshot/labelers.yaml` with three labeler entries
2. Create `moonshot/video_report_pipeline.py` skeleton (imports, dataclasses)
3. Copy-paste `SrtAligner`, `KeyframeExtractor`, `ReportWriter` bodies from `demo/segment_video.py` into class methods
4. Write `VLMLabeler` with YAML loader and `.format()`-based prompt templating
5. Write `VideoReportPipeline.run()` orchestrator (fixed / scene_detect / semantic branches, dryrun handling)
6. Write `main()` CLI
7. Run **config dryrun** — `python moonshot/video_report_pipeline.py --labelers-yaml moonshot/labelers.yaml --config-dryrun` *(or equivalent quick check)*
8. Run **wiring dryrun** — `python moonshot/video_report_pipeline.py moonshot/demo/videos/correct_assemble_v1.mp4 --dryrun`
9. Fix anything that breaks; commit.

---

## 10. Open Questions (resolved)

| Q | Decision |
|---|---|
| Same structure as `demo/`? | Yes — 1:1 markdown format |
| YAML controls labelers? | Yes — prompt / model / tokens / temperature per named labeler |
| Semantic segmenter? | Keep `srt2segment.py` as-is, don't touch; expose `mode=semantic` via `--segments-json` |
| Single file vs package? | Single file `moonshot/video_report_pipeline.py` |
| Smoke test? | No. Dryrun (real VLM call on segment 0) only. |
| TTS for narration-less videos? | Deferred. `SrtAligner` gets a TODO comment noting the future extension point. |

---

## 2026-04-09 05:49 — YAML now also controls keyframe extractors

**Change:** The original design left keyframe extractor mode/params as CLI flags (`--mode`, `--interval`, `--threshold`, etc). Per user feedback, extractors must also be YAML-driven so users can define named extractor presets alongside named labelers.

**File renamed:** `moonshot/labelers.yaml` → `moonshot/pipeline.yaml` (now holds both `extractors:` and `labelers:` top-level sections).

**New YAML schema:**

```yaml
extractors:
  - name: <id>
    mode: fixed | scene_detect | semantic
    # mode=fixed:         interval_sec + (frames_per_segment | keyframe_interval_sec)
    # mode=scene_detect:  threshold + min_scene_sec + (frames_per_segment | keyframe_interval_sec)
    # mode=semantic:      (frames_per_segment | keyframe_interval_sec)   [segments_json via CLI]
labelers:
  - name: <id>
    model: ...
    max_tokens: ...
    temperature: ...
    prompt: ...
```

Six preset extractors ship in `pipeline.yaml`: `fixed_5s_2frames`, `fixed_10s_3frames`, `fixed_5s_every_1s`, `scene_default`, `scene_sensitive`, `semantic_default`.

**Code changes in `video_report_pipeline.py`:**

- Added `load_extractor_config(yaml_path, name)` — validates and returns an extractor config dict; raises on missing fields.
- Added `list_extractors(yaml_path)` — summary for `--config-dryrun`.
- `VideoReportPipeline.run()` signature simplified: now takes `extractor_cfg: dict` instead of separate `mode`/`interval_sec`/`threshold`/`min_scene_sec`/`frames_per_seg`/`keyframe_interval_sec` kwargs. The dict carries all extractor-specific params.
- CLI flags **removed**: `--mode`, `--interval`, `--threshold`, `--min-scene`, `--frames-per-seg`, `--keyframe-interval`.
- CLI flags **added**: `--extractor <name>` (default `fixed_5s_2frames`).
- CLI flag **renamed**: `--labelers-yaml` → `--pipeline-yaml` (default `./pipeline.yaml`).
- CLI flags **kept**: `--segments-json` (still supplied at runtime, not in YAML — it is per-input-video), `--srt`, `--max-sec`, `--out`, `--report-name`, `--config-dryrun`, `--dryrun`.
- `--config-dryrun` now prints both extractor and labeler summaries.

**Bug fixed during implementation:** Initial edit accidentally placed `load_extractor_config` / `list_extractors` between `VLMLabeler.list_labelers` and `VLMLabeler.label`, which broke the class (methods became nested inside `list_extractors`). Moved helpers after the class.

**Validation:**

- Config dryrun: `python moonshot/video_report_pipeline.py --config-dryrun` → 6 extractors + 3 labelers printed with full config. ✓
- Wiring dryrun: `python moonshot/video_report_pipeline.py moonshot/videos/correct_assemble_v1.mp4 --dryrun --extractor scene_default --labeler generic_describe --max-sec 30` → scene_detect mode loaded from YAML, real VLM call on segment 0 returned a valid `generic_describe`-style response (no `**Tools**` header, confirming the new labeler's prompt was actually used). ✓

**Three requirements now satisfied:**

| # | Requirement | Satisfied by |
|---|---|---|
| 1 | YAML controls which keyframe extractor | `extractors:` section + `--extractor <name>` |
| 2 | User can write own prompt | `labelers[].prompt` |
| 3 | User can choose model | `labelers[].model` |
