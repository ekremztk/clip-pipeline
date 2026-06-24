from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import psycopg2
from psycopg2.extras import RealDictCursor
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.config import settings
from app.middleware.auth import get_current_user
from app.services.supabase_client import get_db_url


router = APIRouter(prefix="/admin", tags=["admin"])

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
]

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_ANALYTICS_REPORTS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"


def _db_connect():
    db_url = get_db_url()
    if not db_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg2.connect(db_url, cursor_factory=RealDictCursor)


def _frontend_admin_url(params: dict[str, str] | None = None) -> str:
    base = (settings.FRONTEND_URL or "http://localhost:3000").rstrip("/")
    if not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    url = f"{base}/admin/channels"
    if params:
        url = f"{url}?{urlencode(params)}"
    return url


def _require_youtube_oauth_config():
    missing = [
        name
        for name, value in {
            "GOOGLE_OAUTH_CLIENT_ID": settings.GOOGLE_OAUTH_CLIENT_ID,
            "GOOGLE_OAUTH_CLIENT_SECRET": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "YOUTUBE_OAUTH_REDIRECT_URI": settings.YOUTUBE_OAUTH_REDIRECT_URI,
            "ADMIN_TOKEN_ENCRYPTION_KEY": settings.ADMIN_TOKEN_ENCRYPTION_KEY,
        }.items()
        if not value
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Missing YouTube OAuth config: {', '.join(missing)}",
        )


def _fernet() -> Fernet:
    try:
        return Fernet(settings.ADMIN_TOKEN_ENCRYPTION_KEY.encode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_TOKEN_ENCRYPTION_KEY must be a valid Fernet key",
        ) from exc


