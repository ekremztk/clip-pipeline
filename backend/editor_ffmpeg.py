# EDITOR MODULE — Isolated module, no dependencies on other project files

# Render pipeline: TWO-PASS architecture
# Pass 1: structural (cuts + crop) → /tmp/pass1.mp4
# Pass 2: visual (subtitles + overlays + audio) → final output
# Never combine time-altering and visual filters in a single pass (causes A/V sync drift)

import os
import re
import json
import logging
import subprocess

logger = logging.getLogger("editor.ffmpeg")

def get_video_dimensions(video_path: str) -> tuple[int, int]:
    """
    Returns (width, height) of the video using ffprobe.
    """
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-select_streams", "v:0", video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        logger.error(f"ffprobe failed: {result.stderr}")
        return (1920, 1080)  # fallback
        
    try:
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        return (int(stream["width"]), int(stream["height"]))
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as e:
        logger.error(f"Failed to parse ffprobe output: {e}")
        return (1920, 1080)

def build_crop_filter(edit_spec: dict, src_width: int, src_height: int) -> str:
    """
    Builds the crop and scale filter for 16:9 to 9:16 conversion.
    """
    crop_info = edit_spec.get("crop", {})
    mode = crop_info.get("mode", "center")
    
    if mode == "manual" and "x" in crop_info:
        crop_x = int(crop_info["x"] * src_width - 540)
    else:
        crop_x = int(src_width / 2 - 540)
        
    crop_x = max(0, min(crop_x, src_width - 1080))
    return f"crop=1080:{src_height}:{crop_x}:0,scale=1080:1920:flags=lanczos,setsar=1"

def build_dynamic_crop_filter(
    crop_segments: list[dict],
    src_width: int,
    src_height: int
) -> str:
    """
    Builds FFmpeg filter_complex for dynamic per-segment cropping.
    Uses the 'select' filter approach to concatenate pre-cropped segments:
    For each segment: trim -> crop -> scale -> concat
    
    Returns the complete filter_complex string for Pass 1 of the render pipeline.
    """
    if not crop_segments:
        # Fallback just in case
        return f"[0:v]crop=1080:{src_height}:{(src_width - 1080) // 2}:0,scale=1080:1920:flags=lanczos,setsar=1[vout_crop]"
        
    n = len(crop_segments)
    lines = []
    
    splits = "".join([f"[s{i}]" for i in range(n)])
    lines.append(f"[0:v]split={n}{splits}")
    
    concat_inputs = ""
    for i, seg in enumerate(crop_segments):
        start = seg.get("start", 0.0)
        end = seg.get("end", 0.0)
        cx = seg.get("crop_x_pixels", 0)
        
        # Keep crop safe
        cx = max(0, min(cx, src_width - 1080))
        
        lines.append(f"[s{i}]trim=start={start}:end={end},setpts=PTS-STARTPTS,crop=1080:{src_height}:{cx}:0,scale=1080:1920:flags=lanczos,setsar=1[v{i}]")
        concat_inputs += f"[v{i}]"
        
    lines.append(f"{concat_inputs}concat=n={n}:v=1:a=0[vout_crop]")
    
    return ";".join(lines)

def build_cuts_filter(cuts: list, clip_start: float, clip_end: float) -> str:
    """
    Builds FFmpeg select+aselect expression to remove segments and keep the rest.
    Returns the between() expression string.
    """
    keep_segments = []
    current = clip_start
    
    # Sort cuts by start time
    sorted_cuts = sorted(cuts, key=lambda x: x.get("remove_from", 0))
    
    for c in sorted_cuts:
        r_from = c.get("remove_from", 0)
        r_to = c.get("remove_to", 0)
        if current < r_from:
            keep_segments.append((current, r_from))
        current = max(current, r_to)
        
    if current < clip_end:
        keep_segments.append((current, clip_end))
        
    if not keep_segments:
        return "0"
        
    expr = "+".join([f"between(t,{s},{e})" for s, e in keep_segments])
    return expr

def escape_ffmpeg_text(text: str) -> str:
    """
    Escapes special characters that break FFmpeg drawtext filter parsing.
    FFmpeg uses these characters as filter/option separators:
    - backslash: must be escaped first (order matters)
    - single quote: breaks filter string boundaries
    - colon: used as option separator in filter_complex
    - percent: used for FFmpeg format strings
    Must be called on ALL text values before embedding in drawtext.
    """
    text = text.replace('\\', '\\\\')   # Must be first
    text = text.replace("'", "\\'")     # Single quotes
    text = text.replace(':', '\\:')     # Colons
    text = text.replace('%', '\\%')     # Percent signs
    return text

