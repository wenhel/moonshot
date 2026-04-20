# Future Work

## 1. Precise Step Boundary Detection (Manual Parser)

**Problem**: VLM estimates step crop boundaries as percentages, but accuracy is ~2-5% off. For multi-step pages (e.g. steps 4-5 on one page), this causes adjacent step content to bleed into crops — the next step's circled number and partial text appear in the current step's crop.

**Current state**: Two-stage VLM detection (structure + per-page pixel boundaries). Better than equal-split but still imprecise.

**Proposed fix**: CV-based vertical gap detection (generalizable, no dependency on circles):
1. Project the page image onto x-axis (sum pixel values per column)
2. On dark-background manuals: columns between steps have near-zero values (blank gap)
3. Detect valleys in the x-projection — these are the step boundaries
4. Split at the widest valley between each pair of expected steps

This works for any manual layout (circles, numbered headers, or no markers at all) because steps are always separated by vertical whitespace. No manual-specific tuning needed.

Algorithm:
```
1. grayscale -> column-wise sum -> 1D signal
2. smooth signal (moving average)
3. find valleys (local minima below threshold)
4. select N-1 deepest valleys for N steps -> split points
```

Fallback: VLM boundaries if CV finds no clear gaps (e.g. steps overlap with no whitespace).

## 2. Streaming / Online Video Processing

**Problem**: Current pipeline processes entire video offline (read all frames, then segment, then label). For real-time use (e.g. live assembly guidance), need streaming architecture.

**Proposed design**:
- Process video in 30s clips as they arrive
- Scene detection maintains a rolling buffer
- When buffer accumulates enough keyframes (>= min_keyframes), flush to labeler
- Labeler runs async, results streamed to UI

## 3. TTS / Whisper Transcript Integration

**Problem**: Assembly videos without narration have no transcript. `SrtAligner` only works with existing SRT files.

**Proposed fix**:
- Integrate Whisper API (already have `WhisperLabeler` in stance project)
- Copy `whisper_labeler.py` to `preprocess/tools/`
- Add `--whisper` flag to pipeline: extract audio → transcribe → align to segments

## 4. Manual Step ↔ Video Segment Matching

**Problem**: Need to determine which manual step each video segment corresponds to, and whether the assembly is correct.

**Proposed design**:
- New labeler `manual_step_match.yaml`
- Input: segment keyframes + manual step summaries (from `manual_parsed.json`)
- Output: `step_number`, `correct: yes/no`, `issues: [...]`
- Requires `manual_steps.md` or `manual_parsed.json` as context in the prompt

## 5. Pipeline YAML Configuration

**Problem**: Current pipeline parameters are split between CLI args, `config/defaults/pipeline.yaml`, and labeler YAMLs. No single file to define a complete run.

**Proposed design**: A `run.yaml` that specifies everything:
```yaml
video: path/to/video.mp4
extractor: scene_fixedcam
labeler: assembly_structured-with-instruction
output: output/my_run
max_sec: 0
report_name: report.md
```
CLI: `python -m task.video_report_pipeline --run run.yaml`

## 6. VLM Provider Abstraction

**Problem**: Currently hardcoded to OpenRouter API. May need to switch to direct Gemini API, Claude API, or local models.

**Proposed fix**: `core/openrouter_labeler.py` is already Layer 2. Add sibling classes:
- `core/gemini_labeler.py` (direct Google Gemini SDK)
- `core/claude_labeler.py` (Anthropic API)
- Layer 3 business classes (`AssemblyVideoLabeler`) should work with any Layer 2 provider
