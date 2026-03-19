"use client";

import React, { useState, useEffect } from "react";
import { Download, Check, X, ChevronDown, Play, FileVideo, MoreHorizontal, ArrowLeft } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { useChannel } from "../layout";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Channel {
    id: string;
    name: string;
}

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
    why_failed: string | null;
    standalone_result?: string;
    quality_notes?: string;
    file_url: string | null;
}

type FilterType = "all" | "successful" | "failed" | "pending";

const formatDate = (dateStr?: string) => {
    if (!dateStr) return 'Just now';
    const diff = Date.now() - new Date(dateStr).getTime();
    const hours = diff / (1000 * 60 * 60);
    const days = Math.floor(hours / 24);
    if (hours < 1) {
        const mins = Math.floor(hours * 60);
        return mins <= 1 ? 'Just now' : `${mins} min ago`;
    }
    if (hours < 24) return 'Today';
    if (days === 1) return 'Yesterday';
    return `${days} days ago`;
};

const ActiveJobCard = ({ initialJob, onComplete }: { initialJob: any, onComplete: (job: any) => void }) => {
    const [job, setJob] = useState(initialJob);

    useEffect(() => {
        if (!job?.id) return;
        if (job.status === 'completed' || job.status === 'failed' || job.status === 'error') return;

        const interval = setInterval(async () => {
            try {
                if (!job?.id) return;
                const res = await fetch(`${API}/jobs/${job.id}`);
                if (res.ok) {
                    const data = await res.json();
                    if (data && data.id) {
                        setJob(data);
                        if (data.status === 'completed' || data.status === 'failed' || data.status === 'error') {
                            onComplete(data);
                        }
                    }
                }
            } catch (err) { }
        }, 3000);

        return () => clearInterval(interval);
    }, [job?.id]); // Removed job.status and onComplete to prevent unnecessary remounts and state clearing

    const progress = job.progress_pct ?? job.progress ?? 0;
    const isAwaiting = job.status === 'awaiting_speaker_confirm';

    return (
        <div className="bg-[#0d0d0d] border border-white/[0.06] rounded-2xl overflow-hidden flex flex-col">
            <div className="w-full aspect-[16/9] relative bg-gradient-to-br from-zinc-900 to-zinc-950 overflow-hidden flex items-center justify-center p-6 text-center">
                <motion.div
                    className="absolute inset-0 z-0 pointer-events-none"
                    style={{
                        background: "linear-gradient(105deg, transparent 40%, rgba(124,58,237,0.15) 50%, transparent 60%)",
                        backgroundSize: "200% 100%"
                    }}
                    animate={{ backgroundPosition: ['200% 0', '-200% 0'] }}
                    transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
                />

                <div className="relative z-10 flex flex-col items-center justify-center w-full h-full gap-3">
                    <div className="flex items-center gap-2 mb-2">
                        <div className="w-2 h-2 rounded-full bg-violet-500 animate-pulse" />
                        <span className="text-zinc-400 text-xs font-medium uppercase tracking-wider">Processing</span>
                    </div>

                    {isAwaiting ? (
                        <div className="flex flex-col items-center gap-3">
                            <span className="text-white font-medium text-sm">Waiting for speaker confirmation...</span>
                            <Link href={`/dashboard/speakers/${job.id}`} className="inline-flex items-center justify-center bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium py-1.5 px-4 rounded-full transition-colors z-20">
                                Confirm Speakers →
                            </Link>
                        </div>
                    ) : (
                        <div className="flex items-center justify-center gap-1.5 whitespace-nowrap">
                            <span className="text-white font-medium text-sm truncate">Finding best clips...</span>
                            <span className="text-violet-400 font-bold text-sm shrink-0">({progress}%)</span>
                        </div>
                    )}
                </div>
            </div>

            <div className="p-4 flex flex-col gap-1 border-t border-white/[0.06] bg-[#0d0d0d]">
                <div className="flex items-center justify-between gap-4">
                    <span className="font-medium text-sm text-gray-200 truncate" title={job.video_title}>
                        {job.video_title || "Untitled Video"}
                    </span>
                    <button className="p-1 text-gray-400/50 cursor-not-allowed">
                        <MoreHorizontal className="w-4 h-4" />
                    </button>
                </div>
                <div className="flex items-center justify-between text-xs text-gray-500">
                    <span>Processing...</span>
                    <span>{formatDate(job.created_at)}</span>
                </div>
            </div>
        </div>
    );
};

