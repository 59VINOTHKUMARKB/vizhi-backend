"""Local logical provider adapter."""

from __future__ import annotations

from app.providers.base import BaseProvider, ProviderResponse
from app.providers.final_call import chat_completion as final_chat_completion


class LocalProvider(BaseProvider):
    provider_name = "local"

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url

    async def chat_completion(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 1.0,
        max_tokens: int | None = None,
        **kwargs,
    ) -> ProviderResponse:
        return await final_chat_completion(
            provider_name=self.provider_name,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=self._base_url,
            **kwargs,
        )
