"""
main.py - WhatsApp Notification Router
========================================
Reads dataset/, uses Groq API (Mixtral), writes output.csv.
110 messages done in under 3 minutes.

SETUP:
    pip install groq
    set GROQ_API_KEY=your-key-here      (Windows)
    export GROQ_API_KEY=your-key-here   (Mac/Linux)

RUN:
    python main.py

No Ollama needed.
"""

import csv
import os
import sys
import time
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE    = Path(__file__).parent if (Path(__file__).parent / "dataset").exists() \
          else Path(__file__).parent.parent
DATASET = BASE / "dataset"
OUTPUT  = BASE / "output.csv"

# ── Add code/ to path ─────────────────────────────────────────────────────────
code_dir = Path(__file__).parent / "code" \
           if not (Path(__file__).parent / "context_loader.py").exists() \
           else Path(__file__).parent
sys.path.insert(0, str(code_dir))

# ── Load .env (no external dependency) ──────────────────────────────────────
def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

load_dotenv(BASE / ".env")

OUTPUT_COLUMNS = ["message_id", "action", "message_type", "reason", "confidence", "evidence_message_ids"]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(rows: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    # ── Check groq installed ──────────────────────────────────────────────────
    try:
        from groq import Groq
    except ImportError:
        print("ERROR: groq not installed. Run: pip install groq")
        sys.exit(1)

    # ── Check Groq API key ────────────────────────────────────────────────────
    groq_api_key = os.environ.get("GROQ_API_KEY")
    if not groq_api_key:
        print("ERROR: GROQ_API_KEY environment variable not set.")
        print("  Windows:     set GROQ_API_KEY=your-key-here")
        print("  Mac / Linux: export GROQ_API_KEY=your-key-here")
        sys.exit(1)

    # ── Check dataset ─────────────────────────────────────────────────────────
    messages_path = DATASET / "messages.csv"
    if not messages_path.exists():
        print(f"ERROR: {messages_path} not found.")
        sys.exit(1)

    # ── Import local modules ──────────────────────────────────────────────────
    try:
        from context_loader import load_all, build_context_block
        from router import route_message
    except ImportError:
        from code.context_loader import load_all, build_context_block
        from code.router import route_message

    # ── Load data ─────────────────────────────────────────────────────────────
    print("Loading dataset...")
    messages = read_csv(messages_path)
    ctx = load_all(DATASET)

    print(f"  {len(messages)} messages to route")
    print(f"  {len(ctx['users'])} users")
    print(f"  {len(ctx['groups'])} groups")
    print(f"  {len(ctx['businesses'])} businesses")
    print(f"  {sum(len(v) for v in ctx['history_by_user'].values())} history rows")
    print(f"  {sum(len(v) for v in ctx['events_by_user'].values())} event rows")

    # ── Init Groq client ──────────────────────────────────────────────────────
    client = Groq(api_key=groq_api_key)
    print(f"\nRouting {len(messages)} messages via Groq (Mixtral-8x7b)...\n")

    # ── Route every message ───────────────────────────────────────────────────
    results = []
    errors  = 0

    for i, row in enumerate(messages, 1):
        msg_id = row.get("message_id", f"row_{i}")
        print(f"  [{i:>3}/{len(messages)}] {msg_id} ...", end=" ", flush=True)

        try:
            context_block, evidence_ids = build_context_block(row, ctx)
            result = route_message(row, context_block, evidence_ids, client)
            results.append(result)
            ev_display = result["evidence_message_ids"][:35] \
                         if result["evidence_message_ids"] != "none" else "none"
            print(f"-> {result['action']:<6} [{result['message_type']:<16}] "
                  f"conf={result['confidence']:.2f}  ev={ev_display}", flush=True)
        except Exception as e:
            errors += 1
            print(f"-> ERROR: {e}", flush=True)
            results.append({
                "message_id":           msg_id,
                "action":               "digest",
                "message_type":         "unknown",
                "reason":               f"Routing error: {e}",
                "confidence":           0.1,
                "evidence_message_ids": "none",
            })

        # small delay to stay within Groq free tier (30 req/min)
        if i < len(messages):
            time.sleep(0.3)

    # ── Write output.csv ──────────────────────────────────────────────────────
    write_csv(results, OUTPUT)

    print(f"\n{'='*60}")
    print(f"Done. {len(results)} rows written to {OUTPUT}")
    if errors:
        print(f"WARNING: {errors} messages fell back to digest due to errors.")

    from collections import Counter
    actions = Counter(r["action"]       for r in results)
    types_  = Counter(r["message_type"] for r in results)

    print(f"\nAction breakdown:")
    print(f"  notify : {actions['notify']}")
    print(f"  digest : {actions['digest']}")
    print(f"  mute   : {actions['mute']}")
    print(f"\nMessage type breakdown:")
    for t, c in sorted(types_.items(), key=lambda x: -x[1]):
        print(f"  {t:<20}: {c}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