def _encrypt_token(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def _decrypt_token(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


def _int_or_none(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _chunks(items: list[str], size: int):
    for index in range(0, len(items), size):
        yield items[index:index + size]


async def _exchange_oauth_code(code: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "redirect_uri": settings.YOUTUBE_OAUTH_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
    if response.status_code >= 400:
        print(f"[AdminYouTube] Token exchange failed: {response.text[:500]}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google OAuth token exchange failed",
        )
    return response.json()


async def _fetch_youtube_channel(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            YOUTUBE_CHANNELS_URL,
            params={
                "part": "snippet,statistics,contentDetails,brandingSettings",
                "mine": "true",
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code >= 400:
        print(f"[AdminYouTube] Channel fetch failed: {response.text[:500]}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="YouTube channel fetch failed",
        )
    payload = response.json()
    items = payload.get("items") or []
    if not items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No YouTube channel found for this Google account",
        )
    return items[0]


async def _refresh_access_token(channel_id: str, token_row: dict) -> str:
    refresh_token = _decrypt_token(token_row.get("refresh_token_encrypted"))
    if not refresh_token:
        raise HTTPException(status_code=400, detail="YouTube refresh token missing")

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if response.status_code >= 400:
        print(f"[AdminYouTube] Refresh token failed: {response.text[:500]}")
        raise HTTPException(status_code=502, detail="Google token refresh failed")

    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise HTTPException(status_code=502, detail="Google refresh did not return access token")

    expires_in = int(payload.get("expires_in") or 0)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in else None

    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE admin_youtube_tokens
                SET access_token_encrypted = %s,
                    token_type = %s,
                    expires_at = %s,
                    updated_at = now()
                WHERE channel_id = %s::uuid
                """,
                (
                    _encrypt_token(access_token),
                    payload.get("token_type") or token_row.get("token_type"),
                    expires_at,
                    channel_id,
                ),
            )
        conn.commit()

    return access_token


async def _get_youtube_access_token(channel_id: str, admin_user_id: str) -> tuple[dict, str]:
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    ch.id::text AS id,
                    ch.admin_user_id::text AS admin_user_id,
                    ch.youtube_channel_id,
                    ch.title,
                    ch.uploads_playlist_id,
                    ch.status,
                    tok.access_token_encrypted,
                    tok.refresh_token_encrypted,
                    tok.token_type,
                    tok.expires_at
                FROM admin_youtube_channels ch
                JOIN admin_youtube_tokens tok ON tok.channel_id = ch.id
                WHERE ch.id = %s::uuid
                  AND ch.admin_user_id = %s::uuid
                  AND ch.status = 'connected'
                LIMIT 1
                """,
                (channel_id, admin_user_id),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Connected YouTube channel not found")

    expires_at = row.get("expires_at")
    access_token = _decrypt_token(row.get("access_token_encrypted"))
    if access_token and expires_at and expires_at > datetime.now(timezone.utc) + timedelta(minutes=2):
        return dict(row), access_token

    refreshed = await _refresh_access_token(channel_id, row)
    return dict(row), refreshed


async def _youtube_get(url: str, access_token: str, params: dict) -> dict:
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code >= 400:
        print(f"[AdminYouTube] GET failed {url}: {response.text[:700]}")
        raise HTTPException(status_code=502, detail="YouTube API request failed")
    return response.json()


def _channel_snapshot(item: dict) -> dict:
    snippet = item.get("snippet") or {}
    statistics = item.get("statistics") or {}
    content_details = item.get("contentDetails") or {}
    playlists = content_details.get("relatedPlaylists") or {}
    thumbnails = snippet.get("thumbnails") or {}
    thumbnail = (
        thumbnails.get("high")
        or thumbnails.get("medium")
        or thumbnails.get("default")
        or {}
    )
    branding = item.get("brandingSettings") or {}
    branding_channel = branding.get("channel") or {}

    return {
        "youtube_channel_id": item.get("id"),
        "title": snippet.get("title") or "Untitled channel",
        "description": snippet.get("description"),
        "custom_url": snippet.get("customUrl"),
        "thumbnail_url": thumbnail.get("url"),
        "country": snippet.get("country") or branding_channel.get("country"),
        "subscriber_count": _int_or_none(statistics.get("subscriberCount")),
        "view_count": _int_or_none(statistics.get("viewCount")),
        "video_count": _int_or_none(statistics.get("videoCount")),
        "uploads_playlist_id": playlists.get("uploads"),
    }


def _store_youtube_connection(
    admin_user_id: str,
    channel: dict,
    token_payload: dict,
) -> dict:
    snapshot = _channel_snapshot(channel)
    if not snapshot["youtube_channel_id"]:
        raise HTTPException(status_code=400, detail="YouTube channel id missing")

    now = datetime.now(timezone.utc)
    expires_in = int(token_payload.get("expires_in") or 0)
    expires_at = now + timedelta(seconds=expires_in) if expires_in else None
    refresh_token = token_payload.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google did not return a refresh token. Revoke access and connect again.",
        )

    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO admin_youtube_channels (
                    admin_user_id,
                    youtube_channel_id,
                    title,
                    description,
                    custom_url,
                    thumbnail_url,
                    country,
                    subscriber_count,
                    view_count,
                    video_count,
                    uploads_playlist_id,
                    status,
                    connected_at,
                    last_synced_at,
                    updated_at
                )
                VALUES (
                    %s::uuid, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, 'connected', now(), now(), now()
                )
                ON CONFLICT (admin_user_id, youtube_channel_id)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    custom_url = EXCLUDED.custom_url,
                    thumbnail_url = EXCLUDED.thumbnail_url,
                    country = EXCLUDED.country,
                    subscriber_count = EXCLUDED.subscriber_count,
                    view_count = EXCLUDED.view_count,
                    video_count = EXCLUDED.video_count,
                    uploads_playlist_id = EXCLUDED.uploads_playlist_id,
                    status = 'connected',
                    last_synced_at = now(),
                    updated_at = now()
                RETURNING *
                """,
                (
                    admin_user_id,
                    snapshot["youtube_channel_id"],
                    snapshot["title"],
                    snapshot["description"],
                    snapshot["custom_url"],
                    snapshot["thumbnail_url"],
                    snapshot["country"],
                    snapshot["subscriber_count"],
                    snapshot["view_count"],
                    snapshot["video_count"],
                    snapshot["uploads_playlist_id"],
                ),
            )
            channel_row = cur.fetchone()
            cur.execute(
                """
                INSERT INTO admin_youtube_tokens (
                    channel_id,
                    scope,
                    token_type,
                    access_token_encrypted,
                    refresh_token_encrypted,
                    expires_at,
                    updated_at
                )
                VALUES (%s::uuid, %s, %s, %s, %s, %s, now())
                ON CONFLICT (channel_id)
                DO UPDATE SET
                    scope = EXCLUDED.scope,
                    token_type = EXCLUDED.token_type,
                    access_token_encrypted = EXCLUDED.access_token_encrypted,
                    refresh_token_encrypted = EXCLUDED.refresh_token_encrypted,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = now()
                """,
                (
                    channel_row["id"],
                    token_payload.get("scope"),
                    token_payload.get("token_type"),
                    _encrypt_token(token_payload.get("access_token")),
                    _encrypt_token(refresh_token),
                    expires_at,
                ),
            )
            cur.execute(
                """
                INSERT INTO admin_youtube_sync_logs (
                    channel_id, admin_user_id, sync_type, status, message
                )
                VALUES (%s::uuid, %s::uuid, 'connect', 'completed', %s)
                """,
                (channel_row["id"], admin_user_id, "YouTube channel connected"),
            )
        conn.commit()
    return dict(channel_row)


def _log_youtube_sync(
    channel_id: str | None,
    admin_user_id: str,
    sync_type: str,
    status_value: str,
    message: str,
):
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO admin_youtube_sync_logs (
                        channel_id, admin_user_id, sync_type, status, message
                    )
                    VALUES (%s::uuid, %s::uuid, %s, %s, %s)
                    """,
                    (channel_id, admin_user_id, sync_type, status_value, message),
                )
            conn.commit()
    except Exception as exc:
        print(f"[AdminYouTube] Sync log insert failed: {exc}")


async def _sync_channel_snapshot(channel_id: str, admin_user_id: str) -> dict:
    channel_row, access_token = await _get_youtube_access_token(channel_id, admin_user_id)
    item = await _fetch_youtube_channel(access_token)
    snapshot = _channel_snapshot(item)

    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE admin_youtube_channels
                SET title = %s,
                    description = %s,
                    custom_url = %s,
                    thumbnail_url = %s,
                    country = %s,
                    subscriber_count = %s,
                    view_count = %s,
                    video_count = %s,
                    uploads_playlist_id = %s,
                    last_synced_at = now(),
                    updated_at = now()
                WHERE id = %s::uuid
                RETURNING *
                """,
                (
                    snapshot["title"],
                    snapshot["description"],
                    snapshot["custom_url"],
                    snapshot["thumbnail_url"],
                    snapshot["country"],
                    snapshot["subscriber_count"],
                    snapshot["view_count"],
                    snapshot["video_count"],
                    snapshot["uploads_playlist_id"],
                    channel_id,
                ),
            )
            updated = cur.fetchone()
        conn.commit()

    _log_youtube_sync(channel_id, admin_user_id, "channel_snapshot", "completed", "Channel public stats synced")
    return dict(updated or channel_row)


async def _fetch_recent_upload_ids(access_token: str, playlist_id: str, max_videos: int) -> list[str]:
    video_ids: list[str] = []
    page_token = None
    while len(video_ids) < max_videos:
        payload = await _youtube_get(
            YOUTUBE_PLAYLIST_ITEMS_URL,
            access_token,
            {
                "part": "contentDetails",
                "playlistId": playlist_id,
                "maxResults": min(50, max_videos - len(video_ids)),
                **({"pageToken": page_token} if page_token else {}),
            },
        )
        for item in payload.get("items") or []:
            video_id = (item.get("contentDetails") or {}).get("videoId")
            if video_id:
                video_ids.append(video_id)
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return video_ids


def _video_snapshot(item: dict) -> dict:
    snippet = item.get("snippet") or {}
    statistics = item.get("statistics") or {}
    content_details = item.get("contentDetails") or {}
    status_payload = item.get("status") or {}
    thumbnails = snippet.get("thumbnails") or {}
    thumbnail = (
        thumbnails.get("maxres")
        or thumbnails.get("standard")
        or thumbnails.get("high")
        or thumbnails.get("medium")
        or thumbnails.get("default")
        or {}
    )
    return {
        "youtube_video_id": item.get("id"),
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "thumbnail_url": thumbnail.get("url"),
        "published_at": snippet.get("publishedAt"),
        "duration": content_details.get("duration"),
        "view_count": _int_or_none(statistics.get("viewCount")) or 0,
        "like_count": _int_or_none(statistics.get("likeCount")),
        "comment_count": _int_or_none(statistics.get("commentCount")),
        "privacy_status": status_payload.get("privacyStatus"),
    }


def _select_smart_realtime_ids(
    channel_id: str,
    all_video_ids: list[str],
    recent_always: int,
    hot_threshold_per_hour: int,
    calibration_hours: int,
) -> tuple[list[str], dict[str, str], dict[str, float], str]:
    now = datetime.now(timezone.utc)
    recent_ids = set(all_video_ids[:max(0, recent_always)])
    tiers: dict[str, str] = {}
    hourly_rates: dict[str, float] = {}

    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT MIN(captured_at) AS first_snapshot_at
                FROM admin_youtube_realtime_snapshots
                WHERE channel_id = %s::uuid
                """,
                (channel_id,),
            )
            first_row = cur.fetchone() or {}
            first_snapshot_at = first_row.get("first_snapshot_at")
            if not first_snapshot_at or first_snapshot_at > now - timedelta(hours=calibration_hours):
                return (
                    all_video_ids,
                    {video_id: "calibration" for video_id in all_video_ids},
                    {video_id: 0.0 for video_id in all_video_ids},
                    "calibration",
                )

            cur.execute(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (youtube_video_id)
                        youtube_video_id,
                        view_count,
                        captured_at
                    FROM admin_youtube_realtime_snapshots
                    WHERE channel_id = %s::uuid
                    ORDER BY youtube_video_id, captured_at DESC
                ),
                baseline AS (
                    SELECT DISTINCT ON (youtube_video_id)
                        youtube_video_id,
                        view_count,
                        captured_at
                    FROM admin_youtube_realtime_snapshots
                    WHERE channel_id = %s::uuid
                      AND captured_at >= now() - (%s::text || ' hours')::interval
                    ORDER BY youtube_video_id, captured_at ASC
                )
                SELECT
                    latest.youtube_video_id,
                    latest.view_count AS latest_views,
                    latest.captured_at AS latest_captured_at,
                    baseline.view_count AS baseline_views,
                    baseline.captured_at AS baseline_captured_at,
                    CASE
                        WHEN baseline.captured_at IS NULL THEN NULL
                        ELSE EXTRACT(EPOCH FROM (latest.captured_at - baseline.captured_at)) / 3600.0
                    END AS elapsed_hours
                FROM latest
                LEFT JOIN baseline ON baseline.youtube_video_id = latest.youtube_video_id
                """,
                (channel_id, channel_id, calibration_hours),
            )
            stats = {row["youtube_video_id"]: dict(row) for row in cur.fetchall()}

    selected: list[str] = []
    for video_id in all_video_ids:
        row = stats.get(video_id)
        latest_at = row.get("latest_captured_at") if row else None
        elapsed_hours = _float_or_none(row.get("elapsed_hours")) if row else None
        baseline_views = _int_or_none(row.get("baseline_views")) if row else None
        latest_views = _int_or_none(row.get("latest_views")) if row else None
        hourly_rate = 0.0
        if elapsed_hours and elapsed_hours > 0 and latest_views is not None and baseline_views is not None:
            hourly_rate = max((latest_views - baseline_views) / elapsed_hours, 0.0)
        hourly_rates[video_id] = hourly_rate

        is_recent = video_id in recent_ids
        is_hot = hourly_rate >= hot_threshold_per_hour
        is_due_hourly = not latest_at or latest_at <= now - timedelta(minutes=55)
        if is_recent:
            tiers[video_id] = "recent"
            selected.append(video_id)
        elif is_hot:
            tiers[video_id] = "hot"
            selected.append(video_id)
        elif is_due_hourly:
            tiers[video_id] = "hourly"
            selected.append(video_id)
        else:
            tiers[video_id] = "hourly"

    return selected, tiers, hourly_rates, "smart"


async def _sync_realtime_snapshots(
    channel_id: str,
    admin_user_id: str,
    max_videos: int = 50,
    strategy: str = "recent",
    recent_always: int = 30,
    hot_threshold_per_hour: int = 100,
    calibration_hours: int = 4,
) -> dict:
    channel_row = await _sync_channel_snapshot(channel_id, admin_user_id)
    _, access_token = await _get_youtube_access_token(channel_id, admin_user_id)
    playlist_id = channel_row.get("uploads_playlist_id")
    if not playlist_id:
        raise HTTPException(status_code=400, detail="Channel uploads playlist is missing")

    all_video_ids = await _fetch_recent_upload_ids(access_token, playlist_id, max(1, min(max_videos, 500)))
    tiers: dict[str, str] = {video_id: "recent" for video_id in all_video_ids}
    hourly_rates: dict[str, float] = {video_id: 0.0 for video_id in all_video_ids}
    selection_mode = "recent"
    if strategy == "smart":
        video_ids, tiers, hourly_rates, selection_mode = _select_smart_realtime_ids(
            channel_id,
            all_video_ids,
            recent_always=recent_always,
            hot_threshold_per_hour=hot_threshold_per_hour,
            calibration_hours=calibration_hours,
        )
    elif strategy == "all":
        video_ids = all_video_ids
        tiers = {video_id: "calibration" for video_id in all_video_ids}
        selection_mode = "all"
    else:
        video_ids = all_video_ids[:max(1, min(max_videos, 500))]

    snapshots: list[dict] = []
    for batch in _chunks(video_ids, 50):
        payload = await _youtube_get(
            YOUTUBE_VIDEOS_URL,
            access_token,
            {
                "part": "snippet,statistics,contentDetails,status",
                "id": ",".join(batch),
                "maxResults": 50,
            },
        )
        snapshots.extend(_video_snapshot(item) for item in payload.get("items") or [])

    with _db_connect() as conn:
        with conn.cursor() as cur:
            for item in snapshots:
                if not item.get("youtube_video_id"):
                    continue
                cur.execute(
                    """
                    INSERT INTO admin_youtube_videos (
                        channel_id,
                        youtube_video_id,
                        title,
                        description,
                        thumbnail_url,
                        published_at,
                        duration,
                        view_count,
                        like_count,
                        comment_count,
                        privacy_status,
                        last_synced_at,
                        updated_at,
                        realtime_tracking_tier,
                        realtime_hourly_view_rate,
                        realtime_last_classified_at,
                        realtime_next_snapshot_at
                    )
                    VALUES (
                        %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        now(), now(), %s, %s, now(),
                        CASE WHEN %s IN ('recent', 'hot', 'calibration') THEN now() + interval '5 minutes' ELSE now() + interval '1 hour' END
                    )
                    ON CONFLICT (channel_id, youtube_video_id)
                    DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        thumbnail_url = EXCLUDED.thumbnail_url,
                        published_at = EXCLUDED.published_at,
                        duration = EXCLUDED.duration,
                        view_count = EXCLUDED.view_count,
                        like_count = EXCLUDED.like_count,
                        comment_count = EXCLUDED.comment_count,
                        privacy_status = EXCLUDED.privacy_status,
                        last_synced_at = now(),
                        updated_at = now(),
                        realtime_tracking_tier = EXCLUDED.realtime_tracking_tier,
                        realtime_hourly_view_rate = EXCLUDED.realtime_hourly_view_rate,
                        realtime_last_classified_at = now(),
                        realtime_next_snapshot_at = EXCLUDED.realtime_next_snapshot_at
                    """,
                    (
                        channel_id,
                        item["youtube_video_id"],
                        item["title"],
                        item["description"],
                        item["thumbnail_url"],
                        item["published_at"],
                        item["duration"],
                        item["view_count"],
                        item["like_count"],
                        item["comment_count"],
                        item["privacy_status"],
                        tiers.get(item["youtube_video_id"], "hourly"),
                        hourly_rates.get(item["youtube_video_id"], 0.0),
                        tiers.get(item["youtube_video_id"], "hourly"),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO admin_youtube_realtime_snapshots (
                        channel_id, youtube_video_id, view_count, like_count, comment_count
                    )
                    VALUES (%s::uuid, %s, %s, %s, %s)
                    """,
                    (
                        channel_id,
                        item["youtube_video_id"],
                        item["view_count"],
                        item["like_count"],
                        item["comment_count"],
                    ),
                )
            for video_id in set(all_video_ids) - {item.get("youtube_video_id") for item in snapshots}:
                cur.execute(
                    """
                    UPDATE admin_youtube_videos
                    SET realtime_tracking_tier = %s,
                        realtime_hourly_view_rate = %s,
                        realtime_last_classified_at = now(),
                        realtime_next_snapshot_at = CASE
                            WHEN %s IN ('recent', 'hot', 'calibration') THEN now() + interval '5 minutes'
                            ELSE now() + interval '1 hour'
                        END,
                        updated_at = now()
                    WHERE channel_id = %s::uuid
                      AND youtube_video_id = %s
                    """,
                    (
                        tiers.get(video_id, "hourly"),
                        hourly_rates.get(video_id, 0.0),
                        tiers.get(video_id, "hourly"),
                        channel_id,
                        video_id,
                    ),
                )
        conn.commit()

    _log_youtube_sync(
        channel_id,
        admin_user_id,
        "realtime_snapshot",
        "completed",
        f"Captured {len(snapshots)} video counter snapshots ({selection_mode})",
    )
    upload_pages = max(1, (len(all_video_ids) + 49) // 50)
    video_pages = max(1, (len(video_ids) + 49) // 50) if video_ids else 0
    return {
        "captured_videos": len(snapshots),
        "tracked_videos": len(all_video_ids),
        "selection_mode": selection_mode,
        "quota_estimate_units": upload_pages + video_pages + 1,
    }


async def _run_analytics_report(
    access_token: str,
    start_date: date,
    end_date: date,
    metrics: list[str],
    dimensions: str | None = None,
    filters: str | None = None,
    sort: str | None = None,
    max_results: int | None = None,
    currency: str = "USD",
) -> list[dict]:
    params = {
        "ids": "channel==MINE",
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "metrics": ",".join(metrics),
        "currency": currency,
    }
    if dimensions:
        params["dimensions"] = dimensions
    if filters:
        params["filters"] = filters
    if sort:
        params["sort"] = sort
    if max_results:
        params["maxResults"] = str(max_results)

    payload = await _youtube_get(YOUTUBE_ANALYTICS_REPORTS_URL, access_token, params)
    headers = [header.get("name") for header in payload.get("columnHeaders") or []]
    return [dict(zip(headers, row)) for row in payload.get("rows") or []]


async def _run_analytics_report_with_revenue_fallback(
    access_token: str,
    start_date: date,
    end_date: date,
    base_metrics: list[str],
    revenue_metrics: list[str],
    **kwargs,
) -> tuple[list[dict], list[str]]:
    try:
        rows = await _run_analytics_report(
            access_token,
            start_date,
            end_date,
            [*base_metrics, *revenue_metrics],
            **kwargs,
        )
        return rows, [*base_metrics, *revenue_metrics]
    except HTTPException as exc:
        print(f"[AdminYouTube] Revenue analytics fallback: {exc.detail}")
        rows = await _run_analytics_report(access_token, start_date, end_date, base_metrics, **kwargs)
        return rows, base_metrics


async def _sync_analytics_metrics(
    channel_id: str,
    admin_user_id: str,
    days: int = 7,
    currency: str = "USD",
    start_date_override: date | None = None,
) -> dict:
    await _sync_channel_snapshot(channel_id, admin_user_id)
    _, access_token = await _get_youtube_access_token(channel_id, admin_user_id)
    end_date = datetime.now(timezone.utc).date()
    start_date = start_date_override or end_date - timedelta(days=max(1, min(days, 90)) - 1)

    base_metrics = [
        "views",
        "estimatedMinutesWatched",
        "averageViewDuration",
        "averageViewPercentage",
        "subscribersGained",
        "subscribersLost",
    ]
    revenue_metrics = ["estimatedRevenue", "estimatedAdRevenue", "cpm", "playbackBasedCpm"]

    daily_rows, _ = await _run_analytics_report_with_revenue_fallback(
        access_token,
        start_date,
        end_date,
        base_metrics,
        revenue_metrics,
        dimensions="day",
        currency=currency,
    )
    country_rows, _ = await _run_analytics_report_with_revenue_fallback(
        access_token,
        start_date,
        end_date,
        ["views", "estimatedMinutesWatched"],
        ["estimatedRevenue"],
        dimensions="country",
        sort="-views",
        max_results=50,
        currency=currency,
    )
    video_rows, _ = await _run_analytics_report_with_revenue_fallback(
        access_token,
        start_date,
        end_date,
        base_metrics,
        revenue_metrics,
        dimensions="video",
        sort="-views",
        max_results=200,
        currency=currency,
    )

    with _db_connect() as conn:
        with conn.cursor() as cur:
            for row in daily_rows:
                cur.execute(
                    """
                    INSERT INTO admin_youtube_daily_metrics (
                        channel_id,
                        metric_date,
                        views,
                        estimated_minutes_watched,
                        average_view_duration_seconds,
                        average_view_percentage,
                        subscribers_gained,
                        subscribers_lost,
                        estimated_revenue,
                        estimated_ad_revenue,
                        cpm,
                        playback_based_cpm,
                        currency,
                        updated_at
                    )
                    VALUES (
                        %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()
                    )
                    ON CONFLICT (channel_id, metric_date)
                    DO UPDATE SET
                        views = EXCLUDED.views,
                        estimated_minutes_watched = EXCLUDED.estimated_minutes_watched,
                        average_view_duration_seconds = EXCLUDED.average_view_duration_seconds,
                        average_view_percentage = EXCLUDED.average_view_percentage,
                        subscribers_gained = EXCLUDED.subscribers_gained,
                        subscribers_lost = EXCLUDED.subscribers_lost,
                        estimated_revenue = EXCLUDED.estimated_revenue,
                        estimated_ad_revenue = EXCLUDED.estimated_ad_revenue,
                        cpm = EXCLUDED.cpm,
                        playback_based_cpm = EXCLUDED.playback_based_cpm,
                        currency = EXCLUDED.currency,
                        updated_at = now()
                    """,
                    (
                        channel_id,
                        row.get("day"),
                        _int_or_none(row.get("views")),
                        _float_or_none(row.get("estimatedMinutesWatched")),
                        _float_or_none(row.get("averageViewDuration")),
                        _float_or_none(row.get("averageViewPercentage")),
                        _int_or_none(row.get("subscribersGained")),
                        _int_or_none(row.get("subscribersLost")),
                        _float_or_none(row.get("estimatedRevenue")),
                        _float_or_none(row.get("estimatedAdRevenue")),
                        _float_or_none(row.get("cpm")),
                        _float_or_none(row.get("playbackBasedCpm")),
                        currency,
                    ),
                )
            for row in country_rows:
                country = row.get("country")
                if not country:
                    continue
                cur.execute(
                    """
                    INSERT INTO admin_youtube_country_metrics (
                        channel_id,
                        period_start,
                        period_end,
                        country_code,
                        views,
                        estimated_minutes_watched,
                        estimated_revenue,
                        currency,
                        updated_at
                    )
                    VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (channel_id, period_start, period_end, country_code)
                    DO UPDATE SET
                        views = EXCLUDED.views,
                        estimated_minutes_watched = EXCLUDED.estimated_minutes_watched,
                        estimated_revenue = EXCLUDED.estimated_revenue,
                        currency = EXCLUDED.currency,
                        updated_at = now()
                    """,
                    (
                        channel_id,
                        start_date,
                        end_date,
                        country,
                        _int_or_none(row.get("views")),
                        _float_or_none(row.get("estimatedMinutesWatched")),
                        _float_or_none(row.get("estimatedRevenue")),
                        currency,
                    ),
                )
            for row in video_rows:
                video_id = row.get("video")
                if not video_id:
                    continue
                cur.execute(
                    """
                    INSERT INTO admin_youtube_video_daily_metrics (
                        channel_id,
                        youtube_video_id,
                        period_start,
                        period_end,
                        views,
                        estimated_minutes_watched,
                        average_view_duration_seconds,
                        average_view_percentage,
                        subscribers_gained,
                        subscribers_lost,
                        estimated_revenue,
                        estimated_ad_revenue,
                        cpm,
                        playback_based_cpm,
                        currency,
                        updated_at
                    )
                    VALUES (
                        %s::uuid, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, now()
                    )
                    ON CONFLICT (channel_id, youtube_video_id, period_start, period_end)
                    DO UPDATE SET
                        views = EXCLUDED.views,
                        estimated_minutes_watched = EXCLUDED.estimated_minutes_watched,
                        average_view_duration_seconds = EXCLUDED.average_view_duration_seconds,
                        average_view_percentage = EXCLUDED.average_view_percentage,
                        subscribers_gained = EXCLUDED.subscribers_gained,
                        subscribers_lost = EXCLUDED.subscribers_lost,
                        estimated_revenue = EXCLUDED.estimated_revenue,
                        estimated_ad_revenue = EXCLUDED.estimated_ad_revenue,
                        cpm = EXCLUDED.cpm,
                        playback_based_cpm = EXCLUDED.playback_based_cpm,
                        currency = EXCLUDED.currency,
                        updated_at = now()
                    """,
                    (
                        channel_id,
                        video_id,
                        start_date,
                        end_date,
                        _int_or_none(row.get("views")),
                        _float_or_none(row.get("estimatedMinutesWatched")),
                        _float_or_none(row.get("averageViewDuration")),
                        _float_or_none(row.get("averageViewPercentage")),
                        _int_or_none(row.get("subscribersGained")),
                        _int_or_none(row.get("subscribersLost")),
                        _float_or_none(row.get("estimatedRevenue")),
                        _float_or_none(row.get("estimatedAdRevenue")),
                        _float_or_none(row.get("cpm")),
                        _float_or_none(row.get("playbackBasedCpm")),
                        currency,
                    ),
                )
        conn.commit()

    _log_youtube_sync(
        channel_id,
        admin_user_id,
        "analytics",
        "completed",
        f"Synced {len(daily_rows)} daily, {len(country_rows)} country, {len(video_rows)} video analytics rows",
    )
    return {
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat(),
        "daily_rows": len(daily_rows),
        "country_rows": len(country_rows),
        "video_rows": len(video_rows),
        "analytics_queries": 3,
    }


def _connected_admin_youtube_channels() -> list[dict]:
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text AS id, admin_user_id::text AS admin_user_id, title
                FROM admin_youtube_channels
                WHERE status = 'connected'
                ORDER BY connected_at DESC
                """
            )
            return [dict(row) for row in cur.fetchall()]


async def run_scheduled_youtube_realtime_sync() -> dict:
    channels = _connected_admin_youtube_channels()
    results = []
    for channel in channels:
        try:
            result = await _sync_realtime_snapshots(
                channel["id"],
                channel["admin_user_id"],
                max_videos=settings.ADMIN_YOUTUBE_REALTIME_MAX_VIDEOS,
                strategy="smart",
                recent_always=settings.ADMIN_YOUTUBE_REALTIME_RECENT_ALWAYS,
                hot_threshold_per_hour=settings.ADMIN_YOUTUBE_REALTIME_HOT_THRESHOLD_PER_HOUR,
                calibration_hours=settings.ADMIN_YOUTUBE_REALTIME_CALIBRATION_HOURS,
            )
            results.append({"channel_id": channel["id"], "ok": True, **result})
        except Exception as exc:
            print(f"[AdminYouTubeScheduler] Realtime failed for {channel.get('title')}: {exc}")
            _log_youtube_sync(channel["id"], channel["admin_user_id"], "realtime_scheduler", "failed", str(exc))
            results.append({"channel_id": channel["id"], "ok": False, "error": str(exc)})
    return {"channels": results}


async def run_scheduled_youtube_analytics_sync() -> dict:
    channels = _connected_admin_youtube_channels()
    results = []
    for channel in channels:
        try:
            result = await _sync_analytics_metrics(
                channel["id"],
                channel["admin_user_id"],
                days=settings.ADMIN_YOUTUBE_ANALYTICS_SYNC_DAYS,
                currency=settings.ADMIN_YOUTUBE_ANALYTICS_CURRENCY.upper(),
            )
            results.append({"channel_id": channel["id"], "ok": True, **result})
        except Exception as exc:
            print(f"[AdminYouTubeScheduler] Analytics failed for {channel.get('title')}: {exc}")
            _log_youtube_sync(channel["id"], channel["admin_user_id"], "analytics_scheduler", "failed", str(exc))
            results.append({"channel_id": channel["id"], "ok": False, "error": str(exc)})
    return {"channels": results}


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    user_id = current_user.get("id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authenticated user",
        )

    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id::text AS user_id, email, role
                    FROM admin_users
                    WHERE user_id = %s::uuid
                    LIMIT 1
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[Admin] Access check failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin access check unavailable",
        ) from exc

    if not row:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return {
        "id": current_user["id"],
        "email": current_user.get("email"),
        "admin_email": row["email"],
        "role": row["role"],
    }


@router.get("/me")
async def admin_me(admin_user: dict = Depends(require_admin)):
    return {
        "is_admin": True,
        "user_id": admin_user["id"],
        "email": admin_user["email"],
        "role": admin_user["role"],
    }


@router.get("/youtube/connect")
async def youtube_connect(admin_user: dict = Depends(require_admin)):
    _require_youtube_oauth_config()
    state = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO admin_youtube_oauth_states (
                        state, admin_user_id, expires_at
                    )
                    VALUES (%s, %s::uuid, %s)
                    """,
                    (state, admin_user["id"], expires_at),
                )
            conn.commit()
    except Exception as exc:
        print(f"[AdminYouTube] State insert failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not start YouTube OAuth",
        ) from exc

    auth_params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": settings.YOUTUBE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(YOUTUBE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(auth_params)}"

    return {"auth_url": auth_url, "expires_at": expires_at.isoformat()}


@router.get("/youtube/oauth/callback")
async def youtube_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    if error:
        return RedirectResponse(
            _frontend_admin_url({"youtube": "error", "reason": error}),
            status_code=status.HTTP_302_FOUND,
        )
    if not code or not state:
        return RedirectResponse(
            _frontend_admin_url({"youtube": "error", "reason": "missing_code"}),
            status_code=status.HTTP_302_FOUND,
        )

    _require_youtube_oauth_config()

    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT state, admin_user_id::text AS admin_user_id
                    FROM admin_youtube_oauth_states
                    WHERE state = %s
                      AND consumed_at IS NULL
                      AND expires_at > now()
                    LIMIT 1
                    """,
                    (state,),
                )
                state_row = cur.fetchone()
                if not state_row:
                    return RedirectResponse(
                        _frontend_admin_url({"youtube": "error", "reason": "invalid_state"}),
                        status_code=status.HTTP_302_FOUND,
                    )
                cur.execute(
                    """
                    UPDATE admin_youtube_oauth_states
                    SET consumed_at = now()
                    WHERE state = %s
                    """,
                    (state,),
                )
            conn.commit()

        token_payload = await _exchange_oauth_code(code)
        channel = await _fetch_youtube_channel(token_payload["access_token"])
        channel_row = _store_youtube_connection(
            state_row["admin_user_id"],
            channel,
            token_payload,
        )
        return RedirectResponse(
            _frontend_admin_url(
                {
                    "youtube": "connected",
                    "channel": str(channel_row["id"]),
                }
            ),
            status_code=status.HTTP_302_FOUND,
        )
    except HTTPException as exc:
        print(f"[AdminYouTube] OAuth callback error: {exc.detail}")
        return RedirectResponse(
            _frontend_admin_url({"youtube": "error", "reason": "callback_failed"}),
            status_code=status.HTTP_302_FOUND,
        )
    except Exception as exc:
        print(f"[AdminYouTube] OAuth callback unexpected error: {exc}")
        return RedirectResponse(
            _frontend_admin_url({"youtube": "error", "reason": "callback_failed"}),
            status_code=status.HTTP_302_FOUND,
        )


@router.get("/youtube/channels")
async def list_youtube_channels(admin_user: dict = Depends(require_admin)):
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id::text AS id,
                        youtube_channel_id,
                        title,
                        description,
                        custom_url,
                        thumbnail_url,
                        country,
                        subscriber_count,
                        view_count,
                        video_count,
                        uploads_playlist_id,
                        status,
                        connected_at,
                        last_synced_at,
                        updated_at
                    FROM admin_youtube_channels
                    WHERE admin_user_id = %s::uuid
                    ORDER BY connected_at DESC
                    """,
                    (admin_user["id"],),
                )
                rows = cur.fetchall()
        return {"channels": [dict(row) for row in rows]}
    except Exception as exc:
        print(f"[AdminYouTube] List channels failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not load YouTube channels",
        ) from exc


@router.post("/youtube/channels/{channel_id}/sync/realtime")
async def sync_youtube_realtime(
    channel_id: str,
    max_videos: int = Query(default=500, ge=1, le=500),
    strategy: str = Query(default="smart", pattern="^(recent|all|smart)$"),
    recent_always: int = Query(default=30, ge=1, le=100),
    hot_threshold_per_hour: int = Query(default=100, ge=1, le=10000),
    calibration_hours: int = Query(default=4, ge=1, le=24),
    admin_user: dict = Depends(require_admin),
):
    try:
        result = await _sync_realtime_snapshots(
            channel_id,
            admin_user["id"],
            max_videos=max_videos,
            strategy=strategy,
            recent_always=recent_always,
            hot_threshold_per_hour=hot_threshold_per_hour,
            calibration_hours=calibration_hours,
        )
        return {"ok": True, **result}
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[AdminYouTube] Realtime sync failed: {exc}")
        _log_youtube_sync(channel_id, admin_user["id"], "realtime_snapshot", "failed", str(exc))
        raise HTTPException(status_code=503, detail="YouTube realtime sync failed") from exc


@router.post("/youtube/channels/{channel_id}/sync/analytics")
async def sync_youtube_analytics(
    channel_id: str,
    days: int = Query(default=30, ge=1, le=90),
    analytics_range: str | None = Query(default=None, alias="range", pattern="^(7d|30d|90d|all)$"),
    currency: str = Query(default="USD", min_length=3, max_length=3),
    admin_user: dict = Depends(require_admin),
):
    try:
        start_date_override = date(2025, 1, 14) if analytics_range == "all" else None
        if analytics_range in {"7d", "30d", "90d"}:
            days = int(analytics_range[:-1])
        result = await _sync_analytics_metrics(
            channel_id,
            admin_user["id"],
            days=days,
            currency=currency.upper(),
            start_date_override=start_date_override,
        )
        return {"ok": True, **result}
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[AdminYouTube] Analytics sync failed: {exc}")
        _log_youtube_sync(channel_id, admin_user["id"], "analytics", "failed", str(exc))
        raise HTTPException(status_code=503, detail="YouTube analytics sync failed") from exc


@router.post("/youtube/sync")
async def sync_youtube_admin_data(
    realtime: bool = Query(default=True),
    analytics: bool = Query(default=True),
    max_videos: int = Query(default=500, ge=1, le=500),
    days: int = Query(default=30, ge=1, le=90),
    analytics_range: str | None = Query(default=None, pattern="^(7d|30d|90d|all)$"),
    currency: str = Query(default="USD", min_length=3, max_length=3),
    realtime_strategy: str = Query(default="smart", pattern="^(recent|all|smart)$"),
    recent_always: int = Query(default=30, ge=1, le=100),
    hot_threshold_per_hour: int = Query(default=100, ge=1, le=10000),
    calibration_hours: int = Query(default=4, ge=1, le=24),
    admin_user: dict = Depends(require_admin),
):
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text AS id
                FROM admin_youtube_channels
                WHERE admin_user_id = %s::uuid
                  AND status = 'connected'
                ORDER BY connected_at DESC
                """,
                (admin_user["id"],),
            )
            channels = [dict(row) for row in cur.fetchall()]

    results = []
    for channel in channels:
        item = {"channel_id": channel["id"], "realtime": None, "analytics": None}
        if realtime:
            item["realtime"] = await _sync_realtime_snapshots(
                channel["id"],
                admin_user["id"],
                max_videos=max_videos,
                strategy=realtime_strategy,
                recent_always=recent_always,
                hot_threshold_per_hour=hot_threshold_per_hour,
                calibration_hours=calibration_hours,
            )
        if analytics:
            start_date_override = date(2025, 1, 14) if analytics_range == "all" else None
            if analytics_range in {"7d", "30d", "90d"}:
                days = int(analytics_range[:-1])
            item["analytics"] = await _sync_analytics_metrics(
                channel["id"],
                admin_user["id"],
                days=days,
                currency=currency.upper(),
                start_date_override=start_date_override,
            )
        results.append(item)

    return {"ok": True, "channels": results}


@router.get("/youtube/realtime")
async def youtube_realtime_summary(
    hours: int = Query(default=48, ge=1, le=168),
    admin_user: dict = Depends(require_admin),
):
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH hourly AS (
                        SELECT
                            ch.id::text AS channel_id,
                            ch.title AS channel_title,
                            date_trunc('hour', snap.captured_at) AS bucket,
                            snap.youtube_video_id,
                            MAX(snap.view_count) AS view_count
                        FROM admin_youtube_realtime_snapshots snap
                        JOIN admin_youtube_channels ch ON ch.id = snap.channel_id
                        WHERE ch.admin_user_id = %s::uuid
                          AND snap.captured_at >= now() - ((%s + 2)::text || ' hours')::interval
                        GROUP BY ch.id, ch.title, bucket, snap.youtube_video_id
                    ),
                    deltas AS (
                        SELECT
                            channel_id,
                            channel_title,
                            bucket,
                            youtube_video_id,
                            view_count - LAG(view_count) OVER (
                                PARTITION BY channel_id, youtube_video_id
                                ORDER BY bucket ASC
                            ) AS delta_views
                        FROM hourly
                    )
                    SELECT
                        bucket,
                        COALESCE(SUM(GREATEST(delta_views, 0)), 0)::bigint AS views
                    FROM deltas
                    WHERE bucket >= now() - (%s::text || ' hours')::interval
                    GROUP BY bucket
                    ORDER BY bucket ASC
                    """,
                    (admin_user["id"], hours, hours),
                )
                hourly_rows = [dict(row) for row in cur.fetchall()]

                cur.execute(
                    """
                    WITH latest AS (
                        SELECT DISTINCT ON (snap.channel_id, snap.youtube_video_id)
                            snap.channel_id,
                            snap.youtube_video_id,
                            snap.view_count,
                            snap.captured_at
                        FROM admin_youtube_realtime_snapshots snap
                        JOIN admin_youtube_channels ch ON ch.id = snap.channel_id
                        WHERE ch.admin_user_id = %s::uuid
                          AND snap.captured_at >= now() - (%s::text || ' hours')::interval
                        ORDER BY snap.channel_id, snap.youtube_video_id, snap.captured_at DESC
                    ),
                    baseline AS (
                        SELECT DISTINCT ON (snap.channel_id, snap.youtube_video_id)
                            snap.channel_id,
                            snap.youtube_video_id,
                            snap.view_count,
                            snap.captured_at
                        FROM admin_youtube_realtime_snapshots snap
                        JOIN admin_youtube_channels ch ON ch.id = snap.channel_id
                        WHERE ch.admin_user_id = %s::uuid
                          AND snap.captured_at >= now() - (%s::text || ' hours')::interval
                        ORDER BY snap.channel_id, snap.youtube_video_id, snap.captured_at ASC
                    )
                    SELECT
                        ch.id::text AS channel_id,
                        ch.title AS channel_title,
                        v.youtube_video_id,
                        v.title,
                        v.thumbnail_url,
                        latest.view_count AS current_views,
                        GREATEST(latest.view_count - baseline.view_count, 0)::bigint AS views_delta
                    FROM latest
                    JOIN baseline ON baseline.channel_id = latest.channel_id
                        AND baseline.youtube_video_id = latest.youtube_video_id
                    JOIN admin_youtube_channels ch ON ch.id = latest.channel_id
                    LEFT JOIN admin_youtube_videos v ON v.channel_id = latest.channel_id
                        AND v.youtube_video_id = latest.youtube_video_id
                    ORDER BY views_delta DESC
                    LIMIT 20
                    """,
                    (admin_user["id"], hours, admin_user["id"], hours),
                )
                top_videos = [dict(row) for row in cur.fetchall()]

        return {
            "hours": hours,
            "total_views": sum(int(row.get("views") or 0) for row in hourly_rows),
            "hourly": [
                {
                    "bucket": row["bucket"].isoformat() if row.get("bucket") else None,
                    "views": int(row.get("views") or 0),
                }
                for row in hourly_rows
            ],
            "top_videos": top_videos,
        }
    except Exception as exc:
        print(f"[AdminYouTube] Realtime summary failed: {exc}")
        raise HTTPException(status_code=503, detail="Could not load realtime YouTube summary") from exc


