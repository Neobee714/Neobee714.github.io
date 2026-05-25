"""LLM client wrapper for translation via OpenAI-compatible API.

Reads LLM_API_KEY, LLM_BASE_URL, LLM_MODEL from environment variables.
Implements retry with exponential backoff (1s, 2s, 4s).
"""

import os
import time
import logging
from typing import Tuple

from openai import OpenAI

log = logging.getLogger(__name__)

_MAX_RETRIES = 5
_BACKOFF_SECONDS = [2, 4, 8, 16, 30]


class LlmClient:
    """Wrapper around OpenAI-compatible API for translation."""

    def __init__(self, api_key: str, base_url: str, model: str):
        """Initialize the LLM client.

        Args:
            api_key: API key for authentication.
            base_url: Base URL of the OpenAI-compatible endpoint.
            model: Model name to use for completions.
        """
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    @classmethod
    def from_env(cls) -> "LlmClient":
        """Create an LlmClient from environment variables.

        Reads:
            LLM_API_KEY: API key for authentication.
            LLM_BASE_URL: Base URL of the API endpoint.
            LLM_MODEL: Model name to use.

        Raises:
            ValueError: If any required env var is missing.
        """
        api_key = os.environ.get("LLM_API_KEY")
        base_url = os.environ.get("LLM_BASE_URL")
        model = os.environ.get("LLM_MODEL")

        if not api_key:
            raise ValueError("LLM_API_KEY environment variable is required")
        if not base_url:
            raise ValueError("LLM_BASE_URL environment variable is required")
        if not model:
            raise ValueError("LLM_MODEL environment variable is required")

        return cls(api_key=api_key, base_url=base_url, model=model)

    def translate_chunk(self, system_prompt: str, content: str) -> Tuple[str, int]:
        """Translate a chunk of content using the LLM.

        Retries up to 3 times with exponential backoff (1s, 2s, 4s).

        Args:
            system_prompt: The system prompt with translation instructions.
            content: The source content to translate.

        Returns:
            A tuple of (translated_text, tokens_used).

        Raises:
            Exception: If all retries are exhausted.
        """
        last_error = None

        for attempt in range(_MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"<SOURCE>\n{content}\n</SOURCE>"},
                    ],
                    temperature=0.3,
                    max_tokens=4096,
                )

                if not response.choices:
                    raise ValueError("LLM returned empty choices")
                text = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response.usage else 0

                # Extract content between <TRANSLATED> tags if present
                if "<TRANSLATED>" in text:
                    start = text.index("<TRANSLATED>") + len("<TRANSLATED>")
                    text = text[start:]
                if "</TRANSLATED>" in text:
                    text = text[:text.index("</TRANSLATED>")]
                text = text.strip()

                return text, tokens

            except Exception as e:
                last_error = e
                if attempt < _MAX_RETRIES - 1:
                    wait = _BACKOFF_SECONDS[attempt]
                    log.warning(
                        f"LLM call failed (attempt {attempt + 1}/{_MAX_RETRIES}), "
                        f"retrying in {wait}s: {e}"
                    )
                    time.sleep(wait)

        raise last_error  # type: ignore[misc]