def find_font_path(font_name: str) -> str:
    """
    Searches common Linux font directories for the specified font.
    Search order:
    1. /usr/share/fonts/ (recursive)
    2. /usr/local/share/fonts/
    3. ./fonts/ (project directory)
    Returns empty string if not found (FFmpeg uses default font).
    Logs found path at INFO level, warns if fallback used.
    """
    import glob
    search_dirs = ['/usr/share/fonts/', '/usr/local/share/fonts/', './fonts/']
    for directory in search_dirs:
        matches = glob.glob(f"{directory}/**/{font_name}*.ttf", recursive=True)
        if matches:
            logger.info(f"Font found: {matches[0]}")
            return matches[0]
    logger.warning(f"Font '{font_name}' not found, FFmpeg will use default")
    return ""

def build_overlay_filter(overlays: list[dict]) -> str:
    """
    Builds professional FFmpeg overlay filters for commentary cards.
    Each card renders as 3 layers:
    1. Semi-transparent dark background box (drawbox, fade animation)
    2. White text with drop shadow (drawtext, fade animation)
    3. 3px indigo accent line below box (drawbox, branded)

    Fade: 0.25s ease-in, 0.25s ease-out using FFmpeg alpha expressions.
    ALL text values are escaped via escape_ffmpeg_text() before use.

    Position Y (for 1080x1920 canvas):
    - "top":    box_y = 120
    - "center": box_y = 900  (1920/2 - 60)
    - "bottom": box_y = 1700

    Per overlay layout:
    - Background box: x=60, y=box_y, w=960, h=100, color=black@0.72, boxborderw=16
    - Text: x=(w-text_w)/2, y=box_y+22, fontsize=46, color=white@{alpha}
      shadowx=2, shadowy=2, shadowcolor=black@0.5
      fontfile={find_font_path('Montserrat-Bold')}
    - Accent line: x=60, y=box_y+96, w=960, h=4, color=0x6366f1@{alpha}

    Alpha expression (same for all 3 layers):
      alpha = if(lt(t-{start},0.25),(t-{start})/0.25,if(lt({end}-t,0.25),({end}-t)/0.25,1))

    Enable expression: enable='between(t,{start},{end})'

    CRITICAL: Call escape_ffmpeg_text(overlay['text']) before embedding in drawtext.
    Returns empty string "" if overlays list is empty.
    Returns comma-separated filter chain string.
    """
    if not overlays:
        return ""
        
    font_path = find_font_path('Montserrat-Bold')
    fontfile_opt = f":fontfile='{font_path}'" if font_path else ""
    
    filters = []
    for ov in overlays:
        text = escape_ffmpeg_text(ov.get("text", ""))
        start = ov.get("start", 0.0)
        end = ov.get("end", 0.0)
        pos = ov.get("position", "center")
        
        if pos == "top":
            box_y = 120
        elif pos == "bottom":
            box_y = 1700
        else:
            box_y = 900
            
        alpha_expr = f"if(lt(t-{start},0.25),(t-{start})/0.25,if(lt({end}-t,0.25),({end}-t)/0.25,1))"
        enable_expr = f"between(t,{start},{end})"
        
        # Background box (drawbox)
        box_filter = f"drawbox=x=60:y={box_y}:w=960:h=100:color=black@0.72:t=fill:enable='{enable_expr}'"
        
        # Text (drawtext)
        text_filter = (
            f"drawtext=text='{text}':x=(w-text_w)/2:y={box_y+22}:fontsize=46:"
            f"fontcolor=white:alpha='{alpha_expr}':shadowx=2:shadowy=2:shadowcolor=black@0.5"
            f"{fontfile_opt}:enable='{enable_expr}'"
        )
        
        # Accent line (drawbox)
        line_filter = f"drawbox=x=60:y={box_y+96}:w=960:h=4:color=0x6366f1:t=fill:enable='{enable_expr}'"
        
        filters.extend([box_filter, text_filter, line_filter])
        
    return ",".join(filters)

