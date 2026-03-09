"""
transcriber.py
--------------
WhisperX tabanlı kelime bazlı transkript modülü.
Her kelimenin tam başlangıç/bitiş zamanını milisaniye hassasiyetinde verir.
Bu veri hem analyzer.py (Gemini'a gönderilir) hem de subtitler.py tarafından kullanılır.
"""

import os
import json
import subprocess
import tempfile
from pathlib import Path

# WhisperX import — kurulu değilse hata mesajı ver
try:
    import whisperx
    WHISPERX_AVAILABLE = True
except ImportError:
    WHISPERX_AVAILABLE = False
    print("[Transcriber] ⚠️ WhisperX kurulu değil. pip install whisperx ile kur.")


def transcribe(audio_path: str, language: str = "tr") -> dict:
    """
    Ses dosyasını WhisperX ile transkribe eder.
    
    Döndürür:
    {
        "segments": [
            {
                "start": 12.34,
                "end": 15.67,
                "text": "Bu cümlenin tamamı",
                "words": [
                    {"word": "Bu", "start": 12.34, "end": 12.56, "score": 0.99},
                    {"word": "cümlenin", "start": 12.60, "end": 13.10, "score": 0.98},
                    ...
                ]
            },
            ...
        ],
        "full_text": "Tüm transkript tek string olarak",
        "language": "tr"
    }
    """
    if not WHISPERX_AVAILABLE:
        print("[Transcriber] WhisperX yok, Gemini fallback'e geçiliyor...")
        return _fallback_transcribe(audio_path)

    print(f"[Transcriber] WhisperX başlatılıyor... ({audio_path})")
    
    try:
        # Model yükle — large-v2 en iyi Türkçe desteği sunar
        # CPU için compute_type="int8" kullan (Mac + Railway uyumlu)
        model = whisperx.load_model(
            "large-v2",
            device="cpu",
            compute_type="int8",
            language=language
        )

        # Ses dosyasını yükle
        audio = whisperx.load_audio(audio_path)

        # Transkripsiyon
        print("[Transcriber] Transkripsiyon yapılıyor...")
        result = model.transcribe(audio, batch_size=8)

        # Forced alignment — kelime bazlı timestamp
        print("[Transcriber] Kelime hizalaması yapılıyor (forced alignment)...")
        model_a, metadata = whisperx.load_align_model(
            language_code=language,
            device="cpu"
        )
        result = whisperx.align(
            result["segments"],
            model_a,
            metadata,
            audio,
            device="cpu",
            return_char_alignments=False
        )

        # Belleği temizle
        del model
        del model_a

        # Çıktıyı düzenle
        segments = result.get("segments", [])
        full_text = " ".join([s.get("text", "").strip() for s in segments])

        print(f"[Transcriber] ✅ Tamamlandı. {len(segments)} segment, {len(full_text.split())} kelime.")

        return {
            "segments": segments,
            "full_text": full_text,
            "language": language
        }

    except Exception as e:
        print(f"[Transcriber] WhisperX hatası: {e}")
        print("[Transcriber] Gemini fallback'e geçiliyor...")
        return _fallback_transcribe(audio_path)


def _fallback_transcribe(audio_path: str) -> dict:
    """
    WhisperX çalışmazsa Gemini ile basit transkript üretir.
    Kelime bazlı timestamp olmaz ama sistem yine de çalışır.
    """
    import google.generativeai as genai
    from dotenv import load_dotenv
    load_dotenv()
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])

    print("[Transcriber] Gemini fallback transkript başlıyor...")

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        audio_file = genai.upload_file(audio_path, mime_type="audio/mp3")

        prompt = """Bu ses dosyasını tamamen transkribe et.
        
SADECE şu JSON formatında yanıt ver, başka hiçbir şey yazma:
{
  "segments": [
    {"start": 0.0, "end": 5.0, "text": "konuşulan cümle", "words": []},
    ...
  ],
  "full_text": "tüm metin tek parça"
}

Zaman damgaları yaklaşık olabilir, her segment 5-10 saniye olsun."""

        response = model.generate_content([audio_file, prompt])
        
        raw = response.text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        
        data = json.loads(raw.strip())
        data["language"] = "tr"
        
        try:
            genai.delete_file(audio_file.name)
        except:
            pass

        print(f"[Transcriber] Gemini fallback tamamlandı. {len(data.get('segments', []))} segment.")
        return data

    except Exception as e:
        print(f"[Transcriber] Fallback da başarısız: {e}")
        return {"segments": [], "full_text": "", "language": "tr"}


