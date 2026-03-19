"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, CheckCircle2, AlertCircle, Clock, Play, Pause } from "lucide-react";
import { useChannel } from "../layout";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Job = {
    id: string;
    video_title: string;
    status: string;
    progress?: number;
    step?: string;
    created_at?: string;
    error?: string;
};

const STEP_LABELS: Record<string, string> = {
    "initializing": "Initializing...",
    "s01_audio_extract": "Extracting Audio...",
    "s02_transcribe": "Transcribing...",
    "s03_speaker_id": "Identifying Speakers...",
    "s04_labeled_transcript": "Building Transcript...",
    "s05_unified_discovery": "Analyzing Video with AI...",
    "s06_batch_evaluation": "Evaluating Clips...",
    "s07_precision_cut": "Calculating Cut Points...",
    "s08_export": "Exporting & Uploading...",
    "finished": "Complete!",
    // Legacy step names (for jobs that started before the update)
    "s05_energy_map": "Analyzing Audio Energy...",
    "s06_video_analysis": "Analyzing Video...",
    "s07_context_build": "Building Context...",
    "s07b_humor_map": "Detecting Humor...",
    "s07c_signal_fusion": "Merging Signals...",
    "s08_clip_finder": "Finding Clips...",
    "s09_quality_gate": "Quality Check...",
    "s09b_clip_strategy": "Planning Strategy...",
    "s10_precision_cut": "Cutting Clips...",
    "s11_export": "Exporting..."
};

function getStepLabel(step: string | undefined): string {
    if (!step) return "Starting...";
    return STEP_LABELS[step] || step.replace(/_/g, " ").replace(/^s\d+\s?/, "");
}

function TimeInput({ value, onChange, max }: { value: number, onChange: (v: number) => void, max: number }) {
    const [localValue, setLocalValue] = useState(value.toString().padStart(2, '0'));

    useEffect(() => {
        setLocalValue(value.toString().padStart(2, '0'));
    }, [value]);

    return (
        <input
            type="text"
            value={localValue}
            onChange={(e) => setLocalValue(e.target.value)}
            onBlur={() => {
                let num = parseInt(localValue);
                if (isNaN(num)) num = 0;
                if (num > max) num = max;
                setLocalValue(num.toString().padStart(2, '0'));
                onChange(num);
            }}
            className="w-10 text-center bg-white/[0.04] border border-white/[0.08] rounded-lg py-1 text-sm text-white focus:border-violet-500/50 outline-none transition-colors"
        />
    )
}

