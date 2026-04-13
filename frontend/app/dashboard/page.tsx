"use client";

import { useState, useEffect, useRef } from "react";
import { Upload, Play, MoreVertical, Dna, Clapperboard, Search, ArrowRight, Link2, Sparkles, X, Scissors, BarChart3, Calendar, ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useChannel } from "./layout";
import { authFetch, API_URL } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { toast } from "@/lib/toast";

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

type Clip = {
    id: string;
    job_id: string;
    file_url: string | null;
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

type FeatureCard = {
    icon: React.ElementType;
    name: string;
    description: string;
    href: string | null;
    gradient: string;
    external?: boolean;
};

const allFeatures: FeatureCard[] = [
    {
        icon: Dna,
        name: "Channel DNA",
        description: "Train the AI on your channel's unique style and voice",
        href: "/dashboard/channel-dna",
        gradient: "linear-gradient(135deg, #f59e0b, #b45309)",
    },
    {
        icon: Search,
        name: "Content Finder",
        description: "Discover viral moments across your long-form content",
        href: "/dashboard/content-finder",
        gradient: "linear-gradient(135deg, #3b82f6, #1d4ed8)",
    },
    {
        icon: Clapperboard,
        name: "AI Director",
        description: "Intelligent recommendations based on your performance data",
        href: "/director",
        gradient: "linear-gradient(135deg, #22c55e, #15803d)",
    },
    {
        icon: Scissors,
        name: "Editor",
        description: "Edit and fine-tune your clips in a powerful online editor",
        href: "https://edit.prognot.com",
        gradient: "linear-gradient(135deg, #a855f7, #7c3aed)",
        external: true,
    },
    {
        icon: BarChart3,
        name: "Analytics",
        description: "Track performance metrics and optimize your content strategy",
        href: "/dashboard/performance",
        gradient: "linear-gradient(135deg, #f97316, #c2410c)",
    },
    {
        icon: Calendar,
        name: "Calendar",
        description: "Plan and schedule your content releases ahead of time",
        href: null,
        gradient: "linear-gradient(135deg, #ec4899, #be185d)",
    },
];

const BALLOON_WORDS = ['Podcast', 'Gaming', 'Interview', 'Vlog', 'Tutorial', 'Shorts', 'Stream', 'Highlight', 'Recap', 'Review'];

interface Balloon {
    id: number;
    word: string;
    side: 'left' | 'right';
    size: number;
    arcX: number;
    arcY: number;
    duration: number;
    wobbleDur: number;
    jitter: number;
}

function GlassBubbles() {
    const [balloons, setBalloons] = useState<Balloon[]>([]);
    const idRef = useRef(0);
    const sideRef = useRef<'left' | 'right'>('left');

    useEffect(() => {
        let active = true;
        let tid: ReturnType<typeof setTimeout>;

        const spawn = () => {
            if (!active) return;
            setBalloons(prev => {
                if (prev.length >= 3) return prev;
                const side = sideRef.current;
                sideRef.current = side === 'left' ? 'right' : 'left';
                // arcX capped at 130px — safe on all screen sizes, bubble stays within page
                const arcMag = 80 + Math.random() * 50;
                return [...prev, {
                    id: idRef.current++,
                    word: BALLOON_WORDS[Math.floor(Math.random() * BALLOON_WORDS.length)],
                    side,
                    size: 50 + Math.floor(Math.random() * 21),
                    arcX: side === 'left' ? -arcMag : arcMag,
                    arcY: -(260 + Math.random() * 100),
                    duration: 4 + Math.random() * 1.5,
                    wobbleDur: 0.9 + Math.random() * 0.6,
                    jitter: Math.random() * 30 - 15,
                }];
            });
            tid = setTimeout(spawn, 4000 + Math.random() * 1000);
        };

        tid = setTimeout(spawn, 500);
        return () => { active = false; clearTimeout(tid); };
    }, []);

    const remove = (id: number) => setBalloons(prev => prev.filter(b => b.id !== id));

    return (
        <>
            {balloons.map(b => {
                const kf = `bbl-${b.id}`;
                const x = (t: number) => (b.arcX * Math.pow(t, 1.8)).toFixed(1);
                const y = (t: number) => (b.arcY * t).toFixed(1);
                const s = (t: number) => (1 - t * 0.45).toFixed(2);
                const o = (t: number) => Math.max(0, 1 - t * 1.15).toFixed(2);
                return (
                    <div key={b.id}>
                        <style>{`
                            @keyframes ${kf} {
                                0%   { transform: translate(0px, 0px) scale(1); opacity: 0; }
                                6%   { opacity: 0.92; }
                                25%  { transform: translate(${x(0.25)}px, ${y(0.25)}px) scale(${s(0.25)}); opacity: ${o(0.25)}; }
                                50%  { transform: translate(${x(0.5)}px, ${y(0.5)}px) scale(${s(0.5)}); opacity: ${o(0.5)}; }
                                75%  { transform: translate(${x(0.75)}px, ${y(0.75)}px) scale(${s(0.75)}); opacity: ${o(0.75)}; }
                                100% { transform: translate(${x(1)}px, ${y(1)}px) scale(${s(1)}); opacity: 0; }
                            }
                        `}</style>
                        <div
                            className="pointer-events-none select-none"
                            style={{
                                position: 'absolute',
                                ...(b.side === 'left'
                                    ? { left: `${60 + b.jitter}px` }
                                    : { right: `${60 + b.jitter}px` }),
                                top: '40%',
                                width: b.size,
                                height: b.size,
                                zIndex: 5,
                                animation: `${kf} ${b.duration}s linear forwards`,
                            }}
                            onAnimationEnd={() => remove(b.id)}
                        >
                            {/* Wobble layer */}
                            <div style={{
                                width: '100%',
                                height: '100%',
                                animation: `bubble-wobble ${b.wobbleDur}s ease-in-out infinite`,
                            }}>
                                {/* Balloon sphere */}
                                <div style={{
                                    position: 'relative',
                                    width: '100%',
                                    height: '100%',
                                    borderRadius: '50%',
                                    background: [
                                        'radial-gradient(circle at 30% 25%, rgba(255,255,255,0.35) 0%, rgba(255,255,255,0.08) 40%, transparent 70%)',
                                        'radial-gradient(circle at 55% 55%, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.02) 60%, transparent 100%)',
                                        'radial-gradient(ellipse at 50% 80%, rgba(255,255,255,0.08) 0%, transparent 50%)',
                                        'linear-gradient(160deg, rgba(255,255,255,0.12) 0%, rgba(255,255,255,0.02) 50%, rgba(0,0,0,0.05) 100%)',
                                    ].join(', '),
                                    boxShadow: [
                                        'inset 0 -4px 8px rgba(255,255,255,0.06)',
                                        'inset 0 2px 4px rgba(255,255,255,0.25)',
                                        '0 4px 16px rgba(0,0,0,0.25)',
                                        '0 0 12px rgba(255,255,255,0.04)',
                                    ].join(', '),
                                    border: '1px solid rgba(255,255,255,0.1)',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    overflow: 'hidden',
                                }}>
                                    {/* Primary specular highlight */}
                                    <div style={{
                                        position: 'absolute',
                                        top: '12%',
                                        left: '16%',
                                        width: '35%',
                                        height: '28%',
                                        borderRadius: '50%',
                                        background: 'radial-gradient(circle, rgba(255,255,255,0.7) 0%, rgba(255,255,255,0.2) 50%, transparent 100%)',
                                        filter: 'blur(1px)',
                                        transform: 'rotate(-20deg)',
                                    }} />
                                    {/* Secondary highlight */}
                                    <div style={{
                                        position: 'absolute',
                                        top: '22%',
                                        right: '18%',
                                        width: '12%',
                                        height: '10%',
                                        borderRadius: '50%',
                                        background: 'rgba(255,255,255,0.35)',
                                        filter: 'blur(0.5px)',
                                    }} />
                                    {/* Word label */}
                                    <span style={{
                                        fontSize: '9px',
                                        fontWeight: 600,
                                        color: 'rgba(255,255,255,0.8)',
                                        textAlign: 'center',
                                        lineHeight: 1,
                                        letterSpacing: '0.02em',
                                        textShadow: '0 1px 3px rgba(0,0,0,0.4)',
                                        zIndex: 1,
                                    }}>{b.word}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                );
            })}
        </>
    );
}

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
            <div className="px-8 py-10 space-y-12">
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
    const [clips, setClips] = useState<Clip[]>([]);
    const [loading, setLoading] = useState(true);
    const [openMenuId, setOpenMenuId] = useState<string | null>(null);
    const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

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

    // Processing state
    const [statusMsg, setStatusMsg] = useState('');

    const fileInputRef = useRef<HTMLInputElement>(null);
    const videoRef = useRef<HTMLVideoElement>(null);
    const timelineRef = useRef<HTMLDivElement>(null);
    const featureCarouselRef = useRef<HTMLDivElement>(null);
    const urlInputRef = useRef<HTMLInputElement>(null);
    const uploadBoxRef = useRef<HTMLDivElement>(null);
    const [inputFocused, setInputFocused] = useState(false);
    const [uploadAreaHovered, setUploadAreaHovered] = useState(false);

    // Feature carousel state
    const [featuresHovered, setFeaturesHovered] = useState(false);
    const [featureCanScrollLeft, setFeatureCanScrollLeft] = useState(false);
    const [featureCanScrollRight, setFeatureCanScrollRight] = useState(true);

    const updateFeatureScroll = () => {
        const el = featureCarouselRef.current;
        if (!el) return;
        setFeatureCanScrollLeft(el.scrollLeft > 2);
        setFeatureCanScrollRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 2);
    };

    const scrollFeatures = (dir: 'left' | 'right') => {
        const el = featureCarouselRef.current;
        if (!el) return;
        el.scrollBy({ left: dir === 'right' ? 296 : -296, behavior: 'smooth' });
    };

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
        Promise.all([
            authFetch(`/jobs?channel_id=${activeChannelId}&limit=20`).then(r => r.ok ? r.json() : []),
            authFetch(`/clips?channel_id=${activeChannelId}&limit=200`).then(r => r.ok ? r.json() : []),
        ])
            .then(([jobsData, clipsData]) => { setJobs(jobsData); setClips(clipsData); })
            .catch(console.error)
            .finally(() => setLoading(false));
    }, [activeChannelId, channelLoading]);

    const handleDeleteJob = async (jobId: string) => {
        try {
            const res = await authFetch(`/jobs/${jobId}`, { method: 'DELETE' });
            if (res.ok) {
                setJobs(prev => prev.filter(j => j.id !== jobId));
                toast.success('Project deleted.');
            } else {
                toast.error('Failed to delete project.');
            }
        } catch { toast.error('Failed to delete project.'); }
        setDeleteConfirmId(null);
    };

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
        setStatusMsg('');
        setYoutubeUrl('');
        setYoutubeFetching(false);
        setFormChannelId(activeChannelId);
        setUploadTab('link');
        setCaptionTemplateIdx(0);
        setWindowStart(0);
        setHoveredIdx(null);
    };

    const handleYoutubeUrl = async (url: string) => {
        const isValid = url.includes('youtube.com/watch') || url.includes('youtu.be/') || url.includes('youtube.com/shorts/');
        if (!isValid) { toast.error('Please enter a valid YouTube URL'); return; }
        setYoutubeFetching(true);

        let channelId = formChannelId || activeChannelId;
        if (!channelId) {
            try { channelId = await autoCreateChannel(); setFormChannelId(channelId); }
            catch { toast.error('Failed to create channel. Please create one in Settings first.'); setYoutubeFetching(false); return; }
        }

        // Step 1: fetch title quickly via oEmbed (no download)
        try {
            const infoRes = await authFetch(`/jobs/youtube-info?url=${encodeURIComponent(url)}`);
            if (!infoRes.ok) { toast.error('Could not fetch video info. Check the URL and try again.'); setYoutubeFetching(false); return; }
            const info = await infoRes.json();
            setTitle(info.title || '');
        } catch {
            toast.error('Could not fetch video info. Check the URL and try again.');
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
                toast.error('Could not download video. Please try again.');
                setUploadPhase('idle');
            }
        };
        xhr.onerror = () => {
            toast.error('Network error downloading video. Please try again.');
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
            toast.error('Unsupported file format. Use MP4, MOV, AVI, MKV, or WEBM.');
            return;
        }

        setFile(selectedFile);
        setUploadPhase('uploading');
        setUploadProgress(0);

        // Auto-create channel if none exists
        let channelId = formChannelId || activeChannelId;
        if (!channelId) {
            try {
                channelId = await autoCreateChannel();
                setFormChannelId(channelId);
            } catch {
                toast.error('Failed to create a channel. Please create one in Settings first.');
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
                toast.error('Upload failed. Please try again.');
                setUploadPhase('idle');
                setFile(null);
                URL.revokeObjectURL(url);
                setVideoUrl('');
            }
        };
        xhr.onerror = () => {
            toast.error('Network error during upload. Please try again.');
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
                toast.error(err.detail || 'Failed to start processing');
                setUploadPhase('settings');
                return;
            }
            const job = await res.json();
            const jobId = job?.id || job?.job_id;
            if (!jobId) {
                toast.error('No job ID returned');
                setUploadPhase('settings');
                return;
            }

            // Add job to list immediately so it shows in Active Jobs, then reset UI
            setJobs(prev => [{ id: jobId, video_title: title, status: 'processing', created_at: new Date().toISOString() }, ...prev]);
            toast.success('Job started! Processing in the background.');
            setUploadPhase('idle');
            resetUpload();
        } catch (err: any) {
            toast.error(err.message || 'Failed to start processing.');
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
            <div className="px-8 py-10 space-y-12">

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
                <div className="w-full">

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

                            {/* Bubble + card wrapper — position:relative creates stacking context for z-index layering */}
                            <div
                                ref={uploadBoxRef}
                                style={{
                                    position: 'relative',
                                    zIndex: 0,
                                    width: (uploadTab === 'file' || uploadAreaHovered || inputFocused || !!youtubeUrl) ? '100%' : '70%',
                                    margin: '0 auto',
                                    transition: 'width 400ms cubic-bezier(0.34, 1.56, 0.64, 1)',
                                }}
                            >
                            {/* Bubbles — z-index: -1, behind the card */}
                            <GlassBubbles />

                            {/* Outer card */}
                            <div
                                className="p-3 relative overflow-hidden"
                                style={{
                                    background: '#181817',
                                    borderRadius: '24px',
                                    boxShadow: '0 10px 40px -10px rgba(0,0,0,0.5)',
                                    width: '100%',
                                    zIndex: 10,
                                    position: 'relative',
                                }}
                                onMouseEnter={() => setUploadAreaHovered(true)}
                                onMouseLeave={() => setUploadAreaHovered(false)}
                                onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
                                onDragLeave={e => {
                                    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
                                        setIsDragging(false);
                                    }
                                }}
                                onDrop={e => {
                                    e.preventDefault();
                                    setIsDragging(false);
                                    if (e.dataTransfer.files?.[0]) handleFileSelect(e.dataTransfer.files[0]);
                                }}
                            >
                                {/* Drag overlay — shown regardless of active tab */}
                                {isDragging && (
                                    <div
                                        className="absolute inset-0 z-10 flex items-center justify-center"
                                        style={{
                                            background: 'rgba(20,20,19,0.9)',
                                            borderRadius: '21px',
                                            border: '2px dashed rgba(250,249,245,0.25)',
                                        }}
                                    >
                                        <div className="text-center pointer-events-none">
                                            <Upload className="w-8 h-8 mx-auto mb-3" style={{ color: '#faf9f5' }} />
                                            <p className="text-sm font-medium" style={{ color: '#faf9f5' }}>Drop your file here</p>
                                        </div>
                                    </div>
                                )}

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

                                {/* Input area — Dynamic Island: synced with outer card width */}
                                <div
                                    className={`flex items-center justify-between p-2 pl-4 min-h-[72px] ${uploadTab === 'file' ? 'cursor-pointer' : ''}`}
                                    style={{
                                        background: '#131312',
                                        borderRadius: '18px',
                                        border: '1px solid rgba(250,249,245,0.03)',
                                        width: '100%',
                                    }}
                                    onClick={() => {
                                        if (uploadTab === 'file') fileInputRef.current?.click();
                                        if (uploadTab === 'link') urlInputRef.current?.focus();
                                    }}
                                >
                                    {uploadTab === 'link' ? (
                                        <>
                                            <div className="flex items-center gap-3 flex-1 px-2">
                                                <Link2 size={16} style={{ color: '#ababab' }} />
                                                <input
                                                    ref={urlInputRef}
                                                    type="text"
                                                    value={youtubeUrl}
                                                    onChange={e => { setYoutubeUrl(e.target.value); }}
                                                    onKeyDown={e => { if (e.key === 'Enter' && youtubeUrl) handleYoutubeUrl(youtubeUrl); }}
                                                    onFocus={() => setInputFocused(true)}
                                                    onBlur={() => { if (!youtubeUrl) setInputFocused(false); }}
                                                    placeholder="Paste a YouTube, Twitch or Vimeo URL..."
                                                    className="w-full text-sm outline-none h-full"
                                                    style={{
                                                        background: 'transparent',
                                                        color: '#faf9f5',
                                                    }}
                                                />
                                            </div>
                                            {/* Snake-border wrapper — scale(1.1) + rotating gradient border when URL present */}
                                            <div
                                                className="relative flex-shrink-0 ml-2 overflow-hidden"
                                                style={{
                                                    borderRadius: '14px',
                                                    padding: youtubeUrl ? '2px' : '0',
                                                    transition: 'padding 0.2s ease',
                                                }}
                                            >
                                                {/* Spinning conic-gradient — large so rotation looks smooth */}
                                                {youtubeUrl && (
                                                    <div
                                                        className="absolute pointer-events-none"
                                                        style={{
                                                            width: '200%',
                                                            height: '200%',
                                                            top: '-50%',
                                                            left: '-50%',
                                                            background: 'conic-gradient(from 0deg, transparent 0deg, transparent 195deg, #3b0764 210deg, #6d28d9 245deg, #8b5cf6 268deg, #a78bfa 280deg, #8b5cf6 295deg, #6d28d9 318deg, transparent 338deg, transparent 360deg)',
                                                            animation: 'snake-rotate 1.8s ease-in-out infinite',
                                                            zIndex: 0,
                                                        }}
                                                    />
                                                )}
                                                <button
                                                    onClick={() => youtubeUrl && handleYoutubeUrl(youtubeUrl)}
                                                    disabled={!youtubeUrl || youtubeFetching}
                                                    className="relative px-6 py-3.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 whitespace-nowrap"
                                                    style={{
                                                        background: '#faf9f5',
                                                        color: '#141413',
                                                        zIndex: 1,
                                                        opacity: youtubeFetching ? 0.75 : 1,
                                                        transition: 'opacity 0.2s ease',
                                                    }}
                                                >
                                                    {youtubeFetching ? (
                                                        <><span className="w-3.5 h-3.5 border-2 border-[rgba(0,0,0,0.15)] border-t-[#141413] rounded-full animate-spin" />Loading</>
                                                    ) : (
                                                        <>Get Clips <ArrowRight size={15} /></>
                                                    )}
                                                </button>
                                            </div>
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
                                            <button
                                                className="px-5 py-3 rounded-xl text-sm font-medium cursor-pointer transition-colors hover:bg-white/10"
                                                style={{ background: 'rgba(250,249,245,0.05)', color: '#faf9f5' }}
                                                onClick={e => { e.stopPropagation(); fileInputRef.current?.click(); }}
                                            >
                                                Browse files
                                            </button>
                                        </div>
                                    )}
                                </div>
                            </div>

                            </div>{/* close bubble+card wrapper */}

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
                    <div
                        onMouseEnter={() => setFeaturesHovered(true)}
                        onMouseLeave={() => setFeaturesHovered(false)}
                    >
                        <div className="mb-5">
                            <h2 className="text-base font-medium" style={{ color: '#faf9f5' }}>Powered by AI</h2>
                        </div>

                        <div className="relative">
                            {/* Scroll container — padding+negative-margin lets hover:-translate-y-1 render
                                without being clipped by overflow-x:auto's implicit overflow-y:auto */}
                            <div
                                ref={featureCarouselRef}
                                className="flex gap-4 no-scrollbar"
                                style={{
                                    overflowX: 'auto',
                                    paddingTop: '8px',
                                    marginTop: '-8px',
                                    paddingBottom: '8px',
                                    marginBottom: '-8px',
                                }}
                                onScroll={updateFeatureScroll}
                            >
                                {allFeatures.map((feature) => {
                                    const Icon = feature.icon;
                                    const cardContent = (
                                        <>
                                            <div
                                                className="w-10 h-10 mb-3 rounded-xl flex items-center justify-center flex-shrink-0"
                                                style={{ background: feature.gradient }}
                                            >
                                                <Icon size={25} style={{ color: 'white' }} strokeWidth={1.8} />
                                            </div>
                                            <h3
                                                className="text-sm font-medium mb-1.5 flex items-center justify-between"
                                                style={{ color: '#faf9f5' }}
                                            >
                                                {feature.name}
                                                {feature.href && (
                                                    <ArrowRight
                                                        className="w-3.5 h-3.5 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all"
                                                        style={{ color: '#ababab' }}
                                                    />
                                                )}
                                            </h3>
                                            <p className="text-xs leading-relaxed" style={{ color: '#ababab' }}>
                                                {feature.description}
                                            </p>
                                        </>
                                    );

                                    const sharedClass = "group rounded-2xl p-5 transition-all duration-300 hover:-translate-y-1";
                                    const sharedStyle: React.CSSProperties = {
                                        background: '#181817',
                                        flex: '0 0 240px',
                                        width: '240px',
                                    };

                                    if (!feature.href) {
                                        return <div key={feature.name} className={sharedClass} style={sharedStyle}>{cardContent}</div>;
                                    }
                                    if (feature.external) {
                                        return <a key={feature.name} href={feature.href} target="_blank" rel="noopener noreferrer" className={sharedClass} style={sharedStyle}>{cardContent}</a>;
                                    }
                                    return <Link key={feature.name} href={feature.href} className={sharedClass} style={sharedStyle}>{cardContent}</Link>;
                                })}
                            </div>

                            {/* Right fade — partial visibility hint */}
                            {featureCanScrollRight && (
                                <div
                                    className="absolute right-0 top-0 bottom-0 w-24 pointer-events-none"
                                    style={{ background: 'linear-gradient(to right, transparent, #141413)' }}
                                />
                            )}

                            {/* Left arrow */}
                            <button
                                onClick={() => scrollFeatures('left')}
                                className="absolute -left-4 top-1/2 -translate-y-1/2 z-10 w-8 h-8 rounded-full flex items-center justify-center hover:text-[#faf9f5]"
                                style={{
                                    background: '#1c1c1b',
                                    border: '1px solid rgba(250,249,245,0.1)',
                                    color: 'rgba(250,249,245,0.5)',
                                    opacity: featuresHovered && featureCanScrollLeft ? 1 : 0,
                                    pointerEvents: featuresHovered && featureCanScrollLeft ? 'auto' : 'none',
                                    transition: 'opacity 0.2s ease',
                                }}
                            >
                                <ChevronLeft size={14} />
                            </button>

                            {/* Right arrow */}
                            <button
                                onClick={() => scrollFeatures('right')}
                                className="absolute -right-4 top-1/2 -translate-y-1/2 z-10 w-8 h-8 rounded-full flex items-center justify-center hover:text-[#faf9f5]"
                                style={{
                                    background: '#1c1c1b',
                                    border: '1px solid rgba(250,249,245,0.1)',
                                    color: 'rgba(250,249,245,0.5)',
                                    opacity: featuresHovered && featureCanScrollRight ? 1 : 0,
                                    pointerEvents: featuresHovered && featureCanScrollRight ? 'auto' : 'none',
                                    transition: 'opacity 0.2s ease',
                                }}
                            >
                                <ChevronRight size={14} />
                            </button>
                        </div>
                    </div>
                )}

                {/* ── Recent Projects ── */}
                <div>
                    <div className="flex items-center justify-between mb-6">
                        <h2 className="text-base font-medium" style={{ color: '#faf9f5' }}>Recent Projects</h2>
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
                            {recentJobs.map((job) => {
                                const firstClip = clips.find(c => c.job_id === job.id && c.file_url);
                                return (
                                <div
                                    key={job.id}
                                    className="group rounded-2xl cursor-pointer hover:-translate-y-1 transition-all duration-300"
                                    style={{ background: '#181817', position: 'relative', zIndex: openMenuId === job.id ? 50 : 1 }}
                                    onClick={() => router.push('/dashboard/projects')}
                                    onMouseLeave={() => setOpenMenuId(null)}
                                >
                                    {/* Thumbnail */}
                                    <div
                                        className="relative aspect-video flex items-center justify-center rounded-t-2xl overflow-hidden"
                                        style={{ background: '#1c1c1b' }}
                                    >
                                        {firstClip?.file_url ? (
                                            <video
                                                src={firstClip.file_url}
                                                className="w-full h-full object-cover"
                                                muted playsInline preload="metadata"
                                                onMouseEnter={e => e.currentTarget.play()}
                                                onMouseLeave={e => { e.currentTarget.pause(); e.currentTarget.currentTime = 0; }}
                                            />
                                        ) : (
                                            <Play
                                                size={20}
                                                style={{ color: 'rgba(250,249,245,0.15)' }}
                                                className="group-hover:opacity-60 transition-opacity"
                                            />
                                        )}
                                        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors" />
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
                                        <div className="absolute top-2.5 right-2.5" style={{ zIndex: 9999 }}>
                                            <button
                                                className="w-7 h-7 rounded-lg flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                                                style={{ background: 'rgba(0,0,0,0.6)', color: '#ababab' }}
                                                onClick={e => { e.stopPropagation(); setOpenMenuId(openMenuId === job.id ? null : job.id); }}
                                            >
                                                <MoreVertical size={14} />
                                            </button>
                                            <div
                                                className="absolute right-0 top-full mt-1 rounded-xl shadow-2xl w-36 overflow-hidden py-1"
                                                style={{
                                                    background: '#1c1c1b',
                                                    border: '1px solid rgba(250,249,245,0.08)',
                                                    zIndex: 9999,
                                                    opacity: openMenuId === job.id ? 1 : 0,
                                                    transform: openMenuId === job.id ? 'scale(1) translateY(0)' : 'scale(0.95) translateY(-4px)',
                                                    pointerEvents: openMenuId === job.id ? 'auto' : 'none',
                                                    transition: 'opacity 150ms ease, transform 150ms ease',
                                                    transformOrigin: 'top right',
                                                }}
                                            >
                                                <button
                                                    className="w-full text-left px-4 py-2.5 text-xs font-medium hover:bg-white/5 transition-colors"
                                                    style={{ color: '#ababab' }}
                                                    onClick={e => { e.stopPropagation(); setOpenMenuId(null); router.push('/dashboard/projects'); }}
                                                >
                                                    View Clips
                                                </button>
                                                <button
                                                    className="w-full text-left px-4 py-2.5 text-xs font-medium hover:bg-red-500/10 transition-colors text-red-400"
                                                    onClick={e => { e.stopPropagation(); setOpenMenuId(null); setDeleteConfirmId(job.id); }}
                                                >
                                                    Delete
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                    {/* Info */}
                                    <div className="p-4">
                                        <p className="text-sm font-medium truncate mb-1" style={{ color: '#faf9f5' }}>
                                            {job.video_title || "Untitled"}
                                        </p>
                                        <p className="text-xs" style={{ color: '#ababab' }}>
                                            {formatDate(job.created_at)}
                                        </p>
                                    </div>
                                </div>
                                );
                            })}
                        </div>
                    )}
                </div>

            </div>

            {/* ── Delete Confirmation Modal ── */}
            {deleteConfirmId && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center p-4"
                    style={{ backdropFilter: 'blur(8px)', background: 'rgba(0,0,0,0.6)' }}
                    onClick={() => setDeleteConfirmId(null)}
                >
                    <div
                        className="relative w-full max-w-md rounded-2xl p-7"
                        style={{
                            background: 'rgba(30,29,28,0.72)',
                            backdropFilter: 'blur(32px) saturate(180%)',
                            WebkitBackdropFilter: 'blur(32px) saturate(180%)',
                            boxShadow: '0 8px 48px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.06)',
                        }}
                        onClick={e => e.stopPropagation()}
                    >
                        <button
                            className="absolute top-4 right-4 w-7 h-7 rounded-lg flex items-center justify-center transition-colors hover:bg-white/5"
                            style={{ color: '#ababab' }}
                            onClick={() => setDeleteConfirmId(null)}
                        >
                            <X size={14} />
                        </button>
                        <p className="text-base font-semibold mb-2" style={{ color: '#faf9f5' }}>Delete project?</p>
                        <p className="text-sm" style={{ color: '#ababab' }}>
                            This will permanently delete the project and all its clips. This action cannot be undone.
                        </p>
                        <div className="flex items-center justify-end gap-2 mt-6">
                            <button
                                className="px-4 py-2 text-sm font-medium rounded-xl transition-colors hover:bg-white/5"
                                style={{ color: '#faf9f5', border: '1px solid rgba(250,249,245,0.12)' }}
                                onClick={() => setDeleteConfirmId(null)}
                            >
                                Cancel
                            </button>
                            <button
                                className="px-4 py-2 text-sm font-medium rounded-xl transition-colors hover:brightness-110"
                                style={{ background: '#ef4444', color: '#fff' }}
                                onClick={() => handleDeleteJob(deleteConfirmId)}
                            >
                                Delete
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
