#!/usr/bin/env python3
"""
OpenRouter Labeler for Moonshot
- Based on stance/labelers/api/openrouter_labeler.py
- Stripped of stance-specific dependencies (ConfigLoader, InstructionGenerator,
  LabelerLogger, LabelerMonitor, LLMCache, text_fixer)
- Core HTTP call chain (_http_post, _read_image_as_data_url, _prepare_messages,
  _extract_json) copied verbatim from original
- Config via constructor args instead of OmegaConf
"""

import os
import json
import base64
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv

from core.interfaces import APILabelerInterface, LabelerInput, LabelerOutput, ConfigurationError

# Auto-load .env from moonshot/code/
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=False)


class OpenRouterLabeler(APILabelerInterface):
    """OpenRouter-based labeler. Stripped for moonshot independent use.

    Constructor takes explicit args instead of OmegaConf config.
    Subclasses implement _build_system_instruction() and _validate_result()
    for specific tasks (assembly video, stance detection, etc.)
    """

    def __init__(
        self,
        name: str,
        model: str,
        api_key: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 500,
        timeout: int = 60,
        max_retries: int = 3,
    ):
        # Skip LabelerInterface.__init__ (requires OmegaConf config)
        self.name = name
        self.model = model
        self.api_key = api_key or os.getenv('OPENROUTER_API_KEY')
        if not self.api_key:
            raise ConfigurationError("OPENROUTER_API_KEY not found in environment variables")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.http_timeout = timeout
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # Core HTTP — copied verbatim from stance/labelers/api/openrouter_labeler.py
    # ------------------------------------------------------------------

    @staticmethod
    def _read_image_as_data_url(image_path: str) -> Optional[Dict[str, Any]]:
        try:
            if not Path(image_path).exists():
                print(f"Image file does not exist: {image_path}")
                return None
            with open(image_path, 'rb') as f:
                data = f.read()
            ext = Path(image_path).suffix.lower()
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }
            mime = mime_types.get(ext, 'image/jpeg')
            b64 = base64.b64encode(data).decode('ascii')
            return {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"}
            }
        except Exception as e:
            print(f"Failed to process image {image_path}: {e}")
            return None

    def _prepare_messages(self, text: str, image_paths: List[str],
                          system_instruction: str) -> List[Dict[str, Any]]:
        """Build multimodal messages. Copied from original, simplified (no PIL path)."""
        parts: List[Dict[str, Any]] = []

        # Images first, then text (default for most models)
        image_parts: List[Dict[str, Any]] = []
        for p in image_paths or []:
            img = self._read_image_as_data_url(p)
            if img:
                image_parts.append(img)

        parts.extend(image_parts)
        if text:
            parts.append({"type": "text", "text": text})

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": parts if parts else text}
        ]
        return messages

    def _http_post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """HTTP POST with retry. Copied verbatim from original."""
        import requests
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(self.base_url, headers=headers,
                                     data=json.dumps(payload), timeout=self.http_timeout)
                if resp.status_code >= 500 or resp.status_code == 429:
                    if attempt < self.max_retries:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                if attempt >= self.max_retries:
                    raise RuntimeError(f"OpenRouter request failed: {e}")
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError("Unexpected failure in _http_post")

    def _extract_json(self, text: str) -> Any:
        """Extract JSON from model output. Copied verbatim from original."""
        # Try direct json
        try:
            return json.loads(text)
        except Exception:
            pass
        # Try to extract fenced code blocks
        pattern = r"```(?:json)?\n([\s\S]*?)\n```"
        m = re.search(pattern, text)
        if m:
            cand = m.group(1)
            try:
                return json.loads(cand)
            except Exception:
                pass
        # Last resort: find first {...} or [...] matching braces
        stack = []
        start = -1
        for i, ch in enumerate(text):
            if ch in '{[':
                if not stack:
                    start = i
                stack.append(ch)
            elif ch in '}]' and stack:
                stack.pop()
                if not stack and start != -1:
                    snippet = text[start:i+1]
                    try:
                        return json.loads(snippet)
                    except Exception:
                        break
        raise ValueError("Failed to parse JSON from model output")

    # ------------------------------------------------------------------
    # APILabelerInterface implementation
    # ------------------------------------------------------------------

    def _make_api_call(self, input_data: LabelerInput) -> Dict[str, Any]:
        """Make API call. Adapted from original — uses self.model/temperature/max_tokens
        instead of OmegaConf config.
        """
        text = input_data.text or ""
        image_paths = input_data.image_paths or []
        system_instruction = input_data.instruction or ""

        start = time.time()
        messages = self._prepare_messages(text, image_paths, system_instruction)

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        raw_resp = self._http_post(payload)

        try:
            choice0 = (raw_resp.get('choices') or [{}])[0]
            content = choice0.get('message', {}).get('content', '') or ''
        except Exception:
            content = json.dumps(raw_resp)

        proc_time = time.time() - start

        return {
            "content": content,
            "processing_time": proc_time,
            "image_count": len(image_paths),
        }

    def _parse_api_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        return response

    def label(self, input_data: LabelerInput) -> LabelerOutput:
        """Core label method. Calls _make_api_call and wraps result."""
        api_result = self._make_api_call(input_data)
        return LabelerOutput(
            result={"content": api_result["content"]},
            processing_time=api_result["processing_time"],
            cached=False,
            metadata={
                "image_count": api_result["image_count"],
                "model": self.model,
                "labeler_name": self.name,
            }
        )
