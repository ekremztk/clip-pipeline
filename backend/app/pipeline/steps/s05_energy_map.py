import os
import gc
import subprocess
import numpy as np

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    print("[S05] Warning: Librosa not installed.")

def run(audio_path: str, job_id: str) -> dict:
    """
    Analyzes audio energy using Librosa RMS.
    
    Returns:
    {
        "energy_peaks": [{"time": float, "energy": float, "type": str}],
        "silence_zones": [{"start": float, "end": float, "duration": float}],
        "windows": [{"start": float, "end": float, "rms_mean": float, "rms_max": float, "rms_spike": bool}],
        "duration": float,
        "summary": str
    }
    """
    if not LIBROSA_AVAILABLE:
        print(f"[S05] Librosa not available, skipping energy map for job {job_id}")
        return _empty_result()

    print(f"[S05] Starting audio energy analysis for {job_id}...")

    # Temp WAV file for Librosa (M4A causes issues with soundfile)
    temp_wav = f"{audio_path}_temp_{job_id}.wav"
    
    try:
        # 1. Convert to 16kHz Mono WAV using FFmpeg
        subprocess.run([
            "ffmpeg", "-y", "-i", audio_path, 
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", 
            temp_wav
        ], capture_output=True, check=True)
        
        # 2. Get duration
        sr = 16000
        try:
            duration = librosa.get_duration(path=temp_wav)
        except TypeError:
            # For older librosa versions
            duration = librosa.get_duration(filename=temp_wav)
            
        print(f"[S05] Duration: {duration:.0f}s, Sample rate: {sr}Hz")

        # 3. Calculate RMS Energy
        frame_length = sr  # 1 second
        hop_length = sr // 2  # 0.5 second step
        
        all_rms = []
        
        # Process in blocks if video is > 10 minutes (600s) to avoid memory issues
        if duration > 600:
            print("[S05] Audio is longer than 600s, processing in 300s blocks...")
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
            print("[S05] Warning: RMS calculation returned empty array.")
            return _empty_result()

        times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)

        # Normalize RMS (0-1)
        rms_max_val = rms.max()
        if rms_max_val > 0:
            rms_normalized = rms / rms_max_val
        else:
            rms_normalized = rms

        # 4. Find Energy Peaks
        # Find peaks above 85th percentile
        threshold = np.percentile(rms_normalized, 85)
        peak_indices = []
        
        i = 0
        while i < len(rms_normalized):
            if rms_normalized[i] >= threshold:
                # Find the highest point in this 10-second window
                window_end = min(i + 20, len(rms_normalized))
                peak_idx = i + np.argmax(rms_normalized[i:window_end])
                peak_indices.append(int(peak_idx))
                i = window_end
            else:
                i += 1

        # Get top 10 peaks
        peak_indices.sort(key=lambda idx: rms_normalized[idx], reverse=True)
        peak_indices = peak_indices[:10]
        peak_indices.sort()  # Sort chronologically

        energy_peaks = []
        for idx in peak_indices:
            t = float(times[idx])
            e = float(rms_normalized[idx])
            energy_peaks.append({
                "time": round(t, 1),
                "energy": round(e, 2),
                "type": _energy_type(e)
            })

        # 5. Find Silence Zones
        # Find regions below 15th percentile
        silence_threshold = np.percentile(rms_normalized, 15)
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
                if silence_duration >= 0.5:  # Minimum 0.5s duration
                    silence_zones.append({
                        "start": round(silence_start, 1),
                        "end": round(float(t), 1),
                        "duration": round(silence_duration, 1)
                    })
        
        # Also check if it ends in silence
        if in_silence:
            t_end = float(times[-1])
            silence_duration = t_end - silence_start
            if silence_duration >= 0.5:
                silence_zones.append({
                    "start": round(silence_start, 1),
                    "end": round(t_end, 1),
                    "duration": round(silence_duration, 1)
                })

        print(f"[S05] Found {len(energy_peaks)} energy peaks and {len(silence_zones)} silence zones.")

        # 6. Windows (30-second windows)
        windows = []
        window_size = 30  # seconds
        for start_sec in range(0, int(duration), window_size):
            end_sec = min(start_sec + window_size, float(duration))
            start_idx = librosa.time_to_frames(start_sec, sr=sr, hop_length=hop_length)
            end_idx = librosa.time_to_frames(end_sec, sr=sr, hop_length=hop_length)
            
            # Get RMS values for this window
            window_rms = rms_normalized[start_idx:end_idx]
            
            if len(window_rms) > 0:
                mean_val = float(window_rms.mean())
                max_val = float(window_rms.max())
                rms_mean_all = float(rms_normalized.mean())
                windows.append({
                    "start": float(start_sec),
                    "end": float(end_sec),
                    "rms_mean": mean_val,
                    "rms_max": max_val,
                    "rms_spike": bool(max_val > rms_mean_all * 1.5)
                })
            else:
                windows.append({
                    "start": float(start_sec),
                    "end": float(end_sec),
                    "rms_mean": 0.0,
                    "rms_max": 0.0,
                    "rms_spike": False
                })

        # 7. Summary text for Gemini
        summary = _build_summary(energy_peaks, silence_zones, duration)

        return {
            "energy_peaks": energy_peaks,
            "silence_zones": silence_zones,
            "windows": windows,
            "duration": round(duration, 1),
            "summary": summary
        }

    except Exception as e:
        print(f"[S05] Error during energy analysis: {e}")
        return _empty_result()
    
    finally:
        if os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except Exception as e:
                print(f"[S05] Error removing temporary WAV file: {e}")


def _energy_type(energy: float) -> str:
    if energy >= 0.90:
        return "Very high energy (shouting/laughing)"
    elif energy >= 0.75:
        return "High energy (excited)"
    elif energy >= 0.60:
        return "Medium-high energy (active speaking)"
    else:
        return "Normal energy"


def _build_summary(peaks: list, silences: list, duration: float) -> str:
    """Human-readable summary for Gemini context."""
    lines = []
    lines.append(f"VIDEO DURATION: {duration:.0f} seconds ({duration/60:.1f} minutes)")
    lines.append("")
    lines.append("MOST ENERGETIC MOMENTS (high viral potential):")
    
    for peak in peaks[:8]:  # Show top 8
        h = int(peak["time"] // 3600)
        m = int((peak["time"] % 3600) // 60)
        s = int(peak["time"] % 60)
        timestamp = f"{h:02}:{m:02}:{s:02}"
        lines.append(f"  - {timestamp} | Energy: {peak['energy']:.0%} | {peak['type']}")
    
    lines.append("")
    lines.append(f"NATURAL CUT POINTS (silences): {len(silences)} zones detected")
    
    if silences:
        for sil in silences[:5]:  # Show first 5
            lines.append(f"  - {sil['start']:.1f}s to {sil['end']:.1f}s ({sil['duration']:.1f}s silence)")
    
    return "\n".join(lines)


def _empty_result() -> dict:
    return {
        "energy_peaks": [],
        "silence_zones": [],
        "windows": [],
        "duration": 0.0,
        "summary": "Audio analysis failed or skipped."
    }
