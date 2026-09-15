#!/usr/bin/env python3
"""
Check the Continente "Fome de Vencer" page for a Seleção fixture and alert
when its tickets are no longer marked as coming soon.

Stateless by design: it does not diff against a previous run, it just asks
"is this fixture still 'em breve'?" — so it works fine on ephemeral runners.

Environment:
    FDV_MATCH    substring identifying the fixture (default "Noruega")
    NTFY_TOPIC   ntfy.sh topic to push to (optional)
    SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS / MAIL_TO  (optional)

Exit codes:  0 = still pending (or alert sent),  1 = check failed.
"""

import os
import re
import smtplib
import sys
import urllib.request
from email.message import EmailMessage

URL = "https://feed.continente.pt/fome-de-vencer"
MATCH = os.environ.get("FDV_MATCH", "Noruega")
PENDING = "em breve"

STATUS_RE = re.compile(r"Os bilhetes para este jogo[^<.]*\.")
TAGS_RE = re.compile(r"<[^>]+>")


def current_status() -> str:
    req = urllib.request.Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; fdv-watcher/1.0)",
            "Accept-Language": "pt-PT",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        text = TAGS_RE.sub(" ", r.read().decode("utf-8", "replace"))

    idx = text.find(MATCH)
    if idx == -1:
        raise LookupError(f"fixture {MATCH!r} not found on page")
    found = STATUS_RE.search(text, idx)
    if not found:
        raise LookupError(f"no status sentence after {MATCH!r}")
    return " ".join(found.group(0).split())


def push_ntfy(title: str, body: str) -> None:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=body.encode("utf-8"),
        headers={"Title": title, "Priority": "urgent", "Tags": "soccer"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30).read()


def send_mail(title: str, body: str) -> None:
    host = os.environ.get("SMTP_HOST")
    if not host:
        return
    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = os.environ.get("SMTP_USER", "")
    msg["To"] = os.environ["MAIL_TO"]
    msg.set_content(body)
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", 587)), timeout=30) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)


def main() -> int:
    try:
        status = current_status()
    except Exception as exc:
        print(f"::warning::check failed: {exc}")
        return 1

    print(f"{MATCH}: {status}")

    if PENDING in status.lower():
        return 0

    title = f"Bilhetes {MATCH} - status mudou"
    body = f"{status}\n\n{URL}"
    push_ntfy(title, body)
    send_mail(title, body)
    print("::notice::alert sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
