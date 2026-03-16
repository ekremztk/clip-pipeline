"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_API = API.replace(/^http/, "ws");
import {
  LayoutDashboard,
  Plus,
  Film,
  BarChart2,
  Brain,
  Settings,
  Bell,
  PanelLeftClose,
  PanelLeftOpen,
  ChevronDown,
  Upload,
  Play,
  TrendingUp,
  Clock,
  CheckCircle2,
  AlertCircle
} from "lucide-react";

type PageState =
  | "dashboard"
  | "new-clip"
  | "library"
  | "performance"
  | "memory"
  | "settings";

type Channel = {
  id: string;
  name: string;
};

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

// Helper to animate numbers
function CountUp({ value, isFloat = false, suffix = "" }: { value: number; isFloat?: boolean; suffix?: string }) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let startTime: number | null = null;
    const duration = 1000;

    const animate = (currentTime: number) => {
      if (!startTime) startTime = currentTime;
      const progress = Math.min((currentTime - startTime) / duration, 1);

      // easeOutExpo
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

export default function PrognotStudio() {
  const [activePage, setActivePage] = useState<PageState>("dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Real Data States
  const [channels, setChannels] = useState<Channel[]>([]);
  const [activeChannelId, setActiveChannelId] = useState<string>("speedy_cast");

  const [jobs, setJobs] = useState<Job[]>([]);
  const [clips, setClips] = useState<Clip[]>([]);

  const [loadingDashboard, setLoadingDashboard] = useState(true);
  const [dashboardError, setDashboardError] = useState("");

  // WebSocket connections map
  const wsConnections = useRef<Record<string, WebSocket>>({});

  // New Clip Job Form State
  const [isDragging, setIsDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [guestName, setGuestName] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };
  const handleDragLeave = () => setIsDragging(false);
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files?.length) setFile(e.dataTransfer.files[0]);
  };

  // --- Fetch Data ---
  useEffect(() => {
    const fetchChannels = async () => {
      try {
        const res = await fetch(`${API}/channels`);
        if (res.ok) {
          const data = await res.json();
          setChannels(data);
          if (data.length > 0 && !data.find((c: Channel) => c.id === activeChannelId)) {
            setActiveChannelId(data[0].id);
          }
        }
      } catch (err) {
        console.error("Failed to fetch channels", err);
      }
    };
    fetchChannels();
  }, []);

  useEffect(() => {
    if (!activeChannelId) return;

    const fetchDashboardData = async () => {
      setLoadingDashboard(true);
      setDashboardError("");
      try {
        // Fetch recent jobs
        const jobsRes = await fetch(`${API}/jobs?channel_id=${activeChannelId}&limit=20`);
        let jobsData = [];
        if (jobsRes.ok) {
          jobsData = await jobsRes.json();
          setJobs(jobsData);
        }

        // Fetch recent clips
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
  }, [activeChannelId, activePage]);

  // --- WebSockets for Active Jobs ---
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

    // Cleanup closed/finished jobs
    Object.keys(wsConnections.current).forEach(id => {
      const job = jobs.find(j => j.id === id);
      if (!job || (job.status !== "processing" && job.status !== "queued" && job.status !== "running")) {
        wsConnections.current[id].close();
        delete wsConnections.current[id];
      }
    });

    return () => {
      // Cleanup on unmount handled gracefully
    };
  }, [jobs]);

  // --- Submissions ---
  const handleStartProcessing = async () => {
    if (!file || !title || !activeChannelId) return;

    setIsSubmitting(true);
    setSubmitError("");

    const formData = new FormData();
    formData.append("video", file);
    formData.append("title", title);
    if (guestName) formData.append("guest_name", guestName);
    formData.append("channel_id", activeChannelId);

    try {
      // NOTE: Using /upload based on previous API structure
      const res = await fetch(`${API}/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) throw new Error("Failed to start job");

      // Clear form
      setFile(null);
      setTitle("");
      setGuestName("");

      // Switch back to dashboard to see progress
      setActivePage("dashboard");
    } catch (err) {
      console.error(err);
      setSubmitError("Failed to start processing. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const navItems = [
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { id: "new-clip", label: "New Clip Job", icon: Plus },
    { id: "library", label: "Clip Library", icon: Film },
    { id: "performance", label: "Performance", icon: BarChart2 },
    { id: "memory", label: "Channel Memory", icon: Brain },
    { id: "settings", label: "Channel Settings", icon: Settings },
  ] as const;

  return (
    <div className="min-h-screen bg-[#000000] text-[#e5e5e5] font-sans flex">
      {/* ─── SIDEBAR ──────────────────────────────────────────────────────── */}
      <aside
        className={`fixed left-0 top-0 bottom-0 bg-[#0d0d0d] border-r border-white/[0.06] transition-all duration-300 z-50 flex flex-col ${sidebarOpen ? "w-[240px]" : "w-[60px]"
          }`}
      >
        {/* Logo Area */}
        <div className="h-16 flex items-center px-4 border-b border-white/[0.06] overflow-hidden whitespace-nowrap">
          {sidebarOpen ? (
            <div className="flex items-center gap-1.5 font-bold tracking-tight">
              <span className="text-white text-lg">PROGNOT</span>
              <span className="text-[#7c3aed] text-lg">STUDIO</span>
            </div>
          ) : (
            <div className="w-full flex justify-center text-[#7c3aed] font-bold text-xl">
              P
            </div>
          )}
        </div>

        {/* Nav Items */}
        <div className="flex-1 py-6 flex flex-col gap-1 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activePage === item.id;
            return (
              <motion.button
                key={item.id}
                whileHover={{ x: 2 }}
                transition={{ duration: 0.15 }}
                onClick={() => setActivePage(item.id)}
                className={`relative flex items-center h-10 transition-colors group ${sidebarOpen ? "px-4" : "justify-center"
                  } ${isActive
                    ? "bg-[#0d0d0d] text-white"
                    : "text-[#6b7280] hover:bg-white/[0.03] hover:text-[#e5e5e5]"
                  }`}
                title={!sidebarOpen ? item.label : undefined}
              >
                {isActive && (
                  <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-[#7c3aed]" />
                )}
                <Icon
                  className={`w-5 h-5 flex-shrink-0 ${isActive ? "text-[#7c3aed]" : ""
                    }`}
                />
                {sidebarOpen && (
                  <span
                    className={`ml-3 text-sm font-medium ${isActive ? "text-white" : ""
                      }`}
                  >
                    {item.label}
                  </span>
                )}
              </motion.button>
            );
          })}
        </div>

        {/* Collapse Button */}
        <div className="p-2 border-t border-white/[0.06]">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="w-full flex items-center justify-center h-10 text-[#6b7280] hover:bg-white/[0.03] hover:text-[#e5e5e5] rounded-md transition-colors"
          >
            {sidebarOpen ? (
              <PanelLeftClose className="w-5 h-5" />
            ) : (
              <PanelLeftOpen className="w-5 h-5" />
            )}
          </button>
        </div>
      </aside>

      {/* ─── MAIN CONTENT AREA ────────────────────────────────────────────── */}
      <div
        className={`flex-1 flex flex-col transition-all duration-300 ${sidebarOpen ? "ml-[240px]" : "ml-[60px]"
          }`}
      >
        {/* TOP BAR */}
        <header className="h-16 bg-[#000000] border-b border-white/[0.06] flex items-center justify-between px-6 sticky top-0 z-40">
          <div className="flex items-center">
            {/* Channel Selector Pill */}
            <div className="relative">
              <select
                value={activeChannelId}
                onChange={(e) => setActiveChannelId(e.target.value)}
                className="appearance-none flex items-center gap-2 pl-4 pr-10 py-1.5 rounded-full border border-[#7c3aed] bg-transparent text-sm font-medium hover:bg-[#7c3aed]/10 transition-colors text-[#e5e5e5] cursor-pointer focus:outline-none"
              >
                {channels.length > 0 ? (
                  channels.map(c => (
                    <option key={c.id} value={c.id} className="bg-[#0d0d0d]">{c.name}</option>
                  ))
                ) : (
                  <option value="speedy_cast" className="bg-[#0d0d0d]">Speedy Cast</option>
                )}
              </select>
              <ChevronDown className="w-4 h-4 text-[#6b7280] absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button className="text-[#6b7280] hover:text-white transition-colors relative">
              <Bell className="w-5 h-5" />
              <span className="absolute top-0 right-0 w-2 h-2 bg-[#7c3aed] rounded-full border-2 border-black" />
            </button>
            <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-[#7c3aed] to-[#06b6d4] flex items-center justify-center cursor-pointer border border-white/10">
              <span className="text-xs font-bold text-white">SC</span>
            </div>
          </div>
        </header>

        {/* PAGE CONTENT */}
        <main className="flex-1 p-6 overflow-y-auto">
          <AnimatePresence mode="wait">
            {activePage === "dashboard" && (
              <motion.div
                key="dashboard"
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
            )}

            {activePage === "new-clip" && (
              <motion.div
                key="new-clip"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2 }}
                className="max-w-3xl mx-auto"
              >
                <h1 className="text-2xl font-bold mb-8">New Clip Job</h1>

                <div className="space-y-6">
                  {/* Dropzone */}
                  <div
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                    className={`border-2 border-dashed rounded-lg p-12 flex flex-col items-center justify-center text-center transition-colors ${isDragging
                      ? "border-[#7c3aed] bg-[#7c3aed]/10"
                      : file
                        ? "border-green-500/50 bg-green-500/5"
                        : "border-[#7c3aed]/30 bg-[#0d0d0d] hover:border-[#7c3aed]/50 hover:bg-white/[0.02]"
                      }`}
                  >
                    {file ? (
                      <>
                        <CheckCircle2 className="w-12 h-12 text-green-500 mb-3" />
                        <div className="text-sm font-medium">{file.name}</div>
                        <div className="text-xs text-[#6b7280] mt-1">{(file.size / (1024 * 1024)).toFixed(2)} MB</div>
                        <button
                          onClick={(e) => { e.stopPropagation(); setFile(null); }}
                          className="mt-4 text-xs text-red-400 hover:text-red-300"
                        >
                          Remove file
                        </button>
                      </>
                    ) : (
                      <>
                        <Upload className={`w-12 h-12 mb-3 ${isDragging ? "text-[#7c3aed]" : "text-[#6b7280]"}`} />
                        <div className="text-sm font-medium mb-1">Drag and drop video file here</div>
                        <div className="text-xs text-[#6b7280]">or click to browse • MP4, MOV, WEBM</div>
                      </>
                    )}
                  </div>

                  {submitError && (
                    <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm flex items-center gap-2">
                      <AlertCircle className="w-4 h-4" />
                      {submitError}
                    </div>
                  )}

                  {/* Form Fields */}
                  <div className="bg-[#0d0d0d] border border-white/[0.06] rounded-lg p-6 space-y-5">
                    <div>
                      <label className="block text-xs font-medium text-[#6b7280] mb-1.5 uppercase tracking-wider">
                        Video Title *
                      </label>
                      <input
                        type="text"
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        placeholder="e.g. Joe Rogan #2054 - Elon Musk"
                        className="w-full bg-[#1a1a1a] border border-white/[0.1] rounded px-3 py-2 text-sm text-white placeholder-[#6b7280] focus:outline-none focus:border-[#7c3aed] transition-colors"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-[#6b7280] mb-1.5 uppercase tracking-wider">
                        Guest Name <span className="lowercase normal-case">(optional)</span>
                      </label>
                      <input
                        type="text"
                        value={guestName}
                        onChange={(e) => setGuestName(e.target.value)}
                        placeholder="e.g. Elon Musk"
                        className="w-full bg-[#1a1a1a] border border-white/[0.1] rounded px-3 py-2 text-sm text-white placeholder-[#6b7280] focus:outline-none focus:border-[#7c3aed] transition-colors"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-[#6b7280] mb-1.5 uppercase tracking-wider">
                        Channel
                      </label>
                      <select
                        value={activeChannelId}
                        onChange={(e) => setActiveChannelId(e.target.value)}
                        className="w-full bg-[#1a1a1a] border border-white/[0.1] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-[#7c3aed] transition-colors appearance-none"
                      >
                        {channels.length > 0 ? (
                          channels.map(c => <option key={c.id} value={c.id}>{c.name}</option>)
                        ) : (
                          <option value="speedy_cast">Speedy Cast</option>
                        )}
                      </select>
                    </div>
                  </div>

                  <motion.button
                    onClick={handleStartProcessing}
                    whileHover={!isSubmitting && file && title ? { scale: 1.02 } : {}}
                    whileTap={!isSubmitting && file && title ? { scale: 0.98 } : {}}
                    className={`w-full py-3 rounded text-sm font-semibold transition-all flex items-center justify-center gap-2 ${file && title && !isSubmitting
                      ? "bg-gradient-to-r from-[#7c3aed] to-[#6d28d9] text-white shadow-lg shadow-[#7c3aed]/20"
                      : "bg-[#1a1a1a] text-[#6b7280] cursor-not-allowed border border-white/[0.06]"
                      }`}
                    disabled={!file || !title || isSubmitting}
                  >
                    {isSubmitting ? (
                      <>
                        <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                        Uploading...
                      </>
                    ) : "Start Processing"}
                  </motion.button>
                </div>

                {/* Recent Jobs */}
                <div className="mt-12">
                  <h2 className="text-[13px] uppercase tracking-wider text-[#6b7280] font-semibold mb-4">Recent Jobs</h2>
                  <div className="space-y-2">
                    {jobs.length === 0 ? (
                      <p className="text-sm text-[#6b7280] p-4 text-center border border-white/[0.06] rounded-lg bg-[#0d0d0d]">No recent jobs</p>
                    ) : (
                      jobs.slice(0, 5).map((job, i) => (
                        <motion.div
                          key={job.id}
                          initial={{ opacity: 0, x: -12 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: i * 0.06 }}
                          className="flex items-center justify-between p-3 bg-[#0d0d0d] border border-white/[0.06] rounded-lg"
                        >
                          <div className="text-sm line-clamp-1 flex-1 pr-4">{job.video_title}</div>
                          <div className="flex items-center gap-3 shrink-0">
                            {job.status === "done" || job.status === "completed" ? (
                              <span className="text-xs font-medium text-green-500 bg-green-500/10 px-2 py-0.5 rounded flex items-center gap-1">
                                <CheckCircle2 className="w-3 h-3" /> Done
                              </span>
                            ) : job.status === "error" || job.status === "failed" ? (
                              <span className="text-xs font-medium text-red-500 bg-red-500/10 px-2 py-0.5 rounded flex items-center gap-1">
                                <AlertCircle className="w-3 h-3" /> Failed
                              </span>
                            ) : (
                              <span className="text-xs font-medium text-[#7c3aed] bg-[#7c3aed]/10 px-2 py-0.5 rounded flex items-center gap-1 capitalize">
                                <Clock className="w-3 h-3" /> {job.status}
                              </span>
                            )}
                          </div>
                        </motion.div>
                      ))
                    )}
                  </div>
                </div>
              </motion.div>
            )}

            {["library", "performance", "memory", "settings"].includes(activePage) && (
              <motion.div
                key={activePage}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2 }}
                className="flex flex-col items-center justify-center h-full text-center"
              >
                <div className="w-16 h-16 mb-4 rounded-full bg-white/[0.03] flex items-center justify-center border border-white/[0.06]">
                  {activePage === "library" && <Film className="w-6 h-6 text-[#6b7280]" />}
                  {activePage === "performance" && <BarChart2 className="w-6 h-6 text-[#6b7280]" />}
                  {activePage === "memory" && <Brain className="w-6 h-6 text-[#6b7280]" />}
                  {activePage === "settings" && <Settings className="w-6 h-6 text-[#6b7280]" />}
                </div>
                <h2 className="text-xl font-semibold mb-2 capitalize text-white">{activePage.replace("-", " ")}</h2>
                <p className="text-[#6b7280] text-sm max-w-sm">
                  This feature is currently under development and will be available soon.
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}
