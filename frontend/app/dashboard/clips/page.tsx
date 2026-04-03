"use client";

import React, { useState, useEffect } from "react";
import { Download, Check, X, Play, FileVideo, MoreHorizontal, ArrowLeft, Upload, Scissors, FolderOpen } from "lucide-react";
import Link from "next/link";
import { useChannel } from "../layout";
import { authFetch } from "@/lib/api";

interface Clip {
    id: string;
    channel_id: string;
    job_id: string;
    hook_text: string;
    duration: number;
    standalone_score: number;
    hook_score: number;
    arc_score: number;
    clip_strategy_role: string;
    posting_order: number;
    is_successful: boolean | null;
    is_published: boolean | null;
    why_failed: string | null;
    quality_verdict?: string | null;
    standalone_result?: string;
    quality_notes?: string;
    file_url: string | null;
    suggested_title: string | null;
    suggested_description: string | null;
}

type FilterType = "all" | "successful" | "failed" | "published";

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
    if (hours < 1) { const mins = Math.floor(hours * 60); return mins <= 1 ? 'Just now' : `${mins}m ago`; }
    if (hours < 24) return 'Today';
    if (days === 1) return 'Yesterday';
    return `${days}d ago`;
};

const formatDuration = (seconds: number) => {
    if (!seconds) return "0:00";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
};

const getScoreColor = (score: number) => {
    if (score >= 7) return "text-green-400";
    if (score >= 5) return "text-yellow-400";
    return "text-red-400";
};

const OpenInEditorButton = ({ clip, guestName }: { clip: Clip; guestName?: string | null }) => {
    if (!clip.file_url) {
        return (
            <button disabled className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg font-medium border border-[#262626] text-[#525252] cursor-not-allowed text-sm">
                <Scissors className="w-4 h-4" /> Open in Editor
            </button>
        );
    }
    const params = new URLSearchParams({ clipUrl: clip.file_url });
    if (clip.suggested_title) params.set("clipTitle", clip.suggested_title);
    if (clip.suggested_description) params.set("clipDesc", clip.suggested_description);
    if (guestName) params.set("clipGuestName", guestName);
    if (clip.job_id) params.set("clipJobId", clip.job_id);
    const href = `https://edit.prognot.com/editor/${crypto.randomUUID()}?${params.toString()}`;

    const handleClick = async (e: React.MouseEvent) => {
        e.preventDefault();
        try {
            await authFetch('/director/events', {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ module_name: "editor", event_type: "clip_opened_in_editor", payload: { clip_id: clip.id, job_id: clip.job_id, channel_id: clip.channel_id, quality_verdict: clip.quality_verdict }, channel_id: clip.channel_id }),
            });
        } catch { /* non-critical */ }
        window.open(href, "_blank", "noopener,noreferrer");
    };

    return (
        <button onClick={handleClick} className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg font-medium border border-[#262626] text-[#a3a3a3] hover:border-[#404040] hover:text-white transition-colors text-sm">
            <Scissors className="w-4 h-4" /> Open in Editor
        </button>
    );
};

