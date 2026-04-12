import os
import tempfile
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from typing import Optional
from app.middleware.auth import get_current_user
from app.captions.core import convert_to_wav, transcribe_with_deepgram, build_word_list, build_segments_from_words

router = APIRouter(prefix="/captions", tags=["captions"])


@router.post("/generate")
async def generate_captions(
    audio: UploadFile = File(...),
    language: Optional[str] = Form(default=None),
    current_user: dict = Depends(get_current_user)
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
        convert_to_wav(tmp_input, tmp_wav)

        raw = transcribe_with_deepgram(tmp_wav, language)

        channels = raw.get("results", {}).get("channels", [])
        if not channels:
            raise HTTPException(status_code=422, detail="Deepgram returned no channels")

        alternative = channels[0].get("alternatives", [{}])[0]
        words = alternative.get("words", [])
        transcript = alternative.get("transcript", "")

        word_list = build_word_list(words)
        segments = build_segments_from_words(words)

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
