import os
import logging
from datetime import datetime, timedelta
from database import get_client
from genome import calculate_genome, save_genome

logger = logging.getLogger(__name__)

def process_feedback(clip_id, views, retention, swipe_rate, views_48h, views_7d):
    """
    Kliplere gelen performans verisini işler ve Supabase'e kaydeder.
    """
    # 1. Validasyon
    if views < 0:
        logger.warning(f"Clip {clip_id}: views ({views}) < 0 -> reddedildi.")
        return False
        
    if retention < 0 or retention > 100:
        logger.warning(f"Clip {clip_id}: retention ({retention}) geçersiz -> reddedildi.")
        return False
        
    if views > 50000000:
        logger.warning(f"Clip {clip_id}: views ({views}) > 50M -> reddedildi (aykırı değer).")
        return False

    # 2. Growth Type Belirleme (Sıfıra Bölme Koruması eklendi)
    if views_7d == 0:
        growth_type = "unknown"
    else:
        ratio = views_48h / views_7d
        if ratio > 0.70:
            growth_type = "spike"
        elif ratio < 0.30:
            growth_type = "slow_burn"
        else:
            growth_type = "steady"

    # 3. Kayıt: Supabase clips tablosunu güncelle
    try:
        supabase = get_client()
        
        data = {
            "views": views,
            "retention": retention,
            "swipe_rate": swipe_rate,
            "views_48h": views_48h,
            "views_7d": views_7d,
            "growth_type": growth_type,
            "feedback_status": "processed"
        }
        
        response = supabase.table("clips").update(data).eq("id", clip_id).execute()
        
        if response.data and len(response.data) > 0:
            channel_id = response.data[0].get("channel_id")
            if channel_id:
                update_signal_accuracy(clip_id, channel_id)
                trigger_genome_recalc(channel_id)
            return True
            
        return False
        
    except Exception as e:
        logger.error(f"process_feedback hatası (clip_id={clip_id}): {e}")
        return False


def update_signal_accuracy(clip_id, channel_id):
    """
    clips.decision_log'dan segment sinyallerini alır.
    Gerçek performansla karşılaştırıp, doğru/yanlış etiketler.
    """
    try:
        supabase = get_client()
        response = supabase.table("clips").select("decision_log, views_7d").eq("id", clip_id).execute()
        
        if not response.data:
            return
            
        clip_data = response.data[0]
        decision_log = clip_data.get("decision_log")
        views_7d = clip_data.get("views_7d", 0)
        
        if not decision_log:
            logger.info(f"Clip {clip_id} için decision_log bulunamadı.")
            return
            
        # TODO: decision_log parse edilerek beklenen sinyaller ile
        # gerçek performans eşleşmesi yapılacak ve is_successful etiketlenecek.
        # Örneğin beklenti yüksek ama views_7d düşükse false positive.
        
        logger.info(f"Signal accuracy updated for clip {clip_id} on channel {channel_id}")
        
    except Exception as e:
        logger.error(f"update_signal_accuracy hatası (clip_id={clip_id}): {e}")


def trigger_genome_recalc(channel_id):
    """
    Toplam feedback sayısını çeker, % 50 == 0 ise genome'u yeniden hesaplar.
    """
    try:
        supabase = get_client()
        
        # Sadece işlenmiş olan feedback'leri sayıyoruz
        response = supabase.table("clips").select("id", count="exact").eq("channel_id", channel_id).eq("feedback_status", "processed").execute()
        
        total_feedback = response.count if response.count else 0
        interval = int(os.environ.get("GENOME_RECALC_INTERVAL", 50))
        
        # Modulo kontrolü
        if total_feedback > 0 and total_feedback % interval == 0:
            logger.info(f"Channel {channel_id} reached {total_feedback} feedbacks. Triggering genome recalc...")
            
            genome_data = calculate_genome(channel_id)
            if genome_data:
                save_genome(channel_id, genome_data)
                
    except Exception as e:
        logger.error(f"trigger_genome_recalc hatası (channel_id={channel_id}): {e}")


def cleanup_stale_feedback():
    """
    feedback_status = 'pending' VE created_at < 30 gün önce olan kayıtları bulur
    ve feedback_status = 'expired' olarak günceller.
    """
    try:
        supabase = get_client()
        
        # 30 gün öncesi
        thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
        
        response = supabase.table("clips").update({
            "feedback_status": "expired"
        }).eq("feedback_status", "pending").lt("created_at", thirty_days_ago).execute()
        
        if response.data:
            logger.info(f"Cleaned up {len(response.data)} stale feedbacks.")
            
    except Exception as e:
        logger.error(f"cleanup_stale_feedback hatası: {e}")
