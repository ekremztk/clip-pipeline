"use client";

import { useState, useEffect } from "react";
import { Upload, Play, MoreVertical, Dna, Clapperboard, Search, ArrowRight, Link2, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useChannel } from "./layout";
import { authFetch } from "@/lib/api";

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
};

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

// ─── Skeleton components ───────────────────────────────────────────────────
function Skeleton({ className }: { className?: string }) {
    return <div className={`bg-[#0f0f0f] rounded animate-pulse ${className ?? ""}`} />;
}

function PageSkeleton() {
    return (
        <div className="min-h-screen bg-black">
            <div className="max-w-5xl mx-auto px-8 py-10 space-y-12">
                {/* Hero */}
                <div className="text-center space-y-3 pt-4">
                    <Skeleton className="h-10 w-2/3 mx-auto rounded-xl" />
                    <Skeleton className="h-4 w-1/3 mx-auto rounded" />
                </div>
                {/* Upload area */}
                <Skeleton className="h-52 w-full rounded-xl border border-[#1a1a1a]" />
                {/* Recent projects */}
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
    const { activeChannelId, isLoading: channelLoading } = useChannel();
    const [jobs, setJobs] = useState<Job[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        // Wait for the layout to finish resolving channel before deciding anything
        if (channelLoading) return;

        if (!activeChannelId) {
            setLoading(false);
            return;
        }

        setLoading(true);
        const fetchJobs = async () => {
            try {
                const res = await authFetch(`/jobs?channel_id=${activeChannelId}&limit=20`);
                if (res.ok) setJobs(await res.json());
            } catch (err) {
                console.error("Dashboard fetch error", err);
            } finally {
                setLoading(false);
            }
        };
        fetchJobs();
    }, [activeChannelId, channelLoading]);

    // Auto-refresh active jobs
    useEffect(() => {
        if (!activeChannelId || channelLoading) return;
        const hasActive = jobs.some(j => ['processing', 'queued', 'running', 'awaiting_speaker_confirm'].includes(j.status));
        if (!hasActive) return;
        const interval = setInterval(async () => {
            try {
                const res = await authFetch(`/jobs?channel_id=${activeChannelId}&limit=20`);
                if (res.ok) setJobs(await res.json());
            } catch { /* silent */ }
        }, 4000);
        return () => clearInterval(interval);
    }, [activeChannelId, channelLoading, jobs]);

    // ── While layout is still resolving channels: show skeleton, never the empty state ──
    if (channelLoading) {
        return <PageSkeleton />;
    }

    const activeJobs  = jobs.filter(j => ['processing', 'queued', 'running', 'awaiting_speaker_confirm'].includes(j.status));
    const recentJobs  = jobs.filter(j => !['processing', 'queued', 'running', 'awaiting_speaker_confirm'].includes(j.status)).slice(0, 8);

    // Confirmed: loading is done and there are genuinely no channels
    if (!activeChannelId) {
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

                {/* Hero */}
                <div className="text-center space-y-3 pt-4">
                    <h1 className="text-4xl font-semibold text-white tracking-tight">
                        Transform Long Videos into Viral Shorts
                    </h1>
                    <p className="text-sm text-[#737373] max-w-xl mx-auto">
                        AI-powered video clipping with Channel DNA, AI Director, and Content Finder
                    </p>
                </div>

                {/* Upload Area */}
                <div className="w-full max-w-4xl mx-auto">
                    <div className="relative">
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

                        <div
                            onClick={() => router.push('/dashboard/new-job')}
                            className="relative border border-dashed border-[#262626] hover:border-[#404040] rounded-xl overflow-hidden transition-all duration-300 cursor-pointer group"
                        >
                            <div className="absolute inset-0 flex items-center justify-center opacity-[0.02] pointer-events-none select-none overflow-hidden">
                                <div className="text-[12rem] font-bold tracking-tighter leading-none whitespace-nowrap text-white">
                                    PROGNOT
                                </div>
                            </div>

                            <div className="relative p-10 flex flex-col items-center justify-center text-center">
                                <div className="w-12 h-12 mb-4 rounded-lg bg-[#0a0a0a] flex items-center justify-center border border-[#262626] group-hover:border-[#404040] transition-colors">
                                    <Upload className="w-6 h-6 text-[#a3a3a3]" />
                                </div>
                                <h3 className="text-lg font-medium text-white mb-1">
                                    Drop your video or paste link
                                </h3>
                                <p className="text-sm text-[#737373] mb-5">
                                    MP4, MOV, AVI, WebM up to 2GB
                                </p>
                                <button
                                    onClick={(e) => { e.stopPropagation(); router.push('/dashboard/new-job'); }}
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
                                            placeholder="Paste YouTube, Twitch, or video URL"
                                            className="w-full pl-10 pr-4 py-2.5 bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg text-sm text-white placeholder-[#525252] focus:outline-none focus:border-[#404040] transition-colors"
                                            readOnly
                                            onClick={() => router.push('/dashboard/new-job')}
                                        />
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <p className="mt-3 text-center text-xs text-[#525252]">
                        YouTube • Twitch • Vimeo • Direct Upload
                    </p>
                </div>

                {/* Active Jobs */}
                {activeJobs.length > 0 && (
                    <div>
                        <div className="flex items-center gap-2 mb-4">
                            <h2 className="text-base font-medium text-white">Active Jobs</h2>
                            <span className="w-2 h-2 rounded-full bg-white pulse-dot" />
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                            {activeJobs.map((job) => {
                                const isAwaiting = job.status === 'awaiting_speaker_confirm';
                                const progress = job.progress_pct ?? job.progress ?? 0;
                                return (
                                    <div key={job.id} className="group bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg overflow-hidden hover:border-[#404040] transition-all">
                                        <div className="aspect-video bg-[#0a0a0a] flex items-center justify-center p-6">
                                            <div className="text-center">
                                                <div className="flex items-center justify-center gap-2 mb-3">
                                                    <div className="w-2 h-2 rounded-full bg-white pulse-dot" />
                                                    <span className="text-xs text-[#737373] uppercase tracking-wider">Processing</span>
                                                </div>
                                                {isAwaiting ? (
                                                    <div className="space-y-3">
                                                        <p className="text-sm text-white">Speaker confirmation needed</p>
                                                        <Link
                                                            href={`/dashboard/speakers/${job.id}`}
                                                            className="inline-block px-4 py-1.5 bg-white text-black text-xs font-medium rounded-lg hover:bg-[#e5e5e5] transition-colors"
                                                        >
                                                            Confirm Speakers →
                                                        </Link>
                                                    </div>
                                                ) : (
                                                    <p className="text-sm text-white">
                                                        {getStepLabel(job.current_step || job.step)}
                                                        {progress > 0 && <span className="text-[#737373] ml-2">({progress}%)</span>}
                                                    </p>
                                                )}
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

                {/* Feature Cards */}
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

                {/* Recent Projects */}
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
