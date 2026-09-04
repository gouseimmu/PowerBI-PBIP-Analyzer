"""Azure OpenAI REST API Provider for DAX Optimization."""

import json
import logging
import requests
from typing import Dict, Any, Optional

from .provider import DAXAIProvider
from .prompts import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)


class AzureOpenAIProvider(DAXAIProvider):
    """Integrates with Azure OpenAI Service Chat Completions API."""

    def __init__(self, endpoint: str, api_key: str, deployment: str, api_version: str = "2024-02-15-preview", timeout: int = 15):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.deployment = deployment
        self.api_version = api_version
        self.timeout = timeout

    @property
    def provider_name(self) -> str:
        return f"Azure OpenAI ({self.deployment})"

    def is_available(self) -> bool:
        return bool(self.endpoint and self.api_key and self.deployment)

    def analyze_dax(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Call Azure OpenAI endpoint and return structured response."""
        if not self.is_available():
            return None

        url = f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions?api-version={self.api_version}"
        headers = {
            "Content-Type": "application/json",
            "api-key": self.api_key,
        }

        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(context)

        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 1200,
        }

        try:
            logger.info(f"Sending DAX analysis request to Azure OpenAI for '{context.get('object_name')}'")
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()

            res_json = response.json()
            choices = res_json.get("choices", [])
            if not choices:
                logger.warning("Azure OpenAI returned empty choices.")
                return None

            content = choices[0].get("message", {}).get("content", "")
            return json.loads(content)

        except requests.exceptions.RequestException as e:
            logger.warning(f"Azure OpenAI API request failed: {e}")
            return None
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse Azure OpenAI JSON response: {e}")
            return None

