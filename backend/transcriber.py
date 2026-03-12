"""
transcriber.py
--------------
Groq Whisper API tabanlı hızlı transkript modülü.
"""

import os
import json
import math
from pathlib import Path

try:
    from groq import Groq  # type: ignore[import-not-found]
    GROQ_AVAILABLE = True
except ImportError:
    Groq = None
    GROQ_AVAILABLE = False
    print("[Transcriber] ⚠️ Groq kurulu değil. pip install groq ile kur.")


GROQ_MAX_BYTES = 25 * 1024 * 1024  # 25MB


def transcribe(audio_path: str, language: str | None = None) -> dict:
    if not GROQ_AVAILABLE:
        print("[Transcriber] Groq kurulu değil, Gemini fallback...")
        return _fallback_transcribe(audio_path)

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("[Transcriber] GROQ_API_KEY bulunamadı, Gemini fallback...")
        return _fallback_transcribe(audio_path)

    print(f"[Transcriber] Groq Whisper başlatılıyor... ({audio_path})")

    try:
        client = Groq(api_key=api_key)  # type: ignore[misc]
        file_size = Path(audio_path).stat().st_size

        if file_size <= GROQ_MAX_BYTES:
            result = _transcribe_single(client, audio_path, language)
        else:
            print(f"[Transcriber] Dosya büyük ({file_size // 1024 // 1024}MB), parçalanıyor...")
            result = _transcribe_chunked(client, audio_path, language)

        segments = result.get("segments", [])
        full_text = " ".join([s.get("text", "").strip() for s in segments])

        print(f"[Transcriber] ✅ Groq tamamlandı. {len(segments)} segment, {len(full_text.split())} kelime.")

        return {
            "segments": segments,
            "full_text": full_text,
            "language": language
        }

    except Exception as e:
        print(f"[Transcriber] Groq hatası: {e}")
        print("[Transcriber] Gemini fallback'e geçiliyor...")
        return _fallback_transcribe(audio_path)


def _transcribe_single(client, audio_path: str, language: str | None) -> dict:
    print("[Transcriber] Groq'a gönderiliyor...")

    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            file=(Path(audio_path).name, f),
            model="whisper-large-v3-turbo",
            **({"language": language} if language else {}),
            response_format="verbose_json",
            timestamp_granularities=["word", "segment"]
        )

    return _parse_groq_response(response, offset=0.0)


def _transcribe_chunked(client, audio_path: str, language: str | None) -> dict:
    import subprocess
    import tempfile

    duration_cmd =[
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", audio_path
    ]
    probe = subprocess.run(duration_cmd, capture_output=True, text=True)
    probe_data = json.loads(probe.stdout)
    total_duration = float(probe_data["format"]["duration"])

    chunk_duration = 600  # 10 dakika per parça
    num_chunks = math.ceil(total_duration / chunk_duration)
    print(f"[Transcriber] Toplam {total_duration:.0f}s → {num_chunks} parça")

    all_segments =[]

    with tempfile.TemporaryDirectory() as tmpdir:
        for i in range(num_chunks):
            start_time = i * chunk_duration
            chunk_path = os.path.join(tmpdir, f"chunk_{i:03d}.mp3")

            cut_cmd =[
                "ffmpeg", "-y", "-ss", str(start_time),
                "-t", str(chunk_duration),
                "-i", audio_path,
                "-ac", "1", "-ar", "16000",
                chunk_path
            ]
            subprocess.run(cut_cmd, capture_output=True)

            if not os.path.exists(chunk_path):
                continue

            print(f"[Transcriber] Parça {i+1}/{num_chunks} (offset: {start_time}s)...")
            try:
                chunk_result = _transcribe_single(client, chunk_path, language)
                chunk_segs = chunk_result.get("segments",[])

                for seg in chunk_segs:
                    seg["start"] = round(seg.get("start", 0) + start_time, 3)  # type: ignore[call-overload]
                    seg["end"] = round(seg.get("end", 0) + start_time, 3)  # type: ignore[call-overload]
                    for w in seg.get("words", []):
                        w["start"] = round(w.get("start", 0) + start_time, 3)  # type: ignore[call-overload]
                        w["end"] = round(w.get("end", 0) + start_time, 3)  # type: ignore[call-overload]

                all_segments.extend(chunk_segs)
            except Exception as e:
                print(f"[Transcriber] Parça {i+1} hatası: {e}, atlanıyor...")

    return {"segments": all_segments}


