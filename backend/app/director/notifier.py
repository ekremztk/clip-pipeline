"""
Director Telegram Notifier — push critical alerts to Telegram.
Uses stdlib only (no httpx/requests dependency needed).

Env vars:
  TELEGRAM_BOT_TOKEN  — from @BotFather
  TELEGRAM_CHAT_ID    — target chat/user ID

Graceful fallback: if env vars missing, logs to director_events only.
"""

import json
import os
import urllib.request
import urllib.error

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8647395439:AAG_qlAyzQ-fwHWO3o2Fzb5Bw3Ew8KWfnRA")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8345507912")


def send_telegram(message: str, parse_mode: str = "Markdown") -> dict:
    """Send a message via Telegram Bot API. Returns API response or error dict."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return {"ok": False, "reason": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set"}

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": parse_mode,
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"[Telegram] HTTP {e.code}: {body}")
        return {"ok": False, "error": f"HTTP {e.code}", "body": body}
    except Exception as e:
        print(f"[Telegram] Error: {e}")
        return {"ok": False, "error": str(e)}


def notify_pipeline_failed(job_id: str, step: str, error: str, channel_id: str | None = None) -> dict:
    """Notify when a pipeline fails."""
    msg = (
        f"🔴 *Pipeline Failed*\n"
        f"Job: `{job_id}`\n"
        f"Step: {step}\n"
        f"Error: {error[:200]}"
    )
    if channel_id:
        msg += f"\nChannel: {channel_id}"
    return send_telegram(msg)


def notify_cost_spike(job_id: str, cost_usd: float, mean_usd: float, z_score: float) -> dict:
    """Notify when a job has abnormal cost."""
    msg = (
        f"💰 *Cost Spike*\n"
        f"Job: `{job_id}`\n"
        f"Cost: ${cost_usd:.4f} (avg: ${mean_usd:.4f})\n"
        f"Z-score: {z_score:.1f}σ"
    )
    return send_telegram(msg)


def notify_performance_drop(rate_7d: float, rate_30d: float, drop_pp: float) -> dict:
    """Notify when pass rate drops significantly."""
    msg = (
        f"📉 *Performance Drop*\n"
        f"Son 7 gün: %{rate_7d:.1f}\n"
        f"30 gün ort: %{rate_30d:.1f}\n"
        f"Düşüş: {drop_pp:.1f}pp"
    )
    return send_telegram(msg)


def notify_rate_limit(count: int) -> dict:
    """Notify when Gemini rate limits are excessive."""
    msg = (
        f"⚠️ *Gemini Rate Limit*\n"
        f"Son 24 saatte {count} rate limit hatası.\n"
        f"Pipeline zamanlama veya batch boyutu kontrol edilmeli."
    )
    return send_telegram(msg)


def notify_weekly_digest(summary: dict) -> dict:
    """Send weekly digest summary."""
    msg = (
        f"📊 *Haftalık Özet*\n"
        f"Jobs: {summary.get('total_jobs', 0)}\n"
        f"Clips: {summary.get('total_clips', 0)}\n"
        f"Pass: {summary.get('pass_count', 0)}\n"
        f"Avg Confidence: {summary.get('avg_confidence', 0):.2f}"
    )
    trend = summary.get("trend", {})
    if trend:
        msg += f"\nTrend: {trend.get('trend', 'N/A')}"
    return send_telegram(msg)


def notify_custom(title: str, body: str) -> dict:
    """Send a custom notification."""
    msg = f"📌 *{title}*\n{body}"
    return send_telegram(msg)
