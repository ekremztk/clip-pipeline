"""
Pipeline Inspector — bir job'un tüm adım çıktılarını gösterir.
Kullanım:
  # Local sunucu:
  PIPELINE_DEBUG=1 uvicorn app.main:app --reload --port 8000
  python pipeline_inspector.py <job_id>
  python pipeline_inspector.py --watch <job_id>

  # Railway sunucu:
  python pipeline_inspector.py <job_id> --url https://your-app.railway.app
  python pipeline_inspector.py --watch <job_id> --url https://your-app.railway.app --token <supabase_token>
"""
import sys, os, json, time, glob, textwrap, requests

# Override via --url and --token args (see arg parsing below)
BASE_URL = "http://localhost:8000"
HEADERS = {"Authorization": "Bearer dev_token"}
REMOTE_MODE = False  # set to True when --url is passed; uses /debug/pipeline API instead of local /tmp

STEP_LABELS = {
    "s01_audio_extract":      "S01 — Ses Çıkarma (FFmpeg)",
    "s02_transcribe":         "S02 — Transkript (Deepgram)",
    "s03_speaker_id":         "S03 — Konuşmacı Tanıma",
    "s04_labeled_transcript": "S04 — Etiketli Transkript",
    "s05_unified_discovery":  "S05 — Clip Adayları (Gemini)",
    "s06_batch_evaluation":   "S06 — Claude Değerlendirmesi",
    "s07_precision_cut":      "S07 — Hassas Kesim",
    "s08_export":             "S08 — Export + R2",
    "s09_reframe":            "S09 — Reframe 9:16",
    "s10_captions":           "S10 — Altyazı",
}


def sep(char="─", n=80):
    print(char * n)