const ProjectCard = ({ job, clips, onClick, onDelete }: { job: any, clips: Clip[], onClick: () => void, onDelete: () => void }) => {
    const firstClip = clips.find(c => c.file_url);
    const videoSrc = firstClip?.file_url;
    const [isMenuOpen, setIsMenuOpen] = useState(false);

    return (
        <motion.div
            className="bg-[#0d0d0d] border border-white/[0.06] rounded-2xl overflow-hidden flex flex-col cursor-pointer"
            whileHover={{ y: -2, borderColor: "rgba(139, 92, 246, 0.3)" }}
            onClick={onClick}
        >
            <div className="w-full aspect-[16/9] bg-[#141414] relative flex items-center justify-center overflow-hidden group">
                {videoSrc ? (
                    <video
                        src={videoSrc}
                        className="w-full h-full object-cover"
                        muted
                        loop
                        preload="metadata"
                        playsInline
                        onMouseEnter={(e) => e.currentTarget.play()}
                        onMouseLeave={(e) => { e.currentTarget.pause(); e.currentTarget.currentTime = 0; }}
                    />
                ) : (
                    <Play className="w-12 h-12 text-white/20" />
                )}
            </div>

            <div className="p-4 flex flex-col gap-1 border-t border-white/[0.06] bg-[#0d0d0d]">
                <div className="flex items-center justify-between gap-4">
                    <span className="font-medium text-sm text-gray-200 truncate" title={job.video_title}>
                        {job.video_title || "Untitled Job"}
                    </span>
                    <div className="relative">
                        <button
                            className="p-1 text-gray-400 hover:text-white rounded transition-colors"
                            onClick={(e) => {
                                e.stopPropagation();
                                setIsMenuOpen(!isMenuOpen);
                            }}
                        >
                            <MoreHorizontal className="w-4 h-4" />
                        </button>
                        <AnimatePresence>
                            {isMenuOpen && (
                                <motion.div
                                    initial={{ opacity: 0, scale: 0.95 }}
                                    animate={{ opacity: 1, scale: 1 }}
                                    exit={{ opacity: 0, scale: 0.95 }}
                                    transition={{ duration: 0.15 }}
                                    className="absolute right-0 top-full mt-1 bg-zinc-900 border border-white/[0.08] rounded-xl shadow-xl z-20 w-36 overflow-hidden"
                                >
                                    <button
                                        className="w-full text-left px-4 py-2.5 text-sm text-gray-300 hover:bg-white/5 hover:text-white transition-colors"
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setIsMenuOpen(false);
                                            onClick();
                                        }}
                                    >
                                        View Clips
                                    </button>
                                    <button
                                        className="w-full text-left px-4 py-2.5 text-sm text-red-400 hover:bg-red-500/10 hover:text-red-300 transition-colors"
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setIsMenuOpen(false);
                                            onDelete();
                                        }}
                                    >
                                        Delete Project
                                    </button>
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>
                </div>
                <div className="flex items-center text-xs text-gray-500">
                    <span>{clips.length} clips</span>
                    <span className="mx-1.5">·</span>
                    <span>{formatDate(job.created_at)}</span>
                </div>
            </div>
        </motion.div>
    );
};

