import os
import tempfile
import subprocess
import httpx
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
from app.config import settings

router = APIRouter(prefix="/captions", tags=["captions"])


def _convert_to_wav(input_path: str, output_path: str) -> None:
    """Converts any audio/video file to mono 16kHz WAV for Deepgram."""
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-ar", "16000",
        "-ac", "1",
        "-f", "wav",
        output_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg conversion failed: {result.stderr.decode()[:300]}")


def _transcribe_with_deepgram(wav_path: str, language: Optional[str]) -> dict:
    """Sends WAV file to Deepgram and returns raw JSON response."""
    with open(wav_path, "rb") as f:
        audio_data = f.read()

    headers = {
        "Authorization": f"Token {settings.DEEPGRAM_API_KEY}",
        "Content-Type": "audio/wav"
    }

    params = {
        "model": "nova-2",
        "punctuate": "true",
        "words": "true",
        "smart_format": "true",
    }

    if language and language != "auto":
        params["language"] = language
    else:
        params["detect_language"] = "true"

    response = httpx.post(
        "https://api.deepgram.com/v1/listen",
        headers=headers,
        params=params,
        content=audio_data,
        timeout=120.0
    )
    response.raise_for_status()
    return response.json()


def _build_segments_from_words(words: list) -> list:
    """
    Groups word-level results into sentence-like segments.
    Splits on sentence-ending punctuation or every 10 words max.
    """
    segments = []
    current_words = []
    current_start = None

    for w in words:
        word_text = w.get("punctuated_word") or w.get("word", "")
        word_start = w.get("start", 0)
        word_end = w.get("end", 0)

        if current_start is None:
            current_start = word_start

        current_words.append(word_text)
        ends_sentence = word_text.rstrip().endswith((".", "?", "!"))
        too_long = len(current_words) >= 10

        if ends_sentence or too_long:
            segments.append({
                "text": " ".join(current_words),
                "start": current_start,
                "end": word_end
            })
            current_words = []
            current_start = None

    if current_words and current_start is not None:
        last_end = words[-1].get("end", current_start + 1) if words else current_start + 1
        segments.append({
            "text": " ".join(current_words),
            "start": current_start,
            "end": last_end
        })

    return segments


@router.post("/generate")
async def generate_captions(
    audio: UploadFile = File(...),
    language: Optional[str] = Form(default=None)
):
    """
    Accepts audio/video blob from the editor (WAV or WebM).
    Converts to 16kHz WAV, transcribes with Deepgram nova-2,
    returns word-level timestamps + segments.
    """
    tmp_input = None
    tmp_wav = None

    try:
        content_type = audio.content_type or "audio/wav"
        ext = ".webm" if "webm" in content_type else ".wav"

        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as f:
            f.write(await audio.read())
            tmp_input = f.name

        tmp_wav = tmp_input.replace(ext, "_16k.wav")
        _convert_to_wav(tmp_input, tmp_wav)

        raw = _transcribe_with_deepgram(tmp_wav, language)

        channels = raw.get("results", {}).get("channels", [])
        if not channels:
            raise HTTPException(status_code=422, detail="Deepgram returned no channels")

        alternative = channels[0].get("alternatives", [{}])[0]
        words = alternative.get("words", [])
        transcript = alternative.get("transcript", "")

        word_list = [
            {
                "word": w.get("word", ""),
                "punctuated_word": w.get("punctuated_word") or w.get("word", ""),
                "start": w.get("start", 0),
                "end": w.get("end", 0),
                "confidence": w.get("confidence", 1.0)
            }
            for w in words
        ]

        segments = _build_segments_from_words(words)

        detected_language = (
            channels[0].get("detected_language")
            or (language if language and language != "auto" else "auto")
        )

        print(f"[Captions] Transcribed {len(word_list)} words, {len(segments)} segments. Lang: {detected_language}")

        return {
            "segments": segments,
            "words": word_list,
            "text": transcript,
            "language": detected_language
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Captions] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for path in [tmp_input, tmp_wav]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
