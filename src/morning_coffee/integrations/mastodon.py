"""Mastodon integration: notifications, home & trending feeds, and composing.

Uses Mastodon.py with a personal access token (Preferences -> Development ->
your app -> "Your access token"). Reading needs ``read:notifications`` and
``read:statuses``; posting needs ``write:statuses`` (or ``write``). Trending is a
public endpoint and needs no scope.

The panel exposes up to four tabs (see ``tabs()``): Notifications, Home,
Trending, and Compose.
"""

from __future__ import annotations

import re

from ..models import FeedItem
from .base import ComposeTab, Field, FeedTab, Integration, Tab

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

# (label, api value) pairs for the compose visibility selector.
VISIBILITIES: list[tuple[str, str]] = [
    ("Public", "public"),
    ("Unlisted", "unlisted"),
    ("Followers-only", "private"),
    ("Direct", "direct"),
]


def _strip_html(text: str, limit: int = 160) -> str:
    """Turn status HTML into a short plaintext excerpt."""
    plain = _TAG_RE.sub("", text or "").strip()
    plain = re.sub(r"\s+", " ", plain)
    return plain[: limit - 1] + "…" if len(plain) > limit else plain


def _home_status_url(home_base: str, status: dict) -> str | None:
    """Build a URL that opens a status on the configured home server.

    Mastodon returns each status with ``id`` = its local id on the server we
    fetched from (the home server) and ``account.acct`` = ``user@domain`` for
    remote users. The home server resolves ``/{@acct}/{id}`` to its own copy, so
    the link stays on the user's instance (logged in, able to interact) instead
    of bouncing to the origin server. Falls back to the origin ``url``.
    """
    account = status.get("account") or {}
    acct = account.get("acct") or account.get("username")
    sid = status.get("id")
    if home_base and acct and sid is not None:
        return f"{home_base}/@{acct}/{sid}"
    return status.get("url")


def _home_account_url(home_base: str, account: dict) -> str | None:
    """Build a home-server profile URL for an account. Falls back to origin."""
    acct = account.get("acct") or account.get("username")
    if home_base and acct:
        return f"{home_base}/@{acct}"
    return account.get("url")


def _status_to_item(status: dict, source: str, home_base: str) -> FeedItem:
    """Map a Mastodon Status to a FeedItem, unwrapping boosts."""
    booster = None
    if status.get("reblog"):
        booster = (status.get("account") or {}).get("acct")
        status = status["reblog"]
    account = status.get("account") or {}
    acct = account.get("acct") or account.get("username") or "someone"
    title = f"@{acct}"
    if booster:
        title = f"@{acct} (boosted by @{booster})"
    return FeedItem(
        title=title,
        subtitle=_strip_html(status.get("content", "")),
        url=_home_status_url(home_base, status),
        timestamp=status.get("created_at"),
        source=source,
        meta={
            "reblogs": status.get("reblogs_count"),
            "favourites": status.get("favourites_count"),
        },
    )


