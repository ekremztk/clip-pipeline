import os
import json
import urllib.request
import logging
from datetime import datetime, timedelta
from database import get_client
from correlation import check_drift
from genome import get_genome

logger = logging.getLogger(__name__)

def check_thresholds(report: dict) -> str:
    """
    Health report değerlerine göre status rengini belirler.
    override_rate > 0.25 → red
    signal_accuracy < 0.50 → red
    0.15 < override_rate <= 0.25 → yellow
    Geri kalan → green
    """
    override_rate = report.get("override_rate", 0)
    signal_accuracy = report.get("signal_accuracy", 1.0)
    
    if override_rate > 0.25 or signal_accuracy < 0.50:
        return "red"
    elif 0.15 < override_rate <= 0.25:
        return "yellow"
    else:
        return "green"

def send_webhook(report: dict):
    """
    Eğer DISCORD_WEBHOOK_URL tanımlıysa, urllib.request ile raporu Discord'a gönderir.
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return
        
    try:
        status_colors = {
            "green": 3066993,   # Yeşil
            "yellow": 16776960, # Sarı
            "red": 15158332     # Kırmızı
        }
        
        status = report.get("status", "green")
        color = status_colors.get(status, 3066993)
        
        embed = {
            "title": f"Genome Health Report [{status.upper()}]",
            "color": color,
            "fields": [
                {"name": "Override Rate", "value": f"{report.get('override_rate', 0):.2f}", "inline": True},
                {"name": "Signal Accuracy", "value": f"{report.get('signal_accuracy', 0):.2f}", "inline": True},
                {"name": "Proxy Weight", "value": f"{report.get('proxy_weight', 0):.2f}", "inline": True},
                {"name": "Stale Feedback", "value": str(report.get('stale_feedback_count', 0)), "inline": True},
                {"name": "Drift Alerts", "value": str(len(report.get('drift_alerts', []))), "inline": True}
            ],
            "timestamp": report.get("generated_at")
        }
        
        embed_fields = embed.get("fields", [])
        if isinstance(embed_fields, list):
            drift_alerts = report.get("drift_alerts", [])
            if drift_alerts:
                alerts_list = [str(a.get("rule_key", "")) for a in drift_alerts if isinstance(a, dict)]
                alerts_str = ", ".join(alerts_list)
                truncated_alerts = ""
                for i, char in enumerate(alerts_str):
                    if i >= 1024:
                        break
                    truncated_alerts += char
                embed_fields.append({"name": "Drift Keys", "value": truncated_alerts})
            embed["fields"] = embed_fields

        payload = {
            "embeds": [embed]
        }
        
        data = json.dumps(payload).encode('utf-8')
        
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'PrognotClipPipeline/3.1'
            },
            method='POST'
        )
        
        with urllib.request.urlopen(req) as response:
            if response.status not in (200, 204):
                logger.warning(f"Discord webhook failed with status: {response.status}")
                
    except Exception as e:
        logger.error(f"Webhook gönderim hatası: {e}")

def generate_health_report(channel_id: str) -> dict:
    """
    Kanalın genel sağlık durumunu analiz edip rapor oluşturur.
    """
    try:
        supabase = get_client()
        
        # 1. Override Rate hesaplama
        clips_response = supabase.table("clips").select("id", count="exact").eq("channel_id", channel_id).execute()
        total_clips = clips_response.count if clips_response.count else 0
        
        # Override sayısını (Kullanıcının viral kütüphaneden / proxy'den override ettiği veya reddettiği manuel eylemler, burada sadece flag sayacağız)
        # Örnekte viral_library tablosundan override_flag üzerinden sayalım
        override_res = supabase.table("viral_library").select("id", count="exact").eq("channel_id", channel_id).eq("override_flag", True).execute()
        override_count = override_res.count if override_res.count else 0
        
        # Yada clips tablosundan manuel bir 'override' flagi
        override_rate = (override_count / total_clips) if total_clips > 0 else 0.0

        # 2. Signal Accuracy ortalaması (örneğin viral_library'den veya clips tablosundan parse ederek, şimdilik placeholder 0.78)
        # TODO: Gerçek verilerden accuracy hesaplanması
        signal_accuracy = 0.78

        # 3. Drift Alerts (correlation modülünden)
        drift_alerts = []
        try:
            drift_alerts = check_drift(channel_id)
        except Exception as e:
            logger.warning(f"check_drift hatası: {e}")

        # 4. Stale Feedback Count
        thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
        stale_res = supabase.table("clips").select("id", count="exact").eq("channel_id", channel_id).eq("feedback_status", "pending").lt("created_at", thirty_days_ago).execute()
        stale_feedback_count = stale_res.count if stale_res.count else 0

        # 5. Proxy Weight & Bootstrap Rules (Genome üzerinden)
        proxy_weight = 0.0
        bootstrap_rules_count = 0
        try:
            genome = get_genome(channel_id)
            if genome:
                proxy_config = genome.get("proxy_config", {})
                proxy_weight = proxy_config.get("weight", 0.0)
                if genome.get("mode") == "bootstrap":
                    # Örnek bootstrap rules
                    bootstrap_rules_count = 12
        except Exception as e:
            logger.warning(f"get_genome hatası: {e}")

        # Raporu oluştur
        report = {
            "override_rate": override_rate,
            "signal_accuracy": signal_accuracy,
            "drift_alerts": drift_alerts,
            "proxy_weight": proxy_weight,
            "bootstrap_rules_count": bootstrap_rules_count,
            "stale_feedback_count": stale_feedback_count,
            "generated_at": datetime.utcnow().isoformat() + "Z"
        }
        
        # Eşikleri kontrol edip status ekle
        report["status"] = check_thresholds(report)
        
        # Webhook gönder
        send_webhook(report)
        
        return report

    except Exception as e:
        logger.error(f"generate_health_report hatası (channel_id={channel_id}): {e}")
        return {
            "status": "red",
            "override_rate": 0,
            "signal_accuracy": 0,
            "drift_alerts": [],
            "proxy_weight": 0,
            "bootstrap_rules_count": 0,
            "stale_feedback_count": 0,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "error": str(e)
        }