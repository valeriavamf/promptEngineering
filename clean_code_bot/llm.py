"""
LLM client abstraction supporting OpenAI and Groq providers.

Both providers expose an OpenAI-compatible REST API, so the same
openai SDK client is reused — only the base URL and default model differ.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from openai import OpenAI


# Issue 2: provider constants moved to module level — not mutable dataclass fields
_PROVIDER_BASE_URLS: dict[str, str | None] = {
    "openai": None,                            # SDK default
    "groq": "https://api.groq.com/openai/v1",
}

_PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "groq": "llama-3.3-70b-versatile",  # 128k context; current Groq recommended model
}


class Provider(str, Enum):
    OPENAI = "openai"
    GROQ = "groq"


# CompletionService Protocol for Dependency Inversion.
# Structural subtyping only — no @runtime_checkable needed because
# no isinstance() guard exists in this codebase.  Type checkers
# (mypy / pyright) verify conformance statically.
class CompletionService(Protocol):
    """
    Protocol that any completion backend must satisfy.

    Decouples ``LLMClient`` from the concrete ``openai.OpenAI`` class so
    that tests can inject a lightweight stub without touching the network.
    """

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a completion request and return the model's text response.

        Args:
            system_prompt: Instructions that define the assistant's behaviour.
            user_prompt: The user-facing request.

        Returns:
            Full text content of the model's response.
        """
        ...


@dataclass
class LLMConfig:
    """
    Configuration for the LLM client.

    Attributes:
        provider: Which API provider to use.
        api_key: Authentication key for the chosen provider.
        model: Model identifier to request completions from.
            Defaults to the provider's recommended model when empty.
        temperature: Sampling temperature (0 = deterministic, 1 = creative).
        max_tokens: Upper bound on response length in tokens.

    Properties:
        base_url: Read-only. Returns the API base URL for the configured
            provider, or ``None`` to use the OpenAI SDK built-in default.
    """

    provider: Provider
    api_key: str
    model: str = ""
    temperature: float = 0.2
    max_tokens: int = 8192  # 6-step CoT reasoning + full refactored file needs >4k tokens

    def __post_init__(self) -> None:
        if not self.model:
            self.model = _PROVIDER_DEFAULT_MODELS[self.provider.value]

    # Issue 2: base_url exposed as a property — LLMClient never accesses private fields
    @property
    def base_url(self) -> str | None:
        """
        Return the API base URL for the configured provider.

        Returns:
            URL string for third-party providers (e.g. Groq), or ``None``
            to use the OpenAI SDK's built-in default.
        """
        return _PROVIDER_BASE_URLS.get(self.provider.value)


class LLMClient:
    """
    Thin wrapper around the OpenAI SDK that supports both OpenAI and Groq.

    Implements the ``CompletionService`` Protocol, so it can be used
    wherever that interface is expected.

    Usage:
        client = LLMClient(config)
        result = client.complete(system_prompt, user_prompt)
    """

    def __init__(self, config: LLMConfig) -> None:
        """
        Initialise the client with the given configuration.

        Args:
            config: ``LLMConfig`` instance specifying provider and credentials.
        """
        # Issue 2: accesses public property instead of private _BASE_URLS
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
        )
        self._config = config

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a chat completion request and return the assistant's reply.

        Args:
            system_prompt: Instructions that define the assistant's behaviour.
            user_prompt: The user-facing request (contains the code to refactor).

        Returns:
            The full text content of the model's response.

        Raises:
            openai.OpenAIError: On any API-level error (auth, rate limit, etc.).
        """
        response = self._client.chat.completions.create(
            model=self._config.model,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""
