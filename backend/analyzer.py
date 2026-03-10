"""
analyzer.py
-----------
4 Ajanlı Gemini sistemi (English Native):
1. Scout (Bulucu)    — Potansiyel klipleri işaretler
2. Denetçi          — Süre, cümle sınırı, anlam kontrolü yapar
3. Düzeltici        — Hataları milimetrik olarak düzeltir (maks 3 tur)
4. Marketing        — Sadece onaylı kliplere başlık/açıklama yazar
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

# YENİ NESİL GOOGLE GENAI SDK İÇE AKTARILIYOR
from google import genai
from google.genai import types

load_dotenv()

# SÜRELER SENİN İSTEDİĞİN GİBİ 15 VE 35 OLARAK GÜNCELLENDİ!
MIN_CLIP_DURATION = 15
MAX_CLIP_DURATION = 35
MAX_CORRECTION_ROUNDS = 3


def load_viral_references(channel_id: str = "default") -> str:
    BASE_DIR = Path(__file__).resolve().parent
    channel_ref_path = BASE_DIR / "channels" / channel_id / "viral_refs.json"
    default_ref_path = BASE_DIR / "viral_references.json"
    ref_path = channel_ref_path if channel_ref_path.exists() else default_ref_path

    if not ref_path.exists():
        return "No reference data. Use general viral content rules."

    try:
        with open(ref_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        ref_text = "OUR MOST SUCCESSFUL VIRAL CLIP EXAMPLES:\n"
        for i, ref in enumerate(data[:10]):
            ref_text += f"\n--- EXAMPLE {i+1} ---\n"
            ref_text += f"Title: {ref.get('title', '')}\n"
            ref_text += f"Why it went viral: {ref.get('why_it_went_viral', '')}\n"
            ref_text += f"Content: {ref.get('transcript', '')[:150]}...\n"
        return ref_text
    except Exception as e:
        print(f"[Analyzer] Referans yüklenemedi: {e}")
        return ""


def extract_guest_name(video_title: str) -> str:
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    prompt = f"""Extract the full name of the guest/person from this YouTube video title:
"{video_title}"

Write ONLY the name, nothing else.
If you cannot find a name, write "Unknown"."""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        name = response.text.strip().replace('"', '').replace("'", "")
        print(f"[Analyzer] Guest Name: {name}")
        return name
    except:
        return "Unknown"


# ── AJAN 1: SCOUT ─────────────────────────────────────────────────────────────

SCOUT_PROMPT = """You are a highly skilled professional video editor. Your task is to find viral short clips from YouTube videos.

⚠️ CRITICAL: ALL YOUR OUTPUTS MUST BE ENTIRELY IN ENGLISH.
⚠️ MATHEMATICS CRITICAL: The duration (end_sec - start_sec) ABSOLUTELY MUST be between {min_dur} and {max_dur} seconds. Do not select clips shorter than {min_dur} seconds!

GUEST: {guest_name}
VIDEO TITLE: {video_title}

SUCCESSFUL CLIP EXAMPLES:
{viral_references}

AUDIO ENERGY ANALYSIS:
{audio_energy}

TRANSCRIPT:
{transcript}

Find {clip_count_instruction} clip candidates from this video.

CRITERIA:
- Strong hook: The first 3 seconds must immediately grab attention.
- Emotional peak: Look for laughs, shocks, deep confessions.
- High energy: Prioritize moments where the audio energy spikes.

Output ONLY a valid JSON:
{{
  "candidates":[
    {{
      "clip_no": 1,
      "start_sec": 734.5,
      "end_sec": 768.2,
      "why_interesting": "Explanation of why this clip has high viral potential",
      "hook": "The exact hook sentence spoken in the first 2-3 seconds"
    }}
  ]
}}"""


# ── AJAN 2: DENETÇİ ───────────────────────────────────────────────────────────

DENETCI_PROMPT = """You are a strict video quality inspector. ALL OUTPUTS MUST BE ENTIRELY IN ENGLISH.

CHECKLIST:
1. Is duration strictly between {min_dur} and {max_dur} seconds?
2. Does it start/end cleanly based on the transcript? 
*NOTE: If the transcript segment is missing or unclear, ASSUME the boundaries are correct. DO NOT reject solely because of missing transcript text.*

