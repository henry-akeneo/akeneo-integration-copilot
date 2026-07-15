#!/usr/bin/env python3
"""SessionStart hook: detect live vs demo mode and write the mode marker.

Live mode requires the Akeneo connection env vars. AKENEO_BASE_URL is
accepted as an alias for AKENEO_API_URL. The marker file
(.akeneo-mode.json in the project root) is a *hint* recorded at session
start — consumers (the agent, validate_write.py) must re-check the
environment at runtime, since env state can change mid-session.

If credentials are absent, the hook scans the project shallowly for .env
files that mention AKENEO_ keys and points the user at them instead of
silently going demo. Stdout is added to Claude's context.
"""
import json
import os
import sys

URL_VARS = ["AKENEO_API_URL", "AKENEO_BASE_URL"]
OTHER_VARS = [
    "AKENEO_CLIENT_ID",
    "AKENEO_CLIENT_SECRET",
    "AKENEO_USERNAME",
    "AKENEO_PASSWORD",
]

SKIP_DIRS = {".git", "node_modules", "vendor", "__pycache__", ".venv", "venv", "dist", "build"}


def missing_vars():
    missing = []
    if not any(os.environ.get(v) for v in URL_VARS):
        missing.append("AKENEO_API_URL (or AKENEO_BASE_URL)")
    missing.extend(v for v in OTHER_VARS if not os.environ.get(v))
    return missing


def find_env_files(cwd, max_depth=2):
    """Shallow scan for .env-style files that mention AKENEO_ keys."""
    hits = []
    base_depth = cwd.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(cwd):
        if root.rstrip(os.sep).count(os.sep) - base_depth >= max_depth:
            dirs[:] = []
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if not name.startswith(".env"):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, errors="ignore") as f:
                    if "AKENEO_" in f.read(65536):
                        hits.append(os.path.relpath(path, cwd))
            except OSError:
                continue
        if len(hits) >= 5:
            break
    return hits


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}
    cwd = payload.get("cwd") or os.getcwd()

    missing = missing_vars()
    mode = "demo" if missing else "live"

    marker = {"mode": mode, "missing_env_vars": missing, "note": "hint only — runtime env wins"}
    try:
        with open(os.path.join(cwd, ".akeneo-mode.json"), "w") as f:
            json.dump(marker, f, indent=2)
    except OSError:
        pass

    if mode == "live":
        msg = (
            "akeneo-integration-copilot: LIVE mode — Akeneo connection env vars "
            "are set; the agent will fetch schema from the live instance via MCP."
        )
        if not os.environ.get("AKENEO_API_URL") and os.environ.get("AKENEO_BASE_URL"):
            msg += (
                " Note: found AKENEO_BASE_URL but not AKENEO_API_URL — treating "
                "them as equivalent, but the bundled MCP server config reads "
                "AKENEO_API_URL; run `export AKENEO_API_URL=\"$AKENEO_BASE_URL\"` "
                "before starting Claude Code so the MCP connection works too."
            )
        print(msg)
    else:
        msg = (
            "akeneo-integration-copilot: DEMO mode — missing env vars: "
            f"{', '.join(missing)}. The agent will use the bundled demo schema "
            "(demo/sample-schema.json). The 'akeneo' MCP server may show as "
            "failed in /mcp; that is expected in demo mode."
        )
        env_files = find_env_files(cwd)
        if env_files:
            msg += (
                " Heads up: AKENEO_ credentials appear to exist in "
                f"{', '.join(env_files)} — they are not exported to this "
                "session. Export them (or pass --env-file to scaffolded "
                "scripts) to enable live mode."
            )
        print(msg)


if __name__ == "__main__":
    main()