def print_step(step_key: str, data: object):
    label = STEP_LABELS.get(step_key, step_key)
    sep("═")
    print(f"  {label}")
    sep("═")

    if step_key == "s01_audio_extract":
        print(f"  audio_path: {data.get('audio_path')}")

    elif step_key == "s02_transcribe":
        words = data.get("words", [])
        utterances = data.get("utterances", [])
        print(f"  Süre        : {data.get('duration', 0):.1f}s")
        print(f"  Kelime sayısı: {len(words)}")
        print(f"  Utterance   : {len(utterances)}")
        print(f"  Dil/model   : {data.get('language', '?')} / {data.get('model', '?')}")
        if utterances:
            print()
            print("  İlk 3 utterance:")
            for u in utterances[:3]:
                spk = u.get("speaker", "?")
                txt = u.get("transcript", "")[:120]
                t0  = u.get("start", 0)
                t1  = u.get("end", 0)
                print(f"    [{t0:.1f}s–{t1:.1f}s] SPEAKER_{spk}: {txt}")

    elif step_key == "s03_speaker_id":
        pmap = data.get("predicted_map", {})
        stats = data.get("speaker_stats", {})
        print(f"  Tahmin edilen roller:")
        for spk_id, info in pmap.items():
            print(f"    SPEAKER_{spk_id} → {info.get('role','?')} ({info.get('name','?')})")
        if stats:
            print(f"  Konuşma süreleri:")
            for spk_id, s in stats.items():
                print(f"    SPEAKER_{spk_id}: {s.get('total_duration', 0):.1f}s, {s.get('utterance_count', 0)} utterance")

    elif step_key == "s04_labeled_transcript":
        lt = data.get("labeled_transcript", "")
        lines = lt.split("\n")[:20]
        print(f"  (İlk 20 satır gösteriliyor, toplam {len(lt.split(chr(10)))} satır)")
        print()
        for line in lines:
            print(f"  {line}")

    elif step_key == "s05_unified_discovery":
        candidates = data if isinstance(data, list) else []
        print(f"  Toplam aday: {len(candidates)}")
        print()
        for i, c in enumerate(candidates, 1):
            print(f"  [{i}] {c.get('start_time', 0):.1f}s – {c.get('end_time', 0):.1f}s  "
                  f"({(c.get('end_time',0)-c.get('start_time',0)):.0f}s)")
            print(f"       hook    : {c.get('hook_text','')[:100]}")
            print(f"       content : {c.get('content_type','?')}  |  strategy: {c.get('clip_strategy_role','?')}")
            print(f"       score   : {c.get('standalone_score','?')}  |  viral: {c.get('viral_potential','?')}")
            print()

    elif step_key == "s06_batch_evaluation":
        clips = data if isinstance(data, list) else []
        print(f"  Quality gate'i geçen clip: {len(clips)}")
        print()
        for i, c in enumerate(clips, 1):
            print(f"  [{i}] {c.get('start_time', 0):.1f}s – {c.get('end_time', 0):.1f}s")
            print(f"       hook        : {c.get('hook_text','')[:100]}")
            print(f"       score       : {c.get('score','?')}  standalone: {c.get('standalone_score','?')}")
            print(f"       content_type: {c.get('content_type','?')}  strategy: {c.get('clip_strategy_role','?')}")
            print(f"       keep        : {c.get('keep','?')}  rationale: {str(c.get('rationale',''))[:100]}")
            print()

    elif step_key == "s07_precision_cut":
        clips = data if isinstance(data, list) else []
        print(f"  Kesilecek clip: {len(clips)}")
        print()
        for i, c in enumerate(clips, 1):
            orig_s = c.get("start_time", c.get("original_start", 0))
            orig_e = c.get("end_time", c.get("original_end", 0))
            final_s = c.get("final_start", orig_s)
            final_e = c.get("final_end", orig_e)
            print(f"  [{i}] {orig_s:.2f}s–{orig_e:.2f}s  →  {final_s:.2f}s–{final_e:.2f}s  "
                  f"(süre: {final_e - final_s:.1f}s)")
            print(f"       hook: {c.get('hook_text','')[:80]}")
            print()

    elif step_key == "s08_export":
        clips = data if isinstance(data, list) else []
        print(f"  Export edilen clip: {len(clips)}")
        print()
        for i, c in enumerate(clips, 1):
            print(f"  [{i}] clip_id : {c.get('clip_id', c.get('id','?'))}")
            print(f"       süre    : {c.get('duration_s','?')}s")
            print(f"       R2 path : {c.get('video_landscape_path','?')}")
            print()

    elif step_key == "s09_reframe":
        clips = data if isinstance(data, list) else []
        print(f"  Reframe edilen clip: {len(clips)}")
        print()
        for i, c in enumerate(clips, 1):
            print(f"  [{i}] clip_id      : {c.get('clip_id', c.get('id','?'))}")
            print(f"       reframed_path: {c.get('video_reframed_path','?')}")
            meta = c.get("reframe_metadata", {})
            if meta:
                print(f"       strateji     : {meta.get('strategy','?')}")
                print(f"       kararlar     : {str(meta.get('frame_decisions',''))[:100]}")
            print()

    elif step_key == "s10_captions":
        clips = data if isinstance(data, list) else []
        print(f"  Altyazı eklenen clip: {len(clips)}")
        print()
        for i, c in enumerate(clips, 1):
            print(f"  [{i}] clip_id       : {c.get('clip_id', c.get('id','?'))}")
            print(f"       captioned_path: {c.get('video_captioned_path','?')}")
            meta = c.get("caption_metadata", {})
            if meta:
                print(f"       template      : {meta.get('template','?')}")
                print(f"       kelime sayısı : {meta.get('word_count','?')}")
            print()

    else:
        # Bilinmeyen adım — ham JSON
        print(json.dumps(data, indent=2, default=str)[:2000])

    print()


def show_full_json(step_key: str, data: object):
    sep("─")
    print(f"  TAM JSON → {step_key}")
    sep("─")
    print(json.dumps(data, indent=2, default=str))
    print()


def load_debug_dir(job_id: str):
    return f"/tmp/pipeline_debug_{job_id}"


