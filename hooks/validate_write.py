#!/usr/bin/env python3
"""PreToolUse write-guard for Akeneo product data.

Gates two write paths:
  1. Akeneo MCP upsert tools (mcp__*akeneo*...upsert*): validates the
     structured payload against the schema cache — attribute codes,
     locale/scope combinations, select options, family codes, bulk size.
  2. Bash commands that look like Akeneo REST writes: coarse guard —
     blocked unless a schema cache exists (payloads inside shell commands
     can't be parsed reliably, so the gate is "discovery ran first").

Fail-closed policy: in live mode, product writes are blocked when
.akeneo-schema-cache.json is missing. In demo mode the bundled
demo/sample-schema.json is used as fallback schema.

Blocking is done via PreToolUse permissionDecision JSON on stdout (exit 0).
"""
import json
import os
import re
import sys
import time

BULK_THRESHOLD = int(os.environ.get("AKENEO_BULK_THRESHOLD", "100"))
STALE_AFTER_SECONDS = 24 * 3600

BASH_WRITE_RE = re.compile(
    r"/api/rest/v1/(products|product-models|product-uuid)", re.IGNORECASE
)
BASH_WRITE_VERB_RE = re.compile(
    r"(-X\s*(PATCH|POST|PUT|DELETE)|--request\s*(PATCH|POST|PUT|DELETE)"
    r"|requests\.(patch|post|put|delete)|\.patch\(|\.post\(|\.put\(|\.delete\()",
    re.IGNORECASE,
)


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def allow():
    sys.exit(0)


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def load_schema(cwd, plugin_root):
    """Return (schema, error_message). Fail closed in live mode."""
    cache_path = os.path.join(cwd, ".akeneo-schema-cache.json")
    schema = load_json(cache_path)
    if schema is not None:
        fetched = schema.get("fetched_at")
        if fetched:
            try:
                import datetime
                dt = datetime.datetime.fromisoformat(fetched.replace("Z", "+00:00"))
                age = time.time() - dt.timestamp()
                if age > STALE_AFTER_SECONDS:
                    print(
                        "akeneo write-guard: schema cache is older than 24h — "
                        "consider re-running discovery.",
                        file=sys.stderr,
                    )
            except ValueError:
                pass
        return schema, None

    mode_marker = load_json(os.path.join(cwd, ".akeneo-mode.json")) or {}
    if mode_marker.get("mode") == "demo" and plugin_root:
        demo = load_json(os.path.join(plugin_root, "demo", "sample-schema.json"))
        if demo is not None:
            return demo, None

    return None, (
        "Blocked: no schema cache found (.akeneo-schema-cache.json). "
        "Run schema discovery first — the akeneo-integration-engineer "
        "agent's DISCOVER step writes this file. Writes to product data "
        "are not allowed against an unverified schema."
    )


def iter_items(tool_input):
    """Find the list of product payloads inside an MCP upsert tool_input."""
    if not isinstance(tool_input, dict):
        return []
    for key in ("items", "products", "product_models", "data", "payload"):
        val = tool_input.get(key)
        if isinstance(val, str):
            parsed = None
            try:
                parsed = json.loads(val)
            except (json.JSONDecodeError, ValueError):
                pass
            if isinstance(parsed, list):
                val = parsed
            elif isinstance(parsed, dict):
                val = [parsed]
        if isinstance(val, list) and all(isinstance(i, dict) for i in val):
            return val
        if isinstance(val, dict):
            return [val]
    if "values" in tool_input or "identifier" in tool_input or "uuid" in tool_input:
        return [tool_input]
    return []