export default function MyProjectsPage() {
    const { channels, activeChannelId, setActiveChannelId, isLoading: channelLoading } = useChannel();
    const [jobs, setJobs] = useState<any[]>([]);
    const [clips, setClips] = useState<Clip[]>([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState<FilterType>("all");
    const [selectedJob, setSelectedJob] = useState<any | null>(null);
    const [selectedClip, setSelectedClip] = useState<Clip | null>(null);
    const [openMenuId, setOpenMenuId] = useState<string | null>(null);

    const fetchData = async (silent = false) => {
        if (!silent) setLoading(true);
        try {
            const [jobsRes, clipsRes] = await Promise.all([
                authFetch(`/jobs?channel_id=${activeChannelId}&limit=50`),
                authFetch(`/clips?channel_id=${activeChannelId}&limit=200`)
            ]);
            if (jobsRes.ok) setJobs(await jobsRes.json());
            if (clipsRes.ok) setClips(await clipsRes.json());
        } catch (err) { console.error(err); }
        finally { if (!silent) setLoading(false); }
    };

    useEffect(() => {
        if (channelLoading) return;
        if (activeChannelId) fetchData();
        else { setJobs([]); setClips([]); setLoading(false); }
    }, [activeChannelId, channelLoading]);

    useEffect(() => {
        if (!activeChannelId) return;
        const hasActive = jobs.some(j => ['processing', 'queued', 'running'].includes(j.status));
        if (!hasActive) return;
        const interval = setInterval(() => fetchData(true), 4000);
        return () => clearInterval(interval);
    }, [activeChannelId, jobs]);

    const handleDeleteProject = async (jobId: string) => {
        if (!confirm("Delete this project and all its clips?")) return;
        try {
            const res = await authFetch(`/jobs/${jobId}`, { method: 'DELETE' });
            if (res.ok) { setJobs(jobs.filter(j => j.id !== jobId)); if (selectedJob?.id === jobId) setSelectedJob(null); }
        } catch (err) { console.error(err); }
    };

    const handleApprove = async (id: string) => {
        const clip = clips.find(c => c.id === id);
        if (!clip) return;
        try {
            const endpoint = clip.is_successful === true ? `/clips/${id}/unset-approval` : `/clips/${id}/approve`;
            const res = await authFetch(endpoint, { method: "PATCH" });
            if (res.ok) {
                const newVal = clip.is_successful === true ? null : true;
                setClips(clips.map(c => c.id === id ? { ...c, is_successful: newVal } : c));
                if (selectedClip?.id === id) setSelectedClip({ ...selectedClip, is_successful: newVal });
            }
        } catch (err) { console.error(err); }
    };

    const handleReject = async (id: string) => {
        const clip = clips.find(c => c.id === id);
        if (!clip) return;
        try {
            const endpoint = clip.is_successful === false ? `/clips/${id}/unset-approval` : `/clips/${id}/reject`;
            const res = await authFetch(endpoint, { method: "PATCH" });
            if (res.ok) {
                const newVal = clip.is_successful === false ? null : false;
                setClips(clips.map(c => c.id === id ? { ...c, is_successful: newVal } : c));
                if (selectedClip?.id === id) setSelectedClip({ ...selectedClip, is_successful: newVal });
            }
        } catch (err) { console.error(err); }
    };

    const handlePublish = async (id: string) => {
        const clip = clips.find(c => c.id === id) || selectedClip;
        if (!clip) return;
        try {
            const endpoint = clip.is_published ? `/clips/${id}/unpublish` : `/clips/${id}/publish`;
            const res = await authFetch(endpoint, { method: "PATCH" });
            if (res.ok) {
                const newVal = !clip.is_published;
                setClips(clips.map(c => c.id === id ? { ...c, is_published: newVal } : c));
                if (selectedClip?.id === id) setSelectedClip({ ...selectedClip, is_published: newVal });
            }
        } catch (err) { console.error(err); }
    };

    const handleDownload = (id: string) => {
        const clip = clips.find(c => c.id === id) || selectedClip;
        if (clip?.file_url) window.open(clip.file_url, "_blank");
    };

    const activeJobs = jobs.filter(j => ['processing', 'queued', 'running'].includes(j.status));
    const completedJobs = jobs.filter(j => ['completed', 'failed', 'error'].includes(j.status));

    const filteredProjects = completedJobs.filter(job => {
        const jobClips = clips.filter(c => c.job_id === job.id);
        if (filter === "all") return true;
        if (filter === "successful") return jobClips.some(c => c.is_successful === true);
        if (filter === "failed") return jobClips.some(c => c.is_successful === false);
        if (filter === "published") return jobClips.some(c => c.is_published === true);
        return true;
    });

    const projectClips = selectedJob ? clips.filter(c => c.job_id === selectedJob.id) : [];
    const filteredProjectClips = projectClips.filter(clip => {
        if (filter === "all") return true;
        if (filter === "successful") return clip.is_successful === true;
        if (filter === "failed") return clip.is_successful === false;
        if (filter === "published") return clip.is_published === true;
        return true;
    });

    // No channel yet
    if (!channelLoading && !loading && !activeChannelId) {
        return (
            <div className="min-h-screen bg-black flex items-center justify-center p-8">
                <div className="text-center max-w-sm">
                    <div className="w-14 h-14 bg-[#0a0a0a] border border-[#1a1a1a] rounded-2xl flex items-center justify-center mx-auto mb-5">
                        <FolderOpen className="w-6 h-6 text-[#525252]" />
                    </div>
                    <h2 className="text-lg font-semibold text-white mb-2">No channel yet</h2>
                    <p className="text-sm text-[#737373] mb-6">Create a channel first to start managing your projects.</p>
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
        <div className="min-h-screen bg-black text-white p-6 pb-24 flex">
            <div className="flex-1">
                {/* Header */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
                    <div>
                        <h1 className="text-2xl font-semibold text-white">My Projects</h1>
                        <p className="text-sm text-[#737373] mt-0.5">All your video projects in one place</p>
                    </div>

                    <div className="flex items-center gap-3">
                        {/* Filter Tabs */}
                        <div className="flex items-center bg-[#0a0a0a] p-1 rounded-lg border border-[#1a1a1a]">
                            {(["all", "successful", "failed", "published"] as FilterType[]).map(f => (
                                <button
                                    key={f}
                                    onClick={() => setFilter(f)}
                                    className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                                        filter === f
                                            ? "bg-white text-black"
                                            : "text-[#737373] hover:text-white"
                                    }`}
                                >
                                    {f.charAt(0).toUpperCase() + f.slice(1)}
                                </button>
                            ))}
                        </div>
                    </div>
                </div>

                {loading ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                        {[...Array(8)].map((_, i) => (
                            <div key={i} className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg overflow-hidden">
                                <div className="aspect-video bg-[#1a1a1a] shimmer-load" />
                                <div className="p-3 space-y-2">
                                    <div className="h-3 bg-[#1a1a1a] rounded w-3/4" />
                                    <div className="h-2 bg-[#1a1a1a] rounded w-1/2" />
                                </div>
                            </div>
                        ))}
                    </div>
                ) : !selectedJob ? (
                    <div>
                        {/* Active Jobs */}
                        {activeJobs.length > 0 && (
                            <div className="mb-8">
                                <div className="flex items-center gap-2 mb-4">
                                    <h2 className="text-sm font-medium text-[#a3a3a3]">Active Jobs</h2>
                                    <span className="w-2 h-2 rounded-full bg-white pulse-dot" />
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                                    {activeJobs.map(job => {
                                        const progress = job.progress_pct ?? job.progress ?? 0;
                                        return (
                                            <div key={job.id} className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg overflow-hidden">
                                                <div className="aspect-video flex items-center justify-center p-4 text-center">
                                                    <div>
                                                        <div className="flex items-center justify-center gap-2 mb-2">
                                                            <div className="w-1.5 h-1.5 rounded-full bg-white pulse-dot" />
                                                            <span className="text-[10px] text-[#737373] uppercase tracking-wider">Processing</span>
                                                        </div>
                                                        <p className="text-xs text-white">{getStepLabel(job.current_step || job.step)} {progress > 0 && `(${progress}%)`}</p>
                                                    </div>
                                                </div>
                                                <div className="p-3 border-t border-[#1a1a1a]">
                                                    <p className="text-xs font-medium text-white truncate">{job.video_title || "Untitled"}</p>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}

                        {/* Projects Grid */}
                        {filteredProjects.length === 0 ? (
                            <div className="flex flex-col items-center justify-center py-20 bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl">
                                <FileVideo className="w-12 h-12 text-[#262626] mb-3" />
                                <p className="text-sm text-[#525252]">No projects yet. Start a new job to create clips.</p>
                            </div>
                        ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                                {filteredProjects.map(job => {
                                    const jobClips = clips.filter(c => c.job_id === job.id);
                                    const firstClip = jobClips.find(c => c.file_url);
                                    return (
                                        <div
                                            key={job.id}
                                            className="group bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg overflow-hidden hover:border-[#404040] transition-all cursor-pointer"
                                            onClick={() => setSelectedJob(job)}
                                        >
                                            <div className="relative aspect-video bg-[#0d0d0d] overflow-hidden flex items-center justify-center">
                                                {firstClip?.file_url ? (
                                                    <video
                                                        src={firstClip.file_url}
                                                        className="w-full h-full object-cover"
                                                        muted loop playsInline preload="metadata"
                                                        onMouseEnter={e => e.currentTarget.play()}
                                                        onMouseLeave={e => { e.currentTarget.pause(); e.currentTarget.currentTime = 0; }}
                                                    />
                                                ) : (
                                                    <Play className="w-8 h-8 text-[#262626]" />
                                                )}
                                                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors" />
                                            </div>
                                            <div className="p-3">
                                                <div className="flex items-center justify-between gap-2">
                                                    <p className="text-xs font-medium text-white truncate">{job.video_title || "Untitled"}</p>
                                                    <div className="relative flex-shrink-0">
                                                        <button
                                                            onClick={e => { e.stopPropagation(); setOpenMenuId(openMenuId === job.id ? null : job.id); }}
                                                            className="p-0.5 hover:bg-[#1a1a1a] rounded transition-colors"
                                                        >
                                                            <MoreHorizontal className="w-3.5 h-3.5 text-[#525252]" />
                                                        </button>
                                                        {openMenuId === job.id && (
                                                            <div className="absolute right-0 top-full mt-1 bg-[#0a0a0a] border border-[#262626] rounded-lg shadow-xl z-20 w-32 overflow-hidden">
                                                                <button className="w-full text-left px-3 py-2 text-xs text-[#a3a3a3] hover:bg-[#1a1a1a] hover:text-white transition-colors" onClick={e => { e.stopPropagation(); setOpenMenuId(null); setSelectedJob(job); }}>
                                                                    View Clips
                                                                </button>
                                                                <button className="w-full text-left px-3 py-2 text-xs text-red-400 hover:bg-red-500/10 transition-colors" onClick={e => { e.stopPropagation(); setOpenMenuId(null); handleDeleteProject(job.id); }}>
                                                                    Delete
                                                                </button>
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-1.5 mt-1 text-[10px] text-[#525252]">
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
                    /* Clips view for a single project */
                    <div>
                        <button
                            onClick={() => setSelectedJob(null)}
                            className="inline-flex items-center gap-2 text-sm text-[#737373] hover:text-white transition-colors mb-6"
                        >
                            <ArrowLeft className="w-4 h-4" />
                            Back to Projects
                        </button>

                        <div className="mb-6 pb-4 border-b border-[#1a1a1a]">
                            <h2 className="text-xl font-semibold text-white">{selectedJob.video_title || "Project Clips"}</h2>
                            <p className="text-xs text-[#737373] mt-1">{formatDate(selectedJob.created_at)} · {projectClips.length} clips</p>
                        </div>

                        {filteredProjectClips.length === 0 ? (
                            <div className="flex flex-col items-center justify-center py-20 bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl">
                                <p className="text-sm text-[#525252]">No clips found</p>
                            </div>
                        ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                                {filteredProjectClips.map(clip => (
                                    <div
                                        key={clip.id}
                                        className="bg-[#0a0a0a] border border-[#1a1a1a] hover:border-[#404040] rounded-lg overflow-hidden cursor-pointer transition-all group flex flex-col"
                                        onClick={() => setSelectedClip(clip)}
                                    >
                                        <div className="relative aspect-[9/16] bg-[#0d0d0d] overflow-hidden flex items-center justify-center">
                                            {clip.file_url ? (
                                                <video src={clip.file_url} className="w-full h-full object-cover" muted playsInline preload="metadata" />
                                            ) : (
                                                <Play className="w-8 h-8 text-[#262626]" />
                                            )}
                                            <div className="absolute bottom-2 right-2 bg-black/80 px-1.5 py-0.5 rounded text-[10px] text-white">
                                                {formatDuration(clip.duration)}
                                            </div>
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
                                        </div>
                                        <div className="p-3 flex flex-col flex-1">
                                            <p className="text-xs text-[#a3a3a3] line-clamp-2 mb-2 flex-1">
                                                "{clip.hook_text || "No hook text"}"
                                            </p>
                                            <div className="flex gap-2 text-[10px] font-medium">
                                                <span className={getScoreColor(clip.standalone_score)}>St:{clip.standalone_score || 0}</span>
                                                <span className={getScoreColor(clip.hook_score)}>Hk:{clip.hook_score || 0}</span>
                                                <span className={getScoreColor(clip.arc_score)}>Ar:{clip.arc_score || 0}</span>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* Slide-in Detail Panel */}
            <div className={`fixed inset-y-0 right-0 w-full md:w-[420px] bg-[#0a0a0a] border-l border-[#1a1a1a] shadow-2xl transform transition-transform duration-300 ease-in-out z-50 flex flex-col ${selectedClip ? "translate-x-0" : "translate-x-full"}`}>
                {selectedClip && (
                    <>
                        <div className="p-4 border-b border-[#1a1a1a] flex items-center justify-between">
                            <h2 className="text-sm font-medium text-white">Clip Details</h2>
                            <button onClick={() => setSelectedClip(null)} className="p-1.5 text-[#737373] hover:text-white rounded-lg transition-colors">
                                <X className="w-4 h-4" />
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto p-5 space-y-6">
                            <div className="w-full aspect-[9/16] bg-black rounded-xl overflow-hidden border border-[#1a1a1a]">
                                {selectedClip.file_url ? (
                                    <video src={selectedClip.file_url} controls playsInline className="w-full h-full rounded-xl" />
                                ) : (
                                    <div className="flex items-center justify-center h-full text-[#525252] text-sm">No video available</div>
                                )}
                            </div>

                            <div>
                                <p className="text-[10px] text-[#525252] uppercase tracking-widest mb-2">Hook Text</p>
                                <p className="text-sm text-[#a3a3a3] leading-relaxed bg-black border border-[#1a1a1a] p-3 rounded-lg">
                                    {selectedClip.hook_text || "No hook text generated"}
                                </p>
                            </div>

                            <div className="grid grid-cols-2 gap-3">
                                <div className="bg-black border border-[#1a1a1a] rounded-lg p-3">
                                    <p className="text-[10px] text-[#525252] uppercase tracking-widest mb-1.5">Strategy Role</p>
                                    <p className="text-xs text-white">{selectedClip.clip_strategy_role || "unassigned"}</p>
                                </div>
                                <div className="bg-black border border-[#1a1a1a] rounded-lg p-3">
                                    <p className="text-[10px] text-[#525252] uppercase tracking-widest mb-1.5">Posting Order</p>
                                    <p className="text-xs text-white">#{selectedClip.posting_order || 0}</p>
                                </div>
                            </div>

                            <div>
                                <p className="text-[10px] text-[#525252] uppercase tracking-widest mb-3">Quality Scores</p>
                                <div className="space-y-3">
                                    {[
                                        { label: "Standalone", value: selectedClip.standalone_score },
                                        { label: "Hook", value: selectedClip.hook_score },
                                        { label: "Arc", value: selectedClip.arc_score }
                                    ].map((score, i) => (
                                        <div key={i}>
                                            <div className="flex justify-between text-xs mb-1">
                                                <span className="text-[#a3a3a3]">{score.label}</span>
                                                <span className={`font-medium ${getScoreColor(score.value)}`}>{score.value || 0}/10</span>
                                            </div>
                                            <div className="h-1.5 bg-[#1a1a1a] rounded-full overflow-hidden">
                                                <div className={`h-full rounded-full ${score.value >= 7 ? "bg-green-500" : score.value >= 5 ? "bg-yellow-500" : "bg-red-500"}`} style={{ width: `${(score.value || 0) * 10}%` }} />
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {(selectedClip.standalone_result || selectedClip.quality_notes) && (
                                <div>
                                    <p className="text-[10px] text-[#525252] uppercase tracking-widest mb-2">AI Reasoning</p>
                                    <p className="text-xs text-[#a3a3a3] leading-relaxed bg-black border border-[#1a1a1a] p-3 rounded-lg">
                                        {selectedClip.standalone_result || selectedClip.quality_notes}
                                    </p>
                                </div>
                            )}

                            {selectedClip.is_successful === false && selectedClip.why_failed && (
                                <div>
                                    <p className="text-[10px] text-red-400 uppercase tracking-widest mb-2">Failure Reason</p>
                                    <p className="text-xs text-red-300 leading-relaxed bg-red-500/5 border border-red-500/20 p-3 rounded-lg">
                                        {selectedClip.why_failed}
                                    </p>
                                </div>
                            )}

                            {(selectedClip.suggested_title || selectedClip.suggested_description) && (
                                <div>
                                    <p className="text-[10px] text-[#525252] uppercase tracking-widest mb-3">YouTube Metadata</p>
                                    <div className="space-y-2">
                                        {selectedClip.suggested_title && (
                                            <div className="bg-black border border-[#1a1a1a] rounded-lg p-3">
                                                <p className="text-[10px] text-[#525252] mb-1">Title</p>
                                                <p className="text-xs text-white font-medium">{selectedClip.suggested_title}</p>
                                            </div>
                                        )}
                                        {selectedClip.suggested_description && (
                                            <div className="bg-black border border-[#1a1a1a] rounded-lg p-3">
                                                <p className="text-[10px] text-[#525252] mb-1">Description</p>
                                                <p className="text-xs text-[#a3a3a3] leading-relaxed whitespace-pre-wrap">{selectedClip.suggested_description}</p>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>

                        <div className="p-4 border-t border-[#1a1a1a] space-y-2">
                            <button onClick={() => handleDownload(selectedClip.id)} className="w-full flex items-center justify-center gap-2 py-2.5 bg-[#1a1a1a] hover:bg-[#262626] text-white rounded-lg font-medium transition-colors text-sm border border-[#262626]">
                                <Download className="w-4 h-4" /> Download
                            </button>
                            <div className="flex gap-2">
                                <button onClick={() => handleApprove(selectedClip.id)} className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-medium transition-colors border ${selectedClip.is_successful === true ? 'bg-green-500/20 text-green-400 border-green-500/30' : 'border-[#262626] text-[#737373] hover:border-green-500/30 hover:text-green-400'}`}>
                                    <Check className="w-3.5 h-3.5" /> Approve
                                </button>
                                <button onClick={() => handleReject(selectedClip.id)} className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-medium transition-colors border ${selectedClip.is_successful === false ? 'bg-red-500/20 text-red-400 border-red-500/30' : 'border-[#262626] text-[#737373] hover:border-red-500/30 hover:text-red-400'}`}>
                                    <X className="w-3.5 h-3.5" /> Reject
                                </button>
                            </div>
                            <button onClick={() => handlePublish(selectedClip.id)} className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-lg font-medium text-sm transition-colors border ${selectedClip.is_published ? 'border-[#262626] text-[#737373] hover:text-white' : 'bg-white text-black border-white hover:bg-[#e5e5e5]'}`}>
                                <Upload className="w-4 h-4" />
                                {selectedClip.is_published ? "Mark as Unpublished" : "Mark as Published"}
                            </button>
                            <OpenInEditorButton clip={selectedClip} guestName={selectedJob?.guest_name} />
                        </div>
                    </>
                )}
            </div>

            {selectedClip && (
                <div className="fixed inset-0 bg-black/50 z-40 md:hidden" onClick={() => setSelectedClip(null)} />
            )}
        </div>
    );
}
