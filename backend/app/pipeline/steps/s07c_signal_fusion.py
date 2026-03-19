import re
from typing import List, Dict, Any, Optional

def run(labeled_transcript: str, energy_data: dict, visual_events: list, humor_moments: list, job_id: str) -> List[Dict[str, Any]]:
    """
    Fuses multiple signals (transcript, energy, visuals, humor) into 5-second windows.
    Returns a list of windows sorted by priority (TRIPLE, DUAL, SINGLE).
    """
    try:
        # 1. Parse labeled_transcript lines
        # Pattern: [MM:SS.s] SPEAKER: [sentiment:X.XX] Text
        # or [MM:SS.s] SPEAKER: Text
        pattern = re.compile(r'\[(\d+):(\d+\.\d+)\]\s+\w.*?:\s*(?:\[sentiment:([-\d.]+)\])?\s*(.+)')
        
        parsed_utterances: List[Dict[str, Any]] = []
        max_timestamp: float = 0.0
        
        for line in labeled_transcript.splitlines():
            line = line.strip()
            if not line:
                continue
                
            match = pattern.search(line)
            if match:
                mm = float(match.group(1))
                ss = float(match.group(2))
                timestamp_seconds = float(mm * 60 + ss)
                
                sentiment_str = match.group(3)
                sentiment_score: Optional[float] = float(sentiment_str) if sentiment_str else None
                
                text = str(match.group(4).strip())
                
                parsed_utterances.append({
                    "timestamp": timestamp_seconds,
                    "sentiment_score": sentiment_score,
                    "text": text
                })
                
                if timestamp_seconds > max_timestamp:
                    max_timestamp = timestamp_seconds
                    
        # 2. Build 5-second windows
        windows: List[Dict[str, Any]] = []
        
        # Ensure energy_data is a dict
        if not isinstance(energy_data, dict):
            energy_data = {}
            
        energy_peaks: list = energy_data.get("energy_peaks", [])
        
        # Calculate dynamic energy threshold based on this video's distribution
        all_energy_values = []
        for e in energy_peaks:
            if isinstance(e, dict) and e.get("energy") is not None:
                try:
                    all_energy_values.append(float(str(e["energy"])))
                except (ValueError, TypeError):
                    pass
        
        if len(all_energy_values) >= 3:
            all_energy_values.sort()
            p75_index = int(len(all_energy_values) * 0.75)
            energy_threshold = all_energy_values[p75_index]
            # Ensure minimum threshold of 0.5 to avoid noise
            energy_threshold = max(0.5, energy_threshold)
        else:
            energy_threshold = 0.75
        
        humor_confidence_threshold = 0.5

        # Ensure visual_events and humor_moments are lists
        if not isinstance(visual_events, list):
            visual_events = []
            
        if not isinstance(humor_moments, list):
            humor_moments = []
            
        total_windows: int = 0
        triple_count: int = 0
        dual_count: int = 0
        
        start: float = 0.0
        while start <= max_timestamp:
            end: float = start + 5.0
            
            # Transcript hit
            window_texts: List[str] = []
            window_sentiments: List[float] = []
            for u in parsed_utterances:
                u_timestamp = float(str(u["timestamp"]))
                if start <= u_timestamp <= end:
                    window_texts.append(str(u["text"]))
                    u_sentiment = u["sentiment_score"]
                    if u_sentiment is not None:
                        window_sentiments.append(float(str(u_sentiment)))
                        
            transcript_hit = len(window_texts) > 0
            transcript_str = " ".join(window_texts) if transcript_hit else ""
            avg_sentiment: Optional[float] = float(sum(window_sentiments)) / len(window_sentiments) if window_sentiments else None
            
            # Energy hit
            energy_hit_val: Optional[float] = None
            for e in energy_peaks:
                if isinstance(e, dict):
                    e_time = e.get("time")
                    e_energy = e.get("energy")
                    if e_time is not None and e_energy is not None:
                        try:
                            f_time = float(str(e_time))
                            f_energy = float(str(e_energy))
                            if start <= f_time <= end and f_energy >= energy_threshold:
                                energy_hit_val = f_energy
                                break
                        except ValueError:
                            pass
                            
            energy_hit = energy_hit_val is not None
            
            # Visual hit
            visual_hit_val: Optional[str] = None
            for v in visual_events:
                if isinstance(v, dict):
                    v_time = v.get("timestamp")
                    if v_time is not None:
                        try:
                            f_v_time = float(str(v_time))
                            if start <= f_v_time <= end:
                                visual_hit_val = str(v.get("event") or v.get("description") or str(v))
                                break
                        except ValueError:
                            pass
            
            visual_hit = visual_hit_val is not None
            
            # Humor hit
            humor_hit_val: Optional[str] = None
            for h in humor_moments:
                if isinstance(h, dict):
                    h_time = h.get("timestamp")
                    h_conf = h.get("confidence")
                    if h_time is not None and h_conf is not None:
                        try:
                            f_h_time = float(str(h_time))
                            f_h_conf = float(str(h_conf))
                            if start <= f_h_time <= end and f_h_conf >= humor_confidence_threshold:
                                humor_hit_val = str(h.get("humor_type") or h.get("type") or "Humor")
                                break
                        except ValueError:
                            pass
                            
            humor_hit = humor_hit_val is not None
            
            # Count signals
            signals_count: int = int(transcript_hit) + int(energy_hit) + int(visual_hit) + int(humor_hit)
            
            if signals_count > 0:
                priority = "SINGLE"
                if signals_count >= 3:
                    priority = "TRIPLE"
                    triple_count += 1
                elif signals_count == 2:
                    priority = "DUAL"
                    dual_count += 1
                    
                windows.append({
                    "timestamp_start": float(start),
                    "timestamp_end": float(end),
                    "transcript": transcript_str,
                    "sentiment_score": avg_sentiment,
                    "energy_level": energy_hit_val,
                    "visual_event": visual_hit_val,
                    "humor_type": humor_hit_val,
                    "priority": priority,
                    "signals_count": signals_count
                })
                
            start += 5.0
            total_windows += 1
            
        # Merge adjacent windows that are both DUAL or higher into single moments
        # This prevents moment-splitting at window boundaries
        merged_windows = []
        skip_next = False
        for idx, w in enumerate(windows):
            if skip_next:
                skip_next = False
                continue

            if idx + 1 < len(windows):
                next_w = windows[idx + 1]
                # If both are DUAL+ and timestamps are adjacent (within 5s)
                if (w["signals_count"] >= 2 and next_w["signals_count"] >= 2
                        and abs(w["timestamp_end"] - next_w["timestamp_start"]) <= 5.0):
                    # Merge: combine into one window
                    merged = {
                        "timestamp_start": w["timestamp_start"],
                        "timestamp_end": next_w["timestamp_end"],
                        "transcript": (w.get("transcript", "") + " " + next_w.get("transcript", "")).strip(),
                        "sentiment_score": w.get("sentiment_score") or next_w.get("sentiment_score"),
                        "energy_level": max(filter(None, [w.get("energy_level"), next_w.get("energy_level")]), default=None),
                        "visual_event": w.get("visual_event") or next_w.get("visual_event"),
                        "humor_type": w.get("humor_type") or next_w.get("humor_type"),
                        "priority": "TRIPLE" if (w["signals_count"] + next_w["signals_count"]) >= 5 else w["priority"],
                        "signals_count": max(w["signals_count"], next_w["signals_count"])
                    }
                    merged_windows.append(merged)
                    skip_next = True
                    continue

            merged_windows.append(w)

        if merged_windows:
            windows = merged_windows

        # 4. Return list sorted by priority (TRIPLE first) then timestamp
        priority_order = {"TRIPLE": 0, "DUAL": 1, "SINGLE": 2}
        
        windows.sort(key=lambda x: (priority_order.get(str(x["priority"]), 3), float(str(x["timestamp_start"]))))
        
        # 5. Print [S07C] logs
        print(f"[S07C] Job {job_id} | Total windows processed: {total_windows} | TRIPLE count: {triple_count} | DUAL count: {dual_count}")
        
        return windows
        
    except Exception as e:
        print(f"[S07C] Error during signal fusion: {e}")
        return []
