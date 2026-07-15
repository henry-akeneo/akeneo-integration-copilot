#!/usr/bin/env python3
"""PreToolUse write-guard for Akeneo product data.

Gates three write paths:
  1. Akeneo MCP product-data upserts (products / product models / assets /
     reference-entity records): validates the structured payload against
     the schema cache — attribute codes, locale/scope combinations, select
     options, family codes, bulk size.
  2. Akeneo MCP *structure* upserts (attributes, families, channels,
     categories, ...): these mutate the schema itself — strictly more
     dangerous than a bad product write, and payload validation against a
     schema cache is meaningless for the thing that *defines* the schema.
     Blocked on live instances unless AKENEO_ALLOW_STRUCTURE=1.
  3. Bash commands that look like Akeneo REST writes: coarse guard —
     blocked unless a schema cache exists (payloads inside shell commands
     can't be parsed reliably, so the gate is "discovery ran first").

Fail-closed policy: in live mode, product writes are blocked when
.akeneo-schema-cache.json is missing — and blocked when the cache is
demo-sourced (source: "demo"), since validating live data against the
demo fixture guarantees false results. In demo mode the bundled
demo/sample-schema.json is used as fallback schema.

Mode is determined from the environment at call time (credentials present
=> live); the .akeneo-mode.json marker is only a fallback hint, because a
session-start snapshot of the environment can go stale.

Blocking is done via PreToolUse permissionDecision JSON on stdout (exit 0).
"""
import json
import os
import re
import sys
import time

BULK_THRESHOLD = int(os.environ.get("AKENEO_BULK_THRESHOLD", "100"))
STALE_AFTER_SECONDS = 24 * 3600

# Upserts that write *data* (validated field-by-field below). Any other
# akeneo upsert tool mutates PIM structure and is gated wholesale — this
# is deliberately a data-allowlist, not a structure-blocklist, so tools
# added to the MCP server later fail closed.
DATA_UPSERT_RE = re.compile(
    r"(products?(_models?)?|assets_assets|ref_entity_records)_upsert"
)

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


def runtime_mode(cwd):
    """Live/demo decided by the environment NOW; marker file is a hint only."""
    has_url = os.environ.get("AKENEO_API_URL") or os.environ.get("AKENEO_BASE_URL")
    others = ["AKENEO_CLIENT_ID", "AKENEO_CLIENT_SECRET", "AKENEO_USERNAME", "AKENEO_PASSWORD"]
    if has_url and all(os.environ.get(v) for v in others):
        return "live"
    marker = load_json(os.path.join(cwd, ".akeneo-mode.json")) or {}
    # Fail closed: only an explicit demo marker relaxes the guard.
    return "demo" if marker.get("mode") == "demo" else "live"


def load_schema(cwd, plugin_root):
    """Return (schema, error_message). Fail closed in live mode."""
    mode = runtime_mode(cwd)
    cache_path = os.path.join(cwd, ".akeneo-schema-cache.json")
    schema = load_json(cache_path)
    if schema is not None and mode == "live" and schema.get("source") == "demo":
        return None, (
            "Blocked: .akeneo-schema-cache.json is demo-sourced (source: "
            "\"demo\") but Akeneo credentials are present, so this is a live "
            "write. Validating live data against the demo fixture would be "
            "meaningless. Re-run schema discovery against the live instance "
            "(the agent's DISCOVER step rebuilds the cache with source: "
            "\"live\")."
        )
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

    if mode == "demo" and plugin_root:
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


def check_bulk(items):
    if len(items) > BULK_THRESHOLD and os.environ.get("AKENEO_ALLOW_BULK") != "1":
        deny(
            f"Blocked: bulk write of {len(items)} items exceeds the threshold "
            f"of {BULK_THRESHOLD}. Set AKENEO_ALLOW_BULK=1 to permit, or batch "
            "the write."
        )


def handle_mcp(tool_name, tool_input, cwd, plugin_root):
    if "upsert" not in tool_name:
        allow()

    if not DATA_UPSERT_RE.search(tool_name):
        # Structure write: mutates the schema itself, so it can't be
        # validated against the schema cache — gate it wholesale on live.
        if runtime_mode(cwd) == "live" and os.environ.get("AKENEO_ALLOW_STRUCTURE") != "1":
            deny(
                f"Blocked: '{tool_name}' modifies PIM *structure* (attributes, "
                "families, channels, categories, ...), not product data. "
                "Structure changes on a live instance are gated: confirm with "
                "the user, then set AKENEO_ALLOW_STRUCTURE=1 to permit for "
                "this session. After any structure change, re-run schema "
                "discovery — the cached schema is stale."
            )
        check_bulk(iter_items(tool_input))
        allow()

    schema, err = load_schema(cwd, plugin_root)
    if schema is None:
        deny(err)

    items = iter_items(tool_input)
    check_bulk(items)

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
