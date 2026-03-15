"""
audio_analyzer.py
-----------------
Librosa tabanlı ses enerji analizi.
Videodaki duygusal zirveleri, gülme/bağırma/sessizlik noktalarını
matematiksel olarak tespit eder.
Bu veri Gemini'a ek bağlam olarak verilir.
"""

import numpy as np
from pathlib import Path

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    print("[AudioAnalyzer] ⚠️ Librosa kurulu değil. pip install librosa ile kur.")


def analyze_energy(audio_path: str, top_n: int = 10) -> dict:
    """
    Ses dosyasını analiz eder ve enerji haritası çıkarır.
    
    Döndürür:
    {
        "energy_peaks": [
            {"time": 123.4, "energy": 0.85, "description": "Yüksek enerji bölgesi"},
            ...
        ],
        "silence_zones": [
            {"start": 45.0, "end": 47.5, "description": "Sessizlik"},
            ...
        ],
        "duration": 3600.0,
        "summary": "Gemini'a göndermek için okunabilir özet"
    }
    """
    if not LIBROSA_AVAILABLE:
        print("[AudioAnalyzer] Librosa yok, ses analizi atlanıyor.")
        return _empty_result()

    print(f"[AudioAnalyzer] Ses analizi başlıyor... ({audio_path})")

    # Geçici WAV dosyası (Librosa/soundfile M4A'da sorun çıkarıyor)
    temp_wav = f"{audio_path}_temp.wav"
    
    try:
        import subprocess
        # FFMPEG ile 16kHz Mono WAV'a çevir (hızlı ve sessiz)
        subprocess.run([
            "ffmpeg", "-y", "-i", audio_path, 
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", 
            temp_wav
        ], capture_output=True, check=True)
        
        # Süreyi librosa ile al (dosyayı tam yüklemeden)
        sr = 16000
        try:
            duration = librosa.get_duration(path=temp_wav)
        except TypeError:
            # Eski librosa sürümleri için
            duration = librosa.get_duration(filename=temp_wav)
            
        print(f"[AudioAnalyzer] Süre: {duration:.0f}s, Sample rate: {sr}Hz")

        # ── 1. RMS Enerji ─────────────────────────────────────────
        frame_length = sr  # 1 saniye
        hop_length = sr // 2  # 0.5 saniye adım
        
        import gc
        all_rms = []
        
        if duration > 600:
            print("[AudioAnalyzer] Video uzun (>10dk), 5 dakikalık bloklar halinde işleniyor...")
            block_duration = 300
            for start_sec in range(0, int(duration) + 1, block_duration):
                y_block, _ = librosa.load(temp_wav, sr=sr, mono=True, offset=start_sec, duration=block_duration)
                if len(y_block) == 0:
                    break
                rms_block = librosa.feature.rms(y=y_block, frame_length=frame_length, hop_length=hop_length)[0]
                all_rms.append(rms_block)
                del y_block
                gc.collect()
            
            if all_rms:
                rms = np.concatenate(all_rms)
            else:
                rms = np.array([])
        else:
            y, _ = librosa.load(temp_wav, sr=sr, mono=True)
            if len(y) > 0:
                rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
            else:
                rms = np.array([])
            del y
            gc.collect()

        if len(rms) == 0:
            return _empty_result()

        times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)

        # Normalize et (0-1 arası)
        rms_max = rms.max()
        if rms_max > 0:
            rms_normalized = rms / rms_max
        else:
            rms_normalized = rms

        # ── 2. Enerji Zirveleri ───────────────────────────────────
        # En yüksek enerji noktalarını bul
        threshold = np.percentile(rms_normalized, 85)  # üst %15
        peak_indices = []
        
        i = 0
        while i < len(rms_normalized):
            if rms_normalized[i] >= threshold:
                # Bu bölgedeki en yüksek noktayı bul
                window_end = min(i + 20, len(rms_normalized))  # 10 saniyelik pencere
                peak_idx = i + np.argmax(rms_normalized[i:window_end])
                peak_indices.append(int(peak_idx))
                i = window_end
            else:
                i += 1

        # En yüksek top_n zirveyi al
        peak_indices.sort(key=lambda idx: rms_normalized[idx], reverse=True)
        peak_indices = peak_indices[:top_n]
        peak_indices.sort()  # Zamana göre sırala

        energy_peaks = []
        for idx in peak_indices:
            t = float(times[idx])
            e = float(rms_normalized[idx])
            energy_peaks.append({
                "time": round(t, 1),
                "energy": round(e, 2),
                "description": _energy_description(e)
            })

        # ── 3. Sessizlik Bölgeleri ────────────────────────────────
        silence_threshold = np.percentile(rms_normalized, 15)  # alt %15
        silence_zones = []
        in_silence = False
        silence_start = 0.0

        for idx, (t, e) in enumerate(zip(times, rms_normalized)):
            if e <= silence_threshold and not in_silence:
                in_silence = True
                silence_start = float(t)
            elif e > silence_threshold and in_silence:
                in_silence = False
                silence_duration = float(t) - silence_start
                if silence_duration >= 0.5:  # En az 0.5 saniye sessizlik
                    silence_zones.append({
                        "start": round(silence_start, 1),
                        "end": round(float(t), 1),
                        "duration": round(silence_duration, 1)
                    })

        print(f"[AudioAnalyzer] ✅ {len(energy_peaks)} enerji zirvesi, {len(silence_zones)} sessizlik bölgesi bulundu.")

        # ── 3.5. Windows (30 Saniyelik Pencereler) ────────────────
        windows = []
        window_size = 30  # saniye
        for start_sec in range(0, int(duration), window_size):
            end_sec = min(start_sec + window_size, float(duration))
            start_idx = librosa.time_to_frames(start_sec, sr=sr, hop_length=hop_length)
            end_idx = librosa.time_to_frames(end_sec, sr=sr, hop_length=hop_length)
            
            # Bu aralıktaki RMS değerlerini al
            window_rms = rms_normalized[start_idx:end_idx]
            
            if len(window_rms) > 0:
                windows.append({
                    "start": start_sec,
                    "end": end_sec,
                    "rms_mean": float(window_rms.mean()),
                    "rms_max": float(window_rms.max()),
                    "rms_spike": bool(window_rms.max() > rms_normalized.mean() * 1.5),
                    "silence_ratio": float(np.sum(window_rms < 0.1) / len(window_rms))
                })
            else:
                windows.append({
                    "start": start_sec,
                    "end": end_sec,
                    "rms_mean": 0.0,
                    "rms_max": 0.0,
                    "rms_spike": False,
                    "silence_ratio": 0.0
                })

        # ── 4. Gemini için özet metin ─────────────────────────────
        summary = _build_summary(energy_peaks, silence_zones, duration)

        return {
            "energy_peaks": energy_peaks,
            "silence_zones": silence_zones,
            "windows": windows,
            "duration": round(duration, 1),
            "summary": summary
        }

    except Exception as e:
        print(f"[AudioAnalyzer] Hata: {e}")
        return _empty_result()
    
    finally:
        import os
        if os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except Exception as e:
                print(f"[AudioAnalyzer] Geçici WAV dosyası silinirken hata: {e}")


