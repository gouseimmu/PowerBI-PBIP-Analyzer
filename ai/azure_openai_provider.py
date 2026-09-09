"""Azure OpenAI REST API Provider for DAX Optimization."""

import json
import logging
import requests
from typing import Dict, Any, Optional

from .provider import DAXAIProvider
from .prompts import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)


class AzureOpenAIProvider(DAXAIProvider):
    """Integrates with Azure OpenAI Service Chat Completions API (supports modern v1 & deployment-path endpoints)."""

    def __init__(self, endpoint: str, api_key: str, deployment: str, api_version: str = "v1", timeout: int = 15):
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
        # Prefer modern v1 endpoint: /openai/v1/chat/completions
        if self.api_version in ("v1", "v1.0", "") or "/openai/v1" in self.endpoint:
            base = self.endpoint
            if not base.endswith("/openai/v1"):
                base = f"{base}/openai/v1"
            url = f"{base}/chat/completions"
            payload = {
                "model": self.deployment,
                "messages": [
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": build_user_prompt(context)},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
                "max_tokens": 1200,
            }
        else:
            # Deployment path backward-compatible endpoint
            url = f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions?api-version={self.api_version}"
            payload = {
                "messages": [
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": build_user_prompt(context)},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
                "max_tokens": 1200,
            }

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
            obj_name = context.get("object_name", "object")
            logger.info(f"Sending DAX analysis request to Azure OpenAI for '{obj_name}'")
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()

            res_json = response.json()
            choices = res_json.get("choices", [])
            if not choices:
                logger.warning("Azure OpenAI returned empty choices array.")
                return None

            content = choices[0].get("message", {}).get("content", "")
            if not content:
                return None

            return json.loads(content)

        except requests.exceptions.RequestException as e:
            err_type = type(e).__name__
            logger.warning(f"Azure OpenAI API request failed ({err_type}). AI optimization unavailable.")
            return None
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse Azure OpenAI JSON response. Static DAX analysis was completed.")
            return None
        except Exception as e:
            logger.warning("Unexpected error during Azure OpenAI execution. Fallback to static analysis.")
            return None

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1000,
    ) -> Optional[str]:
        """Send chat message history to Azure OpenAI endpoint and return string response."""
        if not self.is_available():
            return None

        # Build endpoint URL (supports modern v1 and deployment path)
        if self.api_version in ("v1", "v1.0", "") or "/openai/v1" in self.endpoint:
            base = self.endpoint
            if not base.endswith("/openai/v1"):
                base = f"{base}/openai/v1"
            url = f"{base}/chat/completions"
            payload = {
                "model": self.deployment,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        else:
            url = f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions?api-version={self.api_version}"
            payload = {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

        headers = {
            "Content-Type": "application/json",
            "api-key": self.api_key,
        }

        try:
            logger.info("Sending chat completion request to Azure OpenAI")
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()

            res_json = response.json()
            choices = res_json.get("choices", [])
            if not choices:
                logger.warning("Azure OpenAI returned empty choices array for chat completion.")
                return None

            return choices[0].get("message", {}).get("content", "")

        except requests.exceptions.RequestException as e:
            err_type = type(e).__name__
            logger.warning(f"Azure OpenAI Chat API request failed ({err_type}). Chat assistant unavailable.")
            return None
        except Exception as e:
            logger.warning("Unexpected error during Azure OpenAI chat completion execution.")
            return None