@router.get("/youtube/channels/{channel_id}/analytics")
async def youtube_channel_analytics(
    channel_id: str,
    days: int = Query(default=30, ge=1, le=90),
    admin_user: dict = Depends(require_admin),
):
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        dm.metric_date::text AS date,
                        dm.views,
                        dm.estimated_minutes_watched,
                        dm.average_view_duration_seconds,
                        dm.average_view_percentage,
                        dm.subscribers_gained,
                        dm.subscribers_lost,
                        dm.estimated_revenue,
                        dm.estimated_ad_revenue,
                        dm.cpm,
                        dm.playback_based_cpm,
                        dm.currency,
                        dm.updated_at AS updated_at
                    FROM admin_youtube_daily_metrics dm
                    JOIN admin_youtube_channels ch ON ch.id = dm.channel_id
                    WHERE dm.channel_id = %s::uuid
                      AND ch.admin_user_id = %s::uuid
                      AND dm.metric_date >= current_date - (%s::text || ' days')::interval
                    ORDER BY dm.metric_date ASC
                    """,
                    (channel_id, admin_user["id"], days),
                )
                daily_rows = [dict(row) for row in cur.fetchall()]

                cur.execute(
                    """
                    SELECT
                        cm.country_code,
                        cm.views,
                        cm.estimated_minutes_watched,
                        cm.estimated_revenue,
                        cm.currency,
                        cm.period_start,
                        cm.period_end,
                        cm.updated_at AS updated_at
                    FROM admin_youtube_country_metrics cm
                    JOIN admin_youtube_channels ch ON ch.id = cm.channel_id
                    WHERE cm.channel_id = %s::uuid
                      AND ch.admin_user_id = %s::uuid
                    ORDER BY cm.period_end DESC, cm.views DESC NULLS LAST
                    LIMIT 50
                    """,
                    (channel_id, admin_user["id"]),
                )
                countries = [dict(row) for row in cur.fetchall()]

                cur.execute(
                    """
                    SELECT
                        vm.youtube_video_id,
                        COALESCE(v.title, vm.youtube_video_id) AS title,
                        v.thumbnail_url,
                        vm.views,
                        vm.estimated_minutes_watched,
                        vm.average_view_duration_seconds,
                        vm.average_view_percentage,
                        vm.subscribers_gained,
                        vm.subscribers_lost,
                        vm.estimated_revenue,
                        vm.cpm,
                        vm.playback_based_cpm,
                        vm.currency,
                        vm.period_start,
                        vm.period_end
                    FROM admin_youtube_video_daily_metrics vm
                    JOIN admin_youtube_channels ch ON ch.id = vm.channel_id
                    LEFT JOIN admin_youtube_videos v ON v.channel_id = vm.channel_id
                        AND v.youtube_video_id = vm.youtube_video_id
                    WHERE vm.channel_id = %s::uuid
                      AND ch.admin_user_id = %s::uuid
                    ORDER BY vm.period_end DESC, vm.views DESC NULLS LAST
                    LIMIT 50
                    """,
                    (channel_id, admin_user["id"]),
                )
                videos = [dict(row) for row in cur.fetchall()]

        return {
            "daily": daily_rows,
            "countries": countries,
            "videos": videos,
        }
    except Exception as exc:
        print(f"[AdminYouTube] Channel analytics failed: {exc}")
        raise HTTPException(status_code=503, detail="Could not load channel analytics") from exc


@router.get("/overview")
async def admin_overview(
    overview_range: str = Query(default="30d", alias="range", pattern="^(7d|30d|90d|all)$"),
    admin_user: dict = Depends(require_admin),
):
    today = date.today()
    range_days = {"7d": 7, "30d": 30, "90d": 90}
    period_start = date(2025, 1, 14) if overview_range == "all" else today - timedelta(days=range_days[overview_range] - 1)
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        COUNT(*)::int AS channel_count,
                        COALESCE(SUM(subscriber_count), 0)::bigint AS subscriber_count,
                        COALESCE(SUM(view_count), 0)::bigint AS view_count,
                        COALESCE(SUM(video_count), 0)::bigint AS video_count
                    FROM admin_youtube_channels
                    WHERE admin_user_id = %s::uuid
                      AND status = 'connected'
                    """,
                    (admin_user["id"],),
                )
                youtube = cur.fetchone() or {}

                cur.execute(
                    """
                    SELECT
                        dm.metric_date::text AS date,
                        COALESCE(SUM(dm.estimated_revenue), 0)::float AS channel_revenue,
                        COALESCE(SUM(dm.views), 0)::bigint AS views,
                        COALESCE(SUM(dm.engaged_views), 0)::bigint AS engaged_views
                    FROM admin_youtube_daily_metrics dm
                    JOIN admin_youtube_channels ch ON ch.id = dm.channel_id
                    WHERE ch.admin_user_id = %s::uuid
                      AND dm.metric_date >= %s
                    GROUP BY dm.metric_date
                    ORDER BY dm.metric_date ASC
                    """,
                    (admin_user["id"], period_start),
                )
                daily_rows = [dict(row) for row in cur.fetchall()]

                cur.execute(
                    """
                    SELECT
                        ch.title AS source,
                        'YouTube channel' AS type,
                        COALESCE(SUM(dm.estimated_revenue), 0)::float AS revenue,
                        0::float AS cost,
                        COALESCE(SUM(dm.estimated_revenue), 0)::float AS net,
                        CASE WHEN COUNT(dm.id) > 0 THEN 'synced' ELSE 'not synced' END AS status
                    FROM admin_youtube_channels ch
                    LEFT JOIN admin_youtube_daily_metrics dm ON dm.channel_id = ch.id
                        AND dm.metric_date >= %s
                    WHERE ch.admin_user_id = %s::uuid
                      AND ch.status = 'connected'
                    GROUP BY ch.id, ch.title
                    ORDER BY revenue DESC
                    """,
                    (period_start, admin_user["id"]),
                )
                source_rows = [dict(row) for row in cur.fetchall()]

        channel_revenue = sum(float(row.get("channel_revenue") or 0) for row in daily_rows)
        api_revenue = 0.0
        total_expenses = 0.0
        total_revenue = channel_revenue + api_revenue

        return {
            "range": overview_range,
            "period_start": period_start.isoformat(),
            "period_end": today.isoformat(),
            "finance": {
                "total_revenue": total_revenue,
                "total_expenses": total_expenses,
                "api_revenue": api_revenue,
                "channel_revenue": channel_revenue,
                "net_revenue": total_revenue - total_expenses,
                "daily": [
                    {
                        "date": row["date"],
                        "revenue": float(row.get("channel_revenue") or 0),
                        "expenses": 0.0,
                        "net": float(row.get("channel_revenue") or 0),
                    }
                    for row in daily_rows
                ],
                "sources": source_rows,
                "expense_breakdown": [],
            },
            "youtube": {
                "channel_count": int(youtube.get("channel_count") or 0),
                "subscriber_count": int(youtube.get("subscriber_count") or 0),
                "view_count": int(youtube.get("view_count") or 0),
                "video_count": int(youtube.get("video_count") or 0),
            },
            "recent_activity": [],
        }
    except Exception as exc:
        print(f"[Admin] Overview failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not load admin overview",
        ) from exc


