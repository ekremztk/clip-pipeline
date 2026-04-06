"use client";

import { useState, useEffect, useRef } from "react";
import { Upload, Play, MoreVertical, Dna, Clapperboard, Search, ArrowRight, Link2, Sparkles, AlertCircle, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useChannel } from "./layout";
import { authFetch, API_URL } from "@/lib/api";
import { supabase } from "@/lib/supabase";

type Job = {
    id: string;
    video_title: string;
    status: string;
    progress?: number;
    progress_pct?: number;
    current_step?: string;
    step?: string;
    created_at?: string;
};

type UploadPhase = 'idle' | 'uploading' | 'settings' | 'processing';

const STEP_LABELS: Record<string, string> = {
    "downloading_video": "Downloading YouTube video...",
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
};

const DURATION_PRESETS = [
    { label: '<30s',   min: 5,   max: 30  },
    { label: '<60s',   min: 10,  max: 60  },
    { label: '30-60s', min: 30,  max: 60  },
    { label: '45-60s', min: 45,  max: 60  },
    { label: '1m-3m',  min: 60,  max: 180 },
    { label: '1m-5m',  min: 60,  max: 300 },
    { label: '5m-15m', min: 300, max: 900 },
];

function getStepLabel(step: string | undefined): string {
    if (!step) return "Processing...";
    return STEP_LABELS[step] || step.replace(/_/g, " ").replace(/^s\d+\s?/, "");
}

const formatDate = (dateStr?: string) => {
    if (!dateStr) return 'Just now';
    const diff = Date.now() - new Date(dateStr).getTime();
    const hours = diff / (1000 * 60 * 60);
    const days = Math.floor(hours / 24);
    if (hours < 1) {
        const mins = Math.floor(hours * 60);
        return mins <= 1 ? 'Just now' : `${mins}m ago`;
    }
    if (hours < 24) return 'Today';
    if (days === 1) return 'Yesterday';
    return `${days}d ago`;
};

function formatTimeDisplay(time: number) {
    const h = Math.floor(time / 3600).toString().padStart(2, '0');
    const m = Math.floor((time % 3600) / 60).toString().padStart(2, '0');
    const s = Math.floor(time % 60).toString().padStart(2, '0');
    return `${h}:${m}:${s}`;
}

function TimeInput({ value, onChange, max }: { value: number; onChange: (v: number) => void; max: number }) {
    const [local, setLocal] = useState(value.toString().padStart(2, '0'));
    useEffect(() => { setLocal(value.toString().padStart(2, '0')); }, [value]);
    return (
        <input
            type="text"
            value={local}
            onChange={e => setLocal(e.target.value)}
            onBlur={() => {
                let n = parseInt(local);
                if (isNaN(n)) n = 0;
                if (n > max) n = max;
                setLocal(n.toString().padStart(2, '0'));
                onChange(n);
            }}
            className="w-9 text-center bg-[#0a0a0a] border border-[#262626] rounded py-1 text-xs text-white focus:outline-none focus:border-[#404040] transition-colors"
        />
    );
}

const features = [
    {
        icon: Dna,
        name: "Channel DNA",
        description: "Train the AI on your channel's unique style and voice",
        href: "/dashboard/channel-dna",
    },
    {
        icon: Clapperboard,
        name: "AI Director",
        description: "Intelligent recommendations based on your performance data",
        href: "/director",
    },
    {
        icon: Search,
        name: "Content Finder",
        description: "Discover viral moments across your long-form content",
        href: "/dashboard/content-finder",
    },
];

function Skeleton({ className }: { className?: string }) {
    return <div className={`bg-[#0f0f0f] rounded animate-pulse ${className ?? ""}`} />;
}

