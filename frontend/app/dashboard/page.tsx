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

const CAPTION_TEMPLATES = [
    {
        key: 'clean', label: 'Clean',
        textStyle: { color: '#ffffff', fontSize: 17, fontWeight: 600, lineHeight: 1.35 } as React.CSSProperties,
        phase2Animation: 'ct-fade',
    },
    {
        key: 'hormozi', label: 'Hormozi',
        textStyle: { color: '#FFE500', fontSize: 16, fontWeight: 900, textTransform: 'uppercase' as const, letterSpacing: 2 } as React.CSSProperties,
        phase2Animation: 'ct-pop',
    },
    {
        key: 'outline', label: 'Outline',
        textStyle: { color: '#fff', fontSize: 16, fontWeight: 900, WebkitTextStroke: '0.8px rgba(255,255,255,0.4)', textTransform: 'uppercase' as const } as React.CSSProperties,
        phase2Animation: 'ct-slide-up',
    },
    {
        key: 'pill', label: 'Pill',
        textStyle: { color: '#fff', fontSize: 14, fontWeight: 700, background: 'rgba(255,255,255,0.18)', borderRadius: 4, padding: '3px 10px' } as React.CSSProperties,
        phase2Animation: 'ct-slide-right',
    },
    {
        key: 'neon', label: 'Neon',
        textStyle: { color: '#00e5ff', fontSize: 16, fontWeight: 800, textShadow: '0 0 12px #00e5ff, 0 0 24px #00a8ff' } as React.CSSProperties,
        phase2Animation: 'ct-neon',
    },
    {
        key: 'cinematic', label: 'Cinematic',
        textStyle: { color: '#e8d5a0', fontSize: 14, fontWeight: 300, fontStyle: 'italic' as const, letterSpacing: 4 } as React.CSSProperties,
        phase2Animation: 'ct-cinematic',
    },
    {
        key: 'bold_pop', label: 'Bold Pop',
        textStyle: { color: '#ff5500', fontSize: 19, fontWeight: 900, fontStyle: 'italic' as const } as React.CSSProperties,
        phase2Animation: 'ct-bounce',
    },
    {
        key: 'fire', label: 'Fire',
        textStyle: { color: '#ff3300', fontSize: 19, fontWeight: 900, textShadow: '0 0 10px #ff2200, 0 0 22px #ff4400' } as React.CSSProperties,
        phase2Animation: 'ct-fire',
    },
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
            className="w-9 text-center rounded py-1 text-xs focus:outline-none transition-colors"
            style={{ background: '#1c1c1b', border: '1px solid rgba(250,249,245,0.08)', color: '#faf9f5' }}
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
    return (
        <div
            className={`rounded animate-pulse ${className ?? ""}`}
            style={{ background: 'rgba(250,249,245,0.06)' }}
        />
    );
}