def validate_item(item, schema, line_no):
    errors = []
    attributes = schema.get("attributes", {})
    families = schema.get("families", {})
    locales = set(schema.get("locales", []))
    channels = {c["code"] for c in schema.get("channels", []) if isinstance(c, dict)}

    family = item.get("family")
    if family and families and family not in families:
        errors.append(f"item {line_no}: unknown family '{family}'")

    values = item.get("values")
    if not isinstance(values, dict):
        return errors

    for attr_code, entries in values.items():
        attr = attributes.get(attr_code)
        if attr is None:
            errors.append(
                f"item {line_no}: unknown attribute '{attr_code}' — "
                "not in the fetched schema"
            )
            continue
        if not isinstance(entries, list):
            errors.append(f"item {line_no}: values for '{attr_code}' must be a list")
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            locale = entry.get("locale")
            # REST payloads use 'scope'; Akeneo MCP tools use 'channel'.
            scope = entry.get("scope", entry.get("channel"))
            if attr.get("localizable") and not locale:
                errors.append(
                    f"item {line_no}: '{attr_code}' is localizable but no locale given"
                )
            if not attr.get("localizable") and locale:
                errors.append(
                    f"item {line_no}: '{attr_code}' is not localizable but "
                    f"locale '{locale}' given (422 guaranteed)"
                )
            if attr.get("scopable") and not scope:
                errors.append(
                    f"item {line_no}: '{attr_code}' is scopable but no scope/channel given"
                )
            if not attr.get("scopable") and scope:
                errors.append(
                    f"item {line_no}: '{attr_code}' is not scopable but "
                    f"scope '{scope}' given (422 guaranteed)"
                )
            if locale and locales and locale not in locales:
                errors.append(
                    f"item {line_no}: locale '{locale}' not enabled on this instance"
                )
            if scope and channels and scope not in channels:
                errors.append(
                    f"item {line_no}: channel '{scope}' does not exist"
                )
            options = attr.get("options")
            if options:
                data = entry.get("data")
                codes = data if isinstance(data, list) else [data]
                for code in codes:
                    if isinstance(code, str) and code not in options:
                        errors.append(
                            f"item {line_no}: '{code}' is not an option of "
                            f"'{attr_code}' (options: {', '.join(options[:10])})"
                        )
    return errors


def handle_mcp(tool_name, tool_input, cwd, plugin_root):
    if "upsert" not in tool_name:
        allow()

    schema, err = load_schema(cwd, plugin_root)
    if schema is None:
        deny(err)

    items = iter_items(tool_input)

    if len(items) > BULK_THRESHOLD and os.environ.get("AKENEO_ALLOW_BULK") != "1":
        deny(
            f"Blocked: bulk write of {len(items)} items exceeds the threshold "
            f"of {BULK_THRESHOLD}. Set AKENEO_ALLOW_BULK=1 to permit, or batch "
            "the write."
        )

    # Full payload validation only makes sense for product-data writes.
    if not re.search(r"products?(_models?)?_upsert", tool_name):
        allow()

    errors = []
    for idx, item in enumerate(items, start=1):
        errors.extend(validate_item(item, schema, idx))

    if errors:
        shown = errors[:15]
        more = f" (+{len(errors) - 15} more)" if len(errors) > 15 else ""
        deny(
            "Blocked: payload does not match the fetched Akeneo schema:\n- "
            + "\n- ".join(shown)
            + more
            + "\nFix the payload against .akeneo-schema-cache.json before retrying."
        )
    allow()


def handle_bash(tool_input, cwd, plugin_root):
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not (BASH_WRITE_RE.search(command) and BASH_WRITE_VERB_RE.search(command)):
        allow()

    schema, err = load_schema(cwd, plugin_root)
    if schema is None:
        deny(
            "Blocked: this command looks like an Akeneo product write, and "
            + err
        )
    allow()


def main():
    plugin_root = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        allow()

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    cwd = payload.get("cwd") or os.getcwd()

    if tool_name == "Bash":
        handle_bash(tool_input, cwd, plugin_root)
    elif tool_name.startswith("mcp__") and "akeneo" in tool_name.lower():
        handle_mcp(tool_name.lower(), tool_input, cwd, plugin_root)
    allow()


if __name__ == "__main__":
    main()
