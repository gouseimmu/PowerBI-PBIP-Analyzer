"""OpenAI REST API Provider for DAX Optimization."""

import json
import logging
import requests
from typing import Dict, Any, Optional

from .provider import DAXAIProvider
from .prompts import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)


class OpenAIProvider(DAXAIProvider):
    """Integrates with OpenAI Chat Completions API."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", timeout: int = 15):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.url = "https://api.openai.com/v1/chat/completions"

    @property
    def provider_name(self) -> str:
        return f"OpenAI ({self.model})"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def analyze_dax(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Call OpenAI endpoint and return structured response."""
        if not self.is_available():
            return None

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(context)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 1200,
        }

        try:
            logger.info(f"Sending DAX analysis request to OpenAI for '{context.get('object_name')}'")
            response = requests.post(self.url, headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()

            res_json = response.json()
            choices = res_json.get("choices", [])
            if not choices:
                logger.warning("OpenAI returned empty choices.")
                return None

            content = choices[0].get("message", {}).get("content", "")
            return json.loads(content)

        except requests.exceptions.RequestException as e:
            logger.warning(f"OpenAI API request failed: {e}")
            return None
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse OpenAI JSON response: {e}")
            return None