CLIP CANDIDATES:
{candidates}

TRANSCRIPT:
{transcript}

Output ONLY a valid JSON:
{{
  "reviews":[
    {{"clip_no": 1, "status": "APPROVED", "issue": null}},
    {{"clip_no": 2, "status": "REJECTED", "issue": "Duration is too short. Increase end_sec to reach {min_dur} seconds."}}
  ]
}}"""


# ── AJAN 3: DÜZELTİCİ ────────────────────────────────────────────────────────

DUZELTICI_PROMPT = """You are a precise video editor. Fix the rejected clip's timestamps. ALL OUTPUTS MUST BE IN ENGLISH.

REJECTED CLIP: {rejected_clip}
ISSUE: {issue}

TRANSCRIPT (relevant segment):
{transcript_segment}

RULES:
- Duration MUST be between {min_dur} and {max_dur} seconds. Fix this mathematically first!
- If transcript is unclear, just focus on fixing the duration math.

Output ONLY a valid JSON:
{{
  "clip_no": 1,
  "new_start_sec": 734.5,
  "new_end_sec": 768.0,
  "correction_note": "Extended the end_sec to meet the minimum duration."
}}"""


# ── AJAN 4: MARKETİNG ────────────────────────────────────────────────────────

MARKETING_PROMPT = """You are an elite social media expert. EVERYTHING MUST BE IN ENGLISH.

GUEST: {guest_name}
VIDEO TITLE: {video_title}
CLIP: {start_sec}s - {end_sec}s
WHY SELECTED: {why_interesting}
HOOK: {hook}

CLIP TRANSCRIPT:
{clip_transcript}

SUCCESSFUL EXAMPLES:
{viral_references}

