"use client";

import React, { useState, useEffect, useRef, useMemo, useCallback, Suspense } from "react";
import {
    Download, Check, X, Play, FileVideo, MoreHorizontal, ArrowLeft,
    Upload, Scissors, FolderOpen, ChevronRight, Layers, Plus,
} from "lucide-react";
import BatchCreateModal from "./BatchCreateModal";
import {
    ClipModal, OpenInEditorButton, getBestUrl, getScoreColor, getScoreBarColor, getScoreHex,
    formatDuration, formatTranscriptTime,
} from "./ClipModal";
import type { Clip, TranscriptWord } from "./ClipModal";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useChannel } from "../layout";
import { authFetch } from "@/lib/api";
import { toast } from "@/lib/toast";

// ─── Types ────────────────────────────────────────────────────────────────────


// The old pills filtered projects by their clips' review state — a filter
// nobody used, on a page whose job is to list work. These name what you are
// looking at instead.
type ScopeTab = "all" | "jobs" | "batches";

interface BatchRow {
    id: string;
    name: string | null;
    status: string;
    created_at: string;
    max_parallel: number;
    job_count: number;
    completed_count: number;
    failed_count: number;
    queued_count: number;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const STEP_LABELS: Record<string, string> = {
    initializing: "Initializing...",
    s01_audio_extract: "Extracting Audio...",
    s02_transcribe: "Transcribing...",
    s03_speaker_id: "Identifying Speakers...",
    s04_labeled_transcript: "Building Transcript...",
    s05_unified_discovery: "Analyzing Video with AI...",
    s06_batch_evaluation: "Evaluating Clips...",
    s07_precision_cut: "Calculating Cut Points...",
    s08_export: "Exporting & Uploading...",
    finished: "Complete!",
};

function getStepLabel(step: string | undefined): string {
    if (!step) return "Processing...";
    return STEP_LABELS[step] || step.replace(/_/g, " ").replace(/^s\d+\s?/, "");
}

const formatDate = (dateStr?: string) => {
    if (!dateStr) return "Just now";
    const diff = Date.now() - new Date(dateStr).getTime();
    const hours = diff / (1000 * 60 * 60);
    const days = Math.floor(hours / 24);
    if (hours < 1) { const mins = Math.floor(hours * 60); return mins <= 1 ? "Just now" : `${mins}m ago`; }
    if (hours < 24) return "Today";
    if (days === 1) return "Yesterday";
    return `${days}d ago`;
};


// ─── Main Page (wrapped in Suspense for useSearchParams) ──────────────────────

/**
 * A job's cover frame. Only the first clip of a job carries a landscape
 * thumbnail, and clips cut before thumbnails existed have none at all — their
 * 16:9 source was deleted from R2 once captions succeeded — so fall back to a
 * vertical frame, which the card crops to its middle band.
 */
function jobCover(jobClips: Clip[]): string | null {
    return jobClips.find(c => c.thumbnail_wide_path)?.thumbnail_wide_path
        ?? jobClips.find(c => c.thumbnail_path)?.thumbnail_path
        ?? null;
}

export default function ProjectsPage() {
    return (
        <Suspense fallback={<div className="min-h-screen bg-black" />}>
            <ProjectsContent />
        </Suspense>
    );
}

/**
 * Scalloped verified-style disc. The path is a 24-point ring alternating
 * between two radii — at this size the straight segments read as scallops.
 */
function ReviewedBadge({ size = 20 }: { size?: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
            <path
                d="M12.00 0.00L14.61 2.24L18.00 1.61L19.14 4.86L22.39 6.00L21.76 9.39L24.00 12.00L21.76 14.61L22.39 18.00L19.14 19.14L18.00 22.39L14.61 21.76L12.00 24.00L9.39 21.76L6.00 22.39L4.86 19.14L1.61 18.00L2.24 14.61L0.00 12.00L2.24 9.39L1.61 6.00L4.86 4.86L6.00 1.61L9.39 2.24Z"
                fill="#1355F0"
            />
            <path
                d="M6.9 12.3l3.3 3.3 6.9-6.9"
                fill="none"
                stroke="#ffffff"
                strokeWidth="2.4"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
        </svg>
    );
}

function ProjectsContent() {
    const searchParams = useSearchParams();
    const router = useRouter();
    const { channels, activeChannelId, isLoading: channelLoading, isAdmin } = useChannel();

    const jobIdParam = searchParams.get("job");
    const clipIdParam = searchParams.get("clip");

    const [jobs, setJobs] = useState<any[]>([]);
    const [clips, setClips] = useState<Clip[]>([]);
    const [loading, setLoading] = useState(true);
    const [scope, setScope] = useState<ScopeTab>("all");
    const [batches, setBatches] = useState<BatchRow[]>([]);
    const [showBatchModal, setShowBatchModal] = useState(false);
    const [selectedJob, setSelectedJob] = useState<any | null>(null);
    const [selectedClip, setSelectedClip] = useState<Clip | null>(null);
    const [openMenuId, setOpenMenuId] = useState<string | null>(null);
    const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
    const [deleteClipId, setDeleteClipId] = useState<string | null>(null);
    const urlRestoredRef = useRef(false);

    const fetchData = async (silent = false) => {
        if (!silent) setLoading(true);
        try {
            const [jobsRes, clipsRes, batchesRes] = await Promise.all([
                authFetch(`/jobs?channel_id=${activeChannelId}&limit=50`),
                authFetch(`/clips?channel_id=${activeChannelId}&limit=200`),
                authFetch(`/batches?channel_id=${activeChannelId}&limit=30`),
            ]);
            if (jobsRes.ok) setJobs(await jobsRes.json());
            if (clipsRes.ok) setClips(await clipsRes.json());
            // Batches are admin-only server-side; a 403 here just means no list.
            if (batchesRes.ok) setBatches(await batchesRes.json());
        } catch (err) { console.error(err); }
        finally { if (!silent) setLoading(false); }
    };

    useEffect(() => {
        if (channelLoading) return;
        if (activeChannelId) { urlRestoredRef.current = false; fetchData(); }
        else { setJobs([]); setClips([]); setLoading(false); }
    }, [activeChannelId, channelLoading]);

    // Auto-refresh while jobs are active
    useEffect(() => {
        if (!activeChannelId) return;
        const hasActive = jobs.some(j => ["processing", "queued", "running"].includes(j.status))
            || batches.some(b => b.status === "running");
        if (!hasActive) return;
        const interval = setInterval(() => fetchData(true), 4000);
        return () => clearInterval(interval);
    }, [activeChannelId, jobs, batches]);

    // Restore state from URL params after data loads
    useEffect(() => {
        if (urlRestoredRef.current || loading || !jobs.length) return;
        urlRestoredRef.current = true;
        if (jobIdParam) {
            const job = jobs.find(j => j.id === jobIdParam);
            if (job) {
                setSelectedJob(job);
                if (clipIdParam) {
                    const clip = clips.find(c => c.id === clipIdParam);
                    if (clip) setSelectedClip(clip);
                }
            }
        }
    }, [loading, jobs, clips, jobIdParam, clipIdParam]);

    // Navigation helpers
    const selectJob = useCallback((job: any) => {
        setSelectedJob(job);
        setSelectedClip(null);
        router.replace(`/dashboard/projects?job=${job.id}`);
    }, [router]);

    const selectClip = useCallback((clip: Clip) => {
        setSelectedClip(clip);
        router.replace(`/dashboard/projects?job=${clip.job_id}&clip=${clip.id}`);
    }, [router]);

    const closeClip = useCallback(() => {
        setSelectedClip(null);
        if (selectedJob) router.replace(`/dashboard/projects?job=${selectedJob.id}`);
    }, [router, selectedJob]);

    const goBack = useCallback(() => {
        setSelectedJob(null);
        setSelectedClip(null);
        router.replace("/dashboard/projects");
    }, [router]);

    // Actions
    const handleToggleReviewed = async (jobId: string) => {
        const job = jobs.find(j => j.id === jobId);
        if (!job) return;
        const next = !job.reviewed_at;
        // Flip locally first — the badge should answer the click, not the network.
        setJobs(prev => prev.map(j =>
            j.id === jobId ? { ...j, reviewed_at: next ? new Date().toISOString() : null } : j
        ));
        try {
            const res = await authFetch(`/jobs/${jobId}/reviewed`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ reviewed: next }),
            });
            if (!res.ok) throw new Error();
            const data = await res.json();
            setJobs(prev => prev.map(j =>
                j.id === jobId ? { ...j, reviewed_at: data.reviewed_at } : j
            ));
        } catch {
            setJobs(prev => prev.map(j =>
                j.id === jobId ? { ...j, reviewed_at: job.reviewed_at ?? null } : j
            ));
            toast.error('Failed to update project.');
        }
    };

    const handleDeleteProject = async (jobId: string) => {
        try {
            const res = await authFetch(`/jobs/${jobId}`, { method: "DELETE" });
            if (res.ok) {
                setJobs(jobs.filter(j => j.id !== jobId));
                if (selectedJob?.id === jobId) { setSelectedJob(null); router.replace("/dashboard/projects"); }
                toast.success('Project deleted.');
            } else {
                toast.error('Failed to delete project.');
            }
        } catch { toast.error('Failed to delete project.'); }
        setDeleteConfirmId(null);
    };

    const handleDeleteClip = async (id: string) => {
        try {
            const res = await authFetch(`/clips/${id}`, { method: "DELETE" });
            if (res.ok) {
                setClips(clips.filter(c => c.id !== id));
                if (selectedClip?.id === id) { setSelectedClip(null); }
                toast.success('Clip deleted.');
            } else {
                toast.error('Failed to delete clip.');
            }
        } catch { toast.error('Failed to delete clip.'); }
        setDeleteClipId(null);
    };

    const handleApprove = async (id: string) => {
        const clip = clips.find(c => c.id === id);
        if (!clip) return;
        const endpoint = clip.is_successful === true ? `/clips/${id}/unset-approval` : `/clips/${id}/approve`;
        try {
            const res = await authFetch(endpoint, { method: "PATCH" });
            if (res.ok) {
                const newVal = clip.is_successful === true ? null : true;
                const updated = clips.map(c => c.id === id ? { ...c, is_successful: newVal } : c);
                setClips(updated);
                if (selectedClip?.id === id) setSelectedClip({ ...selectedClip, is_successful: newVal });
                toast.success(newVal === true ? 'Clip approved.' : 'Approval removed.');
            } else { toast.error('Failed to update clip.'); }
        } catch { toast.error('Failed to update clip.'); }
    };

    const handleReject = async (id: string) => {
        const clip = clips.find(c => c.id === id);
        if (!clip) return;
        const endpoint = clip.is_successful === false ? `/clips/${id}/unset-approval` : `/clips/${id}/reject`;
        try {
            const res = await authFetch(endpoint, { method: "PATCH" });
            if (res.ok) {
                const newVal = clip.is_successful === false ? null : false;
                const updated = clips.map(c => c.id === id ? { ...c, is_successful: newVal } : c);
                setClips(updated);
                if (selectedClip?.id === id) setSelectedClip({ ...selectedClip, is_successful: newVal });
                toast.success(newVal === false ? 'Clip rejected.' : 'Rejection removed.');
            } else { toast.error('Failed to update clip.'); }
        } catch { toast.error('Failed to update clip.'); }
    };

    const handlePublish = async (id: string) => {
        const clip = clips.find(c => c.id === id) || selectedClip;
        if (!clip) return;
        const endpoint = clip.is_published ? `/clips/${id}/unpublish` : `/clips/${id}/publish`;
        try {
            const res = await authFetch(endpoint, { method: "PATCH" });
            if (res.ok) {
                const newVal = !clip.is_published;
                const updated = clips.map(c => c.id === id ? { ...c, is_published: newVal } : c);
                setClips(updated);
                if (selectedClip?.id === id) setSelectedClip({ ...selectedClip, is_published: newVal });
                toast.success(newVal ? 'Clip marked as published.' : 'Clip unpublished.');
            } else { toast.error('Failed to update clip.'); }
        } catch { toast.error('Failed to update clip.'); }
    };

    const handleStockReview = async (
        id: string,
        status: "unreviewed" | "maybe" | "rejected" | "posted",
        note: string,
    ) => {
        try {
            const res = await authFetch(`/clips/${id}/stock-review`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ status, note }),
            });
            if (!res.ok) {
                throw new Error('request failed');
            }
            const updatedClip = await res.json();
            const updated = clips.map(c => c.id === id ? { ...c, ...updatedClip } : c);
            setClips(updated);
            if (selectedClip?.id === id) setSelectedClip({ ...selectedClip, ...updatedClip });
            toast.success('Review saved.');
        } catch {
            toast.error('Failed to save review.');
            throw new Error('review save failed');
        }
    };

    const handleDownload = (id: string) => {
        const clip = clips.find(c => c.id === id) || selectedClip;
        if (clip) { const u = getBestUrl(clip); if (u) window.open(u, "_blank"); }
    };

    // Derived data
    const activeJobs = jobs.filter(j => ["processing", "queued", "running"].includes(j.status));
    const completedJobs = jobs.filter(j => ["completed", "failed", "error"].includes(j.status));

    // A batch's jobs live on their own page; showing them here too would list
    // the same work twice under two different parents.
    const standaloneJobs = completedJobs.filter(j => !j.batch_id);
    const filteredProjects = scope === "batches" ? [] : standaloneJobs;

    const projectClips = selectedJob ? clips.filter(c => c.job_id === selectedJob.id) : [];
    // The scope tabs say which kind of thing to list, not which clips to keep,
    // so inside a project every clip is shown.
    const filteredProjectClips = projectClips;

    // No channel
    if (!channelLoading && !loading && !activeChannelId) {
        return (
            <div className="min-h-screen flex items-center justify-center p-8" style={{ background: '#141413' }}>
                <div className="text-center max-w-sm">
                    <div
                        className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-5"
                        style={{ background: '#181817', border: '1px solid rgba(250,249,245,0.07)' }}
                    >
                        <FolderOpen className="w-6 h-6" style={{ color: '#ababab' }} />
                    </div>
                    <h2 className="text-lg font-semibold mb-2" style={{ color: '#faf9f5' }}>No channel yet</h2>
                    <p className="text-sm mb-6" style={{ color: '#ababab' }}>Create a channel first to start managing your projects.</p>
                    <Link href="/dashboard/settings" className="inline-flex items-center gap-2 bg-white hover:bg-[#e5e5e5] text-black text-sm font-medium px-5 py-2.5 rounded-xl transition-colors">
                        Add Channel
                    </Link>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen p-6 pb-24" style={{ background: '#141413', color: '#faf9f5' }}>
            {/* Header */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
                <div>
                    {selectedJob ? (
                        <div>
                            <button
                                onClick={goBack}
                                className="inline-flex items-center gap-1.5 text-xs mb-2 transition-colors hover:!text-[#faf9f5]"
                                style={{ color: '#ababab' }}
                            >
                                <ArrowLeft className="w-3.5 h-3.5" /> Projects
                            </button>
                            <div className="flex items-center gap-2">
                                <h1 className="text-2xl font-semibold" style={{ color: '#faf9f5' }}>{selectedJob.video_title || "Project Clips"}</h1>
                                <ChevronRight className="w-4 h-4" style={{ color: '#ababab' }} />
                                <span className="text-sm" style={{ color: '#ababab' }}>{projectClips.length} clips</span>
                            </div>
                            <p className="text-xs mt-0.5" style={{ color: '#ababab' }}>{formatDate(selectedJob.created_at)}</p>
                        </div>
                    ) : (
                        <div>
                            <h1 className="text-2xl font-semibold" style={{ color: '#faf9f5' }}>Projects</h1>
                            <p className="text-sm mt-0.5" style={{ color: '#ababab' }}>All your video projects in one place</p>
                        </div>
                    )}
                </div>

                {!selectedJob && (
                    <div className="flex items-center gap-3">
                        <div
                            className="flex items-center p-1 rounded-xl gap-1"
                            style={{ background: 'rgba(250,249,245,0.03)' }}
                        >
                            {(["all", "jobs", "batches"] as ScopeTab[]).map(t => (
                                <button
                                    key={t}
                                    onClick={() => setScope(t)}
                                    className="px-4 py-2 rounded-lg text-sm font-medium uppercase tracking-wide transition-all"
                                    style={{
                                        background: scope === t ? 'rgba(250,249,245,0.08)' : 'transparent',
                                        color: scope === t ? '#faf9f5' : 'rgba(250,249,245,0.4)',
                                    }}
                                >
                                    {t}
                                </button>
                            ))}
                        </div>
                        {isAdmin && (
                            <button
                                onClick={() => setShowBatchModal(true)}
                                className="flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium transition-colors"
                                style={{ background: '#faf9f5', color: '#141413' }}
                            >
                                <Plus className="w-4 h-4" /> Create batch
                            </button>
                        )}
                    </div>
                )}
            </div>

            {/* Content */}
            {loading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    {[...Array(8)].map((_, i) => (
                        <div key={i} className="rounded-2xl overflow-hidden" style={{ background: '#181817' }}>
                            <div className="aspect-video shimmer-load" style={{ background: 'rgba(250,249,245,0.06)' }} />
                            <div className="p-4 space-y-2">
                                <div className="h-3 rounded w-3/4 animate-pulse" style={{ background: 'rgba(250,249,245,0.06)' }} />
                                <div className="h-2 rounded w-1/2 animate-pulse" style={{ background: 'rgba(250,249,245,0.04)' }} />
                            </div>
                        </div>
                    ))}
                </div>
            ) : !selectedJob ? (
                /* ── Projects grid ── */
                <div>
                    {/* Batches — a batch is a parent of jobs, so it gets its own row
                        above the projects rather than a card among them. */}
                    {scope !== "jobs" && batches.length > 0 && (
                        <div className="mb-8">
                            <div className="flex items-center gap-2 mb-4">
                                <Layers className="w-4 h-4" style={{ color: '#ababab' }} />
                                <h2 className="text-sm font-medium" style={{ color: '#ababab' }}>Batches</h2>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                {batches.map(b => {
                                    const done = b.completed_count + b.failed_count;
                                    const pct = b.job_count ? Math.round((done / b.job_count) * 100) : 0;
                                    return (
                                        <button
                                            key={b.id}
                                            onClick={() => router.push(`/dashboard/projects/batchs/${b.id}`)}
                                            className="text-left rounded-2xl p-4 transition-all hover:-translate-y-1 duration-300"
                                            style={{ background: '#181817' }}
                                        >
                                            <div className="flex items-center justify-between mb-2">
                                                <span className="text-sm font-medium truncate" style={{ color: '#faf9f5' }}>
                                                    {b.name || 'Untitled batch'}
                                                </span>
                                                <span
                                                    className="text-[10px] px-2 py-0.5 rounded-full whitespace-nowrap"
                                                    style={{
                                                        background: b.status === 'running' ? 'rgba(95,159,111,0.15)' : 'rgba(250,249,245,0.06)',
                                                        color: b.status === 'running' ? '#8fd4a0' : '#ababab',
                                                    }}
                                                >
                                                    {b.status}
                                                </span>
                                            </div>
                                            <div className="h-1 rounded-full overflow-hidden mb-2" style={{ background: '#2a2a28' }}>
                                                <div className="h-full rounded-full transition-all"
                                                    style={{ width: `${pct}%`, background: '#faf9f5' }} />
                                            </div>
                                            <div className="flex items-center gap-1.5 text-[10px]" style={{ color: '#ababab' }}>
                                                <span>{done}/{b.job_count} done</span>
                                                {b.failed_count > 0 && <><span>·</span><span style={{ color: '#e07a5f' }}>{b.failed_count} failed</span></>}
                                                <span>·</span>
                                                <span>{formatDate(b.created_at)}</span>
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {/* Active Jobs */}
                    {scope !== "batches" && activeJobs.length > 0 && (
                        <div className="mb-8">
                            <div className="flex items-center gap-2 mb-4">
                                <h2 className="text-sm font-medium" style={{ color: '#ababab' }}>Active Jobs</h2>
                                <span className="w-2 h-2 rounded-full pulse-dot" style={{ background: '#faf9f5' }} />
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                {activeJobs.map(job => {
                                    const progress = job.progress_pct ?? job.progress ?? 0;
                                    return (
                                        <div key={job.id} className="rounded-2xl overflow-hidden" style={{ background: '#181817' }}>
                                            <div className="aspect-video flex items-center justify-center p-4 text-center" style={{ background: '#1c1c1b' }}>
                                                <div>
                                                    <div className="flex items-center justify-center gap-2 mb-2">
                                                        <div className="w-1.5 h-1.5 rounded-full pulse-dot" style={{ background: '#faf9f5' }} />
                                                        <span className="text-[10px] uppercase tracking-wider" style={{ color: '#ababab' }}>Processing</span>
                                                    </div>
                                                    <p className="text-xs" style={{ color: '#faf9f5' }}>
                                                        {getStepLabel(job.current_step || job.step)} {progress > 0 && `(${progress}%)`}
                                                    </p>
                                                </div>
                                            </div>
                                            <div className="p-3" style={{ borderTop: '1px solid rgba(250,249,245,0.06)' }}>
                                                <p className="text-xs font-medium truncate" style={{ color: '#faf9f5' }}>{job.video_title || "Untitled"}</p>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {/* Completed Projects */}
                    {scope === "batches" ? null : filteredProjects.length === 0 ? (
                        <div
                            className="flex flex-col items-center justify-center py-20 rounded-2xl"
                            style={{ background: '#181817' }}
                        >
                            <FileVideo className="w-12 h-12 mb-3" style={{ color: 'rgba(250,249,245,0.1)' }} />
                            <p className="text-sm" style={{ color: '#ababab' }}>No projects yet. Start a new job to create clips.</p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                            {filteredProjects.map(job => {
                                const jobClips = clips.filter(c => c.job_id === job.id);
                                const firstClip = jobClips.find(c => c.file_url);
                                return (
                                    <div
                                        key={job.id}
                                        className="group rounded-2xl cursor-pointer hover:-translate-y-1 transition-all duration-300"
                                        style={{ background: '#181817', overflow: 'visible', position: 'relative', zIndex: openMenuId === job.id ? 50 : 1 }}
                                        onClick={() => selectJob(job)}
                                        onMouseLeave={() => setOpenMenuId(null)}
                                    >
                                        <div
                                            className="relative aspect-video flex items-center justify-center rounded-t-2xl overflow-hidden"
                                            style={{ background: '#1c1c1b' }}
                                        >
                                            {firstClip && getBestUrl(firstClip) ? (
                                                /* The poster carries the card and `preload="none"` means no
                                                   video bytes move until someone hovers — a grid of these
                                                   used to pull a few hundred kilobytes per card just to
                                                   paint one frame, six at a time, with the rest queued. */
                                                <video
                                                    src={getBestUrl(firstClip)!}
                                                    poster={jobCover(jobClips) ?? undefined}
                                                    className="w-full h-full object-cover"
                                                    muted loop playsInline preload="none"
                                                    onMouseEnter={e => e.currentTarget.play()}
                                                    onMouseLeave={e => { e.currentTarget.pause(); e.currentTarget.currentTime = 0; }}
                                                />
                                            ) : (
                                                <Play size={20} style={{ color: 'rgba(250,249,245,0.15)' }} className="group-hover:opacity-60 transition-opacity" />
                                            )}
                                            <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors" />

                                            {/* Reviewed badge — stays visible without hover, since its
                                                whole job is to be readable while scanning the grid. */}
                                            {job.reviewed_at && (
                                                <div className="absolute top-2.5 left-2.5" style={{ zIndex: 20 }}>
                                                    <ReviewedBadge size={20} />
                                                </div>
                                            )}

                                            {/* Review toggle + more menu — overlay on thumbnail */}
                                            <div className="absolute top-2.5 right-2.5 flex items-center gap-1.5" style={{ zIndex: 9999 }}>
                                                <button
                                                    title={job.reviewed_at ? 'Mark as not reviewed' : 'Mark as reviewed'}
                                                    className="w-7 h-7 rounded-lg flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                                                    style={{
                                                        background: 'rgba(0,0,0,0.6)',
                                                        color: job.reviewed_at ? '#1355F0' : '#ababab',
                                                    }}
                                                    onClick={e => { e.stopPropagation(); setOpenMenuId(null); handleToggleReviewed(job.id); }}
                                                >
                                                    <Check size={14} strokeWidth={3} />
                                                </button>
                                                <div className="relative">
                                                <button
                                                    className="w-7 h-7 rounded-lg flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                                                    style={{ background: 'rgba(0,0,0,0.6)', color: '#ababab' }}
                                                    onClick={e => { e.stopPropagation(); setOpenMenuId(openMenuId === job.id ? null : job.id); }}
                                                >
                                                    <MoreHorizontal size={14} />
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
                                                        onClick={e => { e.stopPropagation(); setOpenMenuId(null); selectJob(job); }}
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
                                        </div>
                                        <div className="p-4">
                                            <p className="text-sm font-medium truncate" style={{ color: '#faf9f5' }}>{job.video_title || "Untitled"}</p>
                                            <div className="flex items-center gap-1.5 mt-1 text-[10px]" style={{ color: '#ababab' }}>
                                                <span>{jobClips.length} clips</span>
                                                <span>·</span>
                                                <span>{formatDate(job.created_at)}</span>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            ) : (
                /* ── Clips grid for a project ── */
                <div>
                    {filteredProjectClips.length === 0 ? (
                        <div
                            className="flex flex-col items-center justify-center py-20 rounded-2xl"
                            style={{ background: '#181817' }}
                        >
                            <p className="text-sm" style={{ color: '#ababab' }}>No clips found</p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                            {filteredProjectClips.map(clip => {
                                const score = clip.standalone_score ?? 0;
                                return (
                                    <div
                                        key={clip.id}
                                        className="rounded-2xl overflow-hidden cursor-pointer transition-all group flex flex-col hover:-translate-y-1 duration-300"
                                        style={{ background: '#181817' }}
                                        onClick={() => selectClip(clip)}
                                    >
                                        <div
                                            className="relative aspect-[9/16] overflow-hidden flex items-center justify-center"
                                            style={{ background: '#1c1c1b' }}
                                        >
                                            {/* A card never played, so it never needed a video element:
                                                the poster frame is the whole point and it is ~25 kB
                                                against a few hundred for a video's header and first
                                                frames. Older clips have no thumbnail and keep the
                                                video, which is also what makes them the slow ones. */}
                                            {clip.thumbnail_path ? (
                                                <img
                                                    src={clip.thumbnail_path}
                                                    alt=""
                                                    loading="lazy"
                                                    decoding="async"
                                                    className="w-full h-full object-cover"
                                                />
                                            ) : getBestUrl(clip) ? (
                                                <video src={getBestUrl(clip)!} className="w-full h-full object-cover" muted playsInline preload="metadata" />
                                            ) : (
                                                <Play size={20} style={{ color: 'rgba(250,249,245,0.15)' }} />
                                            )}
                                            {/* Duration */}
                                            <div
                                                className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded text-[10px]"
                                                style={{ background: 'rgba(0,0,0,0.75)', color: '#faf9f5' }}
                                            >
                                                {formatDuration(clip.duration_s)}
                                            </div>
                                            {/* Score pill */}
                                            <div
                                                className={`absolute top-2 left-2 rounded-lg px-1.5 py-0.5 text-[10px] font-bold ${getScoreColor(score)}`}
                                                style={{ background: 'rgba(0,0,0,0.75)' }}
                                            >
                                                {score}
                                            </div>
                                            {/* Approval indicator */}
                                            {clip.is_successful === true && (
                                                <div className="absolute top-2 right-2 bg-green-500/90 text-white p-0.5 rounded-full">
                                                    <Check className="w-3 h-3" />
                                                </div>
                                            )}
                                            {clip.is_successful === false && (
                                                <div className="absolute top-2 right-2 bg-red-500/90 text-white p-0.5 rounded-full">
                                                    <X className="w-3 h-3" />
                                                </div>
                                            )}
                                            {/* Delete button — hover overlay */}
                                            <button
                                                className="absolute bottom-2 left-2 w-6 h-6 rounded-md flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                                                style={{ background: 'rgba(0,0,0,0.75)', color: '#f87171' }}
                                                title="Delete clip"
                                                onClick={e => { e.stopPropagation(); setDeleteClipId(clip.id); }}
                                            >
                                                <X size={12} />
                                            </button>
                                        </div>
                                        <div className="p-3 flex flex-col flex-1">
                                            <p
                                                className="text-[10px] line-clamp-2 flex-1 leading-relaxed"
                                                style={{ color: '#ababab' }}
                                            >
                                                &ldquo;{clip.hook_text || "No hook text"}&rdquo;
                                            </p>
                                            <div className="flex items-center justify-between mt-2">
                                                <span className="text-[9px] capitalize" style={{ color: '#ababab' }}>{clip.clip_strategy_role || "—"}</span>
                                                <span className="text-[9px]" style={{ color: '#ababab' }}>#{clip.posting_order || "—"}</span>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            )}

            {/* Clip Modal */}
            {selectedClip && (
                <ClipModal
                    clip={selectedClip}
                    targetGuest={selectedJob?.target_guest}
                    onClose={closeClip}
                    onApprove={handleApprove}
                    onReject={handleReject}
                    onPublish={handlePublish}
                    onDownload={handleDownload}
                    onStockReview={handleStockReview}
                />
            )}

            {/* ── Delete Confirmation Modal ── */}
            {(deleteConfirmId || deleteClipId) && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center p-4"
                    style={{ backdropFilter: 'blur(8px)', background: 'rgba(0,0,0,0.6)' }}
                    onClick={() => { setDeleteConfirmId(null); setDeleteClipId(null); }}
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
                        {/* Close */}
                        <button
                            className="absolute top-4 right-4 w-7 h-7 rounded-lg flex items-center justify-center transition-colors hover:bg-white/5"
                            style={{ color: '#ababab' }}
                            onClick={() => { setDeleteConfirmId(null); setDeleteClipId(null); }}
                        >
                            <X size={14} />
                        </button>

                        <div className="mb-1">
                            <p className="text-base font-semibold mb-2" style={{ color: '#faf9f5' }}>
                                {deleteClipId ? 'Delete clip?' : 'Delete project?'}
                            </p>
                            <p className="text-sm" style={{ color: '#ababab' }}>
                                {deleteClipId
                                    ? 'This will permanently delete the clip and its video files. This action cannot be undone.'
                                    : 'This will permanently delete the project and all its clips. This action cannot be undone.'}
                            </p>
                        </div>

                        <div className="flex items-center justify-end gap-2 mt-6">
                            <button
                                className="px-4 py-2 text-sm font-medium rounded-xl transition-colors hover:bg-white/5"
                                style={{ color: '#faf9f5', border: '1px solid rgba(250,249,245,0.12)' }}
                                onClick={() => { setDeleteConfirmId(null); setDeleteClipId(null); }}
                            >
                                Cancel
                            </button>
                            <button
                                className="px-4 py-2 text-sm font-medium rounded-xl transition-colors hover:brightness-110"
                                style={{ background: '#ef4444', color: '#fff' }}
                                onClick={() => {
                                    if (deleteClipId) { handleDeleteClip(deleteClipId); }
                                    else if (deleteConfirmId) { handleDeleteProject(deleteConfirmId); }
                                }}
                            >
                                Delete
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {showBatchModal && activeChannelId && (
                <BatchCreateModal
                    channelId={activeChannelId}
                    isAdmin={isAdmin}
                    onClose={() => setShowBatchModal(false)}
                    onCreated={(batchId) => {
                        setShowBatchModal(false);
                        fetchData(true);
                        router.push(`/dashboard/projects/batchs/${batchId}`);
                    }}
                />
            )}
        </div>
    );
}
