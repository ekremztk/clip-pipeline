"""
scorer.py
---------
K2 Segment Skorlama.
"""

from database import get_client

_celebrity_cache = None

def _check_celebrity(text: str) -> bool:
    global _celebrity_cache
    if not text.strip():
        return False
        
    try:
        if _celebrity_cache is None:
            client = get_client()
            if client:
                response = client.table("celebrity_registry").select("name").execute()
                _celebrity_cache = [row.get("name", "").lower() for row in response.data if row.get("name")]
            else:
                _celebrity_cache = []
                
        text_lower = text.lower()
        for name in _celebrity_cache:
            if name in text_lower:
                return True
    except Exception as e:
        print(f"[Scorer] Celebrity check error: {e}")
        _celebrity_cache = []
        
    return False

def extract_signals(start_sec: float, end_sec: float, transcript_data: dict, energy_data: dict, genome: dict) -> dict:
    window = {
        "start": start_sec,
        "end": end_sec,
        "wpm": 0.0,
        "has_question": 0.0,
        "has_exclamation": 0.0,
        "speaker_change": 0.0,
        "celebrity_name": 0.0,
        "rms_spike": 0.0,
        "golden_duration": 0.0
    }
    
    duration = end_sec - start_sec
    if duration <= 0:
        return window

    # TRANSKRİPT SİNYALLERİ
    segments = transcript_data.get("segments", [])
    word_count = 0
    full_text = []

    has_question = False
    has_exclamation = False
    speaker_change = False

    for i, seg in enumerate(segments):
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)

        if seg_end > start_sec and seg_start < end_sec:
            text = seg.get("text", "")
            full_text.append(text)
            word_count += len(text.split())

            if "?" in text:
                has_question = True
            if "!" in text:
                has_exclamation = True

            if i < len(segments) - 1:
                next_start = segments[i + 1].get("start", 0)
                if seg_end + 1.0 < next_start:
                    speaker_change = True

    combined_text = " ".join(full_text)
    
    wpm = word_count / (duration / 60.0) if duration > 0 else 0.0
    window["wpm"] = min(wpm / 200.0, 1.0)
    window["has_question"] = 1.0 if has_question else 0.0
    window["has_exclamation"] = 1.0 if has_exclamation else 0.0
    window["speaker_change"] = 1.0 if speaker_change else 0.0
    
    window["celebrity_name"] = 1.0 if _check_celebrity(combined_text) else 0.0

    # AKUSTİK SİNYALLER
    rms_spike = 0.0
    if "windows" in energy_data:
        for w in energy_data["windows"]:
            w_start = w.get("start", 0)
            w_end = w.get("end", 0)
            if (w_start + w_end) / 2 >= start_sec and (w_start + w_end) / 2 <= end_sec:
                val = w.get("rms_spike", 0.0)
                if val > rms_spike:
                    rms_spike = float(val)
    else:
        for peak in energy_data.get("energy_peaks", []):
            t = peak.get("time", 0)
            if start_sec <= t <= end_sec:
                e = peak.get("energy", 0.0)
                if e > rms_spike:
                    rms_spike = float(e)
                    
    window["rms_spike"] = rms_spike

    # GENOME SİNYALLERİ
    golden_match = 1.0
    if genome and "golden_duration" in genome:
        avg_dur = genome["golden_duration"].get("avg", 0)
        if avg_dur > 0:
            diff = abs(duration - avg_dur)
            golden_match = max(0.0, 1.0 - (diff / avg_dur))
    window["golden_duration"] = golden_match

    return window

def _calculate_window_score(window: dict, signal_weights: dict) -> float:
    total = 0.0
    weight_sum = 0.0
    
    for key, weight in signal_weights.items():
        if key in window:
            val = window[key]
            total += val * weight
            weight_sum += weight
            
    if weight_sum > 0:
        return (total / weight_sum) * 100.0
    return 0.0

def coarse_scan(transcript_data: dict, energy_data: dict, signal_weights: dict, genome: dict = None) -> list:
    duration = energy_data.get("duration", 0)
    if duration == 0:
        segments = transcript_data.get("segments", [])
        if segments:
            duration = segments[-1].get("end", 0)

    window_size = 30.0
    steps = int(duration // window_size) + (1 if duration % window_size > 0 else 0)
    
    windows = []
    for i in range(steps):
        start = i * window_size
        end = min(start + window_size, duration)
        if end - start < 1.0:
            continue
            
        window_sigs = extract_signals(start, end, transcript_data, energy_data, genome)
        score = _calculate_window_score(window_sigs, signal_weights)
        window_sigs["score"] = score
        windows.append(window_sigs)

    if not windows:
        return []
        
    max_score = max(w["score"] for w in windows)
    cutoff = max_score * 0.6
    
    passed = [w for w in windows if w["score"] >= cutoff]
    passed.sort(key=lambda x: x["score"], reverse=True)
    
    result = passed[:8]
    if len(result) < 3:
        all_sorted = sorted(windows, key=lambda x: x["score"], reverse=True)
        result = all_sorted[:3]
        
    result.sort(key=lambda x: x["start"])
    return [{"start": r["start"], "end": r["end"]} for r in result]

def fine_scan(passed_sections: list, transcript_data: dict, energy_data: dict, signal_weights: dict, genome: dict = None) -> list:
    fine_windows = []
    window_size = 5.0
    
    for sec in passed_sections:
        start_sec = sec["start"]
        end_sec = sec["end"]
        
        current = start_sec
        while current + window_size <= end_sec:
            w_start = current
            w_end = current + window_size
            
            window_sigs = extract_signals(w_start, w_end, transcript_data, energy_data, genome)
            score = _calculate_window_score(window_sigs, signal_weights)
            
            fine_windows.append({
                "start": w_start,
                "end": w_end,
                "score": score,
                "signals": {k: v for k, v in window_sigs.items() if k not in ["start", "end"]}
            })
            
            current += window_size
            
    fine_windows.sort(key=lambda x: x["score"], reverse=True)
    return fine_windows

def score_segments(transcript_data: dict, energy_data: dict, genome: dict, signal_weights: dict) -> list:
    duration = energy_data.get("duration", 0)
    if duration == 0:
        segments = transcript_data.get("segments", [])
        if segments:
            duration = segments[-1].get("end", 0)

    MIN_VIDEO_DURATION = 60
    if duration < MIN_VIDEO_DURATION:
        return []

    if duration < 120:
        passed_sections = [{"start": 0, "end": duration}]
    else:
        passed_sections = coarse_scan(transcript_data, energy_data, signal_weights, genome)

    return fine_scan(passed_sections, transcript_data, energy_data, signal_weights, genome)