def _parse_groq_response(response, offset: float = 0.0) -> dict:
    segments =[]

    if isinstance(response, dict):
        raw_segments = response.get("segments", [])
        raw_words = response.get("words",[])
        full_text = response.get("text", "").strip()
    else:
        raw_segments = getattr(response, "segments", []) or[]
        raw_words = getattr(response, "words", []) or[]
        full_text = getattr(response, "text", "").strip()

    word_list =[]
    for w in raw_words:
        if isinstance(w, dict):
            w_word = w.get("word", "")
            w_start = w.get("start", 0.0)
            w_end = w.get("end", 0.0)
        else:
            w_word = getattr(w, "word", "")
            w_start = getattr(w, "start", 0.0)
            w_end = getattr(w, "end", 0.0)

        word_list.append({
            "word": w_word,
            "start": round(float(w_start + offset), 3),  # type: ignore[call-overload]
            "end": round(float(w_end + offset), 3),  # type: ignore[call-overload]
            "score": 0.99
        })

    for seg in raw_segments:
        if isinstance(seg, dict):
            seg_start = seg.get("start", 0.0)
            seg_end = seg.get("end", 0.0)
            seg_text = seg.get("text", "").strip()
        else:
            seg_start = getattr(seg, "start", 0.0)
            seg_end = getattr(seg, "end", 0.0)
            seg_text = getattr(seg, "text", "").strip()

        seg_start = round(float(seg_start + offset), 3)  # type: ignore[call-overload]
        seg_end = round(float(seg_end + offset), 3)  # type: ignore[call-overload]

        seg_words =[
            w for w in word_list
            if w["start"] >= seg_start and w["end"] <= seg_end + 0.1
        ]

        if seg_text and seg_text.strip():
            segments.append({
                "start": seg_start,
                "end": seg_end,
                "text": seg_text,
                "words": seg_words
            })

    if not segments and word_list:
        segments =[{
            "start": word_list[0]["start"] if word_list else 0,
            "end": word_list[-1]["end"] if word_list else 0,
            "text": full_text,
            "words": word_list
        }]

    return {"segments": segments}


def _fallback_transcribe(audio_path: str) -> dict:
    """YENİ MİMARİ: google-genai kullanılarak transkript üretimi"""
    from google import genai  # type: ignore
    from google.genai import types  # type: ignore
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[Transcriber] GEMINI_API_KEY yok, boş transkript döndürülüyor.")
        return {"segments":[], "full_text": "", "language": "tr"}

    client = genai.Client(api_key=api_key)
    print("[Transcriber] Gemini fallback transkript başlıyor...")

    try:
        audio_file = client.files.upload(file=audio_path)

        prompt = """Bu ses dosyasını tamamen transkribe et.

SADECE şu JSON formatında yanıt ver, başka hiçbir şey yazma:
{
  "segments":[
    {"start": 0.0, "end": 5.0, "text": "konuşulan cümle", "words": []},
    ...
  ],
  "full_text": "tüm metin tek parça"
}

Zaman damgaları yaklaşık olabilir, her segment 5-10 saniye olsun."""

        json_config = types.GenerateContentConfig(response_mime_type="application/json")
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[audio_file, prompt],
            config=json_config
        )

        raw = response.text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw.strip())
        data["language"] = "tr"

        try:
            client.files.delete(name=audio_file.name)
        except:
            pass

        print(f"[Transcriber] Gemini fallback tamamlandı. {len(data.get('segments',[]))} segment.")
        return data

    except Exception as e:
        print(f"[Transcriber] Fallback da başarısız: {e}")
        return {"segments":[], "full_text": "", "language": "tr"}


def format_transcript_for_gemini(transcript: dict) -> str:
    segments = transcript.get("segments", [])
    lines =[]
    for seg in segments:
        start = seg.get("start", 0)
        text = seg.get("text", "").strip()
        if not text: continue
        h = int(start // 3600)
        m = int((start % 3600) // 60)
        s = int(start % 60)
        lines.append(f"[{h:02}:{m:02}:{s:02}] {text}")
    return "\n".join(lines)


def get_words_in_range(transcript: dict, start_sec: float, end_sec: float) -> list:
    words =[]
    for seg in transcript.get("segments",[]):
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)
        if seg_end < start_sec or seg_start > end_sec: continue
        for word_data in seg.get("words",[]):
            w_start = word_data.get("start", seg_start)
            w_end = word_data.get("end", seg_end)
            if w_start >= start_sec and w_end <= end_sec:
                words.append({
                    "word": word_data.get("word", ""),
                    "start": w_start - start_sec,
                    "end": w_end - start_sec,
                    "score": word_data.get("score", 1.0)
                })
    return words


def find_nearest_silence(transcript: dict, target_sec: float, window: float = 3.0) -> float:
    segments = transcript.get("segments",[])
    best_point = target_sec
    best_distance = float("inf")
    for i in range(len(segments) - 1):
        current_end = segments[i].get("end", 0)
        next_start = segments[i + 1].get("start", 0)
        silence_mid = (current_end + next_start) / 2
        distance = abs(silence_mid - target_sec)
        if distance <= window and distance < best_distance:
            best_distance = distance
            best_point = silence_mid
    if best_distance < window:
        print(f"[Transcriber] Sessizlik noktası: {target_sec:.1f}s → {best_point:.1f}s")
    return best_point


def find_sentence_boundary(transcript: dict, target_sec: float, direction: str = "nearest") -> float:
    segments = transcript.get("segments", [])
    boundaries =[]
    for seg in segments:
        boundaries.append(seg.get("start", 0))
        boundaries.append(seg.get("end", 0))
    if not boundaries: return target_sec
    if direction == "before":
        candidates =[b for b in boundaries if b <= target_sec]
        return max(candidates) if candidates else target_sec
    elif direction == "after":
        candidates = [b for b in boundaries if b >= target_sec]
        return min(candidates) if candidates else target_sec
    else:
        return min(boundaries, key=lambda b: abs(b - target_sec))