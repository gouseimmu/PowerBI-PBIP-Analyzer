"""Power BI AI Assistant Chatbot Service.

Provides a grounded conversational interface over analyzed PBIP metadata.
Reuses existing Azure OpenAI provider architecture and enforces grounding,
request limits, SHA-256 caching, and safe error handling.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from .context_builder import ContextBuilder
from .provider import DAXAIProvider, NullAIProvider
from .response_parser import AIResponseParser
from analyzers.dax_dependency_analyzer import ModelCatalog

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a Power BI technical assistant specializing in semantic model governance, DAX optimization, relationship analysis, visual usage, and model health.

Answer questions using ONLY the supplied PBIP analysis context.

CRITICAL GROUNDING RULES:
1. Do NOT invent tables, columns, measures, relationships, visuals, pages, data sources, or DAX dependencies.
2. If the user asks about an object (table, column, measure) or information that does not exist in the supplied PBIP analysis context, explicitly state:
   "I couldn't find '[requested object]' in the analyzed PBIP model."
3. Do NOT pretend to have access to Power BI Service, live data sources, or claim to have executed DAX expressions live.
4. Clearly distinguish empirical facts (from PBIP metadata) from recommendations.
5. When providing DAX optimization recommendations, include:
   - Explanation of the current implementation
   - Potential Issue / Bottleneck
   - Suggested DAX (if appropriate)
   - Expected Benefit
   - Confidence Level (High / Medium / Low)
   - Manual Validation (Required / Not Required)
"""


class PowerBIChatbot:
    """PBIP-grounded AI Assistant service for Streamlit chat UI."""

    def __init__(self, ai_provider: Optional[DAXAIProvider] = None, max_ai_requests: int = 50):
        self.ai_provider = ai_provider or NullAIProvider()
        self.max_ai_requests = max_ai_requests
        self.ai_requests_sent = 0
        self._cache: Dict[str, str] = {}

    def ask(
        self,
        question: str,
        metadata: Optional[Dict[str, Any]],
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Process user question using relevant PBIP context and AI provider."""
        if not metadata:
            return {
                "status": "no_metadata",
                "answer": "Please upload and analyze a PBIP project before using the AI Assistant.",
                "cached": False,
            }

        if not self.ai_provider.is_available():
            return {
                "status": "ai_disabled",
                "answer": "AI Assistant is disabled. Enable AI analysis to use the chatbot.",
                "cached": False,
            }

        if self.ai_requests_sent >= self.max_ai_requests:
            return {
                "status": "limit_reached",
                "answer": "AI request limit reached for this analysis session. Static analysis and existing results remain available.",
                "cached": False,
            }

        # Build focused PBIP context
        context = ContextBuilder.build_context(question, metadata, chat_history)
        context_str = json.dumps(context, sort_keys=True, default=str)

        # Hash for response caching
        cache_key = hashlib.sha256(f"{question.strip().lower()}:{context_str}".encode()).hexdigest()
        if cache_key in self._cache:
            logger.info("Returning cached chatbot response.")
            return {
                "status": "success",
                "answer": self._cache[cache_key],
                "cached": True,
            }

        # Prepare messages
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n=== RELEVANT PBIP ANALYSIS CONTEXT ===\n{context_str}"}
        ]

        # Add recent conversation history for multi-turn context (last 6 messages max)
        if chat_history:
            for msg in chat_history[-6:]:
                role = msg.get("role", "user")
                if role in ("user", "assistant") and msg.get("content"):
                    messages.append({"role": role, "content": msg["content"]})

        # Append current user question
        messages.append({"role": "user", "content": question})

        try:
            self.ai_requests_sent += 1
            logger.info(f"Sending chat completion request (Request #{self.ai_requests_sent}/{self.max_ai_requests})")
            answer = self.ai_provider.chat_completion(messages, temperature=0.2, max_tokens=1000)

            if not answer:
                return {
                    "status": "error",
                    "answer": "AI Assistant is temporarily unavailable. Please verify the Azure OpenAI configuration.",
                    "cached": False,
                }

            # Optional DAX catalog validation check if response proposes DAX
            if "DIVIDE(" in answer or "CALCULATE(" in answer or "VAR " in answer:
                catalog = ModelCatalog(
                    metadata.get("tables", []),
                    metadata.get("columns", []),
                    metadata.get("measures", []),
                    metadata.get("calculated_columns", []),
                )
                val_status, val_note = AIResponseParser._validate_references(answer, catalog, "")
                if val_status == "Invalid":
                    logger.debug(f"Chat response contains invalid references: {val_note}")

            self._cache[cache_key] = answer
            return {
                "status": "success",
                "answer": answer,
                "cached": False,
            }

        except Exception as exc:
            logger.warning(f"Error during chatbot execution: {exc}")
            return {
                "status": "error",
                "answer": "AI Assistant is temporarily unavailable. Please verify the Azure OpenAI configuration.",
                "cached": False,
            }
