"use client";

import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { Play, Clock, CheckCircle2, AlertCircle, MoreHorizontal } from "lucide-react";
import Link from "next/link";
import { useChannel } from "./layout";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Job = {
    id: string;
    video_title: string;
    status: string;
    progress?: number;
    progress_pct?: number;
    step?: string;
    created_at?: string;
    error?: string;
};

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
        if (job.status === 'completed' || job.status === 'failed' || job.status === 'error') return;

        const interval = setInterval(async () => {
            try {
                const res = await fetch(`${API}/jobs/${job.id}`);
                if (res.ok) {
                    const data = await res.json();
                    setJob(data);
                    if (data.status === 'completed' || data.status === 'failed' || data.status === 'error') {
                        onComplete(data);
                    }
                }
            } catch (err) { }
        }, 3000);

        return () => clearInterval(interval);
    }, [job.id]); // Removed job.status and onComplete to prevent unnecessary remounts and state clearing

    const progress = job.progress_pct ?? job.progress ?? 0;
    const isAwaiting = job.status === 'awaiting_speaker_confirm';

    return (
        <div className="bg-[#0d0d0d] border border-white/[0.06] rounded-2xl overflow-hidden flex flex-col h-full">
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

type Clip = {
    id: number | string;
    hook: string;
    score: number;
    path: string;
    suggested_title?: string;
    created_at?: string;
};

function CountUp({ value, isFloat = false, suffix = "" }: { value: number; isFloat?: boolean; suffix?: string }) {
    const [count, setCount] = useState(0);

    useEffect(() => {
        let startTime: number | null = null;
        const duration = 1000;

        const animate = (currentTime: number) => {
            if (!startTime) startTime = currentTime;
            const progress = Math.min((currentTime - startTime) / duration, 1);

            const ease = 1 - Math.pow(1 - progress, 3);
            setCount(value * ease);

            if (progress < 1) {
                requestAnimationFrame(animate);
            } else {
                setCount(value);
            }
        };

        requestAnimationFrame(animate);
    }, [value]);

    return (
        <>
            {isFloat
                ? count.toFixed(1)
                : count.toLocaleString("en-US", { maximumFractionDigits: 0 })
            }
            {suffix}
        </>
    );
}

export default function DashboardPage() {
    const { activeChannelId } = useChannel();

    const [jobs, setJobs] = useState<Job[]>([]);
    const [clips, setClips] = useState<Clip[]>([]);
    const [loadingDashboard, setLoadingDashboard] = useState(true);
    const [dashboardError, setDashboardError] = useState("");

    const fetchDashboardData = async () => {
        setLoadingDashboard(true);
        setDashboardError("");
        try {
            const jobsRes = await fetch(`${API}/jobs?channel_id=${activeChannelId}&limit=20`);
            if (jobsRes.ok) {
                setJobs(await jobsRes.json());
            }

            const clipsRes = await fetch(`${API}/clips?channel_id=${activeChannelId}&limit=4`);
            if (clipsRes.ok) {
                setClips(await clipsRes.json());
            }
        } catch (err) {
            console.error("Dashboard fetch error", err);
            setDashboardError("Failed to load dashboard data.");
        } finally {
            setLoadingDashboard(false);
        }
    };

    useEffect(() => {
        if (!activeChannelId) return;
        fetchDashboardData();
    }, [activeChannelId]);

    const handleJobComplete = (updatedJob: any) => {
        setJobs((prev) => prev.map(j => j.id === updatedJob.id ? updatedJob : j));
        fetchDashboardData();
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
            className={`max-w-6xl mx-auto space-y-8 ${loadingDashboard ? "opacity-50 pointer-events-none animate-pulse" : ""}`}
        >
            {dashboardError && (
                <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm flex items-center gap-2">
                    <AlertCircle className="w-4 h-4" />
                    {dashboardError}
                </div>
            )}

            {/* Row 1: Stat Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                {/* Total Clips */}
                <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0 * 0.08, duration: 0.3 }}
                    className="bg-[#0d0d0d] border border-white/[0.06] rounded-lg p-5 hover:border-l-[#7c3aed] hover:border-l-2 transition-all"
                >
                    <div className="text-[#6b7280] text-sm mb-1">Total Clips</div>
                    <div className="flex items-end justify-between">
                        <div className="text-3xl font-bold">
                            {loadingDashboard ? "..." : <CountUp value={clips.length} />}
                        </div>
                        <div className="flex items-center text-gray-500 text-xs font-medium bg-gray-500/10 px-2 py-0.5 rounded">
                            —
                        </div>
                    </div>
                    <div className="text-[#6b7280] text-xs mt-2">total from api</div>
                </motion.div>

                {/* This Month Views */}
                <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 1 * 0.08, duration: 0.3 }}
                    className="bg-[#0d0d0d] border border-white/[0.06] rounded-lg p-5 hover:border-l-[#7c3aed] hover:border-l-2 transition-all"
                >
                    <div className="text-[#6b7280] text-sm mb-1">This Month Views</div>
                    <div className="flex items-end justify-between">
                        <div className="text-3xl font-bold">0</div>
                        <div className="flex items-center text-gray-500 text-xs font-medium bg-gray-500/10 px-2 py-0.5 rounded">
                            —
                        </div>
                    </div>
                    <div className="text-[#6b7280] text-xs mt-2">across platforms (pending)</div>
                </motion.div>

                {/* Avg Performance */}
                <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 2 * 0.08, duration: 0.3 }}
                    className="bg-[#0d0d0d] border border-white/[0.06] rounded-lg p-5 hover:border-l-[#7c3aed] hover:border-l-2 transition-all flex items-center justify-between"
                >
                    <div>
                        <div className="text-[#6b7280] text-sm mb-1">Avg Performance</div>
                        <div className="text-3xl font-bold">0<span className="text-lg text-[#6b7280]">%</span></div>
                        <div className="text-[#6b7280] text-xs mt-2">virality score</div>
                    </div>
                    <div className="relative w-14 h-14">
                        <svg className="w-full h-full transform -rotate-90">
                            <circle cx="28" cy="28" r="24" fill="none" stroke="#1a1a1a" strokeWidth="6" />
                            <circle
                                cx="28"
                                cy="28"
                                r="24"
                                fill="none"
                                stroke="#06b6d4"
                                strokeWidth="6"
                                strokeDasharray={`0 150`}
                                strokeLinecap="round"
                            />
                        </svg>
                    </div>
                </motion.div>

                {/* Pipeline Cost */}
                <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 3 * 0.08, duration: 0.3 }}
                    className="bg-[#0d0d0d] border border-white/[0.06] rounded-lg p-5 hover:border-l-[#7c3aed] hover:border-l-2 transition-all"
                >
                    <div className="text-[#6b7280] text-sm mb-1">Pipeline Cost</div>
                    <div className="text-3xl font-bold">$0.00</div>
                    <div className="text-[#6b7280] text-xs mt-2">this billing cycle</div>
                </motion.div>
            </div>

            {/* Row 2: Active Jobs */}
            <div>
                <div className="flex items-center gap-2 mb-4">
                    <h2 className="text-[13px] uppercase tracking-wider text-[#6b7280] font-semibold">Active Jobs</h2>
                    {jobs.some(j => ['processing', 'queued', 'running', 'awaiting_speaker_confirm'].includes(j.status)) && (
                        <span className="w-2 h-2 rounded-full bg-violet-500 animate-pulse" />
                    )}
                </div>

                {jobs.filter(j => ['processing', 'queued', 'running', 'awaiting_speaker_confirm'].includes(j.status)).length === 0 ? (
                    <div className="bg-[#0d0d0d] border border-white/[0.06] rounded-lg p-8 text-center">
                        <p className="text-[#6b7280] text-sm">No active jobs</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {jobs.filter(j => ['processing', 'queued', 'running', 'awaiting_speaker_confirm'].includes(j.status)).map((job, index) => (
                            <motion.div
                                key={job.id}
                                initial={{ opacity: 0, x: -12 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: index * 0.06 }}
                            >
                                <ActiveJobCard initialJob={job} onComplete={handleJobComplete} />
                            </motion.div>
                        ))}
                    </div>
                )}
            </div>

            {/* Row 3: Two Columns */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Recent Clips */}
                <div>
                    <h2 className="text-[13px] uppercase tracking-wider text-[#6b7280] font-semibold mb-4">Recent Clips</h2>

                    {clips.length === 0 ? (
                        <div className="bg-[#0d0d0d] border border-white/[0.06] rounded-lg p-8 text-center h-[220px] flex items-center justify-center">
                            <p className="text-[#6b7280] text-sm">No clips yet. Start your first job.</p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-2 gap-4">
                            {clips.slice(0, 4).map((clip, index) => {
                                const scoreColor = clip.score >= 90 ? "text-green-400 border-green-500/20" :
                                    clip.score >= 80 ? "text-orange-400 border-orange-500/20" :
                                        "text-blue-400 border-blue-500/20";
                                return (
                                    <motion.div
                                        key={clip.id}
                                        initial={{ opacity: 0, y: 16 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        transition={{ delay: index * 0.08, duration: 0.3 }}
                                        className="bg-[#0d0d0d] border border-white/[0.06] rounded-lg p-3 group hover:bg-white/[0.02] transition-colors cursor-pointer relative overflow-hidden"
                                    >
                                        <div className={`absolute top-2 right-2 flex items-center gap-1 bg-[#0a0a0a]/80 backdrop-blur px-1.5 py-0.5 rounded text-[10px] font-bold border z-10 ${scoreColor}`}>
                                            {clip.score}
                                        </div>
                                        <div className="aspect-video bg-[#1a1a1a] rounded mb-3 relative overflow-hidden">
                                            {clip.path ? (
                                                <video src={`${API}${clip.path}`} className="w-full h-full object-cover opacity-60 group-hover:opacity-80 transition-opacity" />
                                            ) : null}
                                            <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/40">
                                                <Play className="w-8 h-8 text-white" />
                                            </div>
                                        </div>
                                        <h3 className="text-sm font-medium line-clamp-1 mb-1 group-hover:text-[#7c3aed] transition-colors">
                                            {clip.suggested_title || `Clip ${clip.id}`}
                                        </h3>
                                        <p className="text-xs text-[#6b7280] line-clamp-2 italic">"{clip.hook}"</p>
                                    </motion.div>
                                );
                            })}
                        </div>
                    )}
                </div>

                {/* Channel Performance Chart Placeholder */}
                <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 2 * 0.08, duration: 0.3 }}
                >
                    <h2 className="text-[13px] uppercase tracking-wider text-[#6b7280] font-semibold mb-4">Channel Performance</h2>
                    <div className="bg-[#0d0d0d] border border-white/[0.06] rounded-lg p-6 h-[220px] flex flex-col">
                        <div className="flex justify-between items-center mb-4">
                            <div className="text-xs text-[#6b7280]">Total Views (30 Days)</div>
                            <div className="text-xs font-medium text-white bg-white/10 px-2 py-1 rounded">Daily</div>
                        </div>
                        <div className="flex-1 w-full relative">
                            {/* Fake SVG Chart */}
                            <svg viewBox="0 0 400 100" className="w-full h-full preserve-3d" preserveAspectRatio="none">
                                <defs>
                                    <linearGradient id="gradient" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#7c3aed" stopOpacity="0.3" />
                                        <stop offset="100%" stopColor="#7c3aed" stopOpacity="0" />
                                    </linearGradient>
                                </defs>
                                <path
                                    d="M0,80 Q40,90 80,60 T160,50 T240,70 T320,30 T400,10 L400,100 L0,100 Z"
                                    fill="url(#gradient)"
                                />
                                <path
                                    d="M0,80 Q40,90 80,60 T160,50 T240,70 T320,30 T400,10"
                                    fill="none"
                                    stroke="#7c3aed"
                                    strokeWidth="2"
                                    vectorEffect="non-scaling-stroke"
                                />
                            </svg>
                        </div>
                    </div>
                </motion.div>
            </div>
        </motion.div>
    );
}