# ─── CLIENT CREDIT MANAGEMENT ──────────────────────────────────────────────────


@router.get("/clients")
async def list_clients(admin_user: dict = Depends(require_admin)):
    """List all client accounts with their balances and status."""
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        ca.user_id::text,
                        ca.display_name,
                        ca.created_at,
                        ca.notes,
                        uc.balance,
                        uc.is_locked,
                        uc.locked_reason,
                        uc.consecutive_failures,
                        uc.max_concurrent_jobs,
                        uc.storage_cap_bytes,
                        uc.clip_retention_days,
                        au.email
                    FROM client_accounts ca
                    LEFT JOIN user_credits uc ON uc.user_id = ca.user_id
                    LEFT JOIN auth.users au ON au.id = ca.user_id
                    ORDER BY ca.created_at DESC
                """)
                rows = cur.fetchall()
        return {"clients": [dict(r) for r in rows]}
    except Exception as exc:
        print(f"[Admin] list_clients error: {exc}")
        raise HTTPException(status_code=503, detail="Could not load clients") from exc


@router.get("/clients/{user_id}/transactions")
async def client_transactions(
    user_id: str,
    admin_user: dict = Depends(require_admin),
):
    """Get credit transaction history for a specific client."""
    from app.services.credits import get_transactions
    txns = get_transactions(user_id, limit=100, offset=0)
    return {"transactions": txns}


from pydantic import BaseModel as _BM


class _TopupBody(_BM):
    user_id: str
    amount: int
    note: str = ""


@router.post("/clients/topup")
async def admin_topup_client(
    body: _TopupBody,
    admin_user: dict = Depends(require_admin),
):
    """Add credits to a client account."""
    from app.services.credits import topup_credits
    if body.amount < 1 or body.amount > 10000:
        raise HTTPException(status_code=400, detail="Amount must be between 1 and 10000")
    result = topup_credits(body.user_id, body.amount, admin_user["id"], body.note)
    if not result["success"]:
        raise HTTPException(status_code=404, detail="Client credit account not found")
    return {"success": True, "new_balance": result["new_balance"]}


class _LockBody(_BM):
    user_id: str
    reason: str = ""


@router.post("/clients/lock")
async def lock_client(body: _LockBody, admin_user: dict = Depends(require_admin)):
    """Lock a client account."""
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE user_credits SET is_locked = TRUE, locked_reason = %s, updated_at = now()
                    WHERE user_id = %s::uuid
                    """,
                    (body.reason or "Locked by admin", body.user_id),
                )
                conn.commit()
        return {"success": True}
    except Exception as exc:
        print(f"[Admin] lock_client error: {exc}")
        raise HTTPException(status_code=503, detail="Lock failed") from exc


