"""
analyzer.py
-----------
4 Ajanlı Gemini sistemi:
1. Scout (Bulucu)    — Potansiyel klipleri işaretler
2. Denetçi          — Süre, cümle sınırı, anlam kontrolü yapar
3. Düzeltici        — Hataları milimetrik olarak düzeltir (maks 3 tur)
4. Marketing        — Sadece onaylı kliplere başlık/açıklama yazar
"""

import os
import json
import google.generativeai as genai
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

MIN_CLIP_DURATION = 30
MAX_CLIP_DURATION = 58
MAX_CORRECTION_ROUNDS = 3


def load_viral_references(channel_id: str = "default") -> str:
    BASE_DIR = Path(__file__).resolve().parent
    channel_ref_path = BASE_DIR / "channels" / channel_id / "viral_refs.json"
    default_ref_path = BASE_DIR / "viral_references.json"
    ref_path = channel_ref_path if channel_ref_path.exists() else default_ref_path

    if not ref_path.exists():
        return "Henüz referans veri yok. Genel viral kurallara göre analiz yap."

    try:
        with open(ref_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        ref_text = "KANALIMIZIN BAŞARILI VİRAL KLİP ÖRNEKLERİ:\n"
        for i, ref in enumerate(data[:10]):
            ref_text += f"\n--- ÖRNEK {i+1} ---\n"
            ref_text += f"Başlık: {ref.get('title', '')}\n"
            ref_text += f"Neden Viral Oldu: {ref.get('why_it_went_viral', '')}\n"
            ref_text += f"İçerik: {ref.get('transcript', '')[:150]}...\n"
        return ref_text
    except Exception as e:
        print(f"[Analyzer] Referans yüklenemedi: {e}")
        return ""


def extract_guest_name(video_title: str) -> str:
    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = f"""Bu YouTube video başlığından konuğun/kişinin tam adını çıkar:
"{video_title}"

SADECE ismi yaz, başka hiçbir şey yazma.
Eğer isim bulamazsan "Bilinmiyor" yaz."""
    try:
        response = model.generate_content(prompt)
        name = response.text.strip().replace('"', '').replace("'", "")
        print(f"[Analyzer] Konuk ismi: {name}")
        return name
    except:
        return "Bilinmiyor"


# ── AJAN 1: SCOUT ─────────────────────────────────────────────────────────────

SCOUT_PROMPT = """Sen bir profesyonel video editörüsün. Görevin YouTube videolarından viral short klipler bulmak.

⚠️ KRİTİK: TÜM ÇIKTILAR YALNIZCA TÜRKÇE OLACAK.

KONUK: {guest_name}
VİDEO BAŞLIĞI: {video_title}

BAŞARILI KLİP ÖRNEKLERİMİZ:
{viral_references}

SES ENERJİSİ ANALİZİ:
{audio_energy}

TRANSKRİPT:
{transcript}

Bu videodan {clip_count_instruction} klip adayı bul.

KRİTERLER:
- Güçlü kanca (ilk 3 saniye izleyiciyi tutmalı)
- Duygusal zirve (gülme, şok, itiraf, tartışma)
- Bağlamdan bağımsız anlaşılabilir
- Ses enerjisi yüksek noktalara öncelik ver

SADECE JSON çıktısı ver:
{{
  "candidates": [
    {{
      "clip_no": 1,
      "start_sec": 734.5,
      "end_sec": 768.2,
      "why_interesting": "Türkçe açıklama",
      "hook": "İlk 2-3 saniyedeki kanca cümlesi"
    }}
  ]
}}"""


# ── AJAN 2: DENETÇİ ───────────────────────────────────────────────────────────

DENETCI_PROMPT = """Sen bir video kalite denetçisisin.

⚠️ KRİTİK: TÜM ÇIKTILAR YALNIZCA TÜRKÇE OLACAK.

KONTROL LİSTESİ:
1. Süre {min_dur}-{max_dur} saniye arasında mı?
2. Başlangıç cümle başında mı?
3. Bitiş cümle sonunda mı?
4. Bağlamdan bağımsız anlaşılabilir mi?
5. Diğer kliplerle çakışıyor mu?

KLİP ADAYLARI:
{candidates}

TRANSKRİPT:
{transcript}

SADECE JSON çıktısı ver:
{{
  "reviews": [
    {{"clip_no": 1, "status": "ONAYLI", "issue": null}},
    {{"clip_no": 2, "status": "REDDEDILDI", "issue": "Bitiş cümle ortasında, 772.0s'ye kaydır"}}
  ]
}}"""


# ── AJAN 3: DÜZELTİCİ ────────────────────────────────────────────────────────

DUZELTICI_PROMPT = """Sen hassas bir video editörüsün. Reddedilen klibi düzelt.

⚠️ KRİTİK: TÜM ÇIKTILAR YALNIZCA TÜRKÇE OLACAK.

REDDEDİLEN KLİP: {rejected_clip}
SORUN: {issue}

TRANSKRİPT (ilgili bölüm):
{transcript_segment}

Kurallar:
- {min_dur}-{max_dur} saniye arasında olmalı
- Cümle başında başla, cümle sonunda bitir
- ASLA kelime ortasında kesme

SADECE JSON çıktısı ver:
{{
  "clip_no": 1,
  "new_start_sec": 734.5,
  "new_end_sec": 763.0,
  "correction_note": "Düzeltme açıklaması"
}}"""


# ── AJAN 4: MARKETİNG ────────────────────────────────────────────────────────

MARKETING_PROMPT = """Sen bir sosyal medya uzmanısın.

⚠️ KRİTİK: TÜM ÇIKTILAR YALNIZCA TÜRKÇE OLACAK. Başlık, açıklama, hashtag — hepsi Türkçe.

KONUK: {guest_name}
VİDEO BAŞLIĞI: {video_title}
KLİP: {start_sec}s - {end_sec}s
NEDEN SEÇİLDİ: {why_interesting}
KANCA: {hook}

KLİP TRANSKRİPTİ:
{clip_transcript}

BAŞARILI ÖRNEKLERİMİZ:
{viral_references}

SADECE JSON çıktısı ver:
{{
  "title": "Emoji içeren Türkçe başlık — {guest_name} adı geçmeli",
  "description": "2-3 cümle SEO uyumlu Türkçe açıklama",
  "hashtags": "#shorts #viral #podcast #türkçe ...",
  "hook_sentence": "İlk 3 saniyedeki kanca",
  "clip_text": "Klipte söylenen kelimelerin tam metni",
  "why_selected": "Detaylı Türkçe açıklama — neden bu an seçildi",
  "bolum_analizi": [
    {{"sure": "0-15s", "aciklama": "Açıklama"}},
    {{"sure": "15-30s", "aciklama": "Açıklama"}},
    {{"sure": "30-45s", "aciklama": "Açıklama"}}
  ],
  "puanlar": {{
    "kanca_gucu": 8,
    "duygusal_zirve": 9,
    "bagimsiz_anlasılabilirlik": 7,
    "izlenme_orani_tahmini": 8,
    "toplam": 8.0
  }},
  "trim_note": "Kırpma önerisi veya 'Kırpma gerekmiyor'"
}}"""


# ── ANA FONKSİYON ─────────────────────────────────────────────────────────────

def analyze_audio(mp3_path: str, clip_count: int, video_title: str = "",
                  transcript: dict = None, audio_energy: dict = None,
                  channel_id: str = "default") -> list[dict]:

    model = genai.GenerativeModel(
        "gemini-2.5-flash",
        generation_config={"response_mime_type": "application/json"}
    )

    clip_count_instruction = "1-3 arası en uygun sayıda" if clip_count == 0 else f"tam olarak {clip_count}"
    viral_refs = load_viral_references(channel_id)
    guest_name = extract_guest_name(video_title) if video_title else "Bilinmiyor"

    # Transkript hazırla
    audio_file = None
    if transcript and transcript.get("segments"):
        transcript_text = _format_transcript(transcript)
        print(f"[Analyzer] WhisperX transkripti kullanılıyor.")
    else:
        print("[Analyzer] Ses dosyası Gemini'a yükleniyor...")
        audio_file = genai.upload_file(mp3_path, mime_type="audio/mp3")
        transcript_text = "[Ses dosyası doğrudan analiz ediliyor]"

    energy_text = audio_energy.get("summary", "Ses analizi mevcut değil.") if audio_energy else "Ses analizi mevcut değil."

    # ── AJAN 1: SCOUT ──────────────────────────────────────────────────────
    print("\n[Analyzer] 🔍 AJAN 1: Scout çalışıyor...")

    scout_prompt = SCOUT_PROMPT.format(
        guest_name=guest_name,
        video_title=video_title,
        viral_references=viral_refs,
        audio_energy=energy_text,
        transcript=transcript_text[:8000],
        clip_count_instruction=clip_count_instruction
    )

    try:
        if audio_file:
            scout_resp = model.generate_content([audio_file, scout_prompt])
        else:
            scout_resp = model.generate_content(scout_prompt)
        candidates = json.loads(scout_resp.text).get("candidates", [])
        print(f"[Analyzer] Scout {len(candidates)} aday buldu.")
    except Exception as e:
        raise RuntimeError(f"Scout ajanı başarısız: {e}")

    # ── AJAN 2 & 3: DENETÇİ + DÜZELTİCİ ─────────────────────────────────
    print("\n[Analyzer] 🔎 AJAN 2 & 3: Denetçi + Düzeltici çalışıyor...")

    approved_clips = []
    pending = candidates.copy()

    for round_no in range(1, MAX_CORRECTION_ROUNDS + 1):
        if not pending:
            break

        print(f"[Analyzer] Tur {round_no}/{MAX_CORRECTION_ROUNDS} — {len(pending)} klip kontrol ediliyor...")

        try:
            denetci_resp = model.generate_content(DENETCI_PROMPT.format(
                min_dur=MIN_CLIP_DURATION,
                max_dur=MAX_CLIP_DURATION,
                candidates=json.dumps(pending, ensure_ascii=False, indent=2),
                transcript=transcript_text[:4000]
            ))
            reviews = json.loads(denetci_resp.text).get("reviews", [])
        except Exception as e:
            print(f"[Analyzer] Denetçi hatası: {e}, tüm adaylar onaylanıyor.")
            approved_clips.extend(pending)
            break

        still_pending = []
        for review in reviews:
            clip_no = review.get("clip_no")
            status = review.get("status", "")
            issue = review.get("issue")
            clip = next((c for c in pending if c.get("clip_no") == clip_no), None)
            if not clip:
                continue

            if status == "ONAYLI":
                approved_clips.append(clip)
                print(f"[Analyzer] ✅ Klip {clip_no} onaylandı.")
            else:
                print(f"[Analyzer] ⚠️ Klip {clip_no} reddedildi: {issue}")
                if round_no < MAX_CORRECTION_ROUNDS:
                    start = clip.get("start_sec", 0)
                    end = clip.get("end_sec", 30)
                    segment = _extract_segment(transcript_text, start - 5, end + 5)

                    try:
                        duz_resp = model.generate_content(DUZELTICI_PROMPT.format(
                            rejected_clip=json.dumps(clip, ensure_ascii=False),
                            issue=issue,
                            transcript_segment=segment,
                            min_dur=MIN_CLIP_DURATION,
                            max_dur=MAX_CLIP_DURATION
                        ))
                        duz_data = json.loads(duz_resp.text)
                        corrected = clip.copy()
                        corrected["start_sec"] = duz_data.get("new_start_sec", start)
                        corrected["end_sec"] = duz_data.get("new_end_sec", end)
                        corrected["correction_note"] = duz_data.get("correction_note", "")
                        still_pending.append(corrected)
                        print(f"[Analyzer] 🔧 Klip {clip_no} düzeltildi, tekrar denetleniyor...")
                    except Exception as e:
                        print(f"[Analyzer] Düzeltici hatası: {e}, klip iptal.")
                else:
                    print(f"[Analyzer] ❌ Klip {clip_no} {MAX_CORRECTION_ROUNDS} turda düzeltilemedi, iptal.")

        pending = still_pending

    if not approved_clips:
        raise RuntimeError("Hiçbir klip kalite kontrolünden geçemedi.")

    print(f"\n[Analyzer] {len(approved_clips)} klip onaylandı.")

    # ── AJAN 4: MARKETİNG ────────────────────────────────────────────────
    print("\n[Analyzer] 📣 AJAN 4: Marketing çalışıyor...")

    final_clips = []
    for clip in approved_clips:
        clip_no = clip.get("clip_no", 0)
        start = clip.get("start_sec", 0)
        end = clip.get("end_sec", 30)
        clip_transcript = _extract_segment(transcript_text, start, end, text_only=True)

        print(f"[Analyzer] Klip {clip_no} için içerik üretiliyor ({start:.0f}s-{end:.0f}s)...")

        try:
            mkt_resp = model.generate_content(MARKETING_PROMPT.format(
                guest_name=guest_name,
                video_title=video_title,
                start_sec=start,
                end_sec=end,
                why_interesting=clip.get("why_interesting", ""),
                hook=clip.get("hook", ""),
                clip_transcript=clip_transcript,
                viral_references=viral_refs[:2000]
            ))
            mkt_data = json.loads(mkt_resp.text)

            final_clip = {
                "clip_no": clip_no,
                "start_sec": start,
                "end_sec": end,
                "guest_name": guest_name,
                **mkt_data,
                # Eski format uyumluluğu
                "title": mkt_data.get("title", ""),
                "description": mkt_data.get("description", ""),
                "hashtags": mkt_data.get("hashtags", ""),
                "score": mkt_data.get("puanlar", {}).get("toplam", 0),
                "why_selected": mkt_data.get("why_selected", ""),
                "clip_text": mkt_data.get("clip_text", clip_transcript),
                "recommendation": mkt_data.get("trim_note", ""),
            }
            final_clips.append(final_clip)
            print(f"[Analyzer] ✅ Klip {clip_no} tamamlandı. Puan: {final_clip['score']}")

        except Exception as e:
            print(f"[Analyzer] Marketing hatası klip {clip_no}: {e}")
            final_clips.append({
                "clip_no": clip_no, "start_sec": start, "end_sec": end,
                "guest_name": guest_name, "title": f"Klip {clip_no}",
                "description": "", "hashtags": "#shorts #viral",
                "score": 0, "why_selected": clip.get("why_interesting", ""),
                "clip_text": clip_transcript, "recommendation": ""
            })

    final_clips.sort(key=lambda x: x["start_sec"])

    try:
        if audio_file:
            genai.delete_file(audio_file.name)
    except:
        pass

    print(f"\n[Analyzer] 🎬 Pipeline tamamlandı. {len(final_clips)} klip hazır.")
    return final_clips


# ── Yardımcı fonksiyonlar ─────────────────────────────────────────────────────

def _format_transcript(transcript: dict) -> str:
    segments = transcript.get("segments", [])
    lines = []
    for seg in segments:
        start = seg.get("start", 0)
        text = seg.get("text", "").strip()
        if not text:
            continue
        h, m, s = int(start // 3600), int((start % 3600) // 60), int(start % 60)
        lines.append(f"[{h:02}:{m:02}:{s:02}] {text}")
    return "\n".join(lines)


def _extract_segment(transcript_text: str, start: float, end: float, text_only: bool = False) -> str:
    lines = []
    for line in transcript_text.split('\n'):
        try:
            if not line.startswith("["):
                continue
            time_str = line[1:9]
            parts = time_str.split(":")
            sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            if start <= sec <= end:
                if text_only and "] " in line:
                    lines.append(line.split("] ", 1)[-1])
                else:
                    lines.append(line)
        except:
            continue
    return " ".join(lines) if text_only else "\n".join(lines)
