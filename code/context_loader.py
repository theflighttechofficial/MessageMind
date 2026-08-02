"""
context_loader.py
-----------------
Loads all dataset CSVs into fast lookup structures.
Called once at startup by main.py.
"""

import csv
from collections import defaultdict
from pathlib import Path


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_all(dataset_dir: Path) -> dict:
    d = dataset_dir

    # ── core tables ────────────────────────────────────────────────────
    users_raw          = load_csv(d / "users.csv")
    groups_raw         = load_csv(d / "groups.csv")
    group_members_raw  = load_csv(d / "group_members.csv")
    businesses_raw     = load_csv(d / "business_accounts.csv")
    user_biz_raw       = load_csv(d / "user_business_history.csv")
    history_raw        = load_csv(d / "message_history.csv")
    events_raw         = load_csv(d / "message_events.csv")
    images_raw         = load_csv(d / "images.csv")
    voice_notes_raw    = load_csv(d / "voice_notes.csv")

    # ── fast lookups ───────────────────────────────────────────────────
    users     = {r["user_id"]: r for r in users_raw}
    groups    = {r["group_id"]: r for r in groups_raw}
    businesses = {r["business_id"]: r for r in businesses_raw}
    images    = {r["image_id"]: r for r in images_raw}
    voice_notes = {r["voice_note_id"]: r for r in voice_notes_raw}

    # group_members[(user_id, group_id)]
    group_members = {}
    for r in group_members_raw:
        group_members[(r["user_id"], r["group_id"])] = r

    # user_business[(user_id, business_id)]
    user_business = {}
    for r in user_biz_raw:
        user_business[(r["user_id"], r["business_id"])] = r

    # history by user_id → list of past message dicts
    history_by_user = defaultdict(list)
    for r in history_raw:
        history_by_user[r["user_id"]].append(r)

    # history by message_id (for event lookup)
    history_by_id = {r["message_id"]: r for r in history_raw}

    # events by user_id → list of event dicts (joined with history text)
    events_by_user = defaultdict(list)
    for r in events_raw:
        uid = r["user_id"]
        mid = r["message_id"]
        # attach the message text for context
        r["_message_text"] = history_by_id.get(mid, {}).get("message_text", "")
        r["_sender"]       = history_by_id.get(mid, {}).get("sender_user_id", "")
        r["_business"]     = history_by_id.get(mid, {}).get("business_id", "")
        r["_group"]        = history_by_id.get(mid, {}).get("group_id", "")
        events_by_user[uid].append(r)

    return {
        "users":          users,
        "groups":         groups,
        "group_members":  group_members,
        "businesses":     businesses,
        "user_business":  user_business,
        "history_by_user": history_by_user,
        "events_by_user": events_by_user,
        "images":         images,
        "voice_notes":    voice_notes,
    }


def get_evidence(row: dict, ctx: dict, max_results: int = 4) -> list[str]:
    """
    Find historical message IDs most relevant to routing this message.
    Returns list of message_id strings to use as evidence.
    """
    uid         = row["user_id"]
    sender_uid  = row.get("sender_user_id", "")
    business_id = row.get("business_id", "")
    group_id    = row.get("group_id", "")

    events = ctx["events_by_user"].get(uid, [])
    scored = []

    for e in events:
        score = 0
        mid = e["message_id"]

        # same sender → strong match
        if sender_uid and e.get("_sender") == sender_uid:
            score += 4
        # same business → strong match
        if business_id and e.get("_business") == business_id:
            score += 4
        # same group → moderate match
        if group_id and e.get("_group") == group_id:
            score += 2
        # user reported or muted → this is evidence of risk
        if e.get("message_reported") == "1":
            score += 3
        if e.get("muted_after_message") == "1":
            score += 2
        # user replied → evidence of engagement
        if e.get("message_replied") == "1":
            score += 1

        if score > 0:
            scored.append((score, mid))

    scored.sort(key=lambda x: -x[0])
    return [mid for _, mid in scored[:max_results]]


