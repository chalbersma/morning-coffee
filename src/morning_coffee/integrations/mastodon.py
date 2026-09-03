"""Mastodon integration: recent social interactions.

Uses Mastodon.py with a personal access token (Preferences -> Development ->
your app -> "Your access token"; scopes ``read`` or ``read:notifications``).
Pulls notifications filtered to the configured types and normalizes them into
``FeedItem``s.
"""

from __future__ import annotations

import re

from ..models import FeedItem
from .base import Integration

_TAG_RE = re.compile(r"<[^>]+>")

# Short verbs for each notification type, for the title line.
_TYPE_VERB = {
    "mention": "mentioned you",
    "favourite": "favourited your post",
    "reblog": "boosted your post",
    "follow": "followed you",
    "follow_request": "requested to follow you",
    "poll": "poll ended",
    "status": "posted",
    "update": "edited a post",
}


def _strip_html(text: str, limit: int = 160) -> str:
    """Turn status HTML into a short plaintext excerpt."""
    plain = _TAG_RE.sub("", text or "").strip()
    plain = re.sub(r"\s+", " ", plain)
    return plain[: limit - 1] + "…" if len(plain) > limit else plain


class MastodonIntegration(Integration):
    name = "Interactions"
    config_key = "mastodon"

    def fetch(self) -> list[FeedItem]:
        self._error = None
        access_token = self.settings.get("access_token", "")
        api_base_url = self.settings.get("api_base_url", "")
        if not access_token or not api_base_url:
            self._error = "mastodon.access_token / api_base_url not configured"
            return []

        try:
            # Imported lazily so a missing/broken dep only affects this panel.
            from mastodon import Mastodon

            client = Mastodon(access_token=access_token, api_base_url=api_base_url)
            types = self.settings.get("types") or [
                "mention",
                "favourite",
                "reblog",
                "follow",
            ]
            limit = int(self.settings.get("limit", 25))
            notifications = client.notifications(types=types, limit=limit)
        except Exception as exc:  # noqa: BLE001 - surface any failure in the panel
            self._error = str(exc)
            return []

        items: list[FeedItem] = []
        for note in notifications:
            account = note.get("account") or {}
            acct = account.get("acct") or account.get("username") or "someone"
            verb = _TYPE_VERB.get(note.get("type", ""), note.get("type", "interacted"))
            status = note.get("status") or {}
            subtitle = _strip_html(status.get("content", "")) if status else ""
            items.append(
                FeedItem(
                    title=f"@{acct} {verb}",
                    subtitle=subtitle,
                    url=status.get("url") or account.get("url"),
                    timestamp=note.get("created_at"),
                    source=self.name,
                    meta={"type": note.get("type")},
                )
            )
        return items
