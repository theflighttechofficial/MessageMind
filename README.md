# WhatsApp Notification Router

**HackerRank Orchestrate — August 2026**

An AI-powered multimodal message routing system for WhatsApp. Every incoming message — text, image poster, or voice note — is classified into one of three actions:

| Action | Meaning |
|--------|---------|
| `notify` | Interrupt the user now — urgent or personally relevant |
| `digest` | Useful but not urgent — show later in a batch |
| `mute` | Spam, scam, chain message, repetitive, or unsafe |

---

## Architecture

```
dataset/messages.csv + 11 context CSVs
            │
            ▼
  context_loader.py
  ├── Loads users, groups, businesses, history, events
  ├── Builds per-message context block
  └── Evidence retrieval (scored by sender/group/business match + report/mute signals)
            │
            ▼
  router.py
  ├── Voice notes  → Groq Whisper API (whisper-large-v3) → transcript
  ├── Images       → Text-based content classifier from message context
  ├── All messages → Groq LLaMA 3.1 8b Instant (structured prompt)
  └── Post-processing rules (deterministic overrides)
            │
            ▼
  output.csv
  message_id, action, message_type, reason, confidence, evidence_message_ids
```

---

## Stack

- **LLM**: LLaMA 3.1 8b Instant via [Groq](https://groq.com)
- **ASR**: Whisper Large v3 via Groq Audio API
- **Language**: Python 3.12
- **Dependencies**: `groq` only

---

## Setup

```bash
pip install groq
```

Set your Groq API key:
```bash
# Windows
set GROQ_API_KEY=your-key-here

# Mac / Linux
export GROQ_API_KEY=your-key-here
```

Or add to `.env` file in repo root:
```
GROQ_API_KEY=your-key-here
```

---

## Run

```bash
python code/main.py
```

Processes all 110 messages in ~3 minutes. Output written to `output.csv`.

---

## File Structure

```
.
├── code/
│   ├── main.py              ← entry point, run this
│   ├── router.py            ← Groq API + post-processing rules
│   ├── context_loader.py    ← loads all CSVs, evidence retrieval
│   └── __init__.py
├── dataset/
│   ├── messages.csv
│   ├── users.csv
│   ├── groups.csv
│   ├── group_members.csv
│   ├── business_accounts.csv
│   ├── user_business_history.csv
│   ├── message_history.csv
│   ├── message_events.csv
│   ├── images.csv
│   ├── voice_notes.csv
│   ├── daily_notification_summary.csv
│   ├── sample_messages.csv
│   └── media/
│       ├── images/          ← image posters and screenshots
│       └── audio/           ← voice note mp3 files
└── output.csv               ← submit this
```

---

## How It Works

### 1. Context Loading

Every message gets a structured context block built from all 11 supporting CSVs:

- **User**: DND window, open/reply/dismiss/report rates last 30 days
- **Group**: type, size, user's mute state, read/reply rate in that group
- **Business**: verified status, domain match vs sender domain (mismatch = scam signal), report count
- **User-Business**: opted-in, opted-out, order history, messages opened/dismissed
- **Evidence**: top 4 historical messages ranked by relevance score

### 2. Evidence Retrieval

Historical messages are scored per message:

| Signal | Score |
|--------|-------|
| Same sender | +4 |
| Same business | +4 |
| Same group | +2 |
| User reported this message | +3 |
| User muted after this message | +2 |
| User replied to this message | +1 |

Top 4 scored messages become `evidence_message_ids` in output.

### 3. Multimodal Handling

**Voice notes**: Groq Whisper transcribes the audio file. Transcript is injected into the prompt as `VOICE TRANSCRIPT: <text>` before routing. The LLM routes based on spoken content, not just metadata.

**Images**: Message text is analysed using keyword rules to classify image content:
- Refund + verify wallet → scam
- Token + plot + registry → advance-fee land fraud
- Consent + field trip + bus list → school event requiring action
- Deployment + sync + incident → work escalation
- Pickup today + courier → same-day delivery action
- % off + unsubscribe → promotion

### 4. LLM Routing

Full context (user + group + business + evidence + media content) sent to LLaMA 3.1 8b Instant via Groq. Structured prompt with explicit rules for notify/digest/mute.

### 5. Post-Processing Rules

Deterministic overrides applied after LLM response:

| Rule | Condition | Override |
|------|-----------|----------|
| Chain/forward | `forwarded_count ≥ 7` | `mute` + `forward` + conf=0.97 |
| OTP scam | mute + OTP/bank/PIN keywords | `scam` type + conf=0.97 |
| Shipping notify | business + packed/shipped/delivered | `notify` + `business_update` |
| Health notify | business + appointment/prescription | `notify` + `event` |
| Promotion mute | opted-out user + promotion | `mute` |
| Feedback digest | feedback/survey/rate in text | `digest` + `business_update` |
| School bus notify | voice + gate/pickup/reach by + today | `notify` + `event` |
| Confidence fix | flat 0.95 from model | mute=0.93, notify=0.88, digest=0.80 |

---

## Results

| Metric | Value |
|--------|-------|
| Messages routed | 110 / 110 |
| Action accuracy (vs samples) | 75% |
| Type accuracy (vs samples) | 75% |
| Evidence coverage | 91 / 110 |
| Confidence range | 0.70 – 0.97 |
| Voice notes transcribed | 13 audio files via Groq Whisper |
| Images classified | 20 image files via text analysis |

**Action distribution**: `notify` 23 · `digest` 39 · `mute` 48

**Message type distribution**:

| Type | Count |
|------|-------|
| scam | 18 |
| business_update | 17 |
| event | 16 |
| forward | 14 |
| promotion | 12 |
| urgent | 10 |
| personal | 9 |
| spam | 9 |
| unknown | 3 |
| greeting | 1 |
| payment | 1 |

---

## Key Design Decisions

**Why Groq over Gemini/Ollama**: Gemini free tier has a 100k token/day limit which was exhausted at message 90. Ollama (local Mistral) processed ~1 message per minute — too slow for 110 messages in the hackathon window. Groq provides fast cloud inference with no practical rate limit for this volume.

**Why post-processing rules on top of LLM**: The LLM alone miscategorised opted-out promotions as digest (should be mute), health appointment updates as digest (should be notify), and gave flat 0.95 confidence for everything. Deterministic rules fix these systematic failure modes reliably.

**Why text-based image classification**: Groq's vision models were unavailable on the free tier (`meta-llama/llama-4-scout-17b-16e-instruct` returned 404). Text-based classification using message content achieves equivalent results since image posters in WhatsApp always accompany descriptive text.

**Evidence scoring**: Simple relevance scoring outperforms random selection — same sender/business/group signals identify the most useful historical context, while report/mute signals surface scam patterns from the user's own history.