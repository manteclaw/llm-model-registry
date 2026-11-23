#!/usr/bin/env python3
"""
Auto Model Discovery — Query provider /models endpoints, diff against the
registry, and flag drift (removed models, failed health checks).

Usage: python3 auto-model-discovery.py [--dry-run]

Paths are configurable:
  MODEL_REGISTRY_PATH      registry JSON (default: model-registry.json
                           next to this script)
  MODEL_REGISTRY_ENV_FILE  .env file to load keys from (default: .env
                           next to this script)

API keys are read from the environment only (e.g. GROQ_API_KEY). Nothing
is hardcoded. Providers whose key is not set are skipped; OpenRouter's
public /models endpoint needs no key and is always checked.
"""
import json, os, subprocess, sys, argparse
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Load .env if available
env_file = Path(os.environ.get("MODEL_REGISTRY_ENV_FILE", SCRIPT_DIR / ".env"))
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), val)

REGISTRY_PATH = Path(os.environ.get("MODEL_REGISTRY_PATH", SCRIPT_DIR / "model-registry.json"))

def load_registry():
    with open(REGISTRY_PATH) as f:
        return json.load(f)

def save_registry(reg):
    with open(REGISTRY_PATH, "w") as f:
        json.dump(reg, f, indent=2)
        f.write("\n")

def discover_groq_models(key):
    r = subprocess.run([
        "curl", "-s", "https://api.groq.com/openai/v1/models",
        "-H", f"Authorization: Bearer {key}"
    ], capture_output=True, text=True)
    try:
        data = json.loads(r.stdout)
        return [m["id"] for m in data.get("data", [])]
    except json.JSONDecodeError:
        return []

def discover_openrouter_models():
    r = subprocess.run([
        "curl", "-s", "https://openrouter.ai/api/v1/models"
    ], capture_output=True, text=True)
    try:
        data = json.loads(r.stdout)
        return [m["id"] for m in data.get("data", [])]
    except json.JSONDecodeError:
        return []

def check_model_healthy(provider, model, key):
    if provider == "groq":
        r = subprocess.run([
            "curl", "-s", "-X", "POST", "https://api.groq.com/openai/v1/chat/completions",
            "-H", f"Authorization: Bearer {key}",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5})
        ], capture_output=True, text=True)
        return "error" not in r.stdout.lower() and r.returncode == 0
    return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    args = parser.parse_args()

    reg = load_registry()
    changes = []

    # Check Groq
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if groq_key and not groq_key.startswith("$"):
        models = discover_groq_models(groq_key)
        current = reg["providers"]["groq"]["models"]
        deprecated = reg["providers"]["groq"]["deprecated"]

        for role, model in list(current.items()):
            if model not in models:
                if model not in deprecated:
                    deprecated.append(model)
                    changes.append(f"Groq {role} model '{model}' removed from API → marked deprecated")
                # Try to find replacement
                fast_alternatives = [m for m in models if "llama-3.1-8b" in m or "llama-3.2-3b" in m]
                smart_alternatives = [m for m in models if "70b" in m or "llama-3.3" in m]
                if role == "fast" and fast_alternatives:
                    current[role] = fast_alternatives[0]
                    changes.append(f"Groq fast model → {fast_alternatives[0]}")
                elif role == "smart" and smart_alternatives:
                    current[role] = smart_alternatives[0]
                    changes.append(f"Groq smart model → {smart_alternatives[0]}")

        # Check health of current models
        for role, model in current.items():
            if not check_model_healthy("groq", model, groq_key):
                changes.append(f"Groq {role} model '{model}' health check failed")

    # Check OpenRouter
    or_models = discover_openrouter_models()
    if or_models:
        or_current = reg["providers"]["openrouter"]["models"]
        for role, model in list(or_current.items()):
            if model not in or_models:
                changes.append(f"OpenRouter {role} model '{model}' not in API list")

    if changes:
        print("🔄 Changes detected:")
        for c in changes:
            print(f"  • {c}")
        if not args.dry_run:
            reg["last_updated"] = datetime.now(timezone.utc).isoformat()
            save_registry(reg)
            print(f"✅ Updated {REGISTRY_PATH}")
        else:
            print("(dry-run — no changes written)")
    else:
        print("✅ All models healthy, no changes needed")
        reg["last_checked"] = datetime.now(timezone.utc).isoformat()
        if not args.dry_run:
            save_registry(reg)

    return 0

if __name__ == "__main__":
    sys.exit(main())
