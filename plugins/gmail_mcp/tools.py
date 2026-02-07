import base64
from email.mime.text import MIMEText

def _decode_body(payload):
    """Extract plain text body from Gmail message payload."""
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(
            payload["body"]["data"].encode("ASCII")
        ).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(
                part["body"]["data"].encode("ASCII")
            ).decode("utf-8", errors="replace")
    return ""


def _get_header(headers, name):
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def list_messages_tool(service):
    async def list_messages(max_results: int = 10, label_ids=None):
        params = {"userId": "me", "maxResults": max_results}
        if label_ids:
            params["labelIds"] = label_ids
        result = service.users().messages().list(**params).execute()
        messages = result.get("messages", [])
        return [
            {"id": m["id"], "threadId": m.get("threadId")}
            for m in messages
        ]

    return {
        "name": "gmail_list_messages",
        "description": "List Gmail messages in the user's mailbox",
        "fn": list_messages,
    }


def get_message_tool(service):
    async def get_message(message_id: str):
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        payload = msg.get("payload", {})
        headers = payload.get("headers", [])
        body = _decode_body(payload)
        return {
            "id": msg["id"],
            "threadId": msg.get("threadId"),
            "snippet": msg.get("snippet"),
            "subject": _get_header(headers, "Subject"),
            "from": _get_header(headers, "From"),
            "to": _get_header(headers, "To"),
            "date": _get_header(headers, "Date"),
            "body": body,
        }

    return {
        "name": "gmail_get_message",
        "description": "Get a single Gmail message by ID",
        "fn": get_message,
    }


def send_message_tool(service):
    async def send_message(to: str, subject: str, body: str):
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ASCII")
        sent = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )
        return {"id": sent["id"], "threadId": sent.get("threadId")}

    return {
        "name": "gmail_send_message",
        "description": "Send a Gmail message",
        "fn": send_message,
    }
