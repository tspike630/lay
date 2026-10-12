# -*- coding: utf-8 -*-
"""JSON stdin/stdout wrapper used by the terminal's 缠论 screen."""

from __future__ import print_function

import json
import sys

from engine import analyze, sample_bars


def _load_bars():
    if len(sys.argv) > 1 and sys.argv[1] == "--sample":
        return sample_bars()
    payload = json.load(sys.stdin)
    if isinstance(payload, dict):
        return payload.get("bars") or []
    return payload


def main():
    result = analyze(_load_bars())
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 — surface a JSON error to the UI
        json.dump({"error": str(exc)}, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        raise SystemExit(1)
