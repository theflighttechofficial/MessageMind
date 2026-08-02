# WhatsApp Notification Router

HackerRank Orchestrate — Message Notification Router submission.

## Setup

```
pip install ollama
ollama pull mistral
```

Make sure Ollama is running locally (`ollama serve`, or the Ollama app).

## Run

```
python main.py
```

No API key needed — routing runs entirely locally against Ollama's Mistral model.

Output is written to `output.csv` in the repo root.

## File layout

```
.
├── main.py              ← entry point, run this
├── code/
│   ├── context_loader.py   ← loads all dataset CSVs, builds evidence index
│   └── router.py           ← Ollama (Mistral) routing logic
└── dataset/
    ├── messages.csv
    ├── users.csv
    ├── groups.csv
    ├── group_members.csv
    ├── business_accounts.csv
    ├── user_business_history.csv
    ├── message_history.csv
    ├── message_events.csv
    ├── images.csv
    ├── voice_notes.csv
    ├── daily_notification_summary.csv
    └── media/
```

## What it does

1. Loads all 12 context CSVs at startup into fast lookup dicts
2. For each incoming message, builds a structured context block containing:
   - User behavior (opens, dismissals, reports, DND window)
   - Group metadata and user's relationship to that group (mute state, read rate)
   - Business metadata (verified status, domain match, report count)
   - User-business relationship (opted-in, opted-out, order history)
   - Top 4 historical evidence messages ranked by relevance (same sender, same business, same group, reported/muted signals)
3. Sends message + context to Ollama's Mistral model (local) with a detailed routing prompt
4. Validates output against allowed action/type values
5. Writes output.csv with: message_id, action, message_type, reason, confidence, evidence_message_ids