def build_audio_duck_filter(has_music: bool, duck_level_db: int) -> tuple[str, list]:
    """
    Returns (filter_string, extra_input_args) for audio ducking.
    """
    # Audio normalization — YouTube/Spotify standard: -16 LUFS, -1.5 TP, LRA 11
    # This makes every clip sound professional regardless of source recording quality
    # Apply BEFORE ducking/mixing to normalize the base audio level
    loudnorm_filter = "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[norm_a]"
    
    if not has_music:
        # If no background music: audio chain = loudnorm only
        return (f"{loudnorm_filter};[norm_a]anull[audio_out]", [])
        
    # If background music present: loudnorm → sidechaincompress (ducking)
    # Apply loudnorm to the voice track [0:a] before feeding into ducking filter
    filter_str = (
        f"{loudnorm_filter};"
        f"[1:a]volume={duck_level_db}dB[bg];"
        f"[bg][norm_a]sidechaincompress=threshold=0.02:ratio=4:attack=5:release=300:level_sc=1[ducked];"
        f"[norm_a][ducked]amix=inputs=2:duration=first:dropout_transition=2[audio_out]"
    )
    return (filter_str, []) # extra_input_args provided by caller as instructed

def write_ass_file(ass_content: str, job_id: str, suffix: str = "") -> str:
    """
    Writes ASS content to disk and returns the path.
    """
    path = f"/tmp/editor_{job_id}{suffix}.ass"
    with open(path, "w", encoding="utf-8") as f:
        f.write(ass_content)
    return path

def recalculate_ass_timestamps(ass_content: str, cuts: list) -> str:
    """
    Recalculates all timestamps in ASS file after cuts are applied.
    """
    if not cuts:
        return ass_content
        
    sorted_cuts = sorted(cuts, key=lambda x: x.get('remove_from', 0))
    
    def time_to_sec(t_str: str) -> float:
        h, m, s = t_str.split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)
        
    def sec_to_time(sec: float) -> str:
        sec = max(0.0, sec)
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = sec % 60
        return f"{h}:{m:02d}:{s:05.2f}"
        
    def shift_match(match: re.Match) -> str:
        t_sec = time_to_sec(match.group(0))
        shift = 0.0
        
        for cut in sorted_cuts:
            r_from = cut.get('remove_from', 0)
            r_to = cut.get('remove_to', 0)
            if t_sec > r_to:
                shift += (r_to - r_from)
            elif t_sec > r_from:
                shift += (t_sec - r_from)
                
        return sec_to_time(t_sec - shift)

    # ASS timestamp format: 0:00:00.00
    pattern = re.compile(r'\d:\d{2}:\d{2}\.\d{2}')
    return pattern.sub(shift_match, ass_content)

