"""
Run this script once to enter your IBM credentials interactively.
It writes them to .env and then tests the connection.

Usage:  python setup_credentials.py
"""
import os, re, sys, pathlib

ENV_PATH = pathlib.Path(".env")

def read_env() -> dict:
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env

def write_env(env: dict):
    lines = []
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k = stripped.split("=")[0].strip()
                if k in env:
                    lines.append(f"{k}={env.pop(k)}")
                    continue
            lines.append(line)
    # append any new keys
    for k, v in env.items():
        lines.append(f"{k}={v}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

def prompt(label: str, current: str, placeholder: str) -> str:
    display = "" if current == placeholder else current
    val = input(f"  {label} [{display or 'not set'}]: ").strip()
    return val if val else current

PLACEHOLDER_API   = "your_ibm_cloud_api_key_here"
PLACEHOLDER_PROJ  = "your_watsonx_project_id_here"

print()
print("=" * 60)
print("  NutriSage AI — IBM Watsonx Credentials Setup")
print("=" * 60)
print()
print("Where to find your credentials:")
print("  IBM_API_KEY    → cloud.ibm.com > Manage > IAM > API Keys")
print("  IBM_PROJECT_ID → dataplatform.cloud.ibm.com > Project > Manage")
print()

env = read_env()

api_key    = prompt("IBM_API_KEY",    env.get("IBM_API_KEY",    PLACEHOLDER_API),  PLACEHOLDER_API)
project_id = prompt("IBM_PROJECT_ID", env.get("IBM_PROJECT_ID", PLACEHOLDER_PROJ), PLACEHOLDER_PROJ)
region     = prompt("IBM_REGION",     env.get("IBM_REGION",     "us-south"),        "")

if api_key == PLACEHOLDER_API or not api_key:
    print("\n❌ IBM_API_KEY is required. Please re-run this script after getting your key.")
    sys.exit(1)
if project_id == PLACEHOLDER_PROJ or not project_id:
    print("\n❌ IBM_PROJECT_ID is required. Please re-run this script after getting your Project ID.")
    sys.exit(1)

env["IBM_API_KEY"]    = api_key
env["IBM_PROJECT_ID"] = project_id
env["IBM_REGION"]     = region or "us-south"
write_env(env)
print("\n✅ .env file updated.")

# ── Test the connection ───────────────────────────────────────
print("\nTesting Watsonx connection...")
try:
    from ibm_watsonx_ai import Credentials
    from ibm_watsonx_ai.foundation_models import ModelInference
    from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams

    url = f"https://{env['IBM_REGION']}.ml.cloud.ibm.com"
    creds = Credentials(url=url, api_key=api_key)
    model = ModelInference(
        model_id="ibm/granite-3-3-8b-instruct",
        credentials=creds,
        project_id=project_id,
        params={GenParams.MAX_NEW_TOKENS: 50, GenParams.TEMPERATURE: 0.5}
    )
    resp = model.chat(messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user",   "content": "Say: Watsonx connected successfully!"}
    ])
    choices = resp.get("choices") or resp.get("results") or []
    if choices:
        text = choices[0].get("message", {}).get("content") or choices[0].get("text", "")
        print(f"\n✅ Connection successful! Model replied:\n   {text.strip()}")
    else:
        print(f"\n⚠️  Got a response but unexpected shape: {resp}")
except Exception as e:
    print(f"\n❌ Connection failed: {e}")
    print("\nCommon causes:")
    print("  • Wrong IBM_API_KEY (expired or typo)")
    print("  • Wrong IBM_PROJECT_ID (must match your Watsonx project)")
    print("  • Wrong IBM_REGION (try: us-south, eu-de, jp-tok, au-syd)")
    print("  • Your project is not associated with a Watsonx.ai instance")
    sys.exit(1)

print()
print("=" * 60)
print("  All done! Now run:  python app.py")
print("  Then open:          http://localhost:5000")
print("=" * 60)
