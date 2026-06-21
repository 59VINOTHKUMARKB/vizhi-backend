# vizhi-backend
backend-vizhi

## Inference routing

All logical providers call `app/providers/final_call.py`. Configure the real
inference backend with environment variables:

```env
INFERENCE_BACKEND=huggingface
HF_TOKEN=hf_your_token
```

Create `vizhi-backend/.env` for real local secrets. The project already ignores
`.env`; use `.env.example` as the template.

For your own OpenAI-compatible deployment:

```env
INFERENCE_BACKEND=custom
CUSTOM_INFERENCE_BASE_URL=http://localhost:8001/v1
CUSTOM_INFERENCE_API_KEY=
```

You can also configure fallback order:

```env
INFERENCE_BACKEND=custom,huggingface
```

Use `INFERENCE_MODEL_MAP` when a Vizhi model alias should call a different
backend model id:

```env
INFERENCE_MODEL_MAP={"qwen/qwen-plus":"Qwen/Qwen2.5-7B-Instruct:fastest"}
```
