"""Lemmy news source: top posts from a Lemmy instance.

Read-only. Fetches ``GET /api/v3/post/list`` (Lemmy 0.19 API) and normalizes each
post into a ``FeedItem``. Works anonymously, or logs in with a configured
username/password to enable authenticated views (e.g. ``type_: Subscribed``).
Used as a source inside the News aggregator (see ``integrations/news.py``), but is
a standalone ``Integration`` so it also works on its own.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from ..models import FeedItem
from .base import Field, FeedSelector, FeedTab, Integration, Tab, VoteAction

USER_AGENT = "morning-coffee/0.1 (+https://github.com/chalbersma/morning-coffee)"

# (label, API value) for the listing-type selector.
VIEW_TYPES: list[tuple[str, str]] = [
    ("Subscribed", "Subscribed"),
    ("Local", "Local"),
    ("All", "All"),
]


def _parse_published(value) -> datetime | None:
    """Parse Lemmy's ISO-8601 ``published`` string to a naive local datetime."""
    if not isinstance(value, str):
        return None
    try:
        # Lemmy uses e.g. "2026-09-04T06:12:00.123456Z" (or without fraction).
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class LemmyIntegration(Integration):
    name = "Lemmy"
    config_key = "lemmy"

    @classmethod
    def config_fields(cls) -> list[Field]:
        return [
            Field("instance", "Instance", help="host only, e.g. lemmy.world"),
            Field(
                "sort", "Sort",
                kind="choice",
                choices=["TopDay", "Hot", "New", "TopHour", "TopWeek", "TopMonth"],
            ),
            Field(
                "type_", "Default listing",
                kind="choice", choices=["Subscribed", "Local", "All"],
            ),
            Field("limit", "Item limit", kind="int"),
            Field("username", "Username", help="optional; enables Subscribed + voting"),
            Field("password", "Password", kind="secret"),
        ]

    def __init__(self, settings: dict) -> None:
        super().__init__(settings)
        self._jwt: str | None = None
        self._view_type: str | None = None

    def _logged_in(self) -> bool:
        """Whether credentials are configured (login/voting require this)."""
        return bool(self.settings.get("username") and self.settings.get("password"))

    def _current_type(self) -> str:
        """The active listing type: UI selection wins, else config, else Subscribed."""
        return self._view_type or str(self.settings.get("type_") or "Subscribed")

    def set_view_type(self, value: str) -> None:
        """Change the listing type (called by the feed selector before re-fetch)."""
        self._view_type = value

    def _instance(self) -> str:
        instance = str(self.settings.get("instance", "")).strip().rstrip("/")
        # Accept a bare host or a full URL; normalize to a scheme-less host.
        instance = instance.replace("https://", "").replace("http://", "")
        if not instance:
            raise RuntimeError("lemmy.instance is not configured")
        return instance

    def _login(self, client: httpx.Client, instance: str) -> str:
        """Log in and return a JWT. Raises with a clear message on failure."""
        body = {
            "username_or_email": self.settings.get("username", ""),
            "password": self.settings.get("password", ""),
        }
        totp = self.settings.get("totp_2fa_token")
        if totp:
            body["totp_2fa_token"] = str(totp)
        resp = client.post(f"https://{instance}/api/v3/user/login", json=body)
        if resp.status_code in (400, 401, 403):
            raise RuntimeError(f"Lemmy login failed ({resp.status_code}); check credentials")
        resp.raise_for_status()
        jwt = (resp.json() or {}).get("jwt")
        if not jwt:
            raise RuntimeError("Lemmy login did not return a token (2FA required?)")
        return jwt

    def _auth_header(self, client: httpx.Client, instance: str) -> dict:
        """Return an Authorization header when credentials are configured.

        Caches the JWT across calls; anonymous when no username/password set.
        """
        if not (self.settings.get("username") and self.settings.get("password")):
            return {}
        if not self._jwt:
            self._jwt = self._login(client, instance)
        return {"Authorization": f"Bearer {self._jwt}"}

    def _post_url(self, instance: str, post: dict) -> str | None:
        """Prefer the external link; else the post page on the home instance.

        Uses the local ``post.id`` on the configured instance (not ``ap_id``) so
        the link opens on the user's own instance.
        """
        external = post.get("url")
        if external:
            return external
        pid = post.get("id")
        if pid is not None:
            return f"https://{instance}/post/{pid}"
        return post.get("ap_id")

    def fetch(self) -> list[FeedItem]:
        instance = self._instance()
        params = {
            "type_": self._current_type(),
            "sort": str(self.settings.get("sort", "TopDay")),
            "limit": int(self.settings.get("limit", 25)),
        }
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        url = f"https://{instance}/api/v3/post/list"
        with httpx.Client(timeout=15.0, headers=headers) as client:
            auth = self._auth_header(client, instance)
            resp = client.get(url, params=params, headers=auth)
            if resp.status_code == 401 and auth:
                # Cached JWT may have expired: re-login once and retry.
                self._jwt = None
                auth = self._auth_header(client, instance)
                resp = client.get(url, params=params, headers=auth)
            resp.raise_for_status()
            data = resp.json()

        items: list[FeedItem] = []
        for view in data.get("posts") or []:
            post = view.get("post") or {}
            community = view.get("community") or {}
            counts = view.get("counts") or {}
            score = counts.get("score")
            comments = counts.get("comments")
            pid = post.get("id")
            # The post page on the configured instance IS the comment thread.
            thread_url = f"https://{instance}/post/{pid}" if pid is not None else None

            # Subtitle: community name + a clickable comments link. (The score
            # lives in the vote control, not the subtitle.)
            community_name = community.get("title") or community.get("name") or ""
            segments: list[tuple[str, str | None]] = []
            subtitle = community_name
            if community_name:
                segments.append((community_name, None))
            if comments is not None:
                if segments:
                    segments.append((" · ", None))
                    subtitle += " · "
                segments.append((f"{comments} comments", thread_url))
                subtitle += f"{comments} comments"

            items.append(
                FeedItem(
                    title=post.get("name", "(untitled)"),
                    subtitle=subtitle,
                    subtitle_segments=segments or None,
                    url=self._post_url(instance, post),
                    timestamp=_parse_published(post.get("published")),
                    source=self.name,
                    meta={
                        "post_id": pid,
                        "score": int(score) if score is not None else 0,
                        "my_vote": int(view.get("my_vote") or 0),
                    },
                )
            )
        return items

    def vote(self, item: FeedItem, score: int) -> tuple[int, int]:
        """Vote on a post (score 1/-1/0). Returns (new_score, new_my_vote).

        Requires login; raises a clear error otherwise.
        """
        if not self._logged_in():
            raise RuntimeError("voting requires a configured Lemmy login")
        post_id = item.meta.get("post_id")
        if post_id is None:
            raise RuntimeError("post has no id")
        instance = self._instance()
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        url = f"https://{instance}/api/v3/post/like"
        body = {"post_id": post_id, "score": score}
        with httpx.Client(timeout=15.0, headers=headers) as client:
            auth = self._auth_header(client, instance)
            resp = client.post(url, json=body, headers=auth)
            if resp.status_code == 401 and auth:
                # Cached JWT may have expired: re-login once and retry.
                self._jwt = None
                auth = self._auth_header(client, instance)
                resp = client.post(url, json=body, headers=auth)
            resp.raise_for_status()
            pv = (resp.json() or {}).get("post_view") or {}
        new_score = int((pv.get("counts") or {}).get("score", item.meta.get("score", 0)))
        new_my_vote = int(pv.get("my_vote") or 0)
        item.meta["score"] = new_score
        item.meta["my_vote"] = new_my_vote
        return new_score, new_my_vote

    def tabs(self) -> list[Tab]:
        return [
            FeedTab(
                title=self.name,
                fetch=self.fetch,
                selector=FeedSelector(
                    options=VIEW_TYPES,
                    on_select=self.set_view_type,
                    default=self._current_type(),
                ),
                # Voting needs auth; only offer it when a login is configured.
                vote_action=VoteAction(vote=self.vote) if self._logged_in() else None,
            )
        ]