class MastodonIntegration(Integration):
    name = "Mastodon"
    config_key = "mastodon"

    @classmethod
    def config_fields(cls) -> list[Field]:
        return [
            Field("api_base_url", "Instance URL", help="e.g. https://mastodon.social"),
            Field("access_token", "Access token", kind="secret",
                  help="Preferences -> Development; needs write:statuses to post"),
            Field("notifications_limit", "Notifications limit", kind="int"),
            Field("home_limit", "Home limit", kind="int"),
            Field("trending_limit", "Trending limit", kind="int"),
            Field("default_visibility", "Default visibility", kind="choice",
                  choices=["public", "unlisted", "private", "direct"]),
            Field("max_characters", "Max characters", kind="int"),
            Field("show_notifications", "Show Notifications tab", kind="bool"),
            Field("show_home", "Show Home tab", kind="bool"),
            Field("show_trending", "Show Trending tab", kind="bool"),
            Field("show_compose", "Show Compose tab", kind="bool"),
        ]

    def _home_base(self) -> str:
        """The configured home server base URL, without a trailing slash."""
        return str(self.settings.get("api_base_url", "")).rstrip("/")

    def _client(self):
        """Build a Mastodon client, raising a clear error if unconfigured."""
        access_token = self.settings.get("access_token", "")
        api_base_url = self.settings.get("api_base_url", "")
        if not access_token or not api_base_url:
            raise RuntimeError("mastodon.access_token / api_base_url not configured")
        # Imported lazily so a missing/broken dep only affects this integration.
        from mastodon import Mastodon

        return Mastodon(access_token=access_token, api_base_url=api_base_url)

    def fetch_notifications(self) -> list[FeedItem]:
        client = self._client()
        types = self.settings.get("notification_types") or [
            "mention",
            "favourite",
            "reblog",
            "follow",
        ]
        limit = int(self.settings.get("notifications_limit", 25))
        notifications = client.notifications(types=types, limit=limit)
        home_base = self._home_base()

        items: list[FeedItem] = []
        for note in notifications:
            account = note.get("account") or {}
            acct = account.get("acct") or account.get("username") or "someone"
            verb = _TYPE_VERB.get(note.get("type", ""), note.get("type", "interacted"))
            status = note.get("status") or {}
            # Link to the status on the home server, or the profile for follows.
            url = (
                _home_status_url(home_base, status)
                if status
                else _home_account_url(home_base, account)
            )
            items.append(
                FeedItem(
                    title=f"@{acct} {verb}",
                    subtitle=_strip_html(status.get("content", "")) if status else "",
                    url=url,
                    timestamp=note.get("created_at"),
                    source=self.name,
                    meta={"type": note.get("type")},
                )
            )
        return items

    def fetch_home(self) -> list[FeedItem]:
        client = self._client()
        limit = int(self.settings.get("home_limit", 25))
        statuses = client.timeline_home(limit=limit)
        home_base = self._home_base()
        return [_status_to_item(s, "Home", home_base) for s in statuses]

    def fetch_trending(self) -> list[FeedItem]:
        limit = int(self.settings.get("trending_limit", 20))
        try:
            client = self._client()
            statuses = client.trending_statuses(limit=limit)
        except RuntimeError:
            # Configuration error: re-raise so the tab shows it.
            raise
        except Exception:  # noqa: BLE001 - trends may be disabled/absent server-side
            return []
        home_base = self._home_base()
        return [_status_to_item(s, "Trending", home_base) for s in statuses]

    def post_status(self, text: str, visibility: str) -> None:
        """Publish a new status. Raises on failure (needs write:statuses)."""
        client = self._client()
        try:
            client.status_post(status=text, visibility=visibility)
        except Exception as exc:  # noqa: BLE001 - annotate the common scope error
            msg = str(exc)
            if "401" in msg or "unauthorized" in msg.lower():
                raise RuntimeError(
                    f"{msg} (does your token have the 'write:statuses' scope?)"
                ) from exc
            raise

    def fetch(self) -> list[FeedItem]:
        """Base-class default view: notifications (with error captured)."""
        self._error = None
        try:
            return self.fetch_notifications()
        except Exception as exc:  # noqa: BLE001 - surface via health()
            self._error = str(exc)
            return []

    def tabs(self) -> list[Tab]:
        tabs: list[Tab] = []
        if self.settings.get("show_notifications", True):
            tabs.append(FeedTab(title="Notif", fetch=self.fetch_notifications))
        if self.settings.get("show_home", True):
            tabs.append(FeedTab(title="Home", fetch=self.fetch_home, default=True))
        if self.settings.get("show_trending", True):
            tabs.append(FeedTab(title="Trending", fetch=self.fetch_trending))
        if self.settings.get("show_compose", True):
            tabs.append(
                ComposeTab(
                    title="Compose",
                    submit=self.post_status,
                    visibilities=VISIBILITIES,
                    default_visibility=str(self.settings.get("default_visibility", "public")),
                    max_characters=int(self.settings.get("max_characters", 500)),
                )
            )
        return tabs
