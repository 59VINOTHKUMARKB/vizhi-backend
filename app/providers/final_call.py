"""Central inference switchboard for all provider adapters.

Provider files keep Vizhi's logical provider names. This module decides which
real inference backend should receive the request.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import random

from app.config.settings import settings
from app.providers.base import ProviderResponse


_CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
_DEFAULT_MODEL_ALIASES = {
    "llama/meta-llama/Llama-3.1-8B-Instruct":
        "meta-llama/Llama-3.1-8B-Instruct:fastest",

    "llama/meta-llama/Llama-3.2-3B-Instruct":
        "meta-llama/Llama-3.2-3B-Instruct:fastest",

    "mistral/mistralai/Mistral-7B-Instruct-v0.3":
        "mistralai/Mistral-7B-Instruct-v0.3:fastest",

    "mistral/mistralai/Mixtral-8x7B-Instruct-v0.1":
        "mistralai/Mixtral-8x7B-Instruct-v0.1:fastest",

    "deepseek/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B":
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B:fastest",

    # Qwen models
    "qwen/Qwen/Qwen2.5-7B-Instruct":
        "Qwen/Qwen2.5-7B-Instruct:fastest",

    "qwen/Qwen/Qwen2.5-3B-Instruct":
        "Qwen/Qwen2.5-3B-Instruct:fastest",

    "qwen/Qwen/Qwen2.5-1.5B-Instruct":
        "Qwen/Qwen2.5-1.5B-Instruct:fastest",

    "qwen/Qwen/Qwen2.5-Coder-7B-Instruct":
        "Qwen/Qwen2.5-Coder-7B-Instruct:fastest",
}


async def chat_completion(
    *,
    provider_name: str,
    model: str,
    messages: list[dict],
    temperature: float = 1.0,
    max_tokens: int | None = None,
    **kwargs: Any,
) -> ProviderResponse:
    """Call the configured inference backend for a logical provider request.

    ``settings.inference_backend`` can be a single backend name or a comma
    separated fallback order, for example ``huggingface`` or
    ``custom,huggingface``.
    """
    
    
    errors: list[str] = []
    for backend in _backend_order():
        candidates = _candidate_models(provider_name=provider_name,fallback_model=model)
        for candidate_model in candidates:
            try:
                if backend == "huggingface":
                    return await _openai_compatible_call(
                        backend_name=backend,
                        provider_name=provider_name,
                        base_url=settings.huggingface_base_url,
                        api_key=settings.huggingface_api_key or settings.hf_token,
                        require_api_key=True,
                        model=candidate_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                if backend == "custom":
                    return await _openai_compatible_call(
                        backend_name=backend,
                        provider_name=provider_name,
                        base_url=kwargs.get("base_url") or settings.custom_inference_base_url,
                        api_key=settings.custom_inference_api_key,
                        require_api_key=False,
                        model=_resolve_model(provider_name, model),
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                raise RuntimeError(f"Unknown inference backend: {backend}")
            except Exception as exc:
                msg = f"{backend}/{candidates}: {exc}"
                errors.append(msg)
                continue
            

    raise RuntimeError("; ".join(errors) or "No inference backend configured")


def _backend_order() -> list[str]:
    backends = [
        backend.strip().lower()
        for backend in settings.inference_backend.split(",")
        if backend.strip()
    ]
    return backends or ["huggingface"]


def _resolve_model(provider_name: str, model: str) -> str:
    candidates = _candidate_models(provider_name=provider_name,fallback_model=model)
    return candidates[0]
 

def _candidate_models(provider_name: str , fallback_model: str) -> list[str]:
    """
       Return an Ordered list of model , which helps the  __openai_compitable call to perform multiple execution of other models.
    """

    pool = list(_DEFAULT_MODEL_ALIASES.values())

    seen,unique_pool = set(),[]

    for m in pool:
        if m not in seen:
            seen.add(m)
            unique_pool.append(m)
    random.shuffle(unique_pool)

    return unique_pool



def _model_map() -> dict[str, str]:
    if not settings.inference_model_map:
        return {}
    try:
        parsed = json.loads(settings.inference_model_map)
    except json.JSONDecodeError as exc:
        raise RuntimeError("INFERENCE_MODEL_MAP must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("INFERENCE_MODEL_MAP must be a JSON object")
    return {str(key): str(value) for key, value in parsed.items()}


async def _openai_compatible_call(
    *,
    backend_name: str,
    provider_name: str,
    base_url: str,
    api_key: str,
    require_api_key: bool,
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int | None,
) -> ProviderResponse:
    if not base_url:
        raise RuntimeError(f"{backend_name.upper()} base URL is not configured")
    if require_api_key and not api_key:
        raise RuntimeError(f"{backend_name.upper()} API key is not configured")

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    url = f"{base_url.rstrip('/').removesuffix('/v1')}{_CHAT_COMPLETIONS_PATH}"
    start = time.perf_counter_ns()
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, json=payload, headers=headers)
    latency = (time.perf_counter_ns() - start) // 1_000_000

    if resp.is_error:
        raise RuntimeError(
            f"{resp.status_code} {resp.reason_phrase} from {backend_name} "
            f"for model '{model}': {resp.text}"
        )

    data = resp.json()
    choice = data["choices"][0]
    usage = data.get("usage", {})

    return ProviderResponse(
        content=choice.get("message", {}).get("content", ""),
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
        model=data.get("model", model),
        provider=provider_name,
        raw_response=data,
        latency_ms=latency,
        finish_reason=choice.get("finish_reason", "stop"),
    )