function PageSkeleton() {
    return (
        <div className="min-h-screen" style={{ background: '#141413' }}>
            <div className="max-w-5xl mx-auto px-8 py-10 space-y-12">
                <div className="text-center space-y-3 pt-4">
                    <Skeleton className="h-10 w-2/3 mx-auto rounded-xl" />
                    <Skeleton className="h-4 w-1/3 mx-auto rounded" />
                </div>
                <Skeleton className="h-52 w-full rounded-2xl" />
                <div className="space-y-5">
                    <div className="space-y-1.5">
                        <Skeleton className="h-5 w-36" />
                        <Skeleton className="h-3 w-48" />
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                        {[...Array(4)].map((_, i) => (
                            <div key={i} className="rounded-2xl overflow-hidden" style={{ background: '#181817' }}>
                                <Skeleton className="aspect-video w-full rounded-none" />
                                <div className="p-4 space-y-2">
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

    // Upload tab (link vs file)
    const [uploadTab, setUploadTab] = useState<'link' | 'file'>('link');
    const [captionTemplateIdx, setCaptionTemplateIdx] = useState(0);
    const [windowStart, setWindowStart] = useState(0);
    const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

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
        setUploadTab('link');
        setCaptionTemplateIdx(0);
        setWindowStart(0);
        setHoveredIdx(null);
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

        // Step 1: fetch title quickly via oEmbed (no download)
        try {
            const infoRes = await authFetch(`/jobs/youtube-info?url=${encodeURIComponent(url)}`);
            if (!infoRes.ok) { setYoutubeError('Could not fetch video info. Check the URL and try again.'); setYoutubeFetching(false); return; }
            const info = await infoRes.json();
            setTitle(info.title || '');
        } catch {
            setYoutubeError('Could not fetch video info. Check the URL and try again.');
            setYoutubeFetching(false);
            return;
        }

        // Step 2: download video to server for preview (shows "Downloading..." state)
        setYoutubeFetching(false);
        setUploadPhase('uploading');

        const { data: sessionData } = await supabase.auth.getSession();
        const token = sessionData?.session?.access_token;

        const xhr = new XMLHttpRequest();
        xhr.open('POST', `${API_URL}/jobs/youtube-preview`, true);
        if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                const resp = JSON.parse(xhr.responseText);
                setUploadId(resp.upload_id);
                const dur = resp.duration_seconds || 0;
                setVideoDuration(dur);
                setEndTime(dur);
                setVideoUrl(`${API_URL}/jobs/video-stream/${resp.upload_id}`);
                setUploadPhase('settings');
            } else {
                setYoutubeError('Could not download video. Please try again.');
                setUploadPhase('idle');
            }
        };
        xhr.onerror = () => {
            setYoutubeError('Network error downloading video. Please try again.');
            setUploadPhase('idle');
        };
        const fd = new FormData();
        fd.append('url', url);
        xhr.send(fd);
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
        if (uploadId) {
            fd.append('upload_id', uploadId);
        } else if (youtubeUrl) {
            fd.append('youtube_url', youtubeUrl);
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
        fd.append('caption_template', CAPTION_TEMPLATES[captionTemplateIdx].key);

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

    const handleCardHover = (idx: number) => setHoveredIdx(idx);
    const handleCardLeave = () => setHoveredIdx(null);

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
                <span className="text-[9px] uppercase tracking-widest" style={{ color: '#ababab' }}>
                    {isStart ? 'START' : 'END'}
                </span>
                <div className="flex items-center gap-0.5">
                    <TimeInput value={h} onChange={v => update('h', v)} max={99} />
                    <span className="text-xs" style={{ color: '#ababab' }}>:</span>
                    <TimeInput value={m} onChange={v => update('m', v)} max={59} />
                    <span className="text-xs" style={{ color: '#ababab' }}>:</span>
                    <TimeInput value={s} onChange={v => update('s', v)} max={59} />
                </div>
                <div className="flex gap-[22px]">
                    <span className="text-[9px]" style={{ color: '#ababab' }}>HH</span>
                    <span className="text-[9px]" style={{ color: '#ababab' }}>MM</span>
                    <span className="text-[9px]" style={{ color: '#ababab' }}>SS</span>
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
            <div className="min-h-screen flex items-center justify-center p-8" style={{ background: '#141413' }}>
                <div className="text-center max-w-sm">
                    <div
                        className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-5"
                        style={{ background: '#181817', border: '1px solid rgba(250,249,245,0.07)' }}
                    >
                        <Sparkles className="w-6 h-6" style={{ color: '#ababab' }} />
                    </div>
                    <h2 className="text-lg font-semibold mb-2" style={{ color: '#faf9f5' }}>Create your first channel</h2>
                    <p className="text-sm mb-6" style={{ color: '#ababab' }}>Set up a channel to start extracting viral clips from your videos.</p>
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
        <div className="min-h-screen" style={{ background: '#141413' }}>
            <div className="max-w-5xl mx-auto px-8 py-10 space-y-12">

                {/* Hero — hidden during settings/processing to give space */}
                {uploadPhase === 'idle' && (
                    <div className="text-center space-y-3 pt-4">
                        <h1 className="text-3xl font-semibold tracking-tight" style={{ color: '#faf9f5' }}>
                            Turn Long Videos Into Viral Shorts
                        </h1>
                        <p className="text-sm max-w-lg mx-auto" style={{ color: '#ababab' }}>
                            Drop a video link or upload a file. Our AI finds the best moments and turns them into ready-to-post clips.
                        </p>
                    </div>
                )}

                {/* ── Upload Zone ── */}
                <div className="w-full max-w-5xl mx-auto">

                    {/* IDLE — tabbed upload widget */}
                    {uploadPhase === 'idle' && (
                        <div className="relative mx-auto w-full max-w-3xl">
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept=".mp4,.mov,.avi,.mkv,.webm,video/*"
                                className="hidden"
                                onChange={e => { if (e.target.files?.[0]) handleFileSelect(e.target.files[0]); }}
                            />

                            {/* Outer card */}
                            <div
                                className="p-3 w-full relative overflow-hidden"
                                style={{
                                    background: '#181817',
                                    borderRadius: '24px',
                                    boxShadow: '0 10px 40px -10px rgba(0,0,0,0.5)',
                                }}
                            >
                                {/* Tab selector */}
                                <div className="flex gap-2 mb-4 px-2 pt-2">
                                    {[
                                        { id: 'link' as const, icon: Link2, label: 'Link' },
                                        { id: 'file' as const, icon: Upload, label: 'File' },
                                    ].map(tab => {
                                        const Icon = tab.icon;
                                        const isActive = uploadTab === tab.id;
                                        return (
                                            <button
                                                key={tab.id}
                                                onClick={() => setUploadTab(tab.id)}
                                                className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-medium transition-all"
                                                style={{
                                                    background: isActive ? 'rgba(250,249,245,0.05)' : 'transparent',
                                                    color: isActive ? '#faf9f5' : 'rgba(250,249,245,0.35)',
                                                }}
                                            >
                                                <Icon size={14} />
                                                {tab.label}
                                            </button>
                                        );
                                    })}
                                </div>

                                {/* Input area */}
                                <div
                                    className="flex items-center justify-between p-2 pl-4 transition-all min-h-[72px]"
                                    style={{
                                        background: isDragging ? 'rgba(250,249,245,0.02)' : '#131312',
                                        borderRadius: '18px',
                                        border: isDragging
                                            ? '1px dashed rgba(250,249,245,0.2)'
                                            : '1px solid rgba(250,249,245,0.03)',
                                    }}
                                    onDragOver={e => { e.preventDefault(); if (uploadTab === 'file') setIsDragging(true); }}
                                    onDragLeave={() => setIsDragging(false)}
                                    onDrop={e => {
                                        e.preventDefault();
                                        setIsDragging(false);
                                        if (uploadTab === 'file' && e.dataTransfer.files?.[0]) handleFileSelect(e.dataTransfer.files[0]);
                                    }}
                                >
                                    {uploadTab === 'link' ? (
                                        <>
                                            <div className="flex items-center gap-3 flex-1 px-2">
                                                <Link2 size={16} style={{ color: '#ababab' }} />
                                                <input
                                                    type="text"
                                                    value={youtubeUrl}
                                                    onChange={e => { setYoutubeUrl(e.target.value); setYoutubeError(''); }}
                                                    onKeyDown={e => { if (e.key === 'Enter' && youtubeUrl) handleYoutubeUrl(youtubeUrl); }}
                                                    placeholder="Paste a YouTube, Twitch or Vimeo URL..."
                                                    className="w-full text-sm outline-none h-full"
                                                    style={{
                                                        background: 'transparent',
                                                        color: '#faf9f5',
                                                    }}
                                                />
                                            </div>
                                            <button
                                                onClick={() => youtubeUrl && handleYoutubeUrl(youtubeUrl)}
                                                disabled={!youtubeUrl || youtubeFetching}
                                                className="px-6 py-3.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 transition-all ml-2 whitespace-nowrap"
                                                style={{
                                                    background: youtubeUrl ? '#faf9f5' : 'rgba(250,249,245,0.05)',
                                                    color: youtubeUrl ? '#141413' : 'rgba(250,249,245,0.3)',
                                                }}
                                            >
                                                {youtubeFetching ? (
                                                    <><span className="w-3.5 h-3.5 border-2 border-[rgba(250,249,245,0.3)] border-t-[#141413] rounded-full animate-spin" />Loading</>
                                                ) : (
                                                    <>Get Clips <ArrowRight size={15} /></>
                                                )}
                                            </button>
                                        </>
                                    ) : (
                                        <div className="flex items-center justify-between w-full px-2">
                                            <div className="flex items-center gap-3">
                                                <div
                                                    className="w-10 h-10 rounded-full flex items-center justify-center"
                                                    style={{ background: 'rgba(250,249,245,0.05)' }}
                                                >
                                                    <Upload size={16} style={{ color: '#ababab' }} />
                                                </div>
                                                <div>
                                                    <p className="text-sm font-medium" style={{ color: '#faf9f5' }}>
                                                        {isDragging ? 'Release to upload' : 'Drag & Drop your video'}
                                                    </p>
                                                    <p className="text-xs" style={{ color: '#ababab' }}>MP4, MOV, AVI up to 2GB</p>
                                                </div>
                                            </div>
                                            <label
                                                className="px-5 py-3 rounded-xl text-sm font-medium cursor-pointer transition-colors hover:bg-white/10"
                                                style={{ background: 'rgba(250,249,245,0.05)', color: '#faf9f5' }}
                                            >
                                                Browse files
                                                <input
                                                    type="file"
                                                    accept="video/*"
                                                    className="hidden"
                                                    onChange={e => { if (e.target.files?.[0]) handleFileSelect(e.target.files[0]); }}
                                                />
                                            </label>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {youtubeError && (
                                <p className="mt-2 text-xs text-red-400 text-center">{youtubeError}</p>
                            )}

                            {submitError && (
                                <div className="mt-3 p-3 rounded-xl text-red-400 text-sm flex items-center gap-2" style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.2)' }}>
                                    <AlertCircle className="w-4 h-4 flex-shrink-0" />
                                    {submitError}
                                </div>
                            )}

                            <p className="mt-3 text-center text-xs" style={{ color: '#ababab' }}>
                                YouTube • Twitch • Vimeo • Direct Upload
                            </p>
                        </div>
                    )}

                    {/* UPLOADING / DOWNLOADING */}
                    {uploadPhase === 'uploading' && (
                        <div
                            className="rounded-2xl p-10 flex flex-col items-center text-center mx-auto w-full max-w-3xl"
                            style={{ background: '#181817', boxShadow: '0 10px 40px -10px rgba(0,0,0,0.5)' }}
                        >
                            <div
                                className="w-10 h-10 mb-4 rounded-xl flex items-center justify-center"
                                style={{ background: 'rgba(250,249,245,0.05)', border: '1px solid rgba(250,249,245,0.08)' }}
                            >
                                <Upload className="w-5 h-5" style={{ color: '#ababab' }} />
                            </div>
                            <p className="text-sm font-medium mb-1 max-w-sm truncate" style={{ color: '#faf9f5' }}>
                                {file ? file.name : (title || 'YouTube Video')}
                            </p>
                            {file && (
                                <p className="text-xs mb-5" style={{ color: '#ababab' }}>
                                    {(file.size / 1024 / 1024).toFixed(1)} MB
                                </p>
                            )}
                            <div
                                className={`w-64 h-1.5 rounded-full overflow-hidden relative ${file ? 'mb-3' : 'mb-3 mt-5'}`}
                                style={{ background: 'rgba(250,249,245,0.08)' }}
                            >
                                {file ? (
                                    <div
                                        className="absolute top-0 left-0 bottom-0 rounded-full transition-all duration-300"
                                        style={{ width: `${uploadProgress}%`, background: '#faf9f5' }}
                                    />
                                ) : (
                                    <div className="absolute inset-0 overflow-hidden rounded-full">
                                        <div
                                            className="h-full rounded-full animate-pulse"
                                            style={{ width: '60%', background: '#faf9f5', animationDuration: '1.2s' }}
                                        />
                                    </div>
                                )}
                            </div>
                            <p className="text-xs" style={{ color: '#ababab' }}>
                                {file ? `Uploading... ${uploadProgress}%` : 'Downloading YouTube video...'}
                            </p>
                        </div>
                    )}

                    {/* SETTINGS */}
                    {uploadPhase === 'settings' && (
                        <div className="rounded-2xl overflow-hidden" style={{ background: '#181817', boxShadow: '0 10px 40px -10px rgba(0,0,0,0.5)' }}>
                            {/* Panel header */}
                            <div
                                className="flex items-center justify-between px-5 py-3"
                                style={{ borderBottom: '1px solid rgba(250,249,245,0.06)' }}
                            >
                                <div className="flex items-center gap-2 min-w-0">
                                    <span className="text-sm font-medium truncate max-w-xs" style={{ color: '#faf9f5' }}>
                                        {youtubeUrl ? title : file?.name}
                                    </span>
                                    <span className="text-xs flex-shrink-0" style={{ color: '#ababab' }}>
                                        · {formatTimeDisplay(videoDuration)}
                                    </span>
                                </div>
                                <button
                                    onClick={() => { setUploadPhase('idle'); resetUpload(); }}
                                    className="flex-shrink-0 p-1.5 rounded-lg transition-colors hover:bg-white/5"
                                    style={{ color: '#ababab' }}
                                >
                                    <X className="w-4 h-4" />
                                </button>
                            </div>

                            <div className="p-5 grid grid-cols-1 lg:grid-cols-2 gap-5">

                                {/* Left: Video Preview + Timeline */}
                                <div className="space-y-3">
                                    <div
                                        className="aspect-video rounded-xl overflow-hidden"
                                        style={{ background: '#111110', border: '1px solid rgba(250,249,245,0.06)' }}
                                    >
                                        <video
                                            ref={videoRef}
                                            src={videoUrl}
                                            className="w-full h-full object-contain"
                                            controls
                                            muted
                                            controlsList="nodownload nofullscreen"
                                        />
                                    </div>

                                    {/* Timeline trimmer */}
                                    <div
                                        className="rounded-xl p-4"
                                        style={{ background: '#111110', border: '1px solid rgba(250,249,245,0.06)' }}
                                    >
                                        <p
                                            className="text-[9px] uppercase tracking-widest font-medium mb-3"
                                            style={{ color: '#ababab' }}
                                        >
                                            Processing Range
                                        </p>
                                        <div className="flex justify-between text-xs mb-2" style={{ color: '#ababab' }}>
                                            <span>{formatTimeDisplay(startTime)}</span>
                                            <span>{formatTimeDisplay(endTime)}</span>
                                        </div>
                                        <div
                                            ref={timelineRef}
                                            className="relative w-full h-8 rounded-md mb-4 select-none overflow-hidden"
                                            style={{ background: 'rgba(250,249,245,0.06)' }}
                                        >
                                            <div className="absolute top-0 bottom-0 left-0 bg-black/50" style={{ width: `${startPercent}%` }} />
                                            <div className="absolute top-0 bottom-0 right-0 bg-black/50" style={{ width: `${100 - endPercent}%` }} />
                                            <div
                                                className="absolute top-0 bottom-0 bg-white/10 border-y border-white/20"
                                                style={{ left: `${startPercent}%`, right: `${100 - endPercent}%` }}
                                            />
                                            <div
                                                className="absolute top-1/2 -translate-y-1/2 w-1 h-6 rounded-full cursor-ew-resize z-10"
                                                style={{ left: `calc(${startPercent}% - 2px)`, background: '#faf9f5' }}
                                                onMouseDown={e => { e.preventDefault(); setDraggingHandle('start'); }}
                                            />
                                            <div
                                                className="absolute top-1/2 -translate-y-1/2 w-1 h-6 rounded-full cursor-ew-resize z-10"
                                                style={{ left: `calc(${endPercent}% - 2px)`, background: '#faf9f5' }}
                                                onMouseDown={e => { e.preventDefault(); setDraggingHandle('end'); }}
                                            />
                                        </div>
                                        <div className="flex items-center justify-center gap-8">
                                            <TimeGroup time={startTime} isStart={true} />
                                            <button
                                                onClick={() => { setStartTime(0); setEndTime(videoDuration); }}
                                                className="text-[11px] transition-colors mt-1 hover:!text-[#faf9f5]"
                                                style={{ color: '#ababab' }}
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
                                        <label
                                            className="block text-[10px] uppercase tracking-widest mb-1.5"
                                            style={{ color: '#ababab' }}
                                        >
                                            Video Title *
                                        </label>
                                        <input
                                            type="text"
                                            value={title}
                                            onChange={e => setTitle(e.target.value)}
                                            placeholder="e.g. Joe Rogan #2054 – Elon Musk"
                                            className="w-full rounded-xl px-3.5 py-2.5 text-sm outline-none transition-colors"
                                            style={{
                                                background: 'rgba(250,249,245,0.03)',
                                                color: '#faf9f5',
                                                border: '1px solid rgba(250,249,245,0.08)',
                                            }}
                                            autoFocus
                                        />
                                    </div>

                                    {/* Duration Preset */}
                                    <div>
                                        <label
                                            className="block text-[10px] uppercase tracking-widest mb-1.5"
                                            style={{ color: '#ababab' }}
                                        >
                                            Clip Duration
                                        </label>
                                        <div className="flex flex-wrap gap-1.5">
                                            {DURATION_PRESETS.map(p => (
                                                <button
                                                    key={p.label}
                                                    onClick={() => setDurationPreset(p.label)}
                                                    className="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
                                                    style={{
                                                        background: durationPreset === p.label ? '#faf9f5' : 'rgba(250,249,245,0.06)',
                                                        color: durationPreset === p.label ? '#141413' : 'rgba(250,249,245,0.5)',
                                                    }}
                                                >
                                                    {p.label}
                                                </button>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Aspect Ratio */}
                                    <div>
                                        <label
                                            className="block text-[10px] uppercase tracking-widest mb-1.5"
                                            style={{ color: '#ababab' }}
                                        >
                                            Aspect Ratio
                                        </label>
                                        <div className="flex gap-2">
                                            {['9:16', '16:9'].map(ar => (
                                                <button
                                                    key={ar}
                                                    onClick={() => setAspectRatio(ar)}
                                                    className="flex-1 py-2 rounded-xl text-xs font-medium transition-colors"
                                                    style={{
                                                        background: aspectRatio === ar ? '#faf9f5' : 'rgba(250,249,245,0.06)',
                                                        color: aspectRatio === ar ? '#141413' : 'rgba(250,249,245,0.5)',
                                                    }}
                                                >
                                                    {ar} {ar === '9:16' ? '· Vertical' : '· Horizontal'}
                                                </button>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Genre + Guest */}
                                    <div className="grid grid-cols-2 gap-3">
                                        <div>
                                            <label
                                                className="block text-[10px] uppercase tracking-widest mb-1.5"
                                                style={{ color: '#ababab' }}
                                            >
                                                Genre
                                            </label>
                                            <select
                                                value={genre}
                                                onChange={e => setGenre(e.target.value)}
                                                className="w-full rounded-xl px-3 py-2.5 text-sm outline-none transition-colors appearance-none"
                                                style={{
                                                    background: 'rgba(250,249,245,0.03)',
                                                    color: '#faf9f5',
                                                    border: '1px solid rgba(250,249,245,0.08)',
                                                }}
                                            >
                                                <option value="" style={{ background: '#181817' }}>Auto-detect</option>
                                                <option value="podcast" style={{ background: '#181817' }}>Podcast</option>
                                                <option value="interview" style={{ background: '#181817' }}>Interview</option>
                                                <option value="talk_show" style={{ background: '#181817' }}>Talk Show</option>
                                                <option value="tutorial" style={{ background: '#181817' }}>Tutorial</option>
                                                <option value="vlog" style={{ background: '#181817' }}>Vlog</option>
                                                <option value="debate" style={{ background: '#181817' }}>Debate</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label
                                                className="block text-[10px] uppercase tracking-widest mb-1.5"
                                                style={{ color: '#ababab' }}
                                            >
                                                Guest Name
                                            </label>
                                            <input
                                                type="text"
                                                value={guestName}
                                                onChange={e => setGuestName(e.target.value)}
                                                placeholder="Optional"
                                                className="w-full rounded-xl px-3 py-2.5 text-sm outline-none transition-colors"
                                                style={{
                                                    background: 'rgba(250,249,245,0.03)',
                                                    color: '#faf9f5',
                                                    border: '1px solid rgba(250,249,245,0.08)',
                                                }}
                                            />
                                        </div>
                                    </div>

                                    {/* Auto Hook */}
                                    <div className="flex items-center justify-between py-1">
                                        <div>
                                            <p className="text-sm" style={{ color: '#faf9f5' }}>Auto Hook</p>
                                            <p className="text-xs" style={{ color: '#ababab' }}>Optimize for the first 3 seconds</p>
                                        </div>
                                        <button
                                            onClick={() => setAutoHook(v => !v)}
                                            className="relative rounded-full transition-all flex-shrink-0"
                                            style={{
                                                height: '22px',
                                                width: '40px',
                                                background: autoHook ? '#faf9f5' : 'rgba(250,249,245,0.08)',
                                                transition: 'all 0.3s ease',
                                            }}
                                        >
                                            <span
                                                className="absolute top-0.5 w-4 h-4 rounded-full"
                                                style={{
                                                    background: autoHook ? '#141413' : 'rgba(250,249,245,0.4)',
                                                    left: autoHook ? 'calc(100% - 20px)' : '4px',
                                                    transition: 'all 0.3s ease',
                                                }}
                                            />
                                        </button>
                                    </div>

                                    {/* Channel */}
                                    {channels.length > 1 && (
                                        <div>
                                            <label
                                                className="block text-[10px] uppercase tracking-widest mb-1.5"
                                                style={{ color: '#ababab' }}
                                            >
                                                Channel
                                            </label>
                                            <select
                                                value={formChannelId}
                                                onChange={e => setFormChannelId(e.target.value)}
                                                className="w-full rounded-xl px-3 py-2.5 text-sm outline-none transition-colors appearance-none"
                                                style={{
                                                    background: 'rgba(250,249,245,0.03)',
                                                    color: '#faf9f5',
                                                    border: '1px solid rgba(250,249,245,0.08)',
                                                }}
                                            >
                                                {channels.map(c => (
                                                    <option key={c.id} value={c.id} style={{ background: '#181817' }}>
                                                        {c.display_name || c.id}
                                                    </option>
                                                ))}
                                            </select>
                                        </div>
                                    )}

                                    {submitError && (
                                        <div
                                            className="p-3 rounded-xl text-red-400 text-xs flex items-center gap-2"
                                            style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.2)' }}
                                        >
                                            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                                            {submitError}
                                        </div>
                                    )}

                                    {/* Submit */}
                                    <button
                                        onClick={handleStartProcessing}
                                        disabled={!title || (!uploadId && !youtubeUrl)}
                                        className="w-full py-3 rounded-xl text-sm font-semibold transition-all"
                                        style={{
                                            background: title && (uploadId || youtubeUrl) ? '#faf9f5' : 'rgba(250,249,245,0.05)',
                                            color: title && (uploadId || youtubeUrl) ? '#141413' : 'rgba(250,249,245,0.25)',
                                            cursor: title && (uploadId || youtubeUrl) ? 'pointer' : 'not-allowed',
                                        }}
                                    >
                                        Start Processing
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* PROCESSING */}
                    {uploadPhase === 'processing' && (
                        <div
                            className="rounded-2xl p-8 flex flex-col items-center text-center mx-auto w-full max-w-3xl"
                            style={{ background: '#181817', boxShadow: '0 10px 40px -10px rgba(0,0,0,0.5)' }}
                        >
                            <div className="flex items-center gap-2 mb-4">
                                <div className="w-2 h-2 rounded-full pulse-dot" style={{ background: '#faf9f5' }} />
                                <span className="text-xs uppercase tracking-wider" style={{ color: '#ababab' }}>Processing</span>
                            </div>
                            <div
                                className="w-10 h-10 rounded-full border-2 animate-spin mb-5"
                                style={{ borderColor: 'rgba(250,249,245,0.12)', borderTopColor: '#faf9f5' }}
                            />
                            <p className="text-base font-medium mb-1" style={{ color: '#faf9f5' }}>{title}</p>
                            <p className="text-sm" style={{ color: '#ababab' }}>{statusMsg || 'Starting pipeline...'}</p>
                        </div>
                    )}
                </div>

                {/* ── Caption Template Carousel ── */}
                {uploadPhase === 'settings' && (
                    <>
                        {/*
                          Word-by-word caption loop: 4 words in a 3.2s infinite cycle.
                          Each word is absolutely centered; only one is visible at a time.
                          This simulates real short-form caption rendering (one word flashes
                          in, holds, then disappears — exactly like CapCut/Opus/Submagic output).
                          All transforms include translate(-50%,-50%) for centering so there
                          is no conflict with position math.
                        */}
                        <style>{`
                            /* Word 1 "Clip/CLIP": 0–25% of cycle */
                            @keyframes ct-w1 {
                                0%        { opacity: 0; transform: translate(-50%,-50%) scale(0.88); }
                                3%        { opacity: 1; transform: translate(-50%,-50%) scale(1); }
                                22%       { opacity: 1; transform: translate(-50%,-50%) scale(1); }
                                25%, 100% { opacity: 0; transform: translate(-50%,-50%) scale(1); }
                            }
                            /* Word 2 "it/IT": 25–50% */
                            @keyframes ct-w2 {
                                0%, 25%   { opacity: 0; transform: translate(-50%,-50%) scale(0.88); }
                                28%       { opacity: 1; transform: translate(-50%,-50%) scale(1); }
                                47%       { opacity: 1; transform: translate(-50%,-50%) scale(1); }
                                50%, 100% { opacity: 0; transform: translate(-50%,-50%) scale(1); }
                            }
                            /* Word 3 "with/WITH": 50–75% */
                            @keyframes ct-w3 {
                                0%, 50%   { opacity: 0; transform: translate(-50%,-50%) scale(0.88); }
                                53%       { opacity: 1; transform: translate(-50%,-50%) scale(1); }
                                72%       { opacity: 1; transform: translate(-50%,-50%) scale(1); }
                                75%, 100% { opacity: 0; transform: translate(-50%,-50%) scale(1); }
                            }
                            /* Word 4 "Prognot/PROGNOT": 75–100% */
                            @keyframes ct-w4 {
                                0%, 75%   { opacity: 0; transform: translate(-50%,-50%) scale(0.88); }
                                78%       { opacity: 1; transform: translate(-50%,-50%) scale(1); }
                                97%       { opacity: 1; transform: translate(-50%,-50%) scale(1); }
                                100%      { opacity: 0; transform: translate(-50%,-50%) scale(1); }
                            }
                        `}</style>

                        <div>
                            <div className="flex items-center justify-between mb-4">
                                <p className="text-[10px] uppercase tracking-widest" style={{ color: '#ababab' }}>
                                    Caption Template
                                </p>
                                <p className="text-xs font-medium" style={{ color: '#ababab' }}>
                                    {CAPTION_TEMPLATES[captionTemplateIdx].label}
                                </p>
                            </div>

                            <div className="flex items-center gap-2">
                                {/* Left arrow */}
                                <button
                                    onClick={() => setWindowStart(w => Math.max(0, w - 1))}
                                    disabled={windowStart === 0}
                                    className="flex-shrink-0 flex items-center justify-center rounded-full transition-colors duration-150"
                                    style={{
                                        width: 26, height: 26,
                                        background: 'rgba(250,249,245,0.05)',
                                        border: '1px solid rgba(250,249,245,0.08)',
                                        color: windowStart === 0 ? 'rgba(250,249,245,0.12)' : 'rgba(250,249,245,0.6)',
                                        cursor: windowStart === 0 ? 'default' : 'pointer',
                                    }}
                                >
                                    <svg width="7" height="12" viewBox="0 0 7 12" fill="none">
                                        <path d="M5.5 1L1 6L5.5 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                                    </svg>
                                </button>

                                {/* Cards container — dynamic fade mask: left edge fades only when not at start */}
                                <div
                                    className="flex-1 overflow-hidden"
                                    style={{
                                        WebkitMaskImage: windowStart === 0
                                            ? 'linear-gradient(to right, black 0%, black 84%, transparent 100%)'
                                            : windowStart >= CAPTION_TEMPLATES.length - 5
                                                ? 'linear-gradient(to right, transparent 0%, black 16%, black 100%)'
                                                : 'linear-gradient(to right, transparent 0%, black 12%, black 88%, transparent 100%)',
                                        maskImage: windowStart === 0
                                            ? 'linear-gradient(to right, black 0%, black 84%, transparent 100%)'
                                            : windowStart >= CAPTION_TEMPLATES.length - 5
                                                ? 'linear-gradient(to right, transparent 0%, black 16%, black 100%)'
                                                : 'linear-gradient(to right, transparent 0%, black 12%, black 88%, transparent 100%)',
                                    }}
                                >
                                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 12 }}>
                                        {CAPTION_TEMPLATES.slice(windowStart, windowStart + 5).map((tpl, posIdx) => {
                                            const tplIdx = windowStart + posIdx;
                                            const isActive = tplIdx === captionTemplateIdx;
                                            const isHovered = tplIdx === hoveredIdx;

                                            // Words to cycle through. Uppercase templates get uppercased via textStyle.
                                            const cycleWords = ['Clip', 'it', 'with', 'Prognot'];
                                            const ANIM_DURATION = '3.2s';

                                            return (
                                                <button
                                                    key={tpl.key}
                                                    onClick={() => setCaptionTemplateIdx(tplIdx)}
                                                    onMouseEnter={() => handleCardHover(tplIdx)}
                                                    onMouseLeave={handleCardLeave}
                                                    className="relative w-full rounded-xl overflow-hidden transition-colors duration-150"
                                                    style={{
                                                        aspectRatio: '16/10',
                                                        background: '#454746',
                                                        border: isActive
                                                            ? '2px solid #ffffff'
                                                            : isHovered
                                                                ? '2px solid rgba(255,255,255,0.28)'
                                                                : '2px solid transparent',
                                                        outline: 'none',
                                                    }}
                                                >
                                                    {/* Template label — top left */}
                                                    <span
                                                        className="absolute top-2 left-0 right-0 text-center text-[9px] font-semibold uppercase tracking-widest pointer-events-none"
                                                        style={{ color: isActive ? 'rgba(250,249,245,0.8)' : 'rgba(250,249,245,0.3)' }}
                                                    >
                                                        {tpl.label}
                                                    </span>

                                                    {/*
                                                      Caption preview area.
                                                      Default: static "Clip it with Prognot" split on two lines.
                                                      Hover: word-by-word CSS loop — one word visible at a time,
                                                             centered with position:absolute, simulating real caption playback.
                                                    */}
                                                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none" style={{ top: 20 }}>

                                                        {!isHovered ? (
                                                            /* STATIC PREVIEW: full text always visible */
                                                            <div className="flex flex-col items-center gap-0.5 px-3">
                                                                <span
                                                                    className="text-center leading-tight"
                                                                    style={{ ...tpl.textStyle, display: 'block' }}
                                                                >
                                                                    Clip it
                                                                </span>
                                                                <span
                                                                    className="text-center leading-tight"
                                                                    style={{ ...tpl.textStyle, display: 'block' }}
                                                                >
                                                                    with Prognot
                                                                </span>
                                                            </div>
                                                        ) : (
                                                            /*
                                                              ANIMATED PREVIEW: word-by-word loop.
                                                              Each span is position:absolute, centered via
                                                              top:50% left:50% + translate(-50%,-50%) baked
                                                              into the @keyframes so no extra transform needed here.
                                                              Only one word is opaque at any time.
                                                            */
                                                            <div className="relative w-full" style={{ height: 48 }}>
                                                                {cycleWords.map((word, i) => (
                                                                    <span
                                                                        key={word}
                                                                        style={{
                                                                            ...tpl.textStyle,
                                                                            position: 'absolute',
                                                                            top: '50%',
                                                                            left: '50%',
                                                                            whiteSpace: 'nowrap',
                                                                            opacity: 0,
                                                                            animation: `ct-w${i + 1} ${ANIM_DURATION} ease-in-out infinite`,
                                                                        }}
                                                                    >
                                                                        {word}
                                                                    </span>
                                                                ))}
                                                            </div>
                                                        )}
                                                    </div>
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>

                                {/* Right arrow */}
                                <button
                                    onClick={() => setWindowStart(w => Math.min(CAPTION_TEMPLATES.length - 5, w + 1))}
                                    disabled={windowStart >= CAPTION_TEMPLATES.length - 5}
                                    className="flex-shrink-0 flex items-center justify-center rounded-full transition-colors duration-150"
                                    style={{
                                        width: 26, height: 26,
                                        background: 'rgba(250,249,245,0.05)',
                                        border: '1px solid rgba(250,249,245,0.08)',
                                        color: windowStart >= CAPTION_TEMPLATES.length - 5 ? 'rgba(250,249,245,0.12)' : 'rgba(250,249,245,0.6)',
                                        cursor: windowStart >= CAPTION_TEMPLATES.length - 5 ? 'default' : 'pointer',
                                    }}
                                >
                                    <svg width="7" height="12" viewBox="0 0 7 12" fill="none">
                                        <path d="M1.5 1L6 6L1.5 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </>
                )}

                                {/* ── Active Jobs ── */}
                {activeJobs.length > 0 && (
                    <div>
                        <div className="flex items-center gap-2 mb-4">
                            <h2 className="text-base font-medium" style={{ color: '#faf9f5' }}>Active Jobs</h2>
                            <span className="w-2 h-2 rounded-full pulse-dot" style={{ background: '#faf9f5' }} />
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {activeJobs.map((job) => {
                                const progress = job.progress_pct ?? job.progress ?? 0;
                                return (
                                    <div
                                        key={job.id}
                                        className="rounded-2xl overflow-hidden"
                                        style={{ background: '#181817' }}
                                    >
                                        <div
                                            className="aspect-video flex items-center justify-center p-6"
                                            style={{ background: '#1c1c1b' }}
                                        >
                                            <div className="text-center">
                                                <div className="flex items-center justify-center gap-2 mb-3">
                                                    <div className="w-2 h-2 rounded-full pulse-dot" style={{ background: '#faf9f5' }} />
                                                    <span className="text-xs uppercase tracking-wider" style={{ color: '#ababab' }}>Processing</span>
                                                </div>
                                                <p className="text-sm" style={{ color: '#faf9f5' }}>
                                                    {getStepLabel(job.current_step || job.step)}
                                                    {progress > 0 && (
                                                        <span className="ml-2" style={{ color: '#ababab' }}>({progress}%)</span>
                                                    )}
                                                </p>
                                            </div>
                                        </div>
                                        <div className="p-4" style={{ borderTop: '1px solid rgba(250,249,245,0.06)' }}>
                                            <div className="flex items-center justify-between">
                                                <p className="text-xs font-medium truncate" style={{ color: '#faf9f5' }}>
                                                    {job.video_title || "Untitled"}
                                                </p>
                                                <span className="text-xs" style={{ color: '#ababab' }}>
                                                    {formatDate(job.created_at)}
                                                </span>
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
                            <h2 className="text-base font-medium" style={{ color: '#faf9f5' }}>Powered by AI</h2>
                            <p className="text-xs mt-0.5" style={{ color: '#ababab' }}>Unique features that set us apart</p>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            {features.map((feature) => (
                                <Link
                                    key={feature.name}
                                    href={feature.href}
                                    className="group rounded-2xl p-5 transition-all duration-300 hover:-translate-y-1"
                                    style={{ background: '#181817' }}
                                >
                                    <div
                                        className="w-10 h-10 mb-3 rounded-xl flex items-center justify-center transition-colors"
                                        style={{ background: 'rgba(250,249,245,0.06)' }}
                                    >
                                        <feature.icon className="w-5 h-5" style={{ color: '#faf9f5' }} />
                                    </div>
                                    <h3
                                        className="text-sm font-medium mb-1.5 flex items-center justify-between"
                                        style={{ color: '#faf9f5' }}
                                    >
                                        {feature.name}
                                        <ArrowRight
                                            className="w-3.5 h-3.5 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all"
                                            style={{ color: '#ababab' }}
                                        />
                                    </h3>
                                    <p className="text-xs leading-relaxed" style={{ color: '#ababab' }}>
                                        {feature.description}
                                    </p>
                                </Link>
                            ))}
                        </div>
                    </div>
                )}

                {/* ── Recent Projects ── */}
                <div>
                    <div className="flex items-center justify-between mb-6">
                        <h2 className="text-lg font-medium" style={{ color: '#faf9f5' }}>Recent Projects</h2>
                        <Link
                            href="/dashboard/projects"
                            className="text-sm flex items-center gap-1 transition-colors hover:!text-[#faf9f5]"
                            style={{ color: '#ababab' }}
                        >
                            View all <ArrowRight size={14} />
                        </Link>
                    </div>

                    {loading ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                            {[...Array(4)].map((_, i) => (
                                <div key={i} className="rounded-2xl overflow-hidden" style={{ background: '#181817' }}>
                                    <div className="aspect-video animate-pulse" style={{ background: 'rgba(250,249,245,0.04)' }} />
                                    <div className="p-4 space-y-2">
                                        <div className="h-3 rounded w-3/4 animate-pulse" style={{ background: 'rgba(250,249,245,0.06)' }} />
                                        <div className="h-2 rounded w-1/2 animate-pulse" style={{ background: 'rgba(250,249,245,0.04)' }} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : recentJobs.length === 0 ? (
                        <div
                            className="rounded-2xl p-12 text-center"
                            style={{ background: '#181817' }}
                        >
                            <p className="text-sm" style={{ color: '#ababab' }}>
                                No projects yet. Upload your first video to get started.
                            </p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                            {recentJobs.map((job) => (
                                <Link
                                    key={job.id}
                                    href="/dashboard/projects"
                                    className="group rounded-2xl overflow-hidden cursor-pointer hover:-translate-y-1 transition-all duration-300"
                                    style={{ background: '#181817' }}
                                >
                                    {/* Thumbnail */}
                                    <div
                                        className="relative aspect-video flex items-center justify-center"
                                        style={{ background: '#1c1c1b' }}
                                    >
                                        <Play
                                            size={20}
                                            style={{ color: 'rgba(250,249,245,0.15)' }}
                                            className="group-hover:opacity-60 transition-opacity"
                                        />
                                        {/* Status badge */}
                                        <div className="absolute top-2.5 left-2.5">
                                            {(job.status === 'completed' || job.status === 'done') && (
                                                <div
                                                    className="text-[10px] font-medium px-2 py-0.5 rounded-lg flex items-center gap-1.5"
                                                    style={{ background: 'rgba(34,197,94,0.15)', color: '#4ade80' }}
                                                >
                                                    <div className="w-1.5 h-1.5 rounded-full bg-[#4ade80]" />
                                                    Done
                                                </div>
                                            )}
                                            {job.status === 'failed' && (
                                                <div
                                                    className="text-[10px] font-medium px-2 py-0.5 rounded-lg flex items-center gap-1.5"
                                                    style={{ background: 'rgba(239,68,68,0.15)', color: '#f87171' }}
                                                >
                                                    <div className="w-1.5 h-1.5 rounded-full bg-[#f87171]" />
                                                    Failed
                                                </div>
                                            )}
                                        </div>
                                        {/* More button */}
                                        <button
                                            className="absolute top-2.5 right-2.5 w-7 h-7 rounded-lg flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                                            style={{ background: 'rgba(0,0,0,0.6)', color: '#ababab' }}
                                            onClick={e => e.preventDefault()}
                                        >
                                            <MoreVertical size={14} />
                                        </button>
                                    </div>
                                    {/* Info */}
                                    <div className="p-4">
                                        <p
                                            className="text-sm font-medium truncate mb-2"
                                            style={{ color: '#faf9f5' }}
                                        >
                                            {job.video_title || "Untitled"}
                                        </p>
                                        <p className="text-xs" style={{ color: '#ababab' }}>
                                            {formatDate(job.created_at)}
                                        </p>
                                    </div>
                                </Link>
                            ))}
                        </div>
                    )}
                </div>

            </div>
        </div>
    );
}