function PageSkeleton() {
    return (
        <div className="min-h-screen bg-black">
            <div className="max-w-5xl mx-auto px-8 py-10 space-y-12">
                <div className="text-center space-y-3 pt-4">
                    <Skeleton className="h-10 w-2/3 mx-auto rounded-xl" />
                    <Skeleton className="h-4 w-1/3 mx-auto rounded" />
                </div>
                <Skeleton className="h-52 w-full rounded-xl border border-[#1a1a1a]" />
                <div className="space-y-5">
                    <div className="space-y-1.5">
                        <Skeleton className="h-5 w-36" />
                        <Skeleton className="h-3 w-48" />
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                        {[...Array(4)].map((_, i) => (
                            <div key={i} className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg overflow-hidden">
                                <Skeleton className="aspect-video w-full rounded-none" />
                                <div className="p-3 space-y-2">
                                    <Skeleton className="h-3 w-3/4" />
                                    <Skeleton className="h-2 w-1/2" />
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}

export default function DashboardPage() {
    const router = useRouter();
    const { channels, activeChannelId, isLoading: channelLoading, refreshChannels } = useChannel();

    // Jobs state
    const [jobs, setJobs] = useState<Job[]>([]);
    const [loading, setLoading] = useState(true);

    // Upload state machine
    const [uploadPhase, setUploadPhase] = useState<UploadPhase>('idle');
    const [uploadProgress, setUploadProgress] = useState(0);
    const [uploadId, setUploadId] = useState('');
    const [file, setFile] = useState<File | null>(null);
    const [videoUrl, setVideoUrl] = useState('');
    const [videoDuration, setVideoDuration] = useState(0);
    const [isDragging, setIsDragging] = useState(false);
    const [draggingHandle, setDraggingHandle] = useState<'start' | 'end' | null>(null);

    // Form state
    const [title, setTitle] = useState('');
    const [guestName, setGuestName] = useState('');
    const [formChannelId, setFormChannelId] = useState('');
    const [durationPreset, setDurationPreset] = useState('<60s');
    const [aspectRatio, setAspectRatio] = useState('9:16');
    const [genre, setGenre] = useState('');
    const [autoHook, setAutoHook] = useState(true);
    const [startTime, setStartTime] = useState(0);
    const [endTime, setEndTime] = useState(0);

    // YouTube URL state
    const [youtubeUrl, setYoutubeUrl] = useState('');
    const [youtubeFetching, setYoutubeFetching] = useState(false);
    const [youtubeError, setYoutubeError] = useState('');

    // Processing state
    const [statusMsg, setStatusMsg] = useState('');
    const [submitError, setSubmitError] = useState('');

    const fileInputRef = useRef<HTMLInputElement>(null);
    const videoRef = useRef<HTMLVideoElement>(null);
    const timelineRef = useRef<HTMLDivElement>(null);

    // Sync channel selection into form
    useEffect(() => {
        if (activeChannelId && !formChannelId) {
            setFormChannelId(activeChannelId);
        }
    }, [activeChannelId, formChannelId]);

    // Load jobs
    useEffect(() => {
        if (channelLoading || !activeChannelId) {
            if (!channelLoading) setLoading(false);
            return;
        }
        setLoading(true);
        authFetch(`/jobs?channel_id=${activeChannelId}&limit=20`)
            .then(r => r.ok ? r.json() : [])
            .then(data => setJobs(data))
            .catch(console.error)
            .finally(() => setLoading(false));
    }, [activeChannelId, channelLoading]);

    // Auto-refresh active jobs
    useEffect(() => {
        if (!activeChannelId || channelLoading) return;
        const hasActive = jobs.some(j => ['processing', 'queued', 'running'].includes(j.status));
        if (!hasActive) return;
        const interval = setInterval(async () => {
            try {
                const res = await authFetch(`/jobs?channel_id=${activeChannelId}&limit=20`);
                if (res.ok) setJobs(await res.json());
            } catch { /* silent */ }
        }, 4000);
        return () => clearInterval(interval);
    }, [activeChannelId, channelLoading, jobs]);

    // Timeline drag
    useEffect(() => {
        const handleMouseMove = (e: MouseEvent) => {
            if (!draggingHandle || !timelineRef.current || videoDuration === 0) return;
            const rect = timelineRef.current.getBoundingClientRect();
            const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
            const time = (x / rect.width) * videoDuration;
            if (draggingHandle === 'start') setStartTime(Math.min(time, Math.max(0, endTime - 30)));
            else setEndTime(Math.max(time, Math.min(videoDuration, startTime + 30)));
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

    // Sync video preview to trim handles
    useEffect(() => {
        if (videoRef.current && uploadPhase === 'settings') {
            if (draggingHandle === 'start') videoRef.current.currentTime = startTime;
            else if (draggingHandle === 'end') videoRef.current.currentTime = endTime;
        }
    }, [startTime, endTime, draggingHandle, uploadPhase]);

    const resetUpload = () => {
        if (videoUrl) URL.revokeObjectURL(videoUrl);
        setFile(null);
        setVideoUrl('');
        setUploadId('');
        setVideoDuration(0);
        setTitle('');
        setGuestName('');
        setStartTime(0);
        setEndTime(0);
        setDurationPreset('<60s');
        setAspectRatio('9:16');
        setGenre('');
        setAutoHook(true);
        setSubmitError('');
        setStatusMsg('');
        setYoutubeUrl('');
        setYoutubeError('');
        setYoutubeFetching(false);
        setFormChannelId(activeChannelId);
    };

    const getYouTubeId = (url: string) => {
        const m = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})/);
        return m?.[1] ?? '';
    };

    const handleYoutubeUrl = async (url: string) => {
        const isValid = url.includes('youtube.com/watch') || url.includes('youtu.be/') || url.includes('youtube.com/shorts/');
        if (!isValid) { setYoutubeError('Please enter a valid YouTube URL'); return; }
        setYoutubeError('');
        setYoutubeFetching(true);

        let channelId = formChannelId || activeChannelId;
        if (!channelId) {
            try { channelId = await autoCreateChannel(); setFormChannelId(channelId); }
            catch { setYoutubeError('Failed to create channel. Please create one in Settings first.'); setYoutubeFetching(false); return; }
        }

        try {
            const res = await authFetch(`/jobs/youtube-info?url=${encodeURIComponent(url)}`);
            if (!res.ok) { setYoutubeError('Could not fetch video info. Check the URL and try again.'); setYoutubeFetching(false); return; }
            const info = await res.json();
            setTitle(info.title || '');
            const dur = info.duration_seconds || 0;
            setVideoDuration(dur);
            setEndTime(dur);
            setUploadPhase('settings');
        } catch {
            setYoutubeError('Could not fetch video info. Check the URL and try again.');
        } finally {
            setYoutubeFetching(false);
        }
    };

    const autoCreateChannel = async (): Promise<string> => {
        const channelId = `my_channel_${Date.now()}`;
        const res = await authFetch('/channels', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channel_id: channelId, display_name: 'My Channel' }),
        });
        if (!res.ok) throw new Error('Failed to create channel');
        await refreshChannels();
        return channelId;
    };

    const handleFileSelect = async (selectedFile: File) => {
        // Validate
        const ext = selectedFile.name.split('.').pop()?.toLowerCase() ?? '';
        if (!['mp4', 'mov', 'avi', 'mkv', 'webm'].includes(ext)) {
            setSubmitError('Unsupported file format. Use MP4, MOV, AVI, MKV, or WEBM.');
            return;
        }

        setFile(selectedFile);
        setUploadPhase('uploading');
        setUploadProgress(0);
        setSubmitError('');

        // Auto-create channel if none exists
        let channelId = formChannelId || activeChannelId;
        if (!channelId) {
            try {
                channelId = await autoCreateChannel();
                setFormChannelId(channelId);
            } catch {
                setSubmitError('Failed to create a channel. Please create one in Settings first.');
                setUploadPhase('idle');
                setFile(null);
                return;
            }
        }

        const url = URL.createObjectURL(selectedFile);
        setVideoUrl(url);

        const { data: sessionData } = await supabase.auth.getSession();
        const token = sessionData?.session?.access_token;

        const xhr = new XMLHttpRequest();
        xhr.open('POST', `${API_URL}/jobs/upload-preview`, true);
        if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) setUploadProgress(Math.round((e.loaded / e.total) * 100));
        };
        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                const resp = JSON.parse(xhr.responseText);
                setUploadId(resp.upload_id);
                const dur = resp.duration_seconds || 0;
                if (dur === 0) {
                    const tmp = document.createElement('video');
                    tmp.src = url;
                    tmp.onloadedmetadata = () => {
                        setVideoDuration(tmp.duration);
                        setEndTime(tmp.duration);
                        setUploadPhase('settings');
                    };
                } else {
                    setVideoDuration(dur);
                    setEndTime(dur);
                    setUploadPhase('settings');
                }
            } else {
                setSubmitError('Upload failed. Please try again.');
                setUploadPhase('idle');
                setFile(null);
                URL.revokeObjectURL(url);
                setVideoUrl('');
            }
        };
        xhr.onerror = () => {
            setSubmitError('Network error during upload. Please try again.');
            setUploadPhase('idle');
            setFile(null);
            URL.revokeObjectURL(url);
            setVideoUrl('');
        };
        const formData = new FormData();
        formData.append('file', selectedFile);
        xhr.send(formData);
    };

    const handleStartProcessing = async () => {
        if ((!uploadId && !youtubeUrl) || !title || !formChannelId) return;
        setUploadPhase('processing');
        setStatusMsg('Starting pipeline...');
        setSubmitError('');

        const preset = DURATION_PRESETS.find(p => p.label === durationPreset) ?? DURATION_PRESETS[1];
        const fd = new FormData();
        if (youtubeUrl) {
            fd.append('youtube_url', youtubeUrl);
        } else {
            fd.append('upload_id', uploadId);
        }
        fd.append('title', title);
        fd.append('channel_id', formChannelId);
        if (guestName) fd.append('guest_name', guestName);
        fd.append('trim_start_seconds', startTime.toString());
        fd.append('trim_end_seconds', endTime.toString());
        fd.append('clip_duration_min', preset.min.toString());
        fd.append('clip_duration_max', preset.max.toString());
        fd.append('aspect_ratio', aspectRatio);
        if (genre) fd.append('genre', genre);
        fd.append('auto_hook', autoHook ? 'true' : 'false');

        try {
            const res = await authFetch('/jobs', { method: 'POST', body: fd });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                setSubmitError(err.detail || 'Failed to start processing');
                setUploadPhase('settings');
                return;
            }
            const job = await res.json();
            const jobId = job?.id || job?.job_id;
            if (!jobId) {
                setSubmitError('No job ID returned');
                setUploadPhase('settings');
                return;
            }

            setStatusMsg('Processing video...');
            let attempts = 0;
            const poll = async () => {
                try {
                    const statusRes = await authFetch(`/jobs/${jobId}`);
                    const jobData = await statusRes.json();
                    const status = jobData?.job?.status || jobData?.status;
                    if (status === 'completed' || status === 'done') {
                        setUploadPhase('idle');
                        resetUpload();
                        // Refresh jobs list
                        const r = await authFetch(`/jobs?channel_id=${formChannelId}&limit=20`);
                        if (r.ok) setJobs(await r.json());
                        return;
                    }
                    if (status === 'failed' || status === 'error') {
                        setSubmitError('Pipeline failed. Please try again.');
                        setUploadPhase('settings');
                        return;
                    }
                    const step = jobData?.job?.current_step || jobData?.job?.step || '';
                    setStatusMsg(getStepLabel(step));
                    attempts++;
                    if (attempts < 90) setTimeout(poll, 2000);
                    else {
                        setUploadPhase('idle');
                        resetUpload();
                    }
                } catch {
                    attempts++;
                    if (attempts < 90) setTimeout(poll, 2000);
                }
            };
            setTimeout(poll, 2000);
        } catch (err: any) {
            setSubmitError(err.message || 'Failed to start processing.');
            setUploadPhase('settings');
        }
    };

    // TimeGroup — inline since it closes over state setters
    const TimeGroup = ({ time, isStart }: { time: number; isStart: boolean }) => {
        const h = Math.floor(time / 3600);
        const m = Math.floor((time % 3600) / 60);
        const s = Math.floor(time % 60);
        const update = (type: 'h' | 'm' | 's', val: number) => {
            let t = time;
            if (type === 'h') t = val * 3600 + m * 60 + s;
            if (type === 'm') t = h * 3600 + val * 60 + s;
            if (type === 's') t = h * 3600 + m * 60 + val;
            if (isStart) setStartTime(Math.max(0, Math.min(t, endTime - 30)));
            else setEndTime(Math.min(videoDuration, Math.max(t, startTime + 30)));
        };
        return (
            <div className="flex flex-col items-center gap-1">
                <span className="text-[9px] text-[#525252] uppercase tracking-widest">{isStart ? 'START' : 'END'}</span>
                <div className="flex items-center gap-0.5">
                    <TimeInput value={h} onChange={v => update('h', v)} max={99} />
                    <span className="text-[#525252] text-xs">:</span>
                    <TimeInput value={m} onChange={v => update('m', v)} max={59} />
                    <span className="text-[#525252] text-xs">:</span>
                    <TimeInput value={s} onChange={v => update('s', v)} max={59} />
                </div>
                <div className="flex gap-[22px]">
                    <span className="text-[9px] text-[#525252]">HH</span>
                    <span className="text-[9px] text-[#525252]">MM</span>
                    <span className="text-[9px] text-[#525252]">SS</span>
                </div>
            </div>
        );
    };

    const startPercent = videoDuration ? (startTime / videoDuration) * 100 : 0;
    const endPercent   = videoDuration ? (endTime / videoDuration) * 100 : 100;

    if (channelLoading) return <PageSkeleton />;

    const activeJobs = jobs.filter(j => ['processing', 'queued', 'running'].includes(j.status));
    const recentJobs = jobs.filter(j => !['processing', 'queued', 'running'].includes(j.status)).slice(0, 8);

    if (!activeChannelId && uploadPhase === 'idle') {
        return (
            <div className="min-h-screen bg-black flex items-center justify-center p-8">
                <div className="text-center max-w-sm">
                    <div className="w-14 h-14 bg-[#0a0a0a] border border-[#1a1a1a] rounded-2xl flex items-center justify-center mx-auto mb-5">
                        <Sparkles className="w-6 h-6 text-[#525252]" />
                    </div>
                    <h2 className="text-lg font-semibold text-white mb-2">Create your first channel</h2>
                    <p className="text-sm text-[#737373] mb-6">Set up a channel to start extracting viral clips from your videos.</p>
                    <Link
                        href="/dashboard/settings"
                        className="inline-flex items-center gap-2 bg-white hover:bg-[#e5e5e5] text-black text-sm font-medium px-5 py-2.5 rounded-xl transition-colors"
                    >
                        Add Channel
                    </Link>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-black">
            <div className="max-w-5xl mx-auto px-8 py-10 space-y-12">

                {/* Hero — hidden during settings/processing to give space */}
                {uploadPhase === 'idle' && (
                    <div className="text-center space-y-3 pt-4">
                        <h1 className="text-4xl font-semibold text-white tracking-tight">
                            Transform Long Videos into Viral Shorts
                        </h1>
                        <p className="text-sm text-[#737373] max-w-xl mx-auto">
                            AI-powered video clipping with Channel DNA, AI Director, and Content Finder
                        </p>
                    </div>
                )}

                {/* ── Upload Zone ── */}
                <div className="w-full max-w-5xl mx-auto">

                    {/* IDLE */}
                    {uploadPhase === 'idle' && (
                        <div className="relative">
                            {/* Corner accents */}
                            <div className="absolute -left-1 -top-1 w-12 h-12 pointer-events-none">
                                <div className="absolute top-0 left-0 w-12 h-px bg-white/10" />
                                <div className="absolute top-0 left-0 w-px h-12 bg-white/10" />
                            </div>
                            <div className="absolute -right-1 -top-1 w-12 h-12 pointer-events-none">
                                <div className="absolute top-0 right-0 w-12 h-px bg-white/10" />
                                <div className="absolute top-0 right-0 w-px h-12 bg-white/10" />
                            </div>
                            <div className="absolute -left-1 -bottom-1 w-12 h-12 pointer-events-none">
                                <div className="absolute bottom-0 left-0 w-12 h-px bg-white/10" />
                                <div className="absolute bottom-0 left-0 w-px h-12 bg-white/10" />
                            </div>
                            <div className="absolute -right-1 -bottom-1 w-12 h-12 pointer-events-none">
                                <div className="absolute bottom-0 right-0 w-12 h-px bg-white/10" />
                                <div className="absolute bottom-0 right-0 w-px h-12 bg-white/10" />
                            </div>

                            <input
                                ref={fileInputRef}
                                type="file"
                                accept=".mp4,.mov,.avi,.mkv,.webm,video/*"
                                className="hidden"
                                onChange={e => { if (e.target.files?.[0]) handleFileSelect(e.target.files[0]); }}
                            />

                            <div
                                onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
                                onDragLeave={() => setIsDragging(false)}
                                onDrop={e => { e.preventDefault(); setIsDragging(false); if (e.dataTransfer.files?.[0]) handleFileSelect(e.dataTransfer.files[0]); }}
                                onClick={() => fileInputRef.current?.click()}
                                className={`relative border border-dashed rounded-xl overflow-hidden transition-all duration-300 cursor-pointer group ${
                                    isDragging ? 'border-white bg-[#0a0a0a]' : 'border-[#262626] hover:border-[#404040]'
                                }`}
                            >
                                <div className="absolute inset-0 flex items-center justify-center opacity-[0.02] pointer-events-none select-none overflow-hidden">
                                    <div className="text-[12rem] font-bold tracking-tighter leading-none whitespace-nowrap text-white">PROGNOT</div>
                                </div>

                                <div className="relative p-10 flex flex-col items-center justify-center text-center">
                                    <div className={`w-12 h-12 mb-4 rounded-lg flex items-center justify-center border transition-colors ${isDragging ? 'bg-[#1a1a1a] border-[#404040]' : 'bg-[#0a0a0a] border-[#262626] group-hover:border-[#404040]'}`}>
                                        <Upload className={`w-6 h-6 ${isDragging ? 'text-white' : 'text-[#a3a3a3]'}`} />
                                    </div>
                                    <h3 className="text-lg font-medium text-white mb-1">Drop your video or paste link</h3>
                                    <p className="text-sm text-[#737373] mb-5">MP4, MOV, AVI, WebM up to 2GB</p>
                                    <button
                                        onClick={e => { e.stopPropagation(); fileInputRef.current?.click(); }}
                                        className="px-5 py-2.5 bg-white text-black rounded-lg text-sm font-medium hover:bg-[#e5e5e5] transition-colors"
                                    >
                                        Select File
                                    </button>

                                    <div className="mt-6 flex items-center gap-3 w-full max-w-sm">
                                        <div className="flex-1 h-px bg-[#1a1a1a]" />
                                        <span className="text-xs text-[#525252]">OR</span>
                                        <div className="flex-1 h-px bg-[#1a1a1a]" />
                                    </div>

                                    <div className="mt-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
                                        <div className="relative">
                                            <Link2 className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#525252]" />
                                            <input
                                                type="text"
                                                value={youtubeUrl}
                                                onChange={e => { setYoutubeUrl(e.target.value); setYoutubeError(''); }}
                                                onKeyDown={e => { if (e.key === 'Enter' && youtubeUrl) handleYoutubeUrl(youtubeUrl); }}
                                                onPaste={e => {
                                                    const pasted = e.clipboardData.getData('text');
                                                    if (pasted.includes('youtube.com') || pasted.includes('youtu.be')) {
                                                        e.preventDefault();
                                                        setYoutubeUrl(pasted);
                                                        handleYoutubeUrl(pasted);
                                                    }
                                                }}
                                                placeholder="Paste YouTube URL"
                                                className="w-full pl-10 pr-4 py-2.5 bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg text-sm text-white placeholder-[#525252] focus:outline-none focus:border-[#404040] transition-colors"
                                            />
                                            {youtubeFetching && (
                                                <div className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 border-2 border-[#404040] border-t-white rounded-full animate-spin" />
                                            )}
                                        </div>
                                        {youtubeError && <p className="mt-1.5 text-xs text-red-400 text-left">{youtubeError}</p>}
                                    </div>
                                </div>
                            </div>

                            {submitError && (
                                <div className="mt-3 p-3 bg-red-500/5 border border-red-500/20 rounded-lg text-red-400 text-sm flex items-center gap-2">
                                    <AlertCircle className="w-4 h-4 flex-shrink-0" />
                                    {submitError}
                                </div>
                            )}

                            <p className="mt-3 text-center text-xs text-[#525252]">
                                YouTube • Twitch • Vimeo • Direct Upload
                            </p>
                        </div>
                    )}

                    {/* UPLOADING */}
                    {uploadPhase === 'uploading' && file && (
                        <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl p-10 flex flex-col items-center text-center">
                            <div className="w-10 h-10 mb-4 rounded-lg bg-[#0f0f0f] border border-[#262626] flex items-center justify-center">
                                <Upload className="w-5 h-5 text-[#a3a3a3]" />
                            </div>
                            <p className="text-sm text-white font-medium mb-1 max-w-sm truncate">{file.name}</p>
                            <p className="text-xs text-[#525252] mb-5">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
                            <div className="w-64 h-1.5 bg-[#1a1a1a] rounded-full overflow-hidden relative mb-3">
                                <div
                                    className="absolute top-0 left-0 bottom-0 bg-white rounded-full transition-all duration-300"
                                    style={{ width: `${uploadProgress}%` }}
                                />
                            </div>
                            <p className="text-xs text-[#525252]">Uploading... {uploadProgress}%</p>
                        </div>
                    )}

                    {/* SETTINGS */}
                    {uploadPhase === 'settings' && (
                        <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl overflow-hidden">
                            {/* Panel header */}
                            <div className="flex items-center justify-between px-5 py-3 border-b border-[#1a1a1a]">
                                <div className="flex items-center gap-2 min-w-0">
                                    <span className="text-sm font-medium text-white truncate max-w-xs">{youtubeUrl ? title : file?.name}</span>
                                    <span className="text-[#525252] text-xs flex-shrink-0">· {formatTimeDisplay(videoDuration)}</span>
                                </div>
                                <button
                                    onClick={() => { setUploadPhase('idle'); resetUpload(); }}
                                    className="flex-shrink-0 p-1.5 rounded-lg text-[#525252] hover:text-white hover:bg-[#1a1a1a] transition-colors ml-3"
                                >
                                    <X className="w-4 h-4" />
                                </button>
                            </div>

                            <div className="p-5 grid grid-cols-1 lg:grid-cols-2 gap-5">

                                {/* Left: Video Preview + Timeline */}
                                <div className="space-y-3">
                                    <div className="aspect-video bg-black rounded-lg overflow-hidden border border-[#262626]">
                                        {youtubeUrl ? (
                                            <iframe
                                                src={`https://www.youtube.com/embed/${getYouTubeId(youtubeUrl)}`}
                                                className="w-full h-full"
                                                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                                                allowFullScreen
                                            />
                                        ) : (
                                            <video
                                                ref={videoRef}
                                                src={videoUrl}
                                                className="w-full h-full object-contain"
                                                controls
                                                muted
                                                controlsList="nodownload nofullscreen"
                                            />
                                        )}
                                    </div>

                                    {/* Timeline trimmer */}
                                    <div className="bg-black border border-[#262626] rounded-lg p-4">
                                        <p className="text-[9px] text-[#525252] uppercase tracking-widest font-medium mb-3">Processing Range</p>
                                        <div className="flex justify-between text-xs text-[#737373] mb-2">
                                            <span>{formatTimeDisplay(startTime)}</span>
                                            <span>{formatTimeDisplay(endTime)}</span>
                                        </div>
                                        <div
                                            ref={timelineRef}
                                            className="relative w-full h-8 bg-[#1a1a1a] rounded-md mb-4 select-none overflow-hidden"
                                        >
                                            <div className="absolute top-0 bottom-0 left-0 bg-black/50" style={{ width: `${startPercent}%` }} />
                                            <div className="absolute top-0 bottom-0 right-0 bg-black/50" style={{ width: `${100 - endPercent}%` }} />
                                            <div
                                                className="absolute top-0 bottom-0 bg-white/10 border-y border-white/20"
                                                style={{ left: `${startPercent}%`, right: `${100 - endPercent}%` }}
                                            />
                                            <div
                                                className="absolute top-1/2 -translate-y-1/2 w-1 h-6 bg-white rounded-full cursor-ew-resize z-10"
                                                style={{ left: `calc(${startPercent}% - 2px)` }}
                                                onMouseDown={e => { e.preventDefault(); setDraggingHandle('start'); }}
                                            />
                                            <div
                                                className="absolute top-1/2 -translate-y-1/2 w-1 h-6 bg-white rounded-full cursor-ew-resize z-10"
                                                style={{ left: `calc(${endPercent}% - 2px)` }}
                                                onMouseDown={e => { e.preventDefault(); setDraggingHandle('end'); }}
                                            />
                                        </div>
                                        <div className="flex items-center justify-center gap-8">
                                            <TimeGroup time={startTime} isStart={true} />
                                            <button
                                                onClick={() => { setStartTime(0); setEndTime(videoDuration); }}
                                                className="text-[11px] text-[#525252] hover:text-white transition-colors mt-1"
                                            >
                                                Reset
                                            </button>
                                            <TimeGroup time={endTime} isStart={false} />
                                        </div>
                                    </div>
                                </div>

                                {/* Right: Settings Form */}
                                <div className="space-y-4">

                                    {/* Title */}
                                    <div>
                                        <label className="block text-[10px] text-[#737373] uppercase tracking-widest mb-1.5">Video Title *</label>
                                        <input
                                            type="text"
                                            value={title}
                                            onChange={e => setTitle(e.target.value)}
                                            placeholder="e.g. Joe Rogan #2054 – Elon Musk"
                                            className="w-full bg-black border border-[#262626] rounded-lg px-3.5 py-2.5 text-sm text-white placeholder-[#525252] focus:outline-none focus:border-[#404040] transition-colors"
                                            autoFocus
                                        />
                                    </div>

                                    {/* Duration Preset */}
                                    <div>
                                        <label className="block text-[10px] text-[#737373] uppercase tracking-widest mb-1.5">Clip Duration</label>
                                        <div className="flex flex-wrap gap-1.5">
                                            {DURATION_PRESETS.map(p => (
                                                <button
                                                    key={p.label}
                                                    onClick={() => setDurationPreset(p.label)}
                                                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                                                        durationPreset === p.label
                                                            ? 'bg-white text-black'
                                                            : 'bg-[#1a1a1a] text-[#a3a3a3] hover:bg-[#262626] hover:text-white'
                                                    }`}
                                                >
                                                    {p.label}
                                                </button>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Aspect Ratio */}
                                    <div>
                                        <label className="block text-[10px] text-[#737373] uppercase tracking-widest mb-1.5">Aspect Ratio</label>
                                        <div className="flex gap-2">
                                            {['9:16', '16:9'].map(ar => (
                                                <button
                                                    key={ar}
                                                    onClick={() => setAspectRatio(ar)}
                                                    className={`flex-1 py-2 rounded-lg text-xs font-medium transition-colors ${
                                                        aspectRatio === ar
                                                            ? 'bg-white text-black'
                                                            : 'bg-[#1a1a1a] text-[#a3a3a3] hover:bg-[#262626] hover:text-white'
                                                    }`}
                                                >
                                                    {ar} {ar === '9:16' ? '· Vertical' : '· Horizontal'}
                                                </button>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Genre + Guest */}
                                    <div className="grid grid-cols-2 gap-3">
                                        <div>
                                            <label className="block text-[10px] text-[#737373] uppercase tracking-widest mb-1.5">Genre</label>
                                            <select
                                                value={genre}
                                                onChange={e => setGenre(e.target.value)}
                                                className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#404040] transition-colors appearance-none"
                                            >
                                                <option value="">Auto-detect</option>
                                                <option value="podcast">Podcast</option>
                                                <option value="interview">Interview</option>
                                                <option value="talk_show">Talk Show</option>
                                                <option value="tutorial">Tutorial</option>
                                                <option value="vlog">Vlog</option>
                                                <option value="debate">Debate</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="block text-[10px] text-[#737373] uppercase tracking-widest mb-1.5">Guest Name</label>
                                            <input
                                                type="text"
                                                value={guestName}
                                                onChange={e => setGuestName(e.target.value)}
                                                placeholder="Optional"
                                                className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2.5 text-sm text-white placeholder-[#525252] focus:outline-none focus:border-[#404040] transition-colors"
                                            />
                                        </div>
                                    </div>

                                    {/* Auto Hook */}
                                    <div className="flex items-center justify-between py-1">
                                        <div>
                                            <p className="text-sm text-white">Auto Hook</p>
                                            <p className="text-xs text-[#525252]">Optimize for the first 3 seconds</p>
                                        </div>
                                        <button
                                            onClick={() => setAutoHook(v => !v)}
                                            className={`relative w-10 h-5.5 rounded-full transition-colors flex-shrink-0 ${autoHook ? 'bg-white' : 'bg-[#262626]'}`}
                                            style={{ height: '22px', width: '40px' }}
                                        >
                                            <span
                                                className={`absolute top-0.5 w-4 h-4 rounded-full transition-transform ${autoHook ? 'bg-black translate-x-5' : 'bg-[#737373] translate-x-0.5'}`}
                                            />
                                        </button>
                                    </div>

                                    {/* Channel */}
                                    {channels.length > 1 && (
                                        <div>
                                            <label className="block text-[10px] text-[#737373] uppercase tracking-widest mb-1.5">Channel</label>
                                            <select
                                                value={formChannelId}
                                                onChange={e => setFormChannelId(e.target.value)}
                                                className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#404040] transition-colors appearance-none"
                                            >
                                                {channels.map(c => (
                                                    <option key={c.id} value={c.id}>{c.display_name || c.id}</option>
                                                ))}
                                            </select>
                                        </div>
                                    )}

                                    {submitError && (
                                        <div className="p-3 bg-red-500/5 border border-red-500/20 rounded-lg text-red-400 text-xs flex items-center gap-2">
                                            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                                            {submitError}
                                        </div>
                                    )}

                                    {/* Submit */}
                                    <button
                                        onClick={handleStartProcessing}
                                        disabled={!title || (!uploadId && !youtubeUrl)}
                                        className={`w-full py-3 rounded-xl text-sm font-medium transition-all ${
                                            title && (uploadId || youtubeUrl)
                                                ? 'bg-white text-black hover:bg-[#e5e5e5]'
                                                : 'bg-[#0f0f0f] border border-[#1a1a1a] text-[#525252] cursor-not-allowed'
                                        }`}
                                    >
                                        Start Processing
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* PROCESSING */}
                    {uploadPhase === 'processing' && (
                        <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl p-8 flex flex-col items-center text-center">
                            <div className="flex items-center gap-2 mb-4">
                                <div className="w-2 h-2 rounded-full bg-white pulse-dot" />
                                <span className="text-xs text-[#737373] uppercase tracking-wider">Processing</span>
                            </div>
                            <div className="w-10 h-10 border-2 border-[#262626] border-t-white rounded-full animate-spin mb-5" />
                            <p className="text-base font-medium text-white mb-1">{title}</p>
                            <p className="text-sm text-[#737373]">{statusMsg || 'Starting pipeline...'}</p>
                        </div>
                    )}
                </div>

                {/* ── Active Jobs ── */}
                {activeJobs.length > 0 && (
                    <div>
                        <div className="flex items-center gap-2 mb-4">
                            <h2 className="text-base font-medium text-white">Active Jobs</h2>
                            <span className="w-2 h-2 rounded-full bg-white pulse-dot" />
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                            {activeJobs.map((job) => {
                                const progress = job.progress_pct ?? job.progress ?? 0;
                                return (
                                    <div key={job.id} className="group bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg overflow-hidden hover:border-[#404040] transition-all">
                                        <div className="aspect-video bg-[#0a0a0a] flex items-center justify-center p-6">
                                            <div className="text-center">
                                                <div className="flex items-center justify-center gap-2 mb-3">
                                                    <div className="w-2 h-2 rounded-full bg-white pulse-dot" />
                                                    <span className="text-xs text-[#737373] uppercase tracking-wider">Processing</span>
                                                </div>
                                                <p className="text-sm text-white">
                                                    {getStepLabel(job.current_step || job.step)}
                                                    {progress > 0 && <span className="text-[#737373] ml-2">({progress}%)</span>}
                                                </p>
                                            </div>
                                        </div>
                                        <div className="p-3 border-t border-[#1a1a1a]">
                                            <div className="flex items-center justify-between">
                                                <p className="text-xs font-medium text-white truncate">{job.video_title || "Untitled"}</p>
                                                <span className="text-xs text-[#525252]">{formatDate(job.created_at)}</span>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}

                {/* ── Feature Cards ── */}
                {uploadPhase === 'idle' && (
                    <div>
                        <div className="mb-5">
                            <h2 className="text-base font-medium text-white">Powered by AI</h2>
                            <p className="text-xs text-[#525252] mt-0.5">Unique features that set us apart</p>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                            {features.map((feature) => (
                                <Link
                                    key={feature.name}
                                    href={feature.href}
                                    className="group bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg p-5 hover:border-[#404040] transition-all duration-300"
                                >
                                    <div className="w-10 h-10 mb-3 rounded-lg bg-black flex items-center justify-center border border-[#1a1a1a] group-hover:border-[#404040] transition-colors">
                                        <feature.icon className="w-5 h-5 text-white" />
                                    </div>
                                    <h3 className="text-sm font-medium text-white mb-1.5 flex items-center justify-between">
                                        {feature.name}
                                        <ArrowRight className="w-3.5 h-3.5 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all" />
                                    </h3>
                                    <p className="text-xs text-[#525252] leading-relaxed">{feature.description}</p>
                                </Link>
                            ))}
                        </div>
                    </div>
                )}

                {/* ── Recent Projects ── */}
                <div>
                    <div className="flex items-center justify-between mb-5">
                        <div>
                            <h2 className="text-base font-medium text-white">Recent Projects</h2>
                            <p className="text-xs text-[#525252] mt-0.5">Continue where you left off</p>
                        </div>
                        <Link href="/dashboard/clips" className="text-xs text-[#525252] hover:text-white transition-colors">
                            View all
                        </Link>
                    </div>

                    {loading ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                            {[...Array(4)].map((_, i) => (
                                <div key={i} className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg overflow-hidden">
                                    <div className="aspect-video bg-[#0f0f0f] animate-pulse" />
                                    <div className="p-3 space-y-2">
                                        <div className="h-3 bg-[#0f0f0f] rounded w-3/4 animate-pulse" />
                                        <div className="h-2 bg-[#0f0f0f] rounded w-1/2 animate-pulse" />
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : recentJobs.length === 0 ? (
                        <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg p-12 text-center">
                            <p className="text-sm text-[#525252]">No projects yet. Upload your first video to get started.</p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                            {recentJobs.map((job) => (
                                <div
                                    key={job.id}
                                    className="group bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg overflow-hidden hover:border-[#404040] transition-all duration-300 cursor-pointer"
                                >
                                    <div className="relative aspect-video bg-[#0d0d0d] overflow-hidden flex items-center justify-center">
                                        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors flex items-center justify-center">
                                            <div className="w-10 h-10 rounded-full bg-white/0 group-hover:bg-white/90 flex items-center justify-center transform scale-75 group-hover:scale-100 transition-all">
                                                <Play className="w-4 h-4 text-black fill-black ml-0.5" />
                                            </div>
                                        </div>
                                        <div className="absolute top-2 right-2">
                                            {job.status === 'completed' && (
                                                <span className="px-1.5 py-0.5 bg-black/80 text-green-400 text-[10px] rounded">Done</span>
                                            )}
                                            {job.status === 'failed' && (
                                                <span className="px-1.5 py-0.5 bg-black/80 text-red-400 text-[10px] rounded">Failed</span>
                                            )}
                                        </div>
                                    </div>
                                    <div className="p-3">
                                        <div className="flex items-start justify-between gap-2">
                                            <div className="flex-1 min-w-0">
                                                <h3 className="text-xs font-medium text-white truncate mb-1">
                                                    {job.video_title || "Untitled"}
                                                </h3>
                                                <p className="text-xs text-[#525252]">{formatDate(job.created_at)}</p>
                                            </div>
                                            <button className="p-0.5 hover:bg-[#1a1a1a] rounded transition-colors">
                                                <MoreVertical className="w-3.5 h-3.5 text-[#525252]" />
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

            </div>
        </div>
    );
}