@router.post("/clients/unlock")
async def unlock_client(body: _LockBody, admin_user: dict = Depends(require_admin)):
    """Unlock a client account and reset consecutive failures."""
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE user_credits
                    SET is_locked = FALSE, locked_reason = NULL, consecutive_failures = 0, updated_at = now()
                    WHERE user_id = %s::uuid
                    """,
                    (body.user_id,),
                )
                conn.commit()
        return {"success": True}
    except Exception as exc:
        print(f"[Admin] unlock_client error: {exc}")
        raise HTTPException(status_code=503, detail="Unlock failed") from exc


@router.get("/credit-requests")
async def list_credit_requests(
    status_filter: str = "pending",
    admin_user: dict = Depends(require_admin),
):
    """List credit requests, optionally filtered by status."""
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                if status_filter == "all":
                    cur.execute("""
                        SELECT cr.id::text, cr.user_id::text, cr.amount_requested,
                               cr.status, cr.admin_note, cr.created_at, cr.resolved_at,
                               au.email
                        FROM credit_requests cr
                        LEFT JOIN auth.users au ON au.id = cr.user_id
                        ORDER BY cr.created_at DESC
                        LIMIT 100
                    """)
                else:
                    cur.execute("""
                        SELECT cr.id::text, cr.user_id::text, cr.amount_requested,
                               cr.status, cr.admin_note, cr.created_at, cr.resolved_at,
                               au.email
                        FROM credit_requests cr
                        LEFT JOIN auth.users au ON au.id = cr.user_id
                        WHERE cr.status = %s
                        ORDER BY cr.created_at DESC
                        LIMIT 100
                    """, (status_filter,))
                rows = cur.fetchall()
        return {"requests": [dict(r) for r in rows]}
    except Exception as exc:
        print(f"[Admin] list_credit_requests error: {exc}")
        raise HTTPException(status_code=503, detail="Could not load credit requests") from exc


class _RequestDecisionBody(_BM):
    request_id: str
    action: str  # "approve" or "reject"
    note: str = ""


@router.post("/credit-requests/decide")
async def decide_credit_request(
    body: _RequestDecisionBody,
    admin_user: dict = Depends(require_admin),
):
    """Approve or reject a credit request."""
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")

    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id::text, amount_requested, status
                    FROM credit_requests WHERE id = %s::uuid
                    """,
                    (body.request_id,),
                )
                req = cur.fetchone()
                if not req:
                    raise HTTPException(status_code=404, detail="Request not found")
                if req["status"] != "pending":
                    raise HTTPException(status_code=409, detail=f"Request already {req['status']}")

                cur.execute(
                    """
                    UPDATE credit_requests
                    SET status = %s, admin_note = %s, resolved_at = now(), resolved_by = %s::uuid
                    WHERE id = %s::uuid
                    """,
                    (
                        "approved" if body.action == "approve" else "rejected",
                        body.note,
                        admin_user["id"],
                        body.request_id,
                    ),
                )
                conn.commit()

        if body.action == "approve":
            from app.services.credits import topup_credits
            topup_credits(req["user_id"], req["amount_requested"], admin_user["id"], f"Approved request #{body.request_id}")

        return {"success": True, "action": body.action, "amount": req["amount_requested"]}
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[Admin] decide_credit_request error: {exc}")
        raise HTTPException(status_code=503, detail="Decision failed") from exc