def format_transcript_for_gemini(transcript: dict) -> str:
    """
    WhisperX çıktısını Gemini'a göndermek için
    okunabilir bir formata çevirir.
    
    Örnek çıktı:
    [00:12:34] Bu çok ilginç bir şey söylüyorsunuz...
    [00:12:40] Evet, ben de öyle düşünüyorum...
    """
    segments = transcript.get("segments", [])
    lines = []
    
    for seg in segments:
        start = seg.get("start", 0)
        text = seg.get("text", "").strip()
        if not text:
            continue
        
        # Saniyeyi saat:dakika:saniye formatına çevir
        h = int(start // 3600)
        m = int((start % 3600) // 60)
        s = int(start % 60)
        timestamp = f"{h:02}:{m:02}:{s:02}"
        
        lines.append(f"[{timestamp}] {text}")
    
    return "\n".join(lines)


def get_words_in_range(transcript: dict, start_sec: float, end_sec: float) -> list:
    """
    Belirli bir zaman aralığındaki tüm kelimeleri döndürür.
    Subtitler.py tarafından stilize altyazı üretmek için kullanılır.
    
    Döndürür: [{"word": "kelime", "start": 12.34, "end": 12.56}, ...]
    """
    words = []
    
    for seg in transcript.get("segments", []):
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)
        
        # Segment bu aralıkla örtüşüyor mu?
        if seg_end < start_sec or seg_start > end_sec:
            continue
        
        for word_data in seg.get("words", []):
            w_start = word_data.get("start", seg_start)
            w_end = word_data.get("end", seg_end)
            
            if w_start >= start_sec and w_end <= end_sec:
                words.append({
                    "word": word_data.get("word", ""),
                    "start": w_start - start_sec,  # klip başlangıcına göre normalize
                    "end": w_end - start_sec,
                    "score": word_data.get("score", 1.0)
                })
    
    return words


def find_nearest_silence(transcript: dict, target_sec: float, window: float = 3.0) -> float:
    """
    Hedef saniyeye en yakın sessizlik noktasını bulur.
    Denetçi ajanın kesim noktasını ayarlaması için kullanılır.
    
    window: kaç saniyelik aralıkta arama yapılacak
    """
    segments = transcript.get("segments", [])
    
    best_point = target_sec
    best_distance = float("inf")
    
    for i in range(len(segments) - 1):
        current_end = segments[i].get("end", 0)
        next_start = segments[i + 1].get("start", 0)
        
        # İki segment arası sessizlik boşluğu
        silence_mid = (current_end + next_start) / 2
        distance = abs(silence_mid - target_sec)
        
        if distance <= window and distance < best_distance:
            best_distance = distance
            best_point = silence_mid
    
    if best_distance < window:
        print(f"[Transcriber] Sessizlik noktası bulundu: {target_sec:.1f}s → {best_point:.1f}s")
    
    return best_point


def find_sentence_boundary(transcript: dict, target_sec: float, direction: str = "nearest") -> float:
    """
    Hedef saniyeye en yakın cümle sınırını bulur.
    Noktalama işareti veya segment bitişi = cümle sonu.
    
    direction: "nearest" | "before" | "after"
    """
    segments = transcript.get("segments", [])
    
    boundaries = []
    for seg in segments:
        boundaries.append(seg.get("start", 0))
        boundaries.append(seg.get("end", 0))
    
    if not boundaries:
        return target_sec
    
    if direction == "before":
        candidates = [b for b in boundaries if b <= target_sec]
        return max(candidates) if candidates else target_sec
    elif direction == "after":
        candidates = [b for b in boundaries if b >= target_sec]
        return min(candidates) if candidates else target_sec
    else:  # nearest
        return min(boundaries, key=lambda b: abs(b - target_sec))