export default function ClipLibraryPage() {
    const { channels, activeChannelId, setActiveChannelId } = useChannel();
    const [jobs, setJobs] = useState<any[]>([]);
    const [clips, setClips] = useState<Clip[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [filter, setFilter] = useState<FilterType>("all");
    const [selectedJob, setSelectedJob] = useState<any | null>(null);
    const [selectedClip, setSelectedClip] = useState<Clip | null>(null);

    useEffect(() => {
        if (activeChannelId) {
            fetchJobsAndClips();
        } else {
            setJobs([]);
            setClips([]);
            setLoading(false);
        }
    }, [activeChannelId]);

    const fetchJobsAndClips = async () => {
        setLoading(true);
        try {
            const [jobsRes, clipsRes] = await Promise.all([
                fetch(`${API}/jobs?channel_id=${activeChannelId}&limit=50`),
                fetch(`${API}/clips?channel_id=${activeChannelId}&limit=200`)
            ]);

            if (jobsRes.ok && clipsRes.ok) {
                setJobs(await jobsRes.json());
                setClips(await clipsRes.json());
            }
        } catch (error) {
            console.error("Failed to fetch data", error);
        } finally {
            setLoading(false);
        }
    };

    const fetchClipsOnly = async () => {
        try {
            const res = await fetch(`${API}/clips?channel_id=${activeChannelId}&limit=200`);
            if (res.ok) setClips(await res.json());
        } catch (err) { }
    };

    const handleJobComplete = (updatedJob: any) => {
        setJobs(prev => prev.map(j => j.id === updatedJob.id ? updatedJob : j));
        fetchClipsOnly();
    };

    const handleDeleteProject = async (jobId: string) => {
        if (!confirm("Are you sure you want to delete this project?")) return;
        try {
            const res = await fetch(`${API}/jobs/${jobId}`, { method: 'DELETE' });
            if (res.ok) {
                setJobs(jobs.filter(j => j.id !== jobId));
                if (selectedJob?.id === jobId) setSelectedJob(null);
            }
        } catch (err) {
            console.error("Failed to delete project", err);
        }
    };

    const handleApprove = async (id: string) => {
        const clip = clips.find(c => c.id === id);
        if (!clip) return;

        try {
            if (clip.is_successful === true) {
                const res = await fetch(`${API}/clips/${id}/unset-approval`, { method: "PATCH" });
                if (res.ok) {
                    setClips(clips.map(c => c.id === id ? { ...c, is_successful: null } : c));
                    if (selectedClip?.id === id) {
                        setSelectedClip({ ...selectedClip, is_successful: null });
                    }
                }
            } else {
                const res = await fetch(`${API}/clips/${id}/approve`, { method: "PATCH" });
                if (res.ok) {
                    setClips(clips.map(c => c.id === id ? { ...c, is_successful: true } : c));
                    if (selectedClip?.id === id) {
                        setSelectedClip({ ...selectedClip, is_successful: true });
                    }
                }
            }
        } catch (error) {
            console.error("Failed to approve clip", error);
        }
    };

    const handleReject = async (id: string) => {
        const clip = clips.find(c => c.id === id);
        if (!clip) return;

        try {
            if (clip.is_successful === false) {
                const res = await fetch(`${API}/clips/${id}/unset-approval`, { method: "PATCH" });
                if (res.ok) {
                    setClips(clips.map(c => c.id === id ? { ...c, is_successful: null } : c));
                    if (selectedClip?.id === id) {
                        setSelectedClip({ ...selectedClip, is_successful: null });
                    }
                }
            } else {
                const res = await fetch(`${API}/clips/${id}/reject`, { method: "PATCH" });
                if (res.ok) {
                    setClips(clips.map(c => c.id === id ? { ...c, is_successful: false } : c));
                    if (selectedClip?.id === id) {
                        setSelectedClip({ ...selectedClip, is_successful: false });
                    }
                }
            }
        } catch (error) {
            console.error("Failed to reject clip", error);
        }
    };

    const handleDownload = (id: string) => {
        const clip = clips.find(c => c.id === id) || selectedClip;
        if (clip && clip.file_url) {
            window.open(clip.file_url, "_blank");
        }
    };

    const getScoreColor = (score: number) => {
        if (score >= 7) return "text-green-400";
        if (score >= 5) return "text-yellow-400";
        return "text-red-400";
    };

    const getRoleColor = (role: string) => {
        switch (role?.toLowerCase()) {
            case "launch": return "bg-purple-500/20 text-purple-400 border-purple-500/30";
            case "viral": return "bg-cyan-500/20 text-cyan-400 border-cyan-500/30";
            case "fan_service": return "bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
            case "context_builder": return "bg-gray-500/20 text-gray-400 border-gray-500/30";
            default: return "bg-gray-800 text-gray-400 border-gray-700";
        }
    };

    const formatDuration = (seconds: number) => {
        if (!seconds) return "0:00";
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, "0")}`;
    };

    const activeJobs = jobs.filter(j => ['processing', 'queued', 'running', 'awaiting_speaker_confirm'].includes(j.status));
    const completedJobs = jobs.filter(j => ['completed', 'failed', 'error'].includes(j.status));

    const filteredProjects = completedJobs.filter(job => {
        const jobClips = clips.filter(c => c.job_id === job.id);
        if (filter === "all") return true;
        if (filter === "successful") return jobClips.some(c => c.is_successful === true);
        if (filter === "failed") return jobClips.some(c => c.is_successful === false);
        if (filter === "pending") return jobClips.some(c => c.is_successful === null);
        return true;
    });

    const projectClips = selectedJob ? clips.filter(c => c.job_id === selectedJob.id) : [];
    const filteredProjectClips = projectClips.filter(clip => {
        if (filter === "all") return true;
        if (filter === "successful") return clip.is_successful === true;
        if (filter === "failed") return clip.is_successful === false;
        if (filter === "pending") return clip.is_successful === null;
        return true;
    });

    return (
        <div className="min-h-screen bg-black text-white p-6 pb-24 flex">
            <div className="flex-1 transition-all duration-300">
                {/* Header Row */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
                    <h1 className="text-2xl font-bold">Clip Library</h1>

                    <div className="flex items-center gap-4 bg-[#0d0d0d] p-1.5 rounded-lg border border-gray-800">
                        {(["all", "successful", "failed", "pending"] as FilterType[]).map((f) => (
                            <button
                                key={f}
                                onClick={() => setFilter(f)}
                                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${filter === f
                                    ? "bg-purple-600 text-white"
                                    : "text-gray-400 hover:text-white hover:bg-white/5"
                                    }`}
                            >
                                {f.charAt(0).toUpperCase() + f.slice(1)}
                            </button>
                        ))}
                    </div>

                    <div className="relative">
                        <select
                            value={activeChannelId}
                            onChange={(e) => {
                                setActiveChannelId(e.target.value);
                                setSelectedJob(null);
                            }}
                            className="appearance-none bg-[#0d0d0d] border border-gray-800 text-white px-4 py-2 pr-10 rounded-lg focus:outline-none focus:ring-1 focus:ring-purple-500"
                        >
                            {channels.length === 0 ? (
                                <option value="">No channels</option>
                            ) : (
                                channels.map((ch) => (
                                    <option key={ch.id} value={ch.id}>
                                        {ch.name}
                                    </option>
                                ))
                            )}
                        </select>
                        <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                    </div>
                </div>

                {/* Content */}
                {loading ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {[...Array(6)].map((_, i) => (
                            <div key={i} className="bg-[#0d0d0d] border border-gray-800 rounded-2xl overflow-hidden animate-pulse">
                                <div className="w-full aspect-[16/9] bg-[#141414]"></div>
                                <div className="p-4 space-y-3">
                                    <div className="h-4 bg-gray-800 rounded w-3/4"></div>
                                    <div className="h-3 bg-gray-800 rounded w-1/2"></div>
                                </div>
                            </div>
                        ))}
                    </div>
                ) : !selectedJob ? (
                    <AnimatePresence mode="wait">
                        <motion.div
                            key="projects-view"
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -10 }}
                            transition={{ duration: 0.2 }}
                        >
                            {activeJobs.length > 0 && (
                                <div className="mb-8">
                                    <h2 className="text-[13px] uppercase tracking-wider text-[#6b7280] font-semibold mb-4 flex items-center gap-2">
                                        Active Jobs
                                        <span className="w-2 h-2 rounded-full bg-violet-500 animate-pulse" />
                                    </h2>
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                        {activeJobs.map(job => (
                                            <ActiveJobCard key={job.id} initialJob={job} onComplete={handleJobComplete} />
                                        ))}
                                    </div>
                                </div>
                            )}

                            <div>
                                <h2 className="text-[13px] uppercase tracking-wider text-[#6b7280] font-semibold mb-4">Projects</h2>
                                {filteredProjects.length === 0 ? (
                                    <div className="flex flex-col items-center justify-center py-20 bg-[#0d0d0d] border border-gray-800 rounded-xl">
                                        <FileVideo className="w-16 h-16 text-gray-700 mb-4" />
                                        <h3 className="text-xl font-medium text-gray-300">No projects found</h3>
                                        <p className="text-[#6b7280] mt-2">Start your first job to extract clips</p>
                                    </div>
                                ) : (
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                        {filteredProjects.map(job => (
                                            <ProjectCard
                                                key={job.id}
                                                job={job}
                                                clips={clips.filter(c => c.job_id === job.id)}
                                                onClick={() => setSelectedJob(job)}
                                                onDelete={() => handleDeleteProject(job.id)}
                                            />
                                        ))}
                                    </div>
                                )}
                            </div>
                        </motion.div>
                    </AnimatePresence>
                ) : (
                    <AnimatePresence mode="wait">
                        <motion.div
                            key="clips-view"
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -10 }}
                            transition={{ duration: 0.2 }}
                            className="w-full"
                        >
                            <div className="mb-6 flex items-center">
                                <button
                                    onClick={() => setSelectedJob(null)}
                                    className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors text-sm font-medium bg-[#0d0d0d] hover:bg-white/5 border border-white/[0.06] px-4 py-2 rounded-lg"
                                >
                                    <ArrowLeft className="w-4 h-4" />
                                    Back to Projects
                                </button>
                            </div>

                            <div className="mb-6 flex items-center justify-between border-b border-gray-800 pb-4">
                                <div>
                                    <h2 className="text-xl font-bold">{selectedJob.video_title || "Project Clips"}</h2>
                                    <p className="text-sm text-gray-500 mt-1">{formatDate(selectedJob.created_at)}</p>
                                </div>
                            </div>

                            {filteredProjectClips.length === 0 ? (
                                <div className="flex flex-col items-center justify-center py-20 bg-[#0d0d0d] border border-gray-800 rounded-xl">
                                    <FileVideo className="w-16 h-16 text-gray-700 mb-4" />
                                    <h3 className="text-xl font-medium text-gray-300">No clips found</h3>
                                    <p className="text-[#6b7280] mt-2">Try changing your filter</p>
                                </div>
                            ) : (
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                    {filteredProjectClips.map((clip) => (
                                        <div
                                            key={clip.id}
                                            className="bg-[#0d0d0d] border border-gray-800 hover:border-purple-500/50 rounded-xl overflow-hidden cursor-pointer transition-colors group flex flex-col"
                                            onClick={() => setSelectedClip(clip)}
                                        >
                                            <div className="w-full aspect-[9/16] bg-[#141414] relative flex items-center justify-center group-hover:bg-[#1a1a1a] transition-colors overflow-hidden">
                                                {clip.file_url ? (
                                                    <video
                                                        src={clip.file_url}
                                                        className="w-full h-full object-cover"
                                                        muted
                                                        playsInline
                                                        preload="metadata"
                                                    />
                                                ) : (
                                                    <Play className="w-12 h-12 text-white/20" />
                                                )}
                                                <div className="absolute bottom-2 right-2 bg-black/80 px-2 py-1 rounded text-xs font-medium text-white">
                                                    {formatDuration(clip.duration)}
                                                </div>
                                                {clip.is_successful === true && (
                                                    <div className="absolute top-2 right-2 bg-green-500/90 text-white p-1 rounded-full">
                                                        <Check className="w-4 h-4" />
                                                    </div>
                                                )}
                                                {clip.is_successful === false && (
                                                    <div className="absolute top-2 right-2 bg-red-500/90 text-white p-1 rounded-full">
                                                        <X className="w-4 h-4" />
                                                    </div>
                                                )}
                                            </div>

                                            <div className="p-4 flex flex-col flex-1">
                                                <p className="text-sm text-gray-300 line-clamp-2 mb-3 h-10">
                                                    "{clip.hook_text || "No hook text generated..."}"
                                                </p>

                                                <div className="flex gap-3 text-xs font-medium mb-3">
                                                    <span className={getScoreColor(clip.standalone_score)}>
                                                        St: {clip.standalone_score || 0}/10
                                                    </span>
                                                    <span className={getScoreColor(clip.hook_score)}>
                                                        Hk: {clip.hook_score || 0}/10
                                                    </span>
                                                    <span className={getScoreColor(clip.arc_score)}>
                                                        Ar: {clip.arc_score || 0}/10
                                                    </span>
                                                </div>

                                                <div className="mb-4">
                                                    <span className={`text-xs px-2 py-1 rounded-md border ${getRoleColor(clip.clip_strategy_role)}`}>
                                                        {clip.clip_strategy_role || "unassigned"}
                                                    </span>
                                                </div>

                                                <div className="mt-auto flex items-center justify-between pt-3 border-t border-gray-800">
                                                    <button
                                                        onClick={(e) => { e.stopPropagation(); handleDownload(clip.id); }}
                                                        className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
                                                        title="Download"
                                                    >
                                                        <Download className="w-4 h-4" />
                                                    </button>
                                                    <div className="flex items-center gap-2">
                                                        <button
                                                            onClick={(e) => { e.stopPropagation(); handleApprove(clip.id); }}
                                                            className="p-2 text-gray-400 hover:text-green-400 hover:bg-green-400/10 rounded-lg transition-colors"
                                                            title="Approve"
                                                        >
                                                            <Check className="w-4 h-4" />
                                                        </button>
                                                        <button
                                                            onClick={(e) => { e.stopPropagation(); handleReject(clip.id); }}
                                                            className="p-2 text-gray-400 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-colors"
                                                            title="Reject"
                                                        >
                                                            <X className="w-4 h-4" />
                                                        </button>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </motion.div>
                    </AnimatePresence>
                )}
            </div>

            {/* Slide-in Detail Panel */}
            <div
                className={`fixed inset-y-0 right-0 w-full md:w-[450px] bg-[#0d0d0d] border-l border-gray-800 shadow-2xl transform transition-transform duration-300 ease-in-out z-50 flex flex-col ${selectedClip ? "translate-x-0" : "translate-x-full"
                    }`}
            >
                {selectedClip && (
                    <>
                        <div className="p-4 border-b border-gray-800 flex items-center justify-between">
                            <h2 className="text-lg font-semibold">Clip Details</h2>
                            <button
                                onClick={() => setSelectedClip(null)}
                                className="p-2 text-gray-400 hover:text-white rounded-lg transition-colors"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto p-6 space-y-8">
                            <div className="w-full aspect-[9/16] bg-[#141414] rounded-xl flex items-center justify-center border border-gray-800 relative overflow-hidden">
                                {selectedClip.file_url ? (
                                    <video
                                        src={selectedClip.file_url}
                                        controls
                                        playsInline
                                        className="w-full h-full rounded-xl"
                                    />
                                ) : (
                                    <div className="flex items-center justify-center h-full text-gray-500">
                                        No video available
                                    </div>
                                )}
                            </div>

                            <div>
                                <h3 className="text-sm font-medium text-gray-400 mb-2">Hook Text</h3>
                                <p className="text-base leading-relaxed bg-black/50 p-4 rounded-lg border border-gray-800">
                                    {selectedClip.hook_text || "No hook text generated"}
                                </p>
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <h3 className="text-sm font-medium text-gray-400 mb-2">Strategy Role</h3>
                                    <span className={`inline-block text-xs px-2.5 py-1 rounded-md border ${getRoleColor(selectedClip.clip_strategy_role)}`}>
                                        {selectedClip.clip_strategy_role || "unassigned"}
                                    </span>
                                </div>
                                <div>
                                    <h3 className="text-sm font-medium text-gray-400 mb-2">Posting Order</h3>
                                    <div className="text-lg font-medium">#{selectedClip.posting_order || 0}</div>
                                </div>
                            </div>

                            <div>
                                <h3 className="text-sm font-medium text-gray-400 mb-4">Quality Scores</h3>
                                <div className="space-y-4">
                                    {[
                                        { label: "Standalone", value: selectedClip.standalone_score },
                                        { label: "Hook", value: selectedClip.hook_score },
                                        { label: "Arc", value: selectedClip.arc_score }
                                    ].map((score, idx) => (
                                        <div key={idx}>
                                            <div className="flex justify-between text-sm mb-1.5">
                                                <span className="text-gray-300">{score.label}</span>
                                                <span className={`font-medium ${getScoreColor(score.value)}`}>
                                                    {score.value || 0}/10
                                                </span>
                                            </div>
                                            <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                                                <div
                                                    className={`h-full rounded-full ${score.value >= 7 ? "bg-green-500" : score.value >= 5 ? "bg-yellow-500" : "bg-red-500"}`}
                                                    style={{ width: `${(score.value || 0) * 10}%` }}
                                                />
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <div>
                                <h3 className="text-sm font-medium text-gray-400 mb-2">AI Reasoning</h3>
                                <p className="text-sm text-gray-300 leading-relaxed bg-black/50 p-4 rounded-lg border border-gray-800">
                                    {selectedClip.standalone_result ||
                                        selectedClip.quality_notes ||
                                        (Array.isArray((selectedClip as any).thinking_steps)
                                            ? (selectedClip as any).thinking_steps.join(' → ')
                                            : (selectedClip as any).thinking_steps) ||
                                        "No reasoning provided."}
                                </p>
                            </div>

                            {selectedClip.is_successful === false && selectedClip.why_failed && (
                                <div>
                                    <h3 className="text-sm font-medium text-red-400 mb-2">Failure Reason</h3>
                                    <p className="text-sm text-red-200 leading-relaxed bg-red-500/10 p-4 rounded-lg border border-red-500/20">
                                        {selectedClip.why_failed}
                                    </p>
                                </div>
                            )}
                        </div>

                        <div className="p-4 border-t border-gray-800 bg-[#0d0d0d] flex gap-3">
                            <button
                                onClick={() => handleDownload(selectedClip.id)}
                                className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-gray-800 hover:bg-gray-700 text-white rounded-lg font-medium transition-colors"
                            >
                                <Download className="w-4 h-4" /> Download
                            </button>
                            <button
                                onClick={() => handleApprove(selectedClip.id)}
                                className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-green-500/10 hover:bg-green-500/20 text-green-400 border border-green-500/20 rounded-lg font-medium transition-colors"
                            >
                                <Check className="w-4 h-4" /> Approve
                            </button>
                            <button
                                onClick={() => handleReject(selectedClip.id)}
                                className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 rounded-lg font-medium transition-colors"
                            >
                                <X className="w-4 h-4" /> Reject
                            </button>
                        </div>
                    </>
                )}
            </div>

            {selectedClip && (
                <div
                    className="fixed inset-0 bg-black/50 z-40 md:hidden"
                    onClick={() => setSelectedClip(null)}
                />
            )}
        </div>
    );
}
