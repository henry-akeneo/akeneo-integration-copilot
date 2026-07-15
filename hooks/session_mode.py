#!/usr/bin/env python3
"""SessionStart hook: detect live vs demo mode and write the mode marker.

Live mode requires all AKENEO_* connection env vars. The marker file
(.akeneo-mode.json in the project root) is read by the agent's DISCOVER
step and by validate_write.py. Stdout is added to Claude's context.
"""
import json
import os
import sys

REQUIRED_VARS = [
    "AKENEO_API_URL",
    "AKENEO_CLIENT_ID",
    "AKENEO_CLIENT_SECRET",
    "AKENEO_USERNAME",
    "AKENEO_PASSWORD",
]


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}
    cwd = payload.get("cwd") or os.getcwd()

    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    mode = "demo" if missing else "live"

    marker = {"mode": mode, "missing_env_vars": missing}
    try:
        with open(os.path.join(cwd, ".akeneo-mode.json"), "w") as f:
            json.dump(marker, f, indent=2)
    except OSError:
        pass

    if mode == "live":
        print(
            "akeneo-integration-copilot: LIVE mode — Akeneo connection env vars "
            "are set; the agent will fetch schema from the live instance via MCP."
        )
    else:
        print(
            "akeneo-integration-copilot: DEMO mode — missing env vars: "
            f"{', '.join(missing)}. The agent will use the bundled demo schema "
            "(demo/sample-schema.json). The 'akeneo' MCP server may show as "
            "failed in /mcp; that is expected in demo mode."
        )


if __name__ == "__main__":
    main()
