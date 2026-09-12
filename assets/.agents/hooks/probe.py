#!/usr/bin/env python3
"""Lifecycle-hook contract probe.

Answers three questions that no amount of reading the docs resolves:
  1. Does PreInvocation fire inside subagent contexts?  (compare conversationId
     across records, and whether a record appears while a subagent is running)
  2. What is the real payload shape / CWD resolution under Windows `cmd /c`?
  3. Is the intent gate feasible -- i.e. can we recover the user's prompt from
     transcriptPath, given PreInvocation does not carry the prompt text?

Read-only and side-effect free apart from appending to state/probe.jsonl.
Always prints a safe no-op JSON directive so the agent loop is never altered.

Delete this file (and its hooks.json entry) once the answers are recorded in
docs/omo-port/MAPPING.md.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Resolve state dir from this file, never from CWD -- CWD is one of the unknowns.
LOG_PATH = Path(__file__).resolve().parent.parent / "state" / "probe.jsonl"

TRANSCRIPT_TAIL_BYTES = 65536
PREVIEW_CHARS = 400

# Per-event safe no-op. Stop mirrors the documented Recipe 4 shape rather than
# relying on "omitted decision permits stop".
SAFE_OUTPUT = {
    "stop": {"decision": "stop"},
}


def transcript_probe(payload):
    """Can we recover the last user message from the transcript? (question 3)"""
    path = payload.get("transcriptPath")
    if not path:
        return {"status": "no-transcriptPath-in-payload"}
    try:
        p = Path(path)
        if not p.is_file():
            return {"status": "path-not-a-file", "path": path}
        size = p.stat().st_size
        with p.open("rb") as fh:
            if size > TRANSCRIPT_TAIL_BYTES:
                fh.seek(-TRANSCRIPT_TAIL_BYTES, os.SEEK_END)
            tail = fh.read().decode("utf-8", errors="replace")

        lines = [ln for ln in tail.splitlines() if ln.strip()]
        # A tail read may slice the first line mid-record; drop it if unparseable.
        records = []
        for ln in lines:
            try:
                records.append(json.loads(ln))
            except ValueError:
                continue

        return {
            "status": "read",
            "size_bytes": size,
            "lines_in_tail": len(lines),
            "parsed_records": len(records),
            # The shapes we need in order to write intent_gate.py later.
            "last_record_keys": sorted(records[-1].keys()) if records else [],
            "last_record_preview": json.dumps(records[-1])[:PREVIEW_CHARS] if records else "",
            "distinct_keysets": sorted({",".join(sorted(r.keys())) for r in records[-25:]}),
        }
    except Exception as exc:  # never let the probe break the loop
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def main():
    event = sys.argv[1] if len(sys.argv) > 1 else "unknown"

    raw = ""
    payload = None
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else None
    except Exception:
        payload = None

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "cwd": os.getcwd(),
        "argv": sys.argv,
        "stdin_bytes": len(raw),
        "payload_keys": sorted(payload.keys()) if isinstance(payload, dict) else None,
        "payload": payload if payload is not None else {"_raw": raw[:PREVIEW_CHARS]},
    }

    if event == "preinvocation" and isinstance(payload, dict):
        record["transcript"] = transcript_probe(payload)

    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        # stdout is reserved for JSON directives; diagnostics go to stderr.
        print(f"probe: could not write log: {exc}", file=sys.stderr)

    print(json.dumps(SAFE_OUTPUT.get(event, {})))


if __name__ == "__main__":
    main()