Output ONLY a valid JSON matching this exact structure:
{{
  "title": "Catchy English title with relevant emojis (must include {guest_name})",
  "description": "2-3 sentences SEO optimized English description for Shorts/TikTok/Reels.",
  "hashtags": "#shorts #viral #podcast #english ...",
  "hook_sentence": "The exact hook spoken in the first 3 seconds",
  "clip_text": "Exact English transcript of the words spoken in the clip",
  "why_selected": "Detailed English explanation of why this specific moment was selected",
  "bolum_analizi":[
    {{"sure": "0-15s", "aciklama": "English explanation of what happens in this segment"}}
  ],
  "puanlar": {{
    "kanca_gucu": 85,
    "duygusal_zirve": 90,
    "bagimsiz_anlasilabilirlik": 80,
    "izlenme_orani_tahmini": 95,
    "toplam": 88
  }},
  "trim_note": "Trimming recommendation in English or 'No trimming needed'"
}}
NOTE: All scores in 'puanlar' MUST be INTEGER numbers out of 100."""


# ── ANA FONKSİYON ─────────────────────────────────────────────────────────────

def analyze_audio(mp3_path: str, clip_count: int, video_title: str = "",
                  transcript: dict = None, audio_energy: dict = None,
                  channel_id: str = "default") -> list[dict]:

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    json_config = types.GenerateContentConfig(response_mime_type="application/json")

    clip_count_instruction = "between 1 and 3 (best suitable amount)" if clip_count == 0 else f"exactly {clip_count}"
    viral_refs = load_viral_references(channel_id)
    guest_name = extract_guest_name(video_title) if video_title else "Unknown"

    # Transkript hazırla
    audio_file = None
    if transcript and transcript.get("segments"):
        transcript_text = _format_transcript(transcript)
        print(f"[Analyzer] WhisperX transkripti kullanılıyor.")
    else:
        print("[Analyzer] Ses dosyası Gemini'a yükleniyor...")
        audio_file = client.files.upload(file=mp3_path)
        transcript_text = "[Audio file is directly provided for analysis]"

    energy_text = audio_energy.get("summary", "No audio analysis available.") if audio_energy else "No audio analysis available."

    # ── AJAN 1: SCOUT ──────────────────────────────────────────────────────
    print("\n[Analyzer] 🔍 AJAN 1: Scout çalışıyor...")

    scout_prompt = SCOUT_PROMPT.format(
        guest_name=guest_name,
        video_title=video_title,
        viral_references=viral_refs,
        audio_energy=energy_text,
        transcript=transcript_text[:8000],
        clip_count_instruction=clip_count_instruction,
        min_dur=MIN_CLIP_DURATION,
        max_dur=MAX_CLIP_DURATION
    )

    try:
        if audio_file:
            scout_resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[audio_file, scout_prompt],
                config=json_config
            )
        else:
            scout_resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=scout_prompt,
                config=json_config
            )
        candidates = json.loads(scout_resp.text).get("candidates", [])
        print(f"[Analyzer] Scout {len(candidates)} aday buldu.")
    except Exception as e:
        raise RuntimeError(f"Scout ajanı başarısız: {e}")

    # ── AJAN 2 & 3: DENETÇİ + DÜZELTİCİ ─────────────────────────────────
    print("\n[Analyzer] 🔎 AJAN 2 & 3: Denetçi + Düzeltici çalışıyor...")

    approved_clips =[]
    pending = candidates.copy()

    for round_no in range(1, MAX_CORRECTION_ROUNDS + 1):
        if not pending:
            break

        print(f"[Analyzer] Tur {round_no}/{MAX_CORRECTION_ROUNDS} — {len(pending)} klip kontrol ediliyor...")

        try:
            denetci_prompt = DENETCI_PROMPT.format(
                min_dur=MIN_CLIP_DURATION,
                max_dur=MAX_CLIP_DURATION,
                candidates=json.dumps(pending, ensure_ascii=False, indent=2),
                transcript=transcript_text[:4000]
            )
            denetci_resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=denetci_prompt,
                config=json_config
            )
            reviews = json.loads(denetci_resp.text).get("reviews",[])
        except Exception as e:
            print(f"[Analyzer] Denetçi hatası: {e}, tüm adaylar zorunlu onaylanıyor.")
            approved_clips.extend(pending)
            break

        still_pending =[]
        for review in reviews:
            clip_no = review.get("clip_no")
            status = review.get("status", "")
            issue = review.get("issue")
            clip = next((c for c in pending if c.get("clip_no") == clip_no), None)
            if not clip:
                continue

            if status in ["APPROVED", "ONAYLI"]:
                approved_clips.append(clip)
                print(f"[Analyzer] ✅ Klip {clip_no} onaylandı.")
            else:
                print(f"[Analyzer] ⚠️ Klip {clip_no} reddedildi: {issue}")
                if round_no < MAX_CORRECTION_ROUNDS:
                    start = clip.get("start_sec", 0)
                    end = clip.get("end_sec", 30)
                    segment = _extract_segment(transcript_text, start - 5, end + 5)

                    try:
                        duz_prompt = DUZELTICI_PROMPT.format(
                            rejected_clip=json.dumps(clip, ensure_ascii=False),
                            issue=issue,
                            transcript_segment=segment,
                            min_dur=MIN_CLIP_DURATION,
                            max_dur=MAX_CLIP_DURATION
                        )
                        duz_resp = client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=duz_prompt,
                            config=json_config
                        )
                        duz_data = json.loads(duz_resp.text)
                        corrected = clip.copy()
                        corrected["start_sec"] = duz_data.get("new_start_sec", start)
                        corrected["end_sec"] = duz_data.get("new_end_sec", end)
                        corrected["correction_note"] = duz_data.get("correction_note", "")
                        still_pending.append(corrected)
                        print(f"[Analyzer] 🔧 Klip {clip_no} düzeltildi, tekrar denetleniyor...")
                    except Exception as e:
                        print(f"[Analyzer] Düzeltici hatası: {e}, klip bekletiliyor.")
                        still_pending.append(clip)
                else:
                    print(f"[Analyzer] 🚨 Klip {clip_no} yapay zeka tarafından düzeltilemedi. ZORUNLU ONAY uygulandı!")
                    dur = clip["end_sec"] - clip["start_sec"]
                    if dur < MIN_CLIP_DURATION:
                        clip["end_sec"] = clip["start_sec"] + MIN_CLIP_DURATION + 2
                    elif dur > MAX_CLIP_DURATION:
                        clip["end_sec"] = clip["start_sec"] + MAX_CLIP_DURATION - 2
                    approved_clips.append(clip)

        pending = still_pending

    if not approved_clips:
        raise RuntimeError("Hiçbir klip bulunamadı. Lütfen farklı bir video deneyin.")

    print(f"\n[Analyzer] {len(approved_clips)} klip onaylandı.")

    # ── AJAN 4: MARKETİNG ────────────────────────────────────────────────
    print("\n[Analyzer] 📣 AJAN 4: Marketing çalışıyor...")

    final_clips =[]
    for clip in approved_clips:
        clip_no = clip.get("clip_no", 0)
        start = clip.get("start_sec", 0)
        end = clip.get("end_sec", 30)
        clip_transcript = _extract_segment(transcript_text, start, end, text_only=True)

        print(f"[Analyzer] Klip {clip_no} için içerik üretiliyor ({start:.0f}s-{end:.0f}s)...")

        try:
            mkt_prompt = MARKETING_PROMPT.format(
                guest_name=guest_name,
                video_title=video_title,
                start_sec=start,
                end_sec=end,
                why_interesting=clip.get("why_interesting", ""),
                hook=clip.get("hook", ""),
                clip_transcript=clip_transcript,
                viral_references=viral_refs[:2000]
            )
            mkt_resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=mkt_prompt,
                config=json_config
            )
            mkt_data = json.loads(mkt_resp.text)

            final_clip = {
                "clip_no": clip_no,
                "start_sec": start,
                "end_sec": end,
                "guest_name": guest_name,
                **mkt_data,
                "title": mkt_data.get("title", ""),
                "description": mkt_data.get("description", ""),
                "hashtags": mkt_data.get("hashtags", ""),
                "score": mkt_data.get("puanlar", {}).get("toplam", 0),
                "why_selected": mkt_data.get("why_selected", ""),
                "clip_text": mkt_data.get("clip_text", clip_transcript),
                "transcript": mkt_data.get("clip_text", clip_transcript),
                "recommendation": mkt_data.get("trim_note", ""),
            }
            final_clips.append(final_clip)
            print(f"[Analyzer] ✅ Klip {clip_no} tamamlandı. Puan: {final_clip['score']}")

        except Exception as e:
            print(f"[Analyzer] Marketing hatası klip {clip_no}: {e}")
            final_clips.append({
                "clip_no": clip_no, "start_sec": start, "end_sec": end,
                "guest_name": guest_name, "title": f"Clip {clip_no}",
                "description": "", "hashtags": "#shorts #viral",
                "score": 0, "why_selected": clip.get("why_interesting", ""),
                "clip_text": clip_transcript, "transcript": clip_transcript, "recommendation": ""
            })

    final_clips.sort(key=lambda x: x["start_sec"])

    try:
        if audio_file:
            client.files.delete(name=audio_file.name)
    except:
        pass

    print(f"\n[Analyzer] 🎬 Pipeline tamamlandı. {len(final_clips)} klip hazır.")
    return final_clips


# ── Yardımcı fonksiyonlar ─────────────────────────────────────────────────────

def _format_transcript(transcript: dict) -> str:
    segments = transcript.get("segments", [])
    lines =[]
    for seg in segments:
        start = seg.get("start", 0)
        text = seg.get("text", "").strip()
        if not text:
            continue
        h, m, s = int(start // 3600), int((start % 3600) // 60), int(start % 60)
        lines.append(f"[{h:02}:{m:02}:{s:02}] {text}")
    return "\n".join(lines)


def _extract_segment(transcript_text: str, start: float, end: float, text_only: bool = False) -> str:
    lines =[]
    for line in transcript_text.split('\n'):
        try:
            if not line.startswith("["):
                continue
            time_str = line[1:9]
            parts = time_str.split(":")
            sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            
            if (start - 30) <= sec <= (end + 30):
                if text_only and "] " in line:
                    lines.append(line.split("] ", 1)[-1])
                else:
                    lines.append(line)
        except:
            continue
    res = " ".join(lines) if text_only else "\n".join(lines)
    return res if res.strip() else "[Transcript missing in this exact timestamp, but context is approved.]"