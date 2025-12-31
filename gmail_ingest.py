# gmail_ingest.py
from __future__ import annotations
import base64
import pathlib
import re
import time
from typing import Any, Dict, List, Optional

import html2text
import yaml
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

ROOT = pathlib.Path(__file__).parent
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# ---------- Config ----------
def _load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text())

# ---------- Gmail client ----------
def _gmail_service():
    from google.auth.transport.requests import Request
    cred_path = ROOT / "credentials.json"
    if not cred_path.exists():
        raise RuntimeError("Missing credentials.json (download Gmail OAuth Desktop client).")
    token_path = ROOT / "token.json"

    creds = None
    if token_path.exists():
        # If token.json is corrupt/empty this will throw — we handle by reauth
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:
            token_path.unlink(missing_ok=True)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                # Refresh failed (invalid_grant, revoked token, etc.)
                print(f"⚠️  Token refresh failed: {e}")
                print("🔄 Deleting expired token and re-authenticating...")
                token_path.unlink(missing_ok=True)
                creds = None

        if not creds:
            # Force Google to give a refresh_token (no include_granted_scopes)
            print("🔐 Opening browser for Gmail authentication...")
            flow = InstalledAppFlow.from_client_secrets_file(str(cred_path), SCOPES)
            creds = flow.run_local_server(
                port=0,
                access_type="offline",
                prompt="consent",
            )
            print("✅ Gmail authentication successful!")

        token_path.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)

# ---------- Helpers ----------
def _get_header(headers: List[Dict[str, str]], name: str) -> Optional[str]:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None

def _html_to_md(html: str) -> str:
    h = html2text.HTML2Text()
    h.ignore_images = False
    h.ignore_links = False
    h.body_width = 0
    return h.handle(html)

def _first_url(md: str) -> Optional[str]:
    m = re.search(r"https?://[^\s\)\]]{12,}", md)
    return m.group(0) if m else None

def _walk_for_html(payload: Dict[str, Any]) -> Optional[str]:
    html = None
    def walk(p):
        nonlocal html
        if "parts" in p:
            for c in p["parts"]:
                walk(c)
        else:
            if (p.get("mimeType") or "").startswith("text/html"):
                data = p.get("body", {}).get("data")
                if data:
                    try:
                        html_dec = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                        html = html_dec
                    except Exception:
                        pass
    walk(payload)
    return html

# ---------- Public API ----------
def fetch_newsletters(window: dict, query: str) -> List[Dict[str, Any]]:
    """
    Fetch AI newsletters from Gmail.

    window:
      {"mode":"days","days":int}
      or {"mode":"since_ts","since_ts":epoch_ms}
    query: Gmail search string from config.yaml (news_query)

    Returns newest-first list of:
      {
        "title": str,
        "source": str,            # From header
        "date": ISO8601 Z,
        "gmail_link": str|None,   # RFC822 search link (works in Gmail)
        "web_link": str|None,     # First URL found in body (for Sources section)
        "internal_ts": int,       # Gmail internal timestamp (ms)
        "text": str               # Markdown version of email
      }
    """
    svc = _gmail_service()

    # Build Gmail query
    if window["mode"] == "days":
        q = f"newer_than:{window['days']}d {query}"
    else:
        # for since_ts we fetch with raw query and filter client-side by internalDate
        q = query

    # Collect message IDs (paginate)
    ids, token = [], None
    while True:
        resp = svc.users().messages().list(
            userId="me", q=q, pageToken=token, maxResults=100
        ).execute()
        ids += [m["id"] for m in resp.get("messages", [])]
        token = resp.get("nextPageToken")
        if not token:
            break

    # Fetch full messages
    items = []
    for mid in ids:
        m = svc.users().messages().get(userId="me", id=mid, format="full").execute()
        ts_ms = int(m["internalDate"])

        if window["mode"] == "since_ts" and ts_ms <= window["since_ts"]:
            continue

        headers = m["payload"].get("headers", [])
        subject = _get_header(headers, "Subject") or "Newsletter"
        sender = _get_header(headers, "From") or "unknown"
        msgid = _get_header(headers, "Message-Id")

        gmail_link = f"https://mail.google.com/mail/u/0/#search/rfc822msgid:{msgid}" if msgid else None
        html = _walk_for_html(m["payload"])
        body_md = _html_to_md(html) if html else (m.get("snippet") or "")
        web_link = _first_url(body_md)

        items.append({
            "title": subject,
            "source": sender,
            "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts_ms/1000)),
            "gmail_link": gmail_link,
            "web_link": web_link,
            "internal_ts": ts_ms,
            "text": body_md
        })

    # De-dup by web_link (fallback gmail_link), newest-first
    dedup = {}
    for it in sorted(items, key=lambda x: x["internal_ts"], reverse=True):
        key = it["web_link"] or it["gmail_link"] or it["title"]
        if key not in dedup:
            dedup[key] = it
    return list(dedup.values())

def fetch_context(window: dict, query: str) -> List[Dict[str, Any]]:
    """
    Fetch context emails (e.g., Granola summaries) from Gmail.

    window:
      {"mode":"all"}                      -> ignore time; return everything matching query
      {"mode":"days","days":int}          -> Gmail newer_than filter
      {"mode":"since_ts","since_ts":ms}   -> client-side filter by internalDate

    query: Gmail search string from config.yaml (context_query)

    Returns newest-first list of:
      {
        "source": "gmail",
        "id": str,           # message-id or Gmail id
        "text": str,         # Markdown body (trimmed)
        "date": ISO8601 Z,
        "ts_ms": int
      }
    """
    svc = _gmail_service()

    # Build query
    if window["mode"] == "days":
        q = f"newer_than:{window['days']}d {query}"
    else:
        # 'all' and 'since_ts' both run raw query, then filter if since_ts
        q = query

    # Collect message IDs (paginate)
    ids, token = [], None
    while True:
        resp = svc.users().messages().list(
            userId="me", q=q, pageToken=token, maxResults=100
        ).execute()
        ids += [m["id"] for m in resp.get("messages", [])]
        token = resp.get("nextPageToken")
        if not token:
            break

    docs = []
    for mid in ids:
        m = svc.users().messages().get(userId="me", id=mid, format="full").execute()
        ts_ms = int(m["internalDate"])
        if window["mode"] == "since_ts" and ts_ms <= window["since_ts"]:
            continue

        headers = m["payload"].get("headers", [])
        msgid = _get_header(headers, "Message-Id") or mid

        html = _walk_for_html(m["payload"])
        text = _html_to_md(html) if html else (m.get("snippet") or "")
        docs.append({
            "source": "gmail",
            "id": msgid,
            "text": text[:200_000],  # keep it sane
            "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts_ms/1000)),
            "ts_ms": ts_ms
        })

    docs.sort(key=lambda d: d["ts_ms"], reverse=True)
    return docs
