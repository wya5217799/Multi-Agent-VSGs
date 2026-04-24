"""Verify whether Claude Desktop new sessions default MCP tools to enabled.

Run after: restart Claude Desktop, enable all tools in UI, open a NEW session.
Compares the most-recent session JSON against prior state to see if the new
default is all-true (root cause fixed) or falls back to all-false (not fixed).
"""
import json
import glob
import os
import sys

ROOT = r"C:/Users/27443/AppData/Roaming/Claude/local-agent-mode-sessions"
TARGETS = [
    "simulink-tools",
    "Claude in Chrome",
    "PDF Tools - Fill, Analyze, Extract, View",
]


def summarize(path: str) -> dict:
    try:
        data = json.load(open(path, "r", encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc)}
    tools = data.get("enabledMcpTools", {})
    result = {"lastActivityAt": data.get("lastActivityAt")}
    for srv in TARGETS:
        prefix = f"local:{srv}:"
        entries = [v for k, v in tools.items() if k.startswith(prefix)]
        if not entries:
            result[srv] = "absent"
        elif all(entries):
            result[srv] = f"GOOD ({len(entries)} true)"
        elif not any(entries):
            result[srv] = f"BAD ({len(entries)} false)"
        else:
            t = sum(1 for v in entries if v)
            result[srv] = f"MIXED ({t}T/{len(entries) - t}F)"
    return result


def main() -> int:
    files = [
        f for f in glob.glob(os.path.join(ROOT, "**", "local_*.json"), recursive=True)
        if ".bak" not in f
    ]
    if not files:
        print("No session files found.")
        return 1
    files.sort(key=lambda p: summarize(p).get("lastActivityAt") or 0, reverse=True)
    top = files[:3]
    for p in top:
        print(f"\n{os.path.basename(p)}")
        for k, v in summarize(p).items():
            print(f"  {k}: {v}")
    newest = summarize(top[0])
    verdict_ok = all(
        str(newest.get(srv, "")).startswith("GOOD") or newest.get(srv) == "absent"
        for srv in TARGETS
    )
    print("\nROOT-CAUSE VERDICT:", "FIXED" if verdict_ok else "NOT FIXED (new session still defaults to disabled)")
    return 0 if verdict_ok else 2


if __name__ == "__main__":
    sys.exit(main())
