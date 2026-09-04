"""AI Provider Abstraction for DAX Optimization."""

import os
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class DAXAIProvider(ABC):
    """Abstract interface for optional AI-assisted DAX optimization."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of the AI provider."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether the AI provider is configured and available."""
        pass

    @abstractmethod
    def analyze_dax(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send sanitized DAX and model context to AI and return structured analysis dictionary."""
        pass


class NullAIProvider(DAXAIProvider):
    """Fallback provider when no AI API credentials are configured."""

    @property
    def provider_name(self) -> str:
        return "None (Static Analysis Only)"

    def is_available(self) -> bool:
        return False

    def analyze_dax(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        logger.debug("NullAIProvider active; AI-assisted analysis skipped.")
        return None


def get_ai_provider() -> DAXAIProvider:
    """Factory function to instantiate configured AI provider from environment variables."""
    # Check explicitly disabled
    if os.getenv("DISABLE_AI", "").lower() in ["1", "true", "yes"]:
        logger.info("AI analysis explicitly disabled via DISABLE_AI.")
        return NullAIProvider()

    provider_env = os.getenv("AI_PROVIDER", "").lower().strip()

    # 1. Check Azure OpenAI
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    azure_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

    if (provider_env in ["azure", "azure_openai"] or (azure_endpoint and azure_key)) and azure_endpoint and azure_key:
        from .azure_openai_provider import AzureOpenAIProvider
        logger.info(f"Initialized AzureOpenAIProvider (Deployment: {azure_deployment})")
        return AzureOpenAIProvider(
            endpoint=azure_endpoint,
            api_key=azure_key,
            deployment=azure_deployment,
            api_version=azure_version,
        )

    # 2. Check OpenAI
    openai_key = os.getenv("OPENAI_API_KEY")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if (provider_env in ["openai"] or openai_key) and openai_key:
        from .openai_provider import OpenAIProvider
        logger.info(f"Initialized OpenAIProvider (Model: {openai_model})")
        return OpenAIProvider(
            api_key=openai_key,
            model=openai_model,
        )

    logger.info("No AI credentials configured; using NullAIProvider (Deterministic Static Analysis).")
    return NullAIProvider()

