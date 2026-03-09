"""
subtitler.py — WhisperX tabanlı altyazı üretici
"""

import os
import json
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def seconds_to_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def load_style_config(channel_id: str = "default") -> dict:
    BASE_DIR = Path(__file__).resolve().parent
    channel_style = BASE_DIR / "channels" / channel_id / "style.json"
    default_style = BASE_DIR / "default_style.json"

    for path in [channel_style, default_style]:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

    return {
        "font": "Montserrat-Bold",
        "base_color": "white",
        "highlight_color": "yellow",
        "base_size": 72,
        "highlight_scale": 1.4,
        "position": "lower_third",
        "words_per_line": 3,
    }


def generate_subtitles(clip_paths: list[str], job_id: str,
                       transcript: dict = None, channel_id: str = "default") -> list[str]:
    srt_paths = []

    for clip_path in clip_paths:
        clip_path_obj = Path(clip_path)
        srt_path = str(clip_path_obj.with_suffix(".srt"))

        try:
            if transcript and transcript.get("segments"):
                srt_content = _from_whisperx(clip_path, transcript, channel_id)
            else:
                srt_content = _from_gemini(clip_path)

            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
            print(f"[Subtitler] ✅ {clip_path_obj.name}")

        except Exception as e:
            print(f"[Subtitler] Hata {clip_path}: {e}")
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write("1\n00:00:00,000 --> 00:00:05,000\n[Altyazı oluşturulamadı]\n")

        srt_paths.append(srt_path)

    return srt_paths


def _from_whisperx(clip_path: str, transcript: dict, channel_id: str) -> str:
    clip_start_sec = _get_clip_start(clip_path)
    clip_duration = _get_duration(clip_path)
    clip_end_sec = clip_start_sec + clip_duration
    style = load_style_config(channel_id)
    wpl = style.get("words_per_line", 3)

    words = []
    for seg in transcript.get("segments", []):
        for wd in seg.get("words", []):
            ws = wd.get("start", seg.get("start", 0))
            we = wd.get("end", seg.get("end", 0))
            if ws >= clip_start_sec and we <= clip_end_sec:
                words.append({
                    "word": wd.get("word", ""),
                    "start": ws - clip_start_sec,
                    "end": we - clip_start_sec,
                })

    if not words:
        return _from_gemini(clip_path)

    srt_lines = []
    block_no = 1
    for i in range(0, len(words), wpl):
        group = words[i:i + wpl]
        text = " ".join(w["word"].strip() for w in group).strip()
        if not text:
            continue
        s = group[0]["start"]
        e = group[-1]["end"]
        srt_lines += [str(block_no), f"{seconds_to_srt_time(s)} --> {seconds_to_srt_time(e)}", text, ""]
        block_no += 1

    return "\n".join(srt_lines)


def _get_clip_start(clip_path: str) -> float:
    stem = Path(clip_path).stem
    if "_start_" in stem:
        try:
            return float(stem.split("_start_")[-1])
        except:
            pass
    return 0.0


def _get_duration(clip_path: str) -> float:
    cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "json", clip_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return float(json.loads(result.stdout)["format"]["duration"])
    return 30.0


def _from_gemini(clip_path: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])

    audio_path = str(Path(clip_path).with_suffix(".tmp.mp3"))
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", clip_path, "-vn", "-acodec", "libmp3lame", "-q:a", "4", audio_path],
            capture_output=True
        )
        duration = _get_duration(clip_path)
        model = genai.GenerativeModel("gemini-2.5-flash")
        af = genai.upload_file(audio_path, mime_type="audio/mp3")

        prompt = f"""Bu sesi transkribe et. Süre: {duration:.1f}s.
SADECE JSON array döndür:
[{{"start": 0.0, "end": 2.5, "text": "kelimeler"}}, ...]
Her blok 3-5 kelime, Türkçe konuşmayı Türkçe yaz."""

        raw = model.generate_content([af, prompt]).text.strip()
        if "```" in raw:
            for part in raw.split("```"):
                p = part.strip().lstrip("json").strip()
                try:
                    json.loads(p)
                    raw = p
                    break
                except:
                    continue

        blocks = json.loads(raw)
        lines = []
        for i, b in enumerate(blocks, 1):
            t = b["text"].strip()
            if t:
                lines += [str(i), f"{seconds_to_srt_time(b['start'])} --> {seconds_to_srt_time(b['end'])}", t, ""]

        try:
            genai.delete_file(af.name)
        except:
            pass
        return "\n".join(lines)

    except Exception as e:
        print(f"[Subtitler] Gemini fallback hatası: {e}")
        return "1\n00:00:00,000 --> 00:00:05,000\n[Altyazı oluşturulamadı]\n"
    finally:
        p = Path(audio_path)
        if p.exists():
            p.unlink()


def burn_subtitles(video_path: str, srt_path: str,
                   output_path: str, channel_id: str = "default") -> str:
    style = load_style_config(channel_id)
    fs = style.get("base_size", 72)
    font = style.get("font", "Montserrat-Bold")

    force_style = (
        f"FontName={font},FontSize={fs},"
        f"PrimaryColour=&H00FFFFFF&,OutlineColour=&H00000000&,"
        f"BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=80"
    )

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"subtitles={srt_path}:force_style='{force_style}'",
        "-c:a", "copy", "-preset", "fast", output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[Subtitler] Burn hata: {result.stderr[:200]}")
        return video_path
    return output_path
