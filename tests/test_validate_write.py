#!/usr/bin/env python3
"""Standalone tests for hooks/validate_write.py — run with:

    python3 tests/test_validate_write.py

No dependencies. Each case pipes a synthetic PreToolUse payload into the
hook script and asserts allow (no deny JSON) or deny (with reason match).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(PLUGIN_ROOT, "hooks", "validate_write.py")

PASS = 0
FAIL = 0


def run_hook(payload, env_extra=None):
    env = {**os.environ, **(env_extra or {})}
    proc = subprocess.run(
        [sys.executable, HOOK, PLUGIN_ROOT],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )
    decision = None
    reason = ""
    if proc.stdout.strip():
        try:
            out = json.loads(proc.stdout.strip())
            hso = out.get("hookSpecificOutput", {})
            decision = hso.get("permissionDecision")
            reason = hso.get("permissionDecisionReason", "")
        except json.JSONDecodeError:
            pass
    return decision, reason, proc


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ok: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name} {detail}")


def mcp_payload(cwd, items, tool="mcp__akeneo__akeneo_catalog_products_upsert"):
    return {"tool_name": tool, "tool_input": {"items": items}, "cwd": cwd}


def write_cache(cwd):
    src = os.path.join(PLUGIN_ROOT, "demo", "sample-schema.json")
    with open(src) as f:
        schema = json.load(f)
    schema["source"] = "live"
    schema["fetched_at"] = "2099-01-01T00:00:00Z"  # never stale in tests
    with open(os.path.join(cwd, ".akeneo-schema-cache.json"), "w") as f:
        json.dump(schema, f)


VALID_ITEM = {
    "identifier": "TS-001-BLK-M",
    "family": "tshirts",
    "values": {
        "description": [
            {"locale": "en_US", "scope": "ecommerce", "data": "hello"}
        ],
        "materials": [{"locale": None, "scope": None, "data": ["cotton"]}],
    },
}


def main():
    tmp = tempfile.mkdtemp(prefix="akeneo-hook-test-")
    try:
        # --- no cache, live mode: fail closed ---
        with open(os.path.join(tmp, ".akeneo-mode.json"), "w") as f:
            json.dump({"mode": "live"}, f)
        d, r, _ = run_hook(mcp_payload(tmp, [VALID_ITEM]))
        check("no cache in live mode blocks", d == "deny" and "schema cache" in r, f"got {d!r} {r!r}")

        # --- no cache, demo mode: falls back to bundled demo schema ---
        with open(os.path.join(tmp, ".akeneo-mode.json"), "w") as f:
            json.dump({"mode": "demo"}, f)
        d, r, _ = run_hook(mcp_payload(tmp, [VALID_ITEM]))
        check("demo mode falls back to demo schema (valid passes)", d is None, f"got {d!r} {r!r}")

        # --- cache present: valid payload allowed ---
        write_cache(tmp)
        d, r, _ = run_hook(mcp_payload(tmp, [VALID_ITEM]))
        check("valid payload allowed", d is None, f"got {d!r} {r!r}")

        # --- unknown attribute blocked ---
        bad = json.loads(json.dumps(VALID_ITEM))
        bad["values"]["product_description"] = [
            {"locale": "en_US", "scope": "ecommerce", "data": "x"}
        ]
        d, r, _ = run_hook(mcp_payload(tmp, [bad]))
        check("unknown attribute blocked", d == "deny" and "product_description" in r, f"got {d!r} {r!r}")

        # --- locale on non-localizable attribute blocked ---
        bad = json.loads(json.dumps(VALID_ITEM))
        bad["values"]["materials"] = [
            {"locale": "en_US", "scope": None, "data": ["cotton"]}
        ]
        d, r, _ = run_hook(mcp_payload(tmp, [bad]))
        check("locale on non-localizable blocked", d == "deny" and "not localizable" in r, f"got {d!r} {r!r}")

        # --- missing scope on scopable attribute blocked ---
        bad = json.loads(json.dumps(VALID_ITEM))
        bad["values"]["description"] = [
            {"locale": "en_US", "scope": None, "data": "x"}
        ]
        d, r, _ = run_hook(mcp_payload(tmp, [bad]))
        check("missing scope on scopable blocked", d == "deny" and "scopable" in r, f"got {d!r} {r!r}")

        # --- MCP 'channel' key accepted in place of 'scope' ---
        ok = json.loads(json.dumps(VALID_ITEM))
        ok["values"]["description"] = [
            {"locale": "en_US", "channel": "ecommerce", "data": "x"}
        ]
        d, r, _ = run_hook(mcp_payload(tmp, [ok]))
        check("MCP 'channel' key accepted", d is None, f"got {d!r} {r!r}")

        # --- unknown channel blocked ---
        bad = json.loads(json.dumps(VALID_ITEM))
        bad["values"]["description"] = [
            {"locale": "en_US", "scope": "mobile", "data": "x"}
        ]
        d, r, _ = run_hook(mcp_payload(tmp, [bad]))
        check("unknown channel blocked", d == "deny" and "mobile" in r, f"got {d!r} {r!r}")

        # --- bad select option blocked ---
        bad = json.loads(json.dumps(VALID_ITEM))
        bad["values"]["materials"] = [
            {"locale": None, "scope": None, "data": ["kevlar"]}
        ]
        d, r, _ = run_hook(mcp_payload(tmp, [bad]))
        check("unknown select option blocked", d == "deny" and "kevlar" in r, f"got {d!r} {r!r}")

        # --- unknown family blocked ---
        bad = json.loads(json.dumps(VALID_ITEM))
        bad["family"] = "sneakers"
        d, r, _ = run_hook(mcp_payload(tmp, [bad]))
        check("unknown family blocked", d == "deny" and "sneakers" in r, f"got {d!r} {r!r}")

        # --- bulk threshold ---
        many = [json.loads(json.dumps(VALID_ITEM)) for _ in range(150)]
        d, r, _ = run_hook(mcp_payload(tmp, many))
        check("bulk over threshold blocked", d == "deny" and "150" in r, f"got {d!r} {r!r}")
        d, r, _ = run_hook(mcp_payload(tmp, many), env_extra={"AKENEO_ALLOW_BULK": "1"})
        check("bulk allowed with AKENEO_ALLOW_BULK=1", d is None, f"got {d!r} {r!r}")

        # --- non-upsert MCP tools always allowed ---
        d, r, _ = run_hook({
            "tool_name": "mcp__akeneo__akeneo_catalog_products_get",
            "tool_input": {"search": "{}"},
            "cwd": tmp,
        })
        check("read tool allowed", d is None, f"got {d!r} {r!r}")

        # --- non-product upserts get bulk check only ---
        d, r, _ = run_hook(mcp_payload(
            tmp,
            [{"code": "totally_new_attr", "type": "pim_catalog_text"}],
            tool="mcp__akeneo__akeneo_catalog_attributes_upsert",
        ))
        check("attribute upsert not value-validated", d is None, f"got {d!r} {r!r}")

        # --- Bash: Akeneo write with cache present allowed ---
        bash = {
            "tool_name": "Bash",
            "tool_input": {"command": "curl -X PATCH https://pim.example.com/api/rest/v1/products/TS-001 -d @payload.json"},
            "cwd": tmp,
        }
        d, r, _ = run_hook(bash)
        check("bash write with cache allowed", d is None, f"got {d!r} {r!r}")

        # --- Bash: Akeneo write without cache blocked ---
        os.remove(os.path.join(tmp, ".akeneo-schema-cache.json"))
        with open(os.path.join(tmp, ".akeneo-mode.json"), "w") as f:
            json.dump({"mode": "live"}, f)
        d, r, _ = run_hook(bash)
        check("bash write without cache blocked", d == "deny" and "schema cache" in r, f"got {d!r} {r!r}")

        # --- Bash: unrelated command allowed even without cache ---
        d, r, _ = run_hook({
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la && git status"},
            "cwd": tmp,
        })
        check("unrelated bash allowed", d is None, f"got {d!r} {r!r}")

        # --- Bash: GET to products endpoint allowed (read) ---
        d, r, _ = run_hook({
            "tool_name": "Bash",
            "tool_input": {"command": "curl https://pim.example.com/api/rest/v1/products?limit=10"},
            "cwd": tmp,
        })
        check("bash GET allowed", d is None, f"got {d!r} {r!r}")

        # --- malformed stdin: allow (never crash the session) ---
        proc = subprocess.run(
            [sys.executable, HOOK, PLUGIN_ROOT],
            input="not json",
            capture_output=True,
            text=True,
        )
        check("malformed stdin exits 0", proc.returncode == 0, f"rc={proc.returncode}")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
