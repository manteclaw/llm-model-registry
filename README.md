# llm-model-registry

A provider/model registry for multi-provider LLM setups, plus a drift checker that diffs the registry against providers' live `/models` endpoints and flags models that disappeared.

Providers rename and retire models without notice. If your router points at a model ID that no longer exists, you find out from a failed request. This catches it first.

## Who it's for

Anyone running LLM routing or failover across more than one provider — agents, gateways, LiteLLM-style proxies — who keeps a "which model do I use for what" table somewhere and wants that table checked against reality on a schedule.

## What's in the registry

`model-registry.json` covers 9 providers (Groq, Cerebras, Mistral, OpenRouter, NVIDIA, Cloudflare, Portkey, LiteLLM, SambaNova). Per provider:

- `base_url` and `api_key_env` — the **name** of the environment variable holding the key. Keys are never stored in the registry.
- `models` — role → model ID (`fast`, `smart`, `free`, `vision`)
- `deprecated` — model IDs known retired
- `fallback` — next provider in the chain
- `rpm`, per-token costs, and a `pricing_note`

Plus a `task_type_map` (task type → provider + role) and `circuit_breaker` settings (failure threshold, recovery timeout, half-open requests).

## The checker

`auto-model-discovery.py` — Python 3, standard library only, shells out to `curl`.

```bash
python3 auto-model-discovery.py --dry-run   # report drift, write nothing
python3 auto-model-discovery.py             # report drift, update the registry
```

What it checks:

- **OpenRouter** — keyless. Fetches the public `https://openrouter.ai/api/v1/models` list and reports any registry role model that is no longer in it.
- **Groq** — only when `GROQ_API_KEY` is set in the environment. Fetches the live model list, marks vanished role models deprecated, suggests a replacement from the live list, and health-checks the current role models with a minimal chat call.
- On a non-dry-run it stamps `last_updated` (changes found) or `last_checked` (none) into the registry.

Keys come from the environment, or from a `.env` file if one sits next to the script. Paths are overridable:

- `MODEL_REGISTRY_PATH` — registry JSON location (default: `model-registry.json` next to the script)
- `MODEL_REGISTRY_ENV_FILE` — `.env` location (default: `.env` next to the script)

Run it weekly from cron and read the output; that was its original job.

## Snapshot status — read this before trusting the data

The bundled registry entries are a snapshot originally dated **2026-05-16**. The checker was re-run against live endpoints on **2026-11-23** and found real drift:

- OpenRouter `fast` model `google/gemma-3-27b-it:free` — no longer in OpenRouter's live `/models` list
- OpenRouter `smart`/`free` model `deepseek/deepseek-r1:free` — no longer in the live list

Those entries were deliberately **not** hand-edited: picking replacements is a judgement call for your own routing, and the checker only reports OpenRouter drift rather than rewriting roles. The Groq section was not re-validated in that run (it needs a key). Treat every entry as a starting point, run the checker with your keys set, and fix the roles it flags.

## Limits

- Only Groq and OpenRouter are polled. The other 7 providers are registry data only — the checker does not verify them.
- Groq replacement suggestions are substring heuristics (`70b`, `llama-3.3`, …), not benchmarks. Sanity-check before adopting.
- Pricing notes are whatever was true when the snapshot was taken. Providers change pricing constantly; verify before budgeting.
- The health check sends a real (tiny) chat completion to Groq. It costs a few tokens.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) Manteclaw.