def _energy_description(energy: float) -> str:
    if energy >= 0.90:
        return "Çok yüksek enerji — bağırma/gülme/alkış olabilir"
    elif energy >= 0.75:
        return "Yüksek enerji — heyecanlı/duygusal an"
    elif energy >= 0.60:
        return "Orta-yüksek enerji — aktif konuşma"
    else:
        return "Normal konuşma enerjisi"


def _build_summary(peaks: list, silences: list, duration: float) -> str:
    """Gemini'a göndermek için okunabilir ses enerji özeti."""
    lines = []
    lines.append(f"VİDEO SÜRESİ: {duration:.0f} saniye ({duration/60:.1f} dakika)")
    lines.append("")
    lines.append("EN ENERJİK ANLAR (viral potansiyel yüksek):")
    
    for peak in peaks[:8]:  # İlk 8 zirveyi göster
        h = int(peak["time"] // 3600)
        m = int((peak["time"] % 3600) // 60)
        s = int(peak["time"] % 60)
        timestamp = f"{h:02}:{m:02}:{s:02}"
        lines.append(f"  • {timestamp} — Enerji: {peak['energy']:.0%} — {peak['description']}")
    
    lines.append("")
    lines.append(f"DOĞAL KESİM NOKTALARı (sessizlikler): {len(silences)} bölge tespit edildi")
    
    if silences:
        # İlk 5 sessizliği göster
        for sil in silences[:5]:
            lines.append(f"  • {sil['start']:.1f}s - {sil['end']:.1f}s ({sil['duration']:.1f}s sessizlik)")
    
    return "\n".join(lines)


def _empty_result() -> dict:
    return {
        "energy_peaks": [],
        "silence_zones": [],
        "windows": [],
        "duration": 0,
        "summary": "Ses analizi yapılamadı."
    }


def get_silence_near(audio_analysis: dict, target_sec: float, window: float = 3.0) -> float:
    """
    Verilen saniyeye en yakın sessizlik noktasını döndürür.
    Cutter.py'nin snap özelliği için kullanılır.
    """
    silences = audio_analysis.get("silence_zones", [])
    
    best = target_sec
    best_dist = float("inf")
    
    for sil in silences:
        mid = (sil["start"] + sil["end"]) / 2
        dist = abs(mid - target_sec)
        if dist <= window and dist < best_dist:
            best_dist = dist
            best = mid
    
    return best
