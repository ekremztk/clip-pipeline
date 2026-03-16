"use client";

import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { Play, Clock, CheckCircle2, AlertCircle } from "lucide-react";
import { useChannel } from "./layout";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_API = API.replace(/^http/, "ws");

type Job = {
    id: string;
    video_title: string;
    status: string;
    progress?: number;
    step?: string;
    created_at?: string;
    error?: string;
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

    const wsConnections = useRef<Record<string, WebSocket>>({});

    useEffect(() => {
        if (!activeChannelId) return;

        const fetchDashboardData = async () => {
            setLoadingDashboard(true);
            setDashboardError("");
            try {
                const jobsRes = await fetch(`${API}/jobs?channel_id=${activeChannelId}&limit=20`);
                let jobsData = [];
                if (jobsRes.ok) {
                    jobsData = await jobsRes.json();
                    setJobs(jobsData);
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

        fetchDashboardData();
    }, [activeChannelId]);

    useEffect(() => {
        const activeJobs = jobs.filter((j) => j.status === "processing" || j.status === "queued" || j.status === "running");

        activeJobs.forEach((job) => {
            if (!wsConnections.current[job.id]) {
                const ws = new WebSocket(`${WS_API}/ws/jobs/${job.id}/progress`);

                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    setJobs((prevJobs) =>
                        prevJobs.map((pJob) =>
                            pJob.id === job.id
                                ? { ...pJob, progress: data.progress, step: data.step, status: data.status || pJob.status }
                                : pJob
                        )
                    );

                    if (data.status === "done" || data.status === "error" || data.status === "completed") {
                        ws.close();
                        delete wsConnections.current[job.id];
                    }
                };

                ws.onclose = () => {
                    delete wsConnections.current[job.id];
                };

                wsConnections.current[job.id] = ws;
            }
        });

        Object.keys(wsConnections.current).forEach(id => {
            const job = jobs.find(j => j.id === id);
            if (!job || (job.status !== "processing" && job.status !== "queued" && job.status !== "running")) {
                wsConnections.current[id].close();
                delete wsConnections.current[id];
            }
        });

        return () => { };
    }, [jobs]);

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
                    {jobs.some(j => j.status === "processing" || j.status === "queued" || j.status === "running") && (
                        <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                    )}
                </div>

                {jobs.filter(j => j.status === "processing" || j.status === "queued" || j.status === "running").length === 0 ? (
                    <div className="bg-[#0d0d0d] border border-white/[0.06] rounded-lg p-8 text-center">
                        <p className="text-[#6b7280] text-sm">No active jobs</p>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {jobs.filter(j => j.status === "processing" || j.status === "queued" || j.status === "running").map((job, index) => (
                            <motion.div
                                key={job.id}
                                initial={{ opacity: 0, x: -12 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: index * 0.06 }}
                                className="bg-[#0d0d0d] border border-white/[0.06] rounded-lg overflow-hidden"
                            >
                                <div className="p-4 border-b border-white/[0.06] flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <Clock className="w-5 h-5 text-[#06b6d4]" />
                                        <span className="font-medium text-sm line-clamp-1">{job.video_title}</span>
                                    </div>
                                    <div className="flex items-center gap-3 shrink-0">
                                        <span className="text-xs text-[#6b7280]">{job.step || "Initializing..."}</span>
                                        <span className="px-2.5 py-1 rounded bg-[#7c3aed]/10 text-[#7c3aed] text-xs font-medium border border-[#7c3aed]/20 capitalize">
                                            {job.status}
                                        </span>
                                    </div>
                                </div>
                                <div className="w-full h-1 bg-[#1a1a1a]">
                                    <div
                                        className="h-full bg-[#7c3aed] relative overflow-hidden transition-all duration-300"
                                        style={{ width: `${job.progress || 0}%` }}
                                    >
                                        <div className="absolute inset-0 bg-white/20 w-full animate-[shimmer_1.5s_infinite]" style={{ backgroundImage: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent)' }} />
                                    </div>
                                </div>
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