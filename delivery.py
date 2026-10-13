"""Telegram acknowledgements and a durable, fail-closed source outbox.

Telegram sendMessage has no idempotency key. An ambiguous response must NOT be
retried automatically: retain it for human reconciliation instead of duplicating.
"""

from pathlib import Path
import requests

from state_store import StateFailure, atomic_json, normalize_state, read_json

OUTBOX_FILE = Path(__file__).resolve().parent / ".digest-outbox.json"
MESSAGE_LIMIT = 4000


class DeliveryFailure(RuntimeError):
    def __init__(self, code, uncertain=False):
        super().__init__(code)
        self.uncertain = uncertain


def send_html(notifier, text):
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{notifier.bot_token}/sendMessage",
            json={"chat_id": notifier.chat_id, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True}, timeout=10,
        )
    except requests.RequestException:
        raise DeliveryFailure("telegram-network-uncertain", uncertain=True) from None
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and body.get("ok") is False:
        raise DeliveryFailure("telegram-rejected")
    if 400 <= response.status_code < 500:
        raise DeliveryFailure("telegram-http-rejected")
    result = body.get("result") if isinstance(body, dict) else None
    message_id = result.get("message_id") if isinstance(result, dict) else None
    if (response.status_code == 200 and isinstance(body, dict)
            and body.get("ok") is True and type(message_id) is int and message_id > 0):
        return message_id
    raise DeliveryFailure("telegram-ack-uncertain", uncertain=True)


def message_length(text):
    return len(text.encode("utf-16-le")) // 2


def source_chunks(section):
    # Each formatter line has balanced HTML. Split only between complete lines.
    title, *lines = section.splitlines()
    prefix = "☀️ <b>Tech Morning Digest</b>\n\n" + title
    chunks = []
    chunk = prefix
    for line in lines:
        if message_length(prefix + "\n" + line) > MESSAGE_LIMIT:
            raise DeliveryFailure("telegram-line-too-long")
        if message_length(chunk + "\n" + line) > MESSAGE_LIMIT:
            chunks.append(chunk)
            chunk = prefix
        chunk += "\n" + line
    chunks.append(chunk)
    return chunks


def load_outbox():
    outbox = read_json(OUTBOX_FILE)
    if not isinstance(outbox, dict):
        raise StateFailure("outbox-invalid-root")
    for entry in outbox.values():
        if not isinstance(entry, dict) or not isinstance(entry.get("cursor"), dict):
            raise StateFailure("outbox-invalid-entry")
        entry["cursor"] = normalize_state({"cursor": entry["cursor"]})["cursor"]
        chunks = entry.get("chunks")
        if not isinstance(chunks, list) or not chunks:
            raise StateFailure("outbox-invalid-chunks")
        for chunk in chunks:
            if (not isinstance(chunk, dict) or not isinstance(chunk.get("text"), str)
                    or chunk.get("status") not in {"pending", "inflight", "ack", "uncertain"}
                    or message_length(chunk["text"]) > MESSAGE_LIMIT):
                raise StateFailure("outbox-invalid-chunk")
            if chunk["status"] == "ack" and (
                    type(chunk.get("message_id")) is not int or chunk["message_id"] <= 0):
                raise StateFailure("outbox-invalid-ack")
    return outbox


def save_outbox(outbox):
    atomic_json(OUTBOX_FILE, outbox)


def deliver_sources(outbox, selected, notifier, state, save_state):
    """Commit each source only after all its chunks have durable acknowledgements."""
    successful = True
    for source in list(outbox):
        if source not in selected:
            continue
        entry = outbox[source]
        for chunk in entry["chunks"]:
            if chunk["status"] == "ack":
                continue
            if chunk["status"] in {"inflight", "uncertain"}:
                # A crash after send but before durable ack is also ambiguous.
                chunk["status"] = "uncertain"
                save_outbox(outbox)
                print(f"{source}: delivery-uncertain; reconcile outbox before retry")
                successful = False
                break
            chunk["status"] = "inflight"
            save_outbox(outbox)  # Must be durable BEFORE the network side effect.
            try:
                message_id = send_html(notifier, chunk["text"])
            except DeliveryFailure as error:
                chunk["status"] = "uncertain" if error.uncertain else "pending"
                save_outbox(outbox)
                print(f"{source}: {error}")
                successful = False
                break
            chunk.update(status="ack", message_id=message_id)
            save_outbox(outbox)
        if all(chunk["status"] == "ack" for chunk in entry["chunks"]):
            state[source] = entry["cursor"]
            save_state(state)  # Resume this commit without re-sending after a crash.
            del outbox[source]
            save_outbox(outbox)
    return successful