export default function NewJobPage() {
    const router = useRouter();
    const { channels, activeChannelId, setActiveChannelId } = useChannel();
    const fileInputRef = useRef<HTMLInputElement>(null);
    const videoRef = useRef<HTMLVideoElement>(null);
    const timelineRef = useRef<HTMLDivElement>(null);

    const [isDragging, setIsDragging] = useState(false);
    const [file, setFile] = useState<File | null>(null);
    const [title, setTitle] = useState("");
    const [guestName, setGuestName] = useState("");

    // Upload state
    const [uploadState, setUploadState] = useState<'idle' | 'uploading' | 'preview_ready' | 'processing'>('idle');
    const [uploadProgress, setUploadProgress] = useState(0);
    const [uploadId, setUploadId] = useState("");
    const [videoDuration, setVideoDuration] = useState(0);
    const [videoUrl, setVideoUrl] = useState("");

    // Trimmer state
    const [startTime, setStartTime] = useState(0);
    const [endTime, setEndTime] = useState(0);
    const [draggingHandle, setDraggingHandle] = useState<'start' | 'end' | null>(null);

    const [submitError, setSubmitError] = useState("");
    const [statusMsg, setStatusMsg] = useState("");
    const [jobs, setJobs] = useState<Job[]>([]);

    useEffect(() => {
        if (!activeChannelId) return;
        const fetchJobs = async () => {
            try {
                const jobsRes = await fetch(`${API}/jobs?channel_id=${activeChannelId}&limit=5`);
                if (jobsRes.ok) {
                    const jobsData = await jobsRes.json();
                    setJobs(jobsData);
                }
            } catch (err) {
                console.error("Dashboard fetch error", err);
            }
        };
        fetchJobs();
    }, [activeChannelId]);

    // Handle Timeline Dragging
    useEffect(() => {
        const handleMouseMove = (e: MouseEvent) => {
            if (!draggingHandle || !timelineRef.current || videoDuration === 0) return;

            const rect = timelineRef.current.getBoundingClientRect();
            let x = e.clientX - rect.left;
            x = Math.max(0, Math.min(x, rect.width));

            const time = (x / rect.width) * videoDuration;

            if (draggingHandle === 'start') {
                setStartTime(Math.min(time, Math.max(0, endTime - 30)));
            } else {
                setEndTime(Math.max(time, Math.min(videoDuration, startTime + 30)));
            }
        };

        const handleMouseUp = () => setDraggingHandle(null);

        if (draggingHandle) {
            window.addEventListener('mousemove', handleMouseMove);
            window.addEventListener('mouseup', handleMouseUp);
        }
        return () => {
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseup', handleMouseUp);
        };
    }, [draggingHandle, startTime, endTime, videoDuration]);

    // Update Video Time based on Trimmer
    useEffect(() => {
        if (videoRef.current && uploadState === 'preview_ready') {
            if (draggingHandle === 'start') {
                videoRef.current.currentTime = startTime;
            } else if (draggingHandle === 'end') {
                videoRef.current.currentTime = endTime;
            }
        }
    }, [startTime, endTime, draggingHandle, uploadState]);

    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault();
        if (uploadState === 'idle') setIsDragging(true);
    };
    const handleDragLeave = () => setIsDragging(false);
    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        if (uploadState === 'idle' && e.dataTransfer.files?.length) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    };

    const handleFileSelect = (selectedFile: File) => {
        setFile(selectedFile);
        const url = URL.createObjectURL(selectedFile);
        setVideoUrl(url);

        setUploadState('uploading');
        setUploadProgress(0);
        setSubmitError("");

        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${API}/jobs/upload-preview`, true);

        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 100);
                setUploadProgress(percent);
            }
        };

        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                const response = JSON.parse(xhr.responseText);
                setUploadId(response.upload_id);

                let dur = response.duration_seconds || 0;

                if (dur === 0) {
                    const tempVideo = document.createElement('video');
                    tempVideo.src = url;
                    tempVideo.onloadedmetadata = () => {
                        setVideoDuration(tempVideo.duration);
                        setEndTime(tempVideo.duration);
                        setUploadState('preview_ready');
                    };
                } else {
                    setVideoDuration(dur);
                    setEndTime(dur);
                    setUploadState('preview_ready');
                }
            } else {
                setSubmitError("Failed to upload video.");
                setUploadState('idle');
                setFile(null);
            }
        };

        xhr.onerror = () => {
            setSubmitError("Network error during upload.");
            setUploadState('idle');
            setFile(null);
        };

        const formData = new FormData();
        formData.append("file", selectedFile);
        xhr.send(formData);
    };

    const handleStartProcessing = async () => {
        if (!uploadId || !title || !activeChannelId) return;

        setUploadState('processing');
        setStatusMsg("Starting pipeline...");
        setSubmitError("");

        const formData = new FormData();
        formData.append("upload_id", uploadId);
        formData.append("title", title);
        formData.append("channel_id", activeChannelId);
        if (guestName) formData.append("guest_name", guestName);
        formData.append("trim_start_seconds", startTime.toString());
        formData.append("trim_end_seconds", endTime.toString());

        try {
            const response = await fetch(`${API}/jobs`, {
                method: "POST",
                body: formData,
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                setSubmitError(err.detail || 'Failed to start processing');
                setUploadState('preview_ready');
                return;
            }

            const job = await response.json();
            const jobId = job?.id || job?.job_id;

            if (!jobId) {
                setSubmitError('No job ID returned');
                setUploadState('preview_ready');
                return;
            }

            // Poll status
            setStatusMsg('Processing video...');
            let attempts = 0;
            const maxAttempts = 90;

            const pollStatus = async () => {
                try {
                    const statusRes = await fetch(`${API}/jobs/${jobId}`);
                    const jobData = await statusRes.json();
                    const status = jobData?.job?.status;

                    if (status === 'awaiting_speaker_confirm') {
                        router.push(`/dashboard/speakers/${jobId}`);
                        return;
                    }

                    if (status === 'completed' || status === 'done') {
                        router.push('/dashboard');
                        return;
                    }

                    if (status === 'failed' || status === 'error') {
                        setSubmitError('Pipeline failed. Please try again.');
                        setUploadState('preview_ready');
                        return;
                    }

                    const step = jobData?.job?.current_step || jobData?.job?.step || '';
                    setStatusMsg(getStepLabel(step));

                    attempts++;
                    if (attempts < maxAttempts) {
                        setTimeout(pollStatus, 2000);
                    } else {
                        router.push('/dashboard');
                    }
                } catch (e) {
                    attempts++;
                    if (attempts < maxAttempts) setTimeout(pollStatus, 2000);
                }
            };

            setTimeout(pollStatus, 2000);

        } catch (err: any) {
            console.error(err);
            setSubmitError(err.message || "Failed to start processing.");
            setUploadState('preview_ready');
        }
    };

    const TimeGroup = ({ time, isStart }: { time: number, isStart: boolean }) => {
        const h = Math.floor(time / 3600);
        const m = Math.floor((time % 3600) / 60);
        const s = Math.floor(time % 60);

        const updateTime = (type: 'h' | 'm' | 's', val: number) => {
            let newTime = time;
            if (type === 'h') newTime = val * 3600 + m * 60 + s;
            if (type === 'm') newTime = h * 3600 + val * 60 + s;
            if (type === 's') newTime = h * 3600 + m * 60 + val;

            if (isStart) {
                setStartTime(Math.max(0, Math.min(newTime, endTime - 30)));
            } else {
                setEndTime(Math.min(videoDuration, Math.max(newTime, startTime + 30)));
            }
        };

        return (
            <div className="flex flex-col items-center gap-2">
                <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-semibold">{isStart ? 'START' : 'END'}</div>
                <div className="flex items-center gap-1.5">
                    <TimeInput value={h} onChange={v => updateTime('h', v)} max={99} />
                    <span className="text-zinc-600 font-bold">:</span>
                    <TimeInput value={m} onChange={v => updateTime('m', v)} max={59} />
                    <span className="text-zinc-600 font-bold">:</span>
                    <TimeInput value={s} onChange={v => updateTime('s', v)} max={59} />
                </div>
                <div className="flex gap-[28px] w-full justify-center px-1">
                    <span className="text-[10px] text-zinc-600 font-medium">HH</span>
                    <span className="text-[10px] text-zinc-600 font-medium">MM</span>
                    <span className="text-[10px] text-zinc-600 font-medium">SS</span>
                </div>
            </div>
        );
    };

    const startPercent = videoDuration ? (startTime / videoDuration) * 100 : 0;
    const endPercent = videoDuration ? (endTime / videoDuration) * 100 : 100;

    return (
        <>
            <style>{`
                @keyframes breathe {
                    0%, 100% { box-shadow: 0 0 30px rgba(124,58,237,0.15), inset 0 0 30px rgba(124,58,237,0.05); border-color: rgba(255,255,255,0.08); }
                    50% { box-shadow: 0 0 60px rgba(124,58,237,0.35), inset 0 0 60px rgba(124,58,237,0.12); border-color: rgba(124,58,237,0.3); }
                }
                .animate-breathe {
                    animation: breathe 2s ease-in-out infinite;
                }
                @keyframes shimmer {
                    0% { transform: translateX(-100%); }
                    100% { transform: translateX(100%); }
                }
                .animate-shimmer {
                    animation: shimmer 2s infinite;
                }
            `}</style>

            <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2 }}
                className="max-w-3xl mx-auto pb-20"
            >
                <h1 className="text-2xl font-bold mb-8">New Clip Job</h1>

                <div className="space-y-6">

                    <AnimatePresence mode="wait">
                        {uploadState === 'idle' && (
                            <motion.div
                                key="idle"
                                initial={{ opacity: 0, scale: 0.97 }}
                                animate={{ opacity: 1, scale: 1 }}
                                exit={{ opacity: 0, scale: 0.97 }}
                                transition={{ duration: 0.3, ease: 'easeOut' }}
                            >
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    accept=".mp4,.mov,.webm,video/*"
                                    className="hidden"
                                    onChange={(e) => {
                                        if (e.target.files?.[0]) handleFileSelect(e.target.files[0]);
                                    }}
                                />
                                <div
                                    onDragOver={handleDragOver}
                                    onDragLeave={handleDragLeave}
                                    onDrop={handleDrop}
                                    onClick={() => fileInputRef.current?.click()}
                                    className={`border-2 border-dashed rounded-lg p-12 flex flex-col items-center justify-center text-center cursor-pointer transition-colors ${isDragging
                                        ? "border-[#7c3aed] bg-[#7c3aed]/10"
                                        : "border-[#7c3aed]/30 bg-[#0d0d0d] hover:border-[#7c3aed]/50 hover:bg-white/[0.02]"
                                        }`}
                                >
                                    <Upload className={`w-12 h-12 mb-3 ${isDragging ? "text-[#7c3aed]" : "text-[#6b7280]"}`} />
                                    <div className="text-sm font-medium mb-1">Drag and drop video file here</div>
                                    <div className="text-xs text-[#6b7280]">or click to browse • MP4, MOV, WEBM</div>
                                </div>
                            </motion.div>
                        )}

                        {uploadState === 'uploading' && file && (
                            <motion.div
                                key="uploading"
                                initial={{ opacity: 0, scale: 0.97 }}
                                animate={{ opacity: 1, scale: 1 }}
                                exit={{ opacity: 0, scale: 0.97 }}
                                transition={{ duration: 0.3, ease: 'easeOut' }}
                                className="bg-white/[0.03] backdrop-blur-xl border border-white/[0.08] rounded-2xl p-10 flex flex-col items-center justify-center text-center animate-breathe"
                            >
                                <div className="text-zinc-400 font-medium mb-6 line-clamp-1 max-w-sm">{file.name}</div>

                                <div className="w-64 h-1.5 bg-white/[0.06] rounded-full overflow-hidden relative mb-3">
                                    <div
                                        className="absolute top-0 left-0 bottom-0 bg-gradient-to-r from-violet-600 to-cyan-500 transition-all duration-300 ease-out"
                                        style={{ width: `${uploadProgress}%` }}
                                    >
                                        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/40 to-transparent w-full h-full animate-shimmer" />
                                    </div>
                                </div>

                                <div className="text-xs text-zinc-500 font-medium">
                                    Uploading... {uploadProgress}%
                                </div>
                            </motion.div>
                        )}

                        {(uploadState === 'preview_ready' || uploadState === 'processing') && (
                            <motion.div
                                key="preview"
                                initial={{ opacity: 0, scale: 0.97 }}
                                animate={{ opacity: 1, scale: 1 }}
                                transition={{ duration: 0.3, ease: 'easeOut' }}
                                className="space-y-6"
                            >
                                {/* SECTION A — VIDEO PREVIEW */}
                                <div className="w-full aspect-video bg-black border border-white/[0.08] rounded-2xl overflow-hidden shadow-[0_0_30px_rgba(124,58,237,0.15)] relative">
                                    <video
                                        ref={videoRef}
                                        src={videoUrl}
                                        className="w-full h-full object-contain"
                                        controls
                                        muted
                                        controlsList="nodownload nofullscreen"
                                    />
                                </div>

                                {/* SECTION B — TIMELINE TRIMMER */}
                                <div className="bg-white/[0.03] backdrop-blur-xl border border-white/[0.06] rounded-xl p-5">
                                    <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-semibold mb-3">
                                        Processing Range
                                    </div>

                                    {/* Timeline Bar */}
                                    <div className="relative">
                                        {/* Time Displays */}
                                        <div className="flex justify-between text-xs text-zinc-400 mb-2 font-medium">
                                            <span>
                                                {formatTimeDisplay(startTime)}
                                            </span>
                                            <span>
                                                {formatTimeDisplay(endTime)}
                                            </span>
                                        </div>

                                        <div
                                            ref={timelineRef}
                                            className="relative w-full h-12 bg-white/[0.04] rounded-xl mb-6 select-none"
                                        >
                                            {/* Unselected regions (darker) */}
                                            <div className="absolute top-0 bottom-0 left-0 bg-[rgba(255,255,255,0.02)] rounded-l-xl" style={{ width: `${startPercent}%` }} />
                                            <div className="absolute top-0 bottom-0 right-0 bg-[rgba(255,255,255,0.02)] rounded-r-xl" style={{ width: `${100 - endPercent}%` }} />

                                            {/* Selected Range Fill */}
                                            <div
                                                className="absolute top-0 bottom-0 bg-[rgba(124,58,237,0.2)] border-y border-violet-500/30"
                                                style={{ left: `${startPercent}%`, right: `${100 - endPercent}%` }}
                                            />

                                            {/* Start Handle */}
                                            <div
                                                className="absolute top-1/2 -translate-y-1/2 w-1 h-8 bg-gradient-to-b from-violet-400 to-violet-600 rounded-full cursor-ew-resize hover:scale-110 transition-transform shadow-[0_0_10px_rgba(124,58,237,0.5)] z-10"
                                                style={{ left: `calc(${startPercent}% - 2px)` }}
                                                onMouseDown={(e) => { e.preventDefault(); setDraggingHandle('start'); }}
                                            />

                                            {/* End Handle */}
                                            <div
                                                className="absolute top-1/2 -translate-y-1/2 w-1 h-8 bg-gradient-to-b from-cyan-400 to-cyan-600 rounded-full cursor-ew-resize hover:scale-110 transition-transform shadow-[0_0_10px_rgba(6,182,212,0.5)] z-10"
                                                style={{ left: `calc(${endPercent}% - 2px)` }}
                                                onMouseDown={(e) => { e.preventDefault(); setDraggingHandle('end'); }}
                                            />
                                        </div>
                                    </div>

                                    {/* Time Inputs */}
                                    <div className="flex items-center justify-center gap-8">
                                        <TimeGroup time={startTime} isStart={true} />

                                        <button
                                            onClick={() => { setStartTime(0); setEndTime(videoDuration); }}
                                            className="text-xs text-zinc-500 hover:text-white transition-colors mt-4"
                                        >
                                            Reset
                                        </button>

                                        <TimeGroup time={endTime} isStart={false} />
                                    </div>
                                </div>

                                {/* SECTION C — FORM FIELDS */}
                                <div className="bg-[#0d0d0d] border border-white/[0.06] rounded-xl p-6 space-y-5">
                                    <div>
                                        <label className="block text-xs font-medium text-[#6b7280] mb-1.5 uppercase tracking-wider">
                                            Video Title *
                                        </label>
                                        <input
                                            type="text"
                                            value={title}
                                            onChange={(e) => setTitle(e.target.value)}
                                            placeholder="e.g. Joe Rogan #2054 - Elon Musk"
                                            className="w-full bg-[#1a1a1a] border border-white/[0.1] rounded-lg px-4 py-2.5 text-sm text-white placeholder-[#6b7280] focus:outline-none focus:border-[#7c3aed] transition-colors"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-[#6b7280] mb-1.5 uppercase tracking-wider">
                                            Guest Name <span className="lowercase normal-case">(optional)</span>
                                        </label>
                                        <input
                                            type="text"
                                            value={guestName}
                                            onChange={(e) => setGuestName(e.target.value)}
                                            placeholder="e.g. Elon Musk"
                                            className="w-full bg-[#1a1a1a] border border-white/[0.1] rounded-lg px-4 py-2.5 text-sm text-white placeholder-[#6b7280] focus:outline-none focus:border-[#7c3aed] transition-colors"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-[#6b7280] mb-1.5 uppercase tracking-wider">
                                            Channel
                                        </label>
                                        <select
                                            value={activeChannelId}
                                            onChange={(e) => setActiveChannelId(e.target.value)}
                                            className="w-full bg-[#1a1a1a] border border-white/[0.1] rounded-lg px-4 py-2.5 text-sm text-white focus:outline-none focus:border-[#7c3aed] transition-colors appearance-none"
                                        >
                                            {channels.length > 0 ? (
                                                channels.map(c => <option key={c.id} value={c.id}>{c.display_name || c.name || c.id}</option>)
                                            ) : (
                                                <option value="speedy_cast">Speedy Cast</option>
                                            )}
                                        </select>
                                    </div>
                                </div>

                                <motion.button
                                    onClick={handleStartProcessing}
                                    whileHover={title && uploadState === 'preview_ready' ? { scale: 1.02 } : {}}
                                    whileTap={title && uploadState === 'preview_ready' ? { scale: 0.98 } : {}}
                                    className={`w-full py-3.5 rounded-lg text-sm font-semibold transition-all flex items-center justify-center gap-2 ${title && uploadState === 'preview_ready'
                                        ? "bg-gradient-to-r from-[#7c3aed] to-[#6d28d9] text-white shadow-lg shadow-[#7c3aed]/20"
                                        : "bg-[#1a1a1a] text-[#6b7280] cursor-not-allowed border border-white/[0.06]"
                                        }`}
                                    disabled={!title || uploadState !== 'preview_ready'}
                                >
                                    {uploadState === 'processing' ? (
                                        <>
                                            <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                                            {statusMsg || "Processing..."}
                                        </>
                                    ) : (
                                        "Start Processing"
                                    )}
                                </motion.button>
                            </motion.div>
                        )}
                    </AnimatePresence>

                    {submitError && (
                        <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm flex items-center gap-2">
                            <AlertCircle className="w-4 h-4" />
                            {submitError}
                        </div>
                    )}
                </div>

                {/* Recent Jobs */}
                <div className="mt-16">
                    <h2 className="text-[13px] uppercase tracking-wider text-[#6b7280] font-semibold mb-4">Recent Jobs</h2>
                    <div className="space-y-2">
                        {jobs.length === 0 ? (
                            <p className="text-sm text-[#6b7280] p-4 text-center border border-white/[0.06] rounded-lg bg-[#0d0d0d]">No recent jobs</p>
                        ) : (
                            jobs.slice(0, 5).map((job, i) => (
                                <motion.div
                                    key={job.id}
                                    initial={{ opacity: 0, x: -12 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: i * 0.06 }}
                                    className="flex items-center justify-between p-3 bg-[#0d0d0d] border border-white/[0.06] rounded-lg"
                                >
                                    <div className="text-sm line-clamp-1 flex-1 pr-4">{job.video_title}</div>
                                    <div className="flex items-center gap-3 shrink-0">
                                        {job.status === "done" || job.status === "completed" ? (
                                            <span className="text-xs font-medium text-green-500 bg-green-500/10 px-2 py-0.5 rounded flex items-center gap-1">
                                                <CheckCircle2 className="w-3 h-3" /> Done
                                            </span>
                                        ) : job.status === "error" || job.status === "failed" ? (
                                            <span className="text-xs font-medium text-red-500 bg-red-500/10 px-2 py-0.5 rounded flex items-center gap-1">
                                                <AlertCircle className="w-3 h-3" /> Failed
                                            </span>
                                        ) : (
                                            <span className="text-xs font-medium text-[#7c3aed] bg-[#7c3aed]/10 px-2 py-0.5 rounded flex items-center gap-1 capitalize">
                                                <Clock className="w-3 h-3" /> {job.status}
                                            </span>
                                        )}
                                    </div>
                                </motion.div>
                            ))
                        )}
                    </div>
                </div>
            </motion.div>
        </>
    );
}

function formatTimeDisplay(time: number) {
    const h = Math.floor(time / 3600).toString().padStart(2, '0');
    const m = Math.floor((time % 3600) / 60).toString().padStart(2, '0');
    const s = Math.floor(time % 60).toString().padStart(2, '0');
    return `${h}:${m}:${s}`;
}