def remote_list_steps(job_id: str) -> list[str]:
    try:
        r = requests.get(f"{BASE_URL}/debug/pipeline/{job_id}/steps", headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return r.json().get("steps", [])
    except Exception as e:
        print(f"  [remote] steps listesi alınamadı: {e}")
    return []


def remote_get_step(job_id: str, step_name: str) -> object:
    try:
        r = requests.get(f"{BASE_URL}/debug/pipeline/{job_id}/steps/{step_name}", headers=HEADERS, timeout=30)
        if r.status_code == 200:
            return r.json().get("data")
    except Exception as e:
        print(f"  [remote] {step_name} alınamadı: {e}")
    return None


def show_job_status(job_id: str):
    r = requests.get(f"{BASE_URL}/jobs/{job_id}", headers=HEADERS, timeout=10)
    if r.status_code != 200:
        print(f"  Job bulunamadı ({r.status_code})")
        return None
    job = r.json().get("job", {})
    print(f"  Job ID   : {job_id}")
    print(f"  Durum    : {job.get('status','?')}")
    print(f"  Adım     : {job.get('current_step','?')} ({job.get('progress_pct','?')}%)")
    print(f"  Clip sayı: {job.get('clip_count','?')}")
    return job


def watch_mode(job_id: str, full_json: bool = False):
    step_order = list(STEP_LABELS.keys())
    seen: set = set()

    if REMOTE_MODE:
        print(f"\nCanlı izleme başladı (remote) — {BASE_URL}")
    else:
        debug_dir = load_debug_dir(job_id)
        print(f"\nCanlı izleme başladı — {debug_dir}")
    print("Pipeline tamamlanınca otomatik durur. Çıkmak için Ctrl+C\n")

    while True:
        if REMOTE_MODE:
            available = remote_list_steps(job_id)
            for step_key in step_order:
                if step_key in available and step_key not in seen:
                    seen.add(step_key)
                    data = remote_get_step(job_id, step_key)
                    if data is not None:
                        print_step(step_key, data)
                        if full_json:
                            show_full_json(step_key, data)
        else:
            debug_dir = load_debug_dir(job_id)
            for step_key in step_order:
                path = f"{debug_dir}/{step_key}.json"
                if path not in seen and os.path.exists(path):
                    seen.add(path)
                    with open(path) as f:
                        data = json.load(f)
                    print_step(step_key, data)
                    if full_json:
                        show_full_json(step_key, data)

        try:
            r = requests.get(f"{BASE_URL}/jobs/{job_id}", headers=HEADERS, timeout=5)
            if r.status_code == 200:
                status = r.json().get("job", {}).get("status", "")
                if status in ("completed", "failed", "partial"):
                    print(f"\nPipeline bitti: {status}")
                    break
        except Exception:
            pass

        time.sleep(3)


def inspect_mode(job_id: str, full_json: bool = False):
    sep("═", 80)
    print(f"  PIPELINE INSPECTOR — job: {job_id}")
    sep("═", 80)
    show_job_status(job_id)
    print()

    step_order = list(STEP_LABELS.keys())

    if REMOTE_MODE:
        available = remote_list_steps(job_id)
        if not available:
            print("  Henüz hiçbir adım tamamlanmamış (veya PIPELINE_DEBUG=1 değil).")
            return
        for step_key in step_order:
            if step_key in available:
                data = remote_get_step(job_id, step_key)
                if data is not None:
                    print_step(step_key, data)
                    if full_json:
                        show_full_json(step_key, data)
    else:
        debug_dir = load_debug_dir(job_id)
        if not os.path.exists(debug_dir):
            print(f"  Hata: Debug dizini yok: {debug_dir}")
            print(f"  Sunucuyu PIPELINE_DEBUG=1 ile başlatman gerekiyor.")
            return
        files = glob.glob(f"{debug_dir}/*.json")
        if not files:
            print("  Henüz hiçbir adım tamamlanmamış.")
            return
        for step_key in step_order:
            path = f"{debug_dir}/{step_key}.json"
            if os.path.exists(path):
                with open(path) as f:
                    data = json.load(f)
                print_step(step_key, data)
                if full_json:
                    show_full_json(step_key, data)


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(0)

    full_json = "--json" in args
    watch = "--watch" in args

    # --url https://xxx.railway.app  →  remote mode
    url_arg = None
    for i, a in enumerate(args):
        if a == "--url" and i + 1 < len(args):
            url_arg = args[i + 1]
        elif a.startswith("--url="):
            url_arg = a.split("=", 1)[1]

    token_arg = None
    for i, a in enumerate(args):
        if a == "--token" and i + 1 < len(args):
            token_arg = args[i + 1]
        elif a.startswith("--token="):
            token_arg = a.split("=", 1)[1]

    if url_arg:
        BASE_URL = url_arg.rstrip("/")
        REMOTE_MODE = True
        if token_arg:
            HEADERS["Authorization"] = f"Bearer {token_arg}"

    positional = [a for a in args if not a.startswith("--") and a not in (url_arg, token_arg)]
    if not positional:
        print("Kullanım: python pipeline_inspector.py <job_id> [--watch] [--json] [--url URL] [--token TOKEN]")
        sys.exit(1)

    job_id = positional[0]

    if watch:
        watch_mode(job_id, full_json=full_json)
    else:
        inspect_mode(job_id, full_json=full_json)
