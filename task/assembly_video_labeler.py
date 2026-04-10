#!/usr/bin/env python3
"""
Assembly Video Labeler — Layer 3 business class

Inherits OpenRouterLabeler (HTTP/retry/JSON parsing) and adds:
- Config loading from config/labeler/*.yaml + config/model/*.yaml
- Prompt template with {time_range} / {transcript_hint} placeholders
- Image-based segment labeling (keyframes -> VLM description)
- Batch labeling with rate limiting
"""

import os
import time
from typing import List, Optional

import yaml

from core.interfaces import LabelerInput
from core.openrouter_labeler import OpenRouterLabeler


class AssemblyVideoLabeler(OpenRouterLabeler):
    """VLM labeler for assembly video segments.

    Loads prompt template and model config from YAML files following the
    project config structure (config/labeler/, config/model/).
    """

    def __init__(
        self,
        name: str,
        model: str,
        prompt_template: str,
        api_key: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 500,
        timeout: int = 60,
        max_retries: int = 3,
    ):
        super().__init__(
            name=name,
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=max_retries,
        )
        self.prompt_template = prompt_template

    @classmethod
    def from_config(cls, config_dir: str, labeler_name: str,
                    api_key: Optional[str] = None) -> "AssemblyVideoLabeler":
        """Construct from config directory structure.

        Reads:
          config_dir/labeler/{labeler_name}.yaml  -> prompt, generation_config
          config_dir/model/openrouter.yaml        -> model, api_config
          config_dir/defaults/pipeline.yaml       -> fallback defaults

        Args:
            config_dir: Path to config/ directory
            labeler_name: Name matching a YAML file in config/labeler/
            api_key: Override for OPENROUTER_API_KEY env var
        """
        # Load labeler config
        labeler_path = os.path.join(config_dir, "labeler", f"{labeler_name}.yaml")
        if not os.path.exists(labeler_path):
            available = [
                f.replace(".yaml", "")
                for f in os.listdir(os.path.join(config_dir, "labeler"))
                if f.endswith(".yaml")
            ]
            raise ValueError(
                f"Labeler '{labeler_name}' not found at {labeler_path}. Available: {available}"
            )

        with open(labeler_path, "r", encoding="utf-8") as f:
            labeler_cfg = yaml.safe_load(f)

        # Load model config
        model_ref = labeler_cfg.get("model_config_ref", "model/openrouter.yaml")
        model_path = os.path.join(config_dir, model_ref)
        with open(model_path, "r", encoding="utf-8") as f:
            model_cfg = yaml.safe_load(f)

        # Load defaults
        defaults_path = os.path.join(config_dir, "defaults", "pipeline.yaml")
        defaults = {}
        if os.path.exists(defaults_path):
            with open(defaults_path, "r", encoding="utf-8") as f:
                defaults = yaml.safe_load(f) or {}
        labeler_defaults = defaults.get("labeler", {})

        # Model name
        model_name = model_cfg.get("model_info", {}).get(
            "default_model", "google/gemini-2.5-flash"
        )

        # Generation config (labeler yaml overrides defaults)
        gen_cfg = labeler_cfg.get("generation_config", {})
        temperature = gen_cfg.get(
            "temperature", labeler_defaults.get("temperature", 0.3)
        )
        max_tokens = gen_cfg.get(
            "max_tokens", labeler_defaults.get("max_tokens", 500)
        )

        # API config from model yaml
        api_cfg = model_cfg.get("api_config", {})
        timeout = api_cfg.get("timeout", 60)
        max_retries = api_cfg.get("max_retries", 3)

        # Prompt template
        instruction_type = labeler_cfg.get("task_config", {}).get(
            "instruction_type", labeler_name
        )
        instructions = labeler_cfg.get("instructions", {})
        prompt_entry = instructions.get(instruction_type, {})
        prompt_template = prompt_entry.get("template", "")
        if not prompt_template:
            raise ValueError(
                f"Labeler '{labeler_name}': no prompt template found "
                f"at instructions.{instruction_type}.template"
            )

        return cls(
            name=labeler_name,
            model=model_name,
            prompt_template=prompt_template,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=max_retries,
        )

    def label_segment(
        self,
        keyframe_paths: List[str],
        time_range: str,
        transcript: str = "",
    ) -> str:
        """Label a single video segment from its keyframes."""
        if not keyframe_paths:
            return "(no keyframes)"

        transcript_hint = (
            f'\nNarration during this segment: "{transcript}"'
            if transcript
            else ""
        )
        prompt_text = self.prompt_template.format(
            time_range=time_range,
            transcript_hint=transcript_hint,
        )

        input_data = LabelerInput(
            text="",
            image_paths=keyframe_paths,
            instruction=prompt_text,
        )

        output = self.label(input_data)
        return output.result.get("content", "")

    def label_all_segments(self, segments: list, rate_sleep_sec: float = 0.5) -> None:
        """Label all segments, populating each segment's vlm_description."""
        total = len(segments)
        for i, seg in enumerate(segments):
            time_range = f"{seg.start_sec:.1f}s - {seg.end_sec:.1f}s"
            print(f"  [vlm] Describing segment {i+1}/{total} ({time_range}) ...")
            seg.vlm_description = self.label_segment(
                keyframe_paths=seg.keyframe_paths,
                time_range=time_range,
                transcript=seg.transcript,
            )
            if i < total - 1:
                time.sleep(rate_sleep_sec)
