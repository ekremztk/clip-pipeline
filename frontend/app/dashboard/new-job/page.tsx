"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Upload, CheckCircle2, AlertCircle, Clock } from "lucide-react";
import { useChannel } from "../layout";
import { authFetch, API_URL } from "@/lib/api";
import { supabase } from "@/lib/supabase";

const API = API_URL;

type Job = {
    id: string;
    video_title: string;
    status: string;
    progress?: number;
    step?: string;
    created_at?: string;
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
    "s05_energy_map": "Analyzing Audio Energy...",
    "s06_video_analysis": "Analyzing Video...",
    "s07_context_build": "Building Context...",
    "s08_clip_finder": "Finding Clips...",
    "s09_quality_gate": "Quality Check...",
    "s10_precision_cut": "Cutting Clips...",
    "s11_export": "Exporting..."
};

function getStepLabel(step: string | undefined): string {
    if (!step) return "Starting...";
    return STEP_LABELS[step] || step.replace(/_/g, " ").replace(/^s\d+\s?/, "");
}

function formatTimeDisplay(time: number) {
    const h = Math.floor(time / 3600).toString().padStart(2, '0');
    const m = Math.floor((time % 3600) / 60).toString().padStart(2, '0');
    const s = Math.floor(time % 60).toString().padStart(2, '0');
    return `${h}:${m}:${s}`;
}

function TimeInput({ value, onChange, max }: { value: number, onChange: (v: number) => void, max: number }) {
    const [localValue, setLocalValue] = useState(value.toString().padStart(2, '0'));

    useEffect(() => { setLocalValue(value.toString().padStart(2, '0')); }, [value]);

    return (
        <input
            type="text"
            value={localValue}
            onChange={e => setLocalValue(e.target.value)}
            onBlur={() => {
                let num = parseInt(localValue);
                if (isNaN(num)) num = 0;
                if (num > max) num = max;
                setLocalValue(num.toString().padStart(2, '0'));
                onChange(num);
            }}
            className="w-10 text-center bg-[#0a0a0a] border border-[#262626] rounded-lg py-1 text-sm text-white focus:outline-none focus:border-[#404040] transition-colors"
        />
    );
}