class _CreateClientBody(_BM):
    email: str
    display_name: str = ""
    initial_credits: int = 0
    notes: str = ""


@router.post("/clients/create")
async def create_client_account(
    body: _CreateClientBody,
    admin_user: dict = Depends(require_admin),
):
    """Register an existing Supabase auth user as a client with credits."""
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                # Find user by email
                cur.execute(
                    "SELECT id::text FROM auth.users WHERE email = %s LIMIT 1",
                    (body.email,),
                )
                user_row = cur.fetchone()
                if not user_row:
                    raise HTTPException(status_code=404, detail=f"No auth user found with email {body.email}")

                target_user_id = user_row["id"]

                # Check not already a client
                cur.execute(
                    "SELECT 1 FROM client_accounts WHERE user_id = %s::uuid",
                    (target_user_id,),
                )
                if cur.fetchone():
                    raise HTTPException(status_code=409, detail="User is already a client")

                # Insert client_accounts (trigger auto-creates user_credits)
                cur.execute(
                    """
                    INSERT INTO client_accounts (user_id, display_name, created_by, notes)
                    VALUES (%s::uuid, %s, %s::uuid, %s)
                    """,
                    (target_user_id, body.display_name or body.email, admin_user["id"], body.notes),
                )
                conn.commit()

        # Topup initial credits if specified
        if body.initial_credits > 0:
            from app.services.credits import topup_credits
            topup_credits(target_user_id, body.initial_credits, admin_user["id"], "Initial balance on account creation")

        return {"success": True, "user_id": target_user_id, "initial_credits": body.initial_credits}
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[Admin] create_client error: {exc}")
        raise HTTPException(status_code=503, detail="Client creation failed") from exc