def build_context_block(row: dict, ctx: dict) -> tuple[str, list[str]]:
    """
    Build the full context string for one message and return
    (context_block_str, evidence_ids_list).
    """
    uid         = row["user_id"]
    group_id    = row.get("group_id", "")
    business_id = row.get("business_id", "")

    lines = []

    # ── user ──────────────────────────────────────────────────────────
    u = ctx["users"].get(uid, {})
    lines.append(f"USER ({uid}):")
    lines.append(f"  do_not_disturb: {u.get('do_not_disturb_window','?')}")
    lines.append(f"  msgs_opened_30d: {u.get('messages_opened_30d','?')}")
    lines.append(f"  msgs_replied_30d: {u.get('messages_replied_30d','?')}")
    lines.append(f"  notifications_dismissed_30d: {u.get('notifications_dismissed_30d','?')}")
    lines.append(f"  messages_reported_30d: {u.get('messages_reported_30d','?')}")

    # ── group ─────────────────────────────────────────────────────────
    if group_id:
        g  = ctx["groups"].get(group_id, {})
        gm = ctx["group_members"].get((uid, group_id), {})
        lines.append(f"GROUP ({group_id}):")
        lines.append(f"  name: {g.get('group_name','?')}")
        lines.append(f"  type: {g.get('group_type','?')}")
        lines.append(f"  member_count: {g.get('member_count','?')}")
        lines.append(f"  messages_30d: {g.get('messages_30d','?')}")
        lines.append(f"  user_role: {gm.get('role','?')}")
        lines.append(f"  group_muted_by_user: {gm.get('group_muted_by_user','?')}")
        lines.append(f"  user_msgs_read_30d: {gm.get('messages_read_30d','?')}")
        lines.append(f"  user_replies_30d: {gm.get('replies_sent_30d','?')}")
        lines.append(f"  user_dismissals_30d: {gm.get('notifications_dismissed_30d','?')}")

    # ── business ──────────────────────────────────────────────────────
    if business_id:
        b  = ctx["businesses"].get(business_id, {})
        ub = ctx["user_business"].get((uid, business_id), {})
        domain_match = b.get("official_domain","") == b.get("domain_used_by_sender","")
        lines.append(f"BUSINESS ({business_id}):")
        lines.append(f"  brand: {b.get('brand_name','?')}")
        lines.append(f"  category: {b.get('category','?')}")
        lines.append(f"  verified: {b.get('verified','?')}")
        lines.append(f"  official_domain: {b.get('official_domain','?')}")
        lines.append(f"  sender_domain: {b.get('domain_used_by_sender','?')}")
        lines.append(f"  domain_matches_brand: {domain_match}")
        lines.append(f"  account_age_days: {b.get('account_age_days','?')}")
        lines.append(f"  user_reports_30d: {b.get('user_reports_30d','?')}")
        lines.append(f"  user_relationship: {ub.get('why_user_knows_account','none')}")
        lines.append(f"  user_allows_promotions: {ub.get('allows_promotions','?')}")
        lines.append(f"  user_opted_out_promotions: {ub.get('promotions_opted_out_at','none')}")
        lines.append(f"  user_msgs_opened_30d: {ub.get('messages_opened_30d','?')}")
        lines.append(f"  user_msgs_dismissed_30d: {ub.get('messages_dismissed_30d','?')}")

    # ── media ─────────────────────────────────────────────────────────
    media_type = row.get("media_type", "")
    media_id   = row.get("media_id", "")
    if media_type == "image" and media_id:
        img = ctx["images"].get(media_id, {})
        lines.append(f"IMAGE: {media_id} → path={img.get('file_path','unknown')}")
    elif media_type == "voice" and media_id:
        vn = ctx["voice_notes"].get(media_id, {})
        lines.append(f"VOICE NOTE: {media_id} → path={vn.get('file_path','unknown')}")

    # ── evidence ──────────────────────────────────────────────────────
    evidence_ids = get_evidence(row, ctx)
    if evidence_ids:
        lines.append(f"HISTORICAL EVIDENCE IDs: {';'.join(evidence_ids)}")
        # show the text of top 3 for context
        for eid in evidence_ids[:3]:
            for e in ctx["events_by_user"].get(uid, []):
                if e["message_id"] == eid:
                    txt = e.get("_message_text", "")[:100]
                    rep = e.get("message_reported", "0")
                    mut = e.get("muted_after_message", "0")
                    lines.append(f"  {eid}: text='{txt}' reported={rep} muted={mut}")
                    break
    else:
        lines.append("HISTORICAL EVIDENCE IDs: none")

    return "\n".join(lines), evidence_ids