export default function NewJobPage() {
    const router = useRouter();
    const { channels, activeChannelId, setActiveChannelId, isLoading: channelLoading } = useChannel();
    const fileInputRef = useRef<HTMLInputElement>(null);
    const videoRef = useRef<HTMLVideoElement>(null);
    const timelineRef = useRef<HTMLDivElement>(null);

    const [isDragging, setIsDragging] = useState(false);
    const [file, setFile] = useState<File | null>(null);
    const [title, setTitle] = useState("");
    const [guestName, setGuestName] = useState("");

    const [uploadState, setUploadState] = useState<'idle' | 'uploading' | 'preview_ready' | 'processing'>('idle');
    const [uploadProgress, setUploadProgress] = useState(0);
    const [uploadId, setUploadId] = useState("");
    const [videoDuration, setVideoDuration] = useState(0);
    const [videoUrl, setVideoUrl] = useState("");

    const [startTime, setStartTime] = useState(0);
    const [endTime, setEndTime] = useState(0);
    const [draggingHandle, setDraggingHandle] = useState<'start' | 'end' | null>(null);

    const [submitError, setSubmitError] = useState("");
    const [statusMsg, setStatusMsg] = useState("");
    const [jobs, setJobs] = useState<Job[]>([]);

    useEffect(() => {
        if (channelLoading || !activeChannelId) return;
        authFetch(`/jobs?channel_id=${activeChannelId}&limit=5`)
            .then(r => r.ok ? r.json() : [])
            .then(data => setJobs(data))
            .catch(console.error);
    }, [activeChannelId, channelLoading]);

    useEffect(() => {
        const handleMouseMove = (e: MouseEvent) => {
            if (!draggingHandle || !timelineRef.current || videoDuration === 0) return;
            const rect = timelineRef.current.getBoundingClientRect();
            let x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
            const time = (x / rect.width) * videoDuration;
            if (draggingHandle === 'start') setStartTime(Math.min(time, Math.max(0, endTime - 30)));
            else setEndTime(Math.max(time, Math.min(videoDuration, startTime + 30)));
        };
        const handleMouseUp = () => setDraggingHandle(null);
        if (draggingHandle) {
            window.addEventListener('mousemove', handleMouseMove);
            window.addEventListener('mouseup', handleMouseUp);
        }
        return () => { window.removeEventListener('mousemove', handleMouseMove); window.removeEventListener('mouseup', handleMouseUp); };
    }, [draggingHandle, startTime, endTime, videoDuration]);

    useEffect(() => {
        if (videoRef.current && uploadState === 'preview_ready') {
            if (draggingHandle === 'start') videoRef.current.currentTime = startTime;
            else if (draggingHandle === 'end') videoRef.current.currentTime = endTime;
        }
    }, [startTime, endTime, draggingHandle, uploadState]);

    const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); if (uploadState === 'idle') setIsDragging(true); };
    const handleDragLeave = () => setIsDragging(false);
    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault(); setIsDragging(false);
        if (uploadState === 'idle' && e.dataTransfer.files?.length) handleFileSelect(e.dataTransfer.files[0]);
    };

    const handleFileSelect = async (selectedFile: File) => {
        setFile(selectedFile);
        const url = URL.createObjectURL(selectedFile);
        setVideoUrl(url);
        setUploadState('uploading');
        setUploadProgress(0);
        setSubmitError("");

        const { data: sessionData } = await supabase.auth.getSession();
        const token = sessionData?.session?.access_token;

        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${API}/jobs/upload-preview`, true);
        if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
        xhr.upload.onprogress = (e) => { if (e.lengthComputable) setUploadProgress(Math.round((e.loaded / e.total) * 100)); };
        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                const response = JSON.parse(xhr.responseText);
                setUploadId(response.upload_id);
                let dur = response.duration_seconds || 0;
                if (dur === 0) {
                    const tempVideo = document.createElement('video');
                    tempVideo.src = url;
                    tempVideo.onloadedmetadata = () => { setVideoDuration(tempVideo.duration); setEndTime(tempVideo.duration); setUploadState('preview_ready'); };
                } else {
                    setVideoDuration(dur); setEndTime(dur); setUploadState('preview_ready');
                }
            } else { setSubmitError("Failed to upload video."); setUploadState('idle'); setFile(null); }
        };
        xhr.onerror = () => { setSubmitError("Network error during upload."); setUploadState('idle'); setFile(null); };
        const formData = new FormData();
        formData.append("file", selectedFile);
        xhr.send(formData);
    };

    const handleStartProcessing = async () => {
        if (!uploadId || !title || !activeChannelId) return;
        setUploadState('processing'); setStatusMsg("Starting pipeline..."); setSubmitError("");

        const formData = new FormData();
        formData.append("upload_id", uploadId);
        formData.append("title", title);
        formData.append("channel_id", activeChannelId);
        if (guestName) formData.append("guest_name", guestName);
        formData.append("trim_start_seconds", startTime.toString());
        formData.append("trim_end_seconds", endTime.toString());

        try {
            const response = await authFetch('/jobs', { method: "POST", body: formData });
            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                setSubmitError(err.detail || 'Failed to start processing'); setUploadState('preview_ready'); return;
            }
            const job = await response.json();
            const jobId = job?.id || job?.job_id;
            if (!jobId) { setSubmitError('No job ID returned'); setUploadState('preview_ready'); return; }

            setStatusMsg('Processing video...');
            let attempts = 0;
            const maxAttempts = 90;
            const pollStatus = async () => {
                try {
                    const statusRes = await authFetch(`/jobs/${jobId}`);
                    const jobData = await statusRes.json();
                    const status = jobData?.job?.status || jobData?.status;
                    if (status === 'completed' || status === 'done') { router.push('/dashboard'); return; }
                    if (status === 'failed' || status === 'error') { setSubmitError('Pipeline failed. Please try again.'); setUploadState('preview_ready'); return; }
                    const step = jobData?.job?.current_step || jobData?.job?.step || '';
                    setStatusMsg(getStepLabel(step));
                    attempts++;
                    if (attempts < maxAttempts) setTimeout(pollStatus, 2000);
                    else router.push('/dashboard');
                } catch { attempts++; if (attempts < maxAttempts) setTimeout(pollStatus, 2000); }
            };
            setTimeout(pollStatus, 2000);
        } catch (err: any) {
            setSubmitError(err.message || "Failed to start processing."); setUploadState('preview_ready');
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
            if (isStart) setStartTime(Math.max(0, Math.min(newTime, endTime - 30)));
            else setEndTime(Math.min(videoDuration, Math.max(newTime, startTime + 30)));
        };
        return (
            <div className="flex flex-col items-center gap-1.5">
                <div className="text-[10px] text-[#525252] uppercase tracking-widest font-medium">{isStart ? 'START' : 'END'}</div>
                <div className="flex items-center gap-1">
                    <TimeInput value={h} onChange={v => updateTime('h', v)} max={99} />
                    <span className="text-[#525252]">:</span>
                    <TimeInput value={m} onChange={v => updateTime('m', v)} max={59} />
                    <span className="text-[#525252]">:</span>
                    <TimeInput value={s} onChange={v => updateTime('s', v)} max={59} />
                </div>
                <div className="flex gap-[28px]">
                    <span className="text-[10px] text-[#525252]">HH</span>
                    <span className="text-[10px] text-[#525252]">MM</span>
                    <span className="text-[10px] text-[#525252]">SS</span>
                </div>
            </div>
        );
    };

    const startPercent = videoDuration ? (startTime / videoDuration) * 100 : 0;
    const endPercent = videoDuration ? (endTime / videoDuration) * 100 : 100;

    return (
        <div className="max-w-3xl mx-auto px-8 py-10 pb-20">
            <h1 className="text-2xl font-semibold text-white mb-2">New Clip Job</h1>
            <p className="text-sm text-[#737373] mb-8">Upload a video and start the AI processing pipeline</p>

            <div className="space-y-5">
                {/* IDLE: Drop zone */}
                {uploadState === 'idle' && (
                    <div>
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".mp4,.mov,.webm,video/*"
                            className="hidden"
                            onChange={e => { if (e.target.files?.[0]) handleFileSelect(e.target.files[0]); }}
                        />
                        <div
                            onDragOver={handleDragOver}
                            onDragLeave={handleDragLeave}
                            onDrop={handleDrop}
                            onClick={() => fileInputRef.current?.click()}
                            className={`border border-dashed rounded-xl p-14 flex flex-col items-center justify-center text-center cursor-pointer transition-all duration-300 ${
                                isDragging
                                    ? "border-white bg-[#0a0a0a]"
                                    : "border-[#262626] hover:border-[#404040]"
                            }`}
                        >
                            {/* PROGNOT watermark */}
                            <div className="absolute inset-0 flex items-center justify-center opacity-[0.02] pointer-events-none select-none overflow-hidden rounded-xl">
                                <div className="text-[8rem] font-bold tracking-tighter leading-none whitespace-nowrap text-white">PROGNOT</div>
                            </div>

                            <div className={`w-12 h-12 mb-4 rounded-lg border flex items-center justify-center transition-colors ${isDragging ? 'bg-[#1a1a1a] border-[#404040]' : 'bg-[#0a0a0a] border-[#262626]'}`}>
                                <Upload className={`w-6 h-6 ${isDragging ? 'text-white' : 'text-[#a3a3a3]'}`} />
                            </div>
                            <h3 className="text-base font-medium text-white mb-1">Drop your video here</h3>
                            <p className="text-sm text-[#737373] mb-5">MP4, MOV, WEBM up to 2GB</p>
                            <button
                                onClick={e => { e.stopPropagation(); fileInputRef.current?.click(); }}
                                className="px-5 py-2.5 bg-white text-black rounded-lg text-sm font-medium hover:bg-[#e5e5e5] transition-colors"
                            >
                                Select File
                            </button>
                        </div>
                    </div>
                )}

                {/* UPLOADING */}
                {uploadState === 'uploading' && file && (
                    <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl p-10 flex flex-col items-center text-center">
                        <p className="text-sm text-[#a3a3a3] font-medium mb-5 truncate max-w-sm">{file.name}</p>
                        <div className="w-64 h-1.5 bg-[#1a1a1a] rounded-full overflow-hidden relative mb-3">
                            <div
                                className="absolute top-0 left-0 bottom-0 bg-white rounded-full transition-all duration-300"
                                style={{ width: `${uploadProgress}%` }}
                            />
                        </div>
                        <p className="text-xs text-[#525252]">Uploading... {uploadProgress}%</p>
                    </div>
                )}

                {/* PREVIEW READY / PROCESSING */}
                {(uploadState === 'preview_ready' || uploadState === 'processing') && (
                    <div className="space-y-5">
                        {/* Video Preview */}
                        <div className="w-full aspect-video bg-black border border-[#1a1a1a] rounded-xl overflow-hidden">
                            <video
                                ref={videoRef}
                                src={videoUrl}
                                className="w-full h-full object-contain"
                                controls
                                muted
                                controlsList="nodownload nofullscreen"
                            />
                        </div>

                        {/* Timeline Trimmer */}
                        <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl p-5">
                            <p className="text-[10px] text-[#525252] uppercase tracking-widest font-medium mb-4">Processing Range</p>

                            <div className="flex justify-between text-xs text-[#737373] mb-2">
                                <span>{formatTimeDisplay(startTime)}</span>
                                <span>{formatTimeDisplay(endTime)}</span>
                            </div>

                            <div
                                ref={timelineRef}
                                className="relative w-full h-10 bg-[#1a1a1a] rounded-lg mb-6 select-none overflow-hidden"
                            >
                                {/* Unselected regions */}
                                <div className="absolute top-0 bottom-0 left-0 bg-black/40" style={{ width: `${startPercent}%` }} />
                                <div className="absolute top-0 bottom-0 right-0 bg-black/40" style={{ width: `${100 - endPercent}%` }} />

                                {/* Selected range */}
                                <div
                                    className="absolute top-0 bottom-0 bg-white/10 border-y border-white/20"
                                    style={{ left: `${startPercent}%`, right: `${100 - endPercent}%` }}
                                />

                                {/* Start handle */}
                                <div
                                    className="absolute top-1/2 -translate-y-1/2 w-1 h-7 bg-white rounded-full cursor-ew-resize hover:scale-110 transition-transform z-10"
                                    style={{ left: `calc(${startPercent}% - 2px)` }}
                                    onMouseDown={e => { e.preventDefault(); setDraggingHandle('start'); }}
                                />

                                {/* End handle */}
                                <div
                                    className="absolute top-1/2 -translate-y-1/2 w-1 h-7 bg-white rounded-full cursor-ew-resize hover:scale-110 transition-transform z-10"
                                    style={{ left: `calc(${endPercent}% - 2px)` }}
                                    onMouseDown={e => { e.preventDefault(); setDraggingHandle('end'); }}
                                />
                            </div>

                            <div className="flex items-center justify-center gap-10">
                                <TimeGroup time={startTime} isStart={true} />
                                <button
                                    onClick={() => { setStartTime(0); setEndTime(videoDuration); }}
                                    className="text-xs text-[#525252] hover:text-white transition-colors mt-2"
                                >
                                    Reset
                                </button>
                                <TimeGroup time={endTime} isStart={false} />
                            </div>
                        </div>

                        {/* Form Fields */}
                        <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl p-5 space-y-4">
                            <div>
                                <label className="block text-[10px] text-[#737373] uppercase tracking-widest mb-1.5">Video Title *</label>
                                <input
                                    type="text"
                                    value={title}
                                    onChange={e => setTitle(e.target.value)}
                                    placeholder="e.g. Joe Rogan #2054 - Elon Musk"
                                    className="w-full bg-black border border-[#262626] rounded-lg px-4 py-2.5 text-sm text-white placeholder-[#525252] focus:outline-none focus:border-[#404040] transition-colors"
                                />
                            </div>
                            <div>
                                <label className="block text-[10px] text-[#737373] uppercase tracking-widest mb-1.5">Guest Name <span className="normal-case">(optional)</span></label>
                                <input
                                    type="text"
                                    value={guestName}
                                    onChange={e => setGuestName(e.target.value)}
                                    placeholder="e.g. Elon Musk"
                                    className="w-full bg-black border border-[#262626] rounded-lg px-4 py-2.5 text-sm text-white placeholder-[#525252] focus:outline-none focus:border-[#404040] transition-colors"
                                />
                            </div>
                            <div>
                                <label className="block text-[10px] text-[#737373] uppercase tracking-widest mb-1.5">Channel</label>
                                {channelLoading ? (
                                    <div className="h-10 bg-[#0a0a0a] border border-[#262626] rounded-lg animate-pulse" />
                                ) : (
                                    <select
                                        value={activeChannelId}
                                        onChange={e => setActiveChannelId(e.target.value)}
                                        className="w-full bg-black border border-[#262626] rounded-lg px-4 py-2.5 text-sm text-white focus:outline-none focus:border-[#404040] transition-colors appearance-none"
                                    >
                                        {channels.map(c => <option key={c.id} value={c.id}>{c.display_name || c.name || c.id}</option>)}
                                    </select>
                                )}
                            </div>
                        </div>

                        {/* Submit Button */}
                        <button
                            onClick={handleStartProcessing}
                            disabled={!title || uploadState !== 'preview_ready'}
                            className={`w-full py-3 rounded-xl text-sm font-medium transition-all flex items-center justify-center gap-2 ${
                                title && uploadState === 'preview_ready'
                                    ? "bg-white text-black hover:bg-[#e5e5e5]"
                                    : "bg-[#0a0a0a] border border-[#1a1a1a] text-[#525252] cursor-not-allowed"
                            }`}
                        >
                            {uploadState === 'processing' ? (
                                <>
                                    <div className="w-4 h-4 border-2 border-black/20 border-t-black rounded-full animate-spin" />
                                    {statusMsg || "Processing..."}
                                </>
                            ) : "Start Processing"}
                        </button>
                    </div>
                )}

                {submitError && (
                    <div className="p-4 bg-red-500/5 border border-red-500/20 rounded-lg text-red-400 text-sm flex items-center gap-2">
                        <AlertCircle className="w-4 h-4 flex-shrink-0" />
                        {submitError}
                    </div>
                )}
            </div>

            {/* Recent Jobs */}
            <div className="mt-12">
                <h2 className="text-sm font-medium text-[#a3a3a3] mb-4">Recent Jobs</h2>
                <div className="space-y-2">
                    {jobs.length === 0 ? (
                        <p className="text-sm text-[#525252] text-center py-6 bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg">No recent jobs</p>
                    ) : (
                        jobs.slice(0, 5).map(job => (
                            <div key={job.id} className="flex items-center justify-between p-3 bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg">
                                <p className="text-sm text-[#a3a3a3] truncate flex-1 pr-4">{job.video_title}</p>
                                <div className="flex-shrink-0">
                                    {job.status === "done" || job.status === "completed" ? (
                                        <span className="text-xs text-green-400 bg-green-400/10 px-2 py-0.5 rounded flex items-center gap-1">
                                            <CheckCircle2 className="w-3 h-3" /> Done
                                        </span>
                                    ) : job.status === "error" || job.status === "failed" ? (
                                        <span className="text-xs text-red-400 bg-red-400/10 px-2 py-0.5 rounded flex items-center gap-1">
                                            <AlertCircle className="w-3 h-3" /> Failed
                                        </span>
                                    ) : (
                                        <span className="text-xs text-[#a3a3a3] bg-[#1a1a1a] px-2 py-0.5 rounded flex items-center gap-1">
                                            <Clock className="w-3 h-3" /> {job.status}
                                        </span>
                                    )}
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </div>
        </div>
    );
}