def render_video(
    job_id: str,
    edit_spec: dict,
    source_path: str,
    output_path: str,
    crop_segments: list[dict] | None = None  # NEW: smart reframe data
) -> str:
    """
    Orchestrates the two-pass render. Returns output_path on success.
    """
    pass1_path = f"/tmp/editor_{job_id}_pass1.mp4"
    ass_path = None
    
    try:
        w, h = get_video_dimensions(source_path)
        
        clip_info = edit_spec.get("clip", {})
        clip_start = clip_info.get("start", 0.0)
        clip_end = clip_info.get("end", 99999.0)
        
        cuts = edit_spec.get("cuts", [])
        
        # --- PASS 1 ---
        cuts_expr = build_cuts_filter(cuts, clip_start, clip_end)
        v_cuts_filter = f"select='{cuts_expr}',setpts=N/FRAME_RATE/TB"
        a_cuts_filter = f"aselect='{cuts_expr}',asetpts=N/SR/TB"
        
        if crop_segments:
            logger.info("Using dynamic reframe")
            dyn_crop = build_dynamic_crop_filter(crop_segments, w, h)
            filter_complex_pass1 = f"{dyn_crop};[vout_crop]{v_cuts_filter}[vout];[0:a]{a_cuts_filter}[aout]"
        else:
            logger.info("Using static center crop")
            crop_filter = build_crop_filter(edit_spec, w, h)
            v_chain = f"{v_cuts_filter},{crop_filter}"
            filter_complex_pass1 = f"[0:v]{v_chain}[vout];[0:a]{a_cuts_filter}[aout]"
        
        cmd_pass1 = [
            "ffmpeg", "-y", "-i", source_path,
            "-filter_complex", filter_complex_pass1,
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-c:a", "aac", "-ar", "44100",
            pass1_path
        ]
        
        logger.info(f"FFmpeg Pass 1: {' '.join(cmd_pass1)}")
        res1 = subprocess.run(cmd_pass1, capture_output=True, text=True, check=False)
        if res1.returncode != 0:
            logger.error(f"Pass 1 stderr: {res1.stderr}")
            raise RuntimeError(f"FFmpeg Pass 1 failed: {res1.stderr}")
            
        # --- BETWEEN PASSES ---
        sub_info = edit_spec.get("subtitles", {})
        if sub_info.get("enabled"):
            ass_content = sub_info.get("ass_content", "")
            adjusted_ass = recalculate_ass_timestamps(ass_content, cuts)
            ass_path = write_ass_file(adjusted_ass, job_id, suffix="_pass2")
            
        # --- PASS 2 ---
        logger.info(f"Applying loudnorm: I=-16 LUFS, TP=-1.5dB, LRA=11 for job {job_id}")
        
        audio_info = edit_spec.get("audio", {})
        bg_music_path = audio_info.get("background_music_path")
        has_music = bool(bg_music_path)
        duck_level_db = audio_info.get("duck_level_db", -12)
        
        duck_filter, _ = build_audio_duck_filter(has_music, duck_level_db)
        
        subtitle_filter = f"ass={ass_path}" if ass_path else None
        overlay_filter = build_overlay_filter(edit_spec.get("overlays", []))
        
        v_filters = []
        if subtitle_filter:
            v_filters.append(subtitle_filter)
        if overlay_filter:
            v_filters.append(overlay_filter)
            
        visual_chain = "[0:v]" + ",".join(v_filters) + "[v_out]" if v_filters else "[0:v]copy[v_out]"
        filter_complex_pass2 = f"{visual_chain};{duck_filter}"
        
        cmd_pass2 = ["ffmpeg", "-y", "-i", pass1_path]
        if has_music and os.path.exists(bg_music_path):
            cmd_pass2.extend(["-i", bg_music_path])
            
        out_quality = edit_spec.get("output", {}).get("quality", "final")
        if out_quality == "draft":
            q_flags = ["-crf", "28", "-preset", "ultrafast"]
        else:
            q_flags = ["-crf", "18", "-preset", "slow"]
            
        cmd_pass2.extend([
            "-filter_complex", filter_complex_pass2,
            "-map", "[v_out]", "-map", "[audio_out]",
            "-c:v", "libx264"
        ])
        cmd_pass2.extend(q_flags)
        cmd_pass2.extend([
            "-c:a", "aac", "-ar", "44100", "-movflags", "+faststart",
            output_path
        ])
        
        logger.info(f"FFmpeg Pass 2: {' '.join(cmd_pass2)}")
        res2 = subprocess.run(cmd_pass2, capture_output=True, text=True, check=False)
        if res2.returncode != 0:
            logger.error(f"Pass 2 stderr: {res2.stderr}")
            raise RuntimeError(f"FFmpeg Pass 2 failed: {res2.stderr}")
            
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("Output file missing or empty after Pass 2")
            
        final_output = output_path
        
    finally:
        if os.path.exists(pass1_path):
            try:
                os.remove(pass1_path)
            except OSError:
                pass
        if ass_path and os.path.exists(ass_path):
            try:
                os.remove(ass_path)
            except OSError:
                pass
                
    return final_output

def render_draft_preview(job_id: str, edit_spec: dict, source_path: str) -> str:
    """
    Same as render_video but forces 'draft' quality and scales output down to 540x960.
    """
    pass2_out = f"/tmp/editor_{job_id}_pass2.mp4"
    output_path = f"/tmp/editor_{job_id}_preview.mp4"
    
    spec = dict(edit_spec)
    if "output" not in spec:
        spec["output"] = {}
    spec["output"]["quality"] = "draft"
    
    render_video(job_id, spec, source_path, pass2_out)
    
    cmd = [
        "ffmpeg", "-y", "-i", pass2_out,
        "-vf", "scale=540:960",
        "-c:v", "libx264", "-crf", "28", "-preset", "ultrafast",
        "-c:a", "copy",
        output_path
    ]
    logger.info(f"FFmpeg Pass 3 (scale): {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    
    if os.path.exists(pass2_out):
        try:
            os.remove(pass2_out)
        except OSError:
            pass
            
    if result.returncode != 0:
        logger.error(f"Pass 3 failed. stderr: {result.stderr}")
        raise RuntimeError(f"FFmpeg Pass 3 failed: {result.stderr}")
        
    return output_path
