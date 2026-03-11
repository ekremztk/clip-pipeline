"""
report_builder.py (V1.5)
------------------------
Gemini'nin JSON çıktısını metadata.py ve pdf_reporter.py'nin 
beklediği standart formata dönüştürür.

Ayrıca transkriptten ilgili zaman aralığındaki metni çeker
ve klip verisine ekler.
"""

from transcriber import get_words_in_range


def build_report_data(clips_data: list[dict], transcript: dict = None) -> list[dict]:
    """
    Gemini'nin analyzer çıktısını metadata.py ve pdf_reporter.py'nin
    beklediği alan adlarına dönüştürür.
    
    Gemini çıktısı:
        start_time, end_time, hook_text, psychological_trigger,
        rag_reference_used, virality_score, why_selected,
        suggested_title, suggested_description, suggested_hashtags,
        audio_energy_note, trim_note
    
    Rapor formatı:
        start_sec, end_sec, title, description, hashtags, score,
        hook, why_selected, audio_highlights, trim_note,
        transcript, recommendation, psychological_trigger,
        rag_reference_used
    """
    report_clips = []
    
    for i, clip in enumerate(clips_data):
        start = float(clip.get("start_time", 0))
        end = float(clip.get("end_time", 30))
        
        # Transkriptten bu aralıktaki metni çek
        clip_transcript = ""
        if transcript and transcript.get("segments"):
            words = get_words_in_range(transcript, start, end)
            if words:
                clip_transcript = " ".join([w["word"] for w in words])
            else:
                # Word-level yoksa segment-level'dan dene
                clip_transcript = _extract_segment_text(transcript, start, end)
        
        report_clip = {
            # --- Temel zamanlar ---
            "start_sec": start,
            "end_sec": end,
            
            # --- Yayın metadata ---
            "title": clip.get("suggested_title", f"Klip {i+1}"),
            "description": clip.get("suggested_description", ""),
            "hashtags": clip.get("suggested_hashtags", ""),
            
            # --- Skor ---
            "score": clip.get("virality_score"),
            
            # --- Analiz detayları ---
            "hook": clip.get("hook_text", ""),
            "why_selected": clip.get("why_selected", ""),
            "audio_highlights": clip.get("audio_energy_note", ""),
            "trim_note": clip.get("trim_note", "none"),
            "psychological_trigger": clip.get("psychological_trigger", ""),
            "rag_reference_used": clip.get("rag_reference_used", ""),
            
            # --- Transkript ---
            "transcript": clip_transcript,
            
            # --- AI tavsiyesi (sadece ilk klipte kullanılır) ---
            "recommendation": clip.get("recommendation", ""),
        }
        
        report_clips.append(report_clip)
    
    # İlk klibe genel bir AI tavsiyesi ekle (eğer yoksa)
    if report_clips and not report_clips[0].get("recommendation"):
        top_score = max([c["score"] for c in report_clips if c["score"]], default=0)
        if top_score >= 85:
            report_clips[0]["recommendation"] = (
                f"Bu videoda yüksek viral potansiyel tespit edildi (En yüksek skor: {top_score}/100). "
                f"Önerilen kliplerin ilk 3 saniyesindeki hook cümlelerini koruyun ve "
                f"altyazı eklerken bu kancaları büyük/vurgulu yazın."
            )
        elif top_score >= 70:
            report_clips[0]["recommendation"] = (
                f"Orta düzey viral potansiyel (En yüksek skor: {top_score}/100). "
                f"Kliplerin etkisini artırmak için başlangıç ve bitiş noktalarını "
                f"düzenleme aşamasında ince ayar yapmanız önerilir."
            )
        else:
            report_clips[0]["recommendation"] = (
                f"Düşük viral potansiyel tespit edildi (En yüksek skor: {top_score}/100). "
                f"Bu videodan farklı bir kesim stratejisi denenmesi veya "
                f"videonun atlanması düşünülebilir."
            )
    
    return report_clips


def _extract_segment_text(transcript: dict, start_sec: float, end_sec: float) -> str:
    """
    Word-level timestamp yoksa segment-level'dan metin çeker.
    Zaman aralığıyla örtüşen segmentlerin metnini birleştirir.
    """
    texts = []
    for seg in transcript.get("segments", []):
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)
        
        # Overlap kontrolü
        if seg_end >= start_sec and seg_start <= end_sec:
            text = seg.get("text", "").strip()
            if text:
                texts.append(text)
    
    return " ".join(texts)