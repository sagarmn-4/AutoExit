"""
generate_token.py
Generates a fresh Kite Connect access token and updates it in the .env file automatically.
"""

import os
import sys
from pathlib import Path

# Ensure project root (one level above this scripts/ directory) is on sys.path
# so we can import `utils.*` reliably whether this script is executed via
# `python -m scripts.generate_token` or by absolute/relative path.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kiteconnect import KiteConnect
from utils.config import get_env_var
from utils.common import ROOT

# Read credentials using centralized helper (falls back to env)
api_key = get_env_var("KITE_API_KEY")
api_secret = get_env_var("KITE_API_SECRET")

if not api_key or not api_secret:
    raise ValueError("❌ Missing KITE_API_KEY or KITE_API_SECRET in environment or .env file")

kite = KiteConnect(api_key=api_key)

# Step 1: Generate login URL
print(f"\n🔗 Login URL:\n{kite.login_url()}")
request_token = input("\nPaste the request_token from redirected URL here: ").strip()

# Step 2: Generate new session
try:
    data = kite.generate_session(request_token, api_secret=api_secret)
    access_token = data["access_token"]
    print(f"\n✅ Access Token generated successfully:\n{access_token}")

    # Step 3: Update .env file in place
    env_path = os.path.join(ROOT, ".env")

    lines = []
    found = False

    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for i, line in enumerate(lines):
            if line.startswith("KITE_ACCESS_TOKEN="):
                lines[i] = f"KITE_ACCESS_TOKEN={access_token}\n"
                found = True
                break

    if not found:
        lines.append(f"\nKITE_ACCESS_TOKEN={access_token}\n")

    with open(env_path, "w") as f:
        f.writelines(lines)

    print("🧩 .env updated successfully with new access token.")

except Exception as e:
    print(f"❌ Error generating access token: {e}")
