"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Zap,
  Film,
  FolderOpen,
  BarChart3,
  Brain,
  Settings,
  Bell,
  ChevronLeft,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Play,
  Download,
  Clock,
  CheckCircle,
  XCircle,
  Loader2,
  Plus,
  Upload,
  X,
  Copy,
  Check,
  RefreshCw,
  FileText,
  ArrowRight,
  User,
  ChevronDown,
} from "lucide-react";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://clip-pipeline-production.up.railway.app";

// ─── TYPES ──────────────────────────────────────────────────────────────────
type ClipResult = {
  index: number;
  hook: string;
  score: number;
  path: string;
  psychological_trigger?: string;
  rag_reference_used?: string;
  suggested_title?: string;
  suggested_description?: string;
  suggested_hashtags?: string;
  why_selected?: string;
  transcript_excerpt?: string;
  audio_energy_note?: string;
  id?: number;
  clip_index?: number;
  real_views?: number | null;
};

type JobResult = {
  clips: ClipResult[];
  original_title: string;
  clips_count: number;
};

type JobStatus = {
  status: "uploading" | "running" | "done" | "error";
  step: string;
  progress: number;
  result: JobResult | null;
  error: string | null;
};

type HistoryJob = {
  id: string;
  video_title: string;
  status: string;
  progress: number;
  created_at: string;
  updated_at: string;
};

type AppState = "idle" | "uploading" | "processing" | "success" | "error";
type ActivePage = "dashboard" | "newjob" | "library" | "performance" | "memory" | "settings";

// ─── HELPER COMPONENTS ──────────────────────────────────────────────────────

function AnimatedNumber({ value, duration = 1000 }: { value: number; duration?: number }) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let startTime: number;
    let animationFrame: number;

    const animate = (currentTime: number) => {
      if (!startTime) startTime = currentTime;
      const progress = Math.min((currentTime - startTime) / duration, 1);
      setCount(Math.floor(progress * value));

      if (progress < 1) {
        animationFrame = requestAnimationFrame(animate);
      }
    };

    animationFrame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationFrame);
  }, [value, duration]);

  return <span>{count.toLocaleString()}</span>;
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { icon: React.ReactNode; bg: string; text: string }> = {
    processing: { icon: <Loader2 className="w-3 h-3 animate-spin" />, bg: "bg-purple-500/20", text: "text-purple-400" },
    running: { icon: <Loader2 className="w-3 h-3 animate-spin" />, bg: "bg-purple-500/20", text: "text-purple-400" },
    completed: { icon: <CheckCircle className="w-3 h-3" />, bg: "bg-green-500/20", text: "text-green-400" },
    done: { icon: <CheckCircle className="w-3 h-3" />, bg: "bg-green-500/20", text: "text-green-400" },
    failed: { icon: <XCircle className="w-3 h-3" />, bg: "bg-red-500/20", text: "text-red-400" },
    error: { icon: <XCircle className="w-3 h-3" />, bg: "bg-red-500/20", text: "text-red-400" },
  };
  const { icon, bg, text } = config[status] || config.processing;

  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium ${bg} ${text}`}>
      {icon}
      {status === "running" ? "Processing" : status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

function CopyButton({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={handleCopy}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded transition-all bg-[#141414] hover:bg-[#1a1a1a] text-[#e5e5e5] border border-[rgba(255,255,255,0.06)]"
    >
      {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
      {copied ? "Copied" : label || "Copy"}
    </button>
  );
}

function MiniSparkline({ data, positive }: { data: number[]; positive: boolean }) {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const width = 60;
  const height = 20;
  const points = data.map((d, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((d - min) / range) * height;
    return `${x},${y}`;
  }).join(" ");

  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline
        points={points}
        fill="none"
        stroke={positive ? "#22c55e" : "#ef4444"}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═════════════════════════════════════════════════════════════════════════════
export default function PrognotStudio() {
  // --- State ---
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activePage, setActivePage] = useState<ActivePage>("dashboard");

  // --- Job State ---
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [guestName, setGuestName] = useState("");
  const [selectedChannel, setSelectedChannel] = useState("speedy-cast");
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [appState, setAppState] = useState<AppState>("idle");
  const [isDragging, setIsDragging] = useState(false);
  const [selectedClip, setSelectedClip] = useState<ClipResult | null>(null);

  // --- History State ---
  const [historyJobs, setHistoryJobs] = useState<HistoryJob[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // ── Load History ────────────────────────────────────────────────────────────
  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/history`);
      const data = await res.json();
      setHistoryJobs(data.jobs || []);
    } catch (e) {
      console.error("History load failed", e);
    }
    setHistoryLoading(false);
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // ── Polling ─────────────────────────────────────────────────────────────────
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (jobId && status?.status !== "done" && status?.status !== "error") {
      interval = setInterval(async () => {
        try {
          const res = await fetch(`${BACKEND_URL}/status/${jobId}`);
          const data = await res.json();
          setStatus(data);
          if (data.status === "running") setAppState("processing");
          if (data.status === "done") {
            setAppState("success");
            loadHistory();
            setActivePage("library");
          }
          if (data.status === "error") setAppState("error");
        } catch (e) {
          console.error("Status check failed", e);
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [jobId, status, loadHistory]);

  // ── Handlers ────────────────────────────────────────────────────────────────
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

  const startProcessing = async () => {
    if (!file || !title) return;
    setAppState("uploading");
    setStatus({ status: "uploading", step: "Uploading...", progress: 5, result: null, error: null });
    const formData = new FormData();
    formData.append("video", file);
    formData.append("title", title);
    formData.append("guest_name", guestName);
    formData.append("channel", selectedChannel);
    try {
      const res = await fetch(`${BACKEND_URL}/upload`, { method: "POST", body: formData });
      const data = await res.json();
      setJobId(data.job_id);
    } catch {
      setAppState("error");
    }
  };

  const resetForm = () => {
    setFile(null);
    setTitle("");
    setGuestName("");
    setJobId(null);
    setStatus(null);
    setAppState("idle");
  };

  const loadHistoryJob = async (jobIdToLoad: string) => {
    try {
      const res = await fetch(`${BACKEND_URL}/history/${jobIdToLoad}`);
      const data = await res.json();
      setStatus(data);
      setAppState("success");
      setActivePage("library");
    } catch (e) {
      console.error("History detail failed", e);
    }
  };

  const backendUrl = (path: string) => `${BACKEND_URL.replace(/\/$/, "")}${path}`;
  const clips = status?.result?.clips || [];

  // ── Stats Data ──────────────────────────────────────────────────────────────
  const totalClips = historyJobs.reduce((acc, job) => acc + (job.status === "done" ? 3 : 0), 0) + clips.length;
  const thisMonthViews = 12847;
  const avgPerformance = 78;
  const pipelineCost = 24.50;

  // ── Active Jobs ─────────────────────────────────────────────────────────────
  const activeJobs = historyJobs.filter(j => j.status === "running" || j.status === "processing");
  if (appState === "processing" || appState === "uploading") {
    activeJobs.unshift({
      id: jobId || "current",
      video_title: title || "Current Job",
      status: appState === "uploading" ? "processing" : "running",
      progress: status?.progress || 10,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  }

  // ── Recent Clips ────────────────────────────────────────────────────────────
  const recentClips = clips.slice(0, 4);

  // ── Navigation Items ────────────────────────────────────────────────────────
  const navItems = [
    { id: "dashboard" as ActivePage, icon: Zap, label: "Dashboard" },
    { id: "newjob" as ActivePage, icon: Film, label: "New Clip Job" },
    { id: "library" as ActivePage, icon: FolderOpen, label: "Clip Library" },
    { id: "performance" as ActivePage, icon: BarChart3, label: "Performance" },
    { id: "memory" as ActivePage, icon: Brain, label: "Channel Memory" },
    { id: "settings" as ActivePage, icon: Settings, label: "Channel Settings" },
  ];

  const channels = [
    { id: "speedy-cast", name: "Speedy Cast Clip" },
    { id: "tech-talks", name: "Tech Talks" },
    { id: "podcast-clips", name: "Podcast Clips" },
  ];

  // ═══════════════════════════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════════════════════════
  return (
    <div className="min-h-screen bg-black text-[#e5e5e5] flex">
      {/* ── SIDEBAR ──────────────────────────────────────────────────────────── */}
      <aside
        className={`fixed left-0 top-0 bottom-0 bg-black border-r border-[rgba(255,255,255,0.06)] z-40 flex flex-col transition-all duration-300 ${sidebarCollapsed ? "w-[60px]" : "w-[240px]"}`}
      >
        {/* Logo */}
        <div className="h-14 flex items-center justify-between px-3 border-b border-[rgba(255,255,255,0.06)]">
          {!sidebarCollapsed && (
            <div className="flex items-center gap-1 animate-fadeIn">
              <span className="text-lg font-bold text-white">PROGNOT</span>
              <span className="text-lg font-bold text-[#7c3aed]">STUDIO</span>
            </div>
          )}
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="p-1.5 rounded hover:bg-[#0d0d0d] text-[#6b7280] hover:text-white transition-all"
          >
            {sidebarCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-2 space-y-0.5">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setActivePage(item.id)}
              className={`sidebar-item w-full ${activePage === item.id ? "active" : ""}`}
            >
              <item.icon className="w-[18px] h-[18px] flex-shrink-0" />
              {!sidebarCollapsed && (
                <span className="text-sm whitespace-nowrap overflow-hidden animate-fadeIn">
                  {item.label}
                </span>
              )}
            </button>
          ))}
        </nav>
      </aside>

      {/* ── MAIN CONTENT ─────────────────────────────────────────────────────── */}
      <main
        className="flex-1 transition-all duration-300"
        style={{ marginLeft: sidebarCollapsed ? 60 : 240 }}
      >
        {/* Top Bar */}
        <header className="h-14 bg-black border-b border-[rgba(255,255,255,0.06)] flex items-center justify-between px-6 sticky top-0 z-30">
          {/* Channel Selector */}
          <div className="relative">
            <button className="flex items-center gap-2 px-3 py-1.5 rounded bg-[#0d0d0d] border border-[rgba(255,255,255,0.06)] text-sm text-[#e5e5e5] hover:bg-[#141414] transition-all">
              <Film className="w-4 h-4 text-[#7c3aed]" />
              <span>Speedy Cast Clip</span>
              <ChevronDown className="w-3.5 h-3.5 text-[#6b7280]" />
            </button>
          </div>

          {/* Right Side */}
          <div className="flex items-center gap-3">
            <button className="p-2 rounded hover:bg-[#0d0d0d] text-[#6b7280] hover:text-white transition-all relative">
              <Bell className="w-[18px] h-[18px]" />
              <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-[#7c3aed] rounded-full" />
            </button>
            <div className="w-8 h-8 rounded-full bg-[#0d0d0d] border border-[rgba(255,255,255,0.06)] flex items-center justify-center text-xs font-medium text-white">
              SC
            </div>
          </div>
        </header>

        {/* Content Area */}
        <div className="p-6">
          {/* ═══════════════════════════════════════════════════════════════════ */}
          {/* DASHBOARD PAGE */}
          {/* ═══════════════════════════════════════════════════════════════════ */}
          {activePage === "dashboard" && (
            <div className="space-y-6 animate-fadeIn">
              {/* Page Title */}
              <h1 className="text-2xl font-bold text-white">Dashboard</h1>

              {/* Stats Cards Row */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {/* Total Clips */}
                <div className="card p-5 animate-fadeInUp" style={{ animationDelay: "0ms" }}>
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-[13px] uppercase tracking-wider text-[#6b7280]">Total Clips</p>
                      <p className="text-[36px] font-bold text-white mt-1 font-geist">
                        <AnimatedNumber value={totalClips || 47} />
                      </p>
                      <p className="text-sm text-green-500 mt-1 flex items-center gap-1">
                        <TrendingUp className="w-3 h-3" />
                        +12%
                      </p>
                    </div>
                    <div className="p-2 rounded bg-[#141414]">
                      <Film className="w-4 h-4 text-[#6b7280]" />
                    </div>
                  </div>
                </div>

                {/* This Month Views */}
                <div className="card p-5 animate-fadeInUp" style={{ animationDelay: "50ms" }}>
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-[13px] uppercase tracking-wider text-[#6b7280]">This Month Views</p>
                      <p className="text-[36px] font-bold text-white mt-1 font-geist">
                        <AnimatedNumber value={thisMonthViews} />
                      </p>
                      <div className="flex items-center gap-2 mt-1">
                        <p className="text-sm text-green-500 flex items-center gap-1">
                          <TrendingUp className="w-3 h-3" />
                          +8%
                        </p>
                        <MiniSparkline data={[30, 35, 45, 40, 55, 50, 60]} positive />
                      </div>
                    </div>
                    <div className="p-2 rounded bg-[#141414]">
                      <BarChart3 className="w-4 h-4 text-[#6b7280]" />
                    </div>
                  </div>
                </div>

                {/* Avg Performance */}
                <div className="card p-5 animate-fadeInUp" style={{ animationDelay: "100ms" }}>
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-[13px] uppercase tracking-wider text-[#6b7280]">Avg Performance</p>
                      <p className="text-[36px] font-bold text-white mt-1 font-geist">{avgPerformance}%</p>
                      <p className="text-sm text-red-500 mt-1 flex items-center gap-1">
                        <TrendingDown className="w-3 h-3" />
                        -3%
                      </p>
                    </div>
                    <div className="p-2 rounded bg-[#141414]">
                      <Zap className="w-4 h-4 text-[#6b7280]" />
                    </div>
                  </div>
                </div>

                {/* Pipeline Cost */}
                <div className="card p-5 animate-fadeInUp" style={{ animationDelay: "150ms" }}>
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-[13px] uppercase tracking-wider text-[#6b7280]">Pipeline Cost</p>
                      <p className="text-[36px] font-bold text-white mt-1 font-geist">
                        ${pipelineCost.toFixed(2)}
                      </p>
                      <p className="text-sm text-[#6b7280] mt-1">This billing cycle</p>
                    </div>
                    <div className="p-2 rounded bg-[#141414]">
                      <Clock className="w-4 h-4 text-[#6b7280]" />
                    </div>
                  </div>
                </div>
              </div>

              {/* Active Jobs */}
              {activeJobs.length > 0 && (
                <div className="card p-5 animate-fadeInUp" style={{ animationDelay: "200ms" }}>
                  <div className="flex items-center gap-2 mb-4">
                    <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                    <h3 className="text-[13px] uppercase tracking-wider text-[#6b7280]">Active Jobs</h3>
                  </div>
                  <div className="space-y-3">
                    {activeJobs.map((job) => (
                      <div key={job.id} className="p-4 rounded-lg bg-[#141414] border border-[rgba(255,255,255,0.06)]">
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-3">
                            <div className="w-9 h-9 rounded bg-[#0d0d0d] flex items-center justify-center">
                              <Film className="w-4 h-4 text-[#7c3aed]" />
                            </div>
                            <div>
                              <p className="text-sm font-medium text-white">{job.video_title}</p>
                              <p className="text-xs text-[#6b7280]">{status?.step || "Processing..."}</p>
                            </div>
                          </div>
                          <StatusBadge status={job.status} />
                        </div>
                        <div className="relative h-1.5 rounded-full bg-[#1a1a1a] overflow-hidden">
                          <div
                            className="absolute left-0 top-0 h-full bg-[#7c3aed] rounded-full progress-shimmer transition-all duration-500"
                            style={{ width: `${job.progress}%` }}
                          />
                        </div>
                        <div className="flex items-center justify-between mt-2">
                          <span className="text-xs text-[#6b7280]">Progress</span>
                          <span className="text-xs text-white">{job.progress}%</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Two Column Row */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Recent Clips */}
                <div className="card p-5 animate-fadeInUp" style={{ animationDelay: "250ms" }}>
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-[13px] uppercase tracking-wider text-[#6b7280]">Recent Clips</h3>
                    <button
                      onClick={() => setActivePage("library")}
                      className="text-xs text-white hover:text-[#e5e5e5] transition-colors flex items-center gap-1"
                    >
                      View All <ArrowRight className="w-3 h-3" />
                    </button>
                  </div>
                  {recentClips.length > 0 ? (
                    <div className="grid grid-cols-2 gap-3">
                      {recentClips.map((clip, idx) => (
                        <button
                          key={idx}
                          onClick={() => setSelectedClip(clip)}
                          className="group relative aspect-video rounded-lg overflow-hidden bg-[#141414] hover:bg-[#1a1a1a] transition-all"
                        >
                          <video
                            src={backendUrl(clip.path)}
                            className="w-full h-full object-cover"
                            muted
                            playsInline
                          />
                          <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />
                          <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                            <div className="w-9 h-9 rounded-full bg-black/50 flex items-center justify-center">
                              <Play className="w-4 h-4 text-white fill-white" />
                            </div>
                          </div>
                          <div className="absolute bottom-2 left-2">
                            <span className="text-xs font-medium text-white bg-[#7c3aed] px-1.5 py-0.5 rounded">
                              {clip.score}
                            </span>
                          </div>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-12">
                      <Film className="w-10 h-10 mb-3 text-[#6b7280]" />
                      <p className="text-sm text-[#6b7280]">No clips yet</p>
                      <button
                        onClick={() => setActivePage("newjob")}
                        className="mt-3 text-sm text-white hover:text-[#e5e5e5] transition-colors flex items-center gap-1"
                      >
                        Create your first clip <ArrowRight className="w-3 h-3" />
                      </button>
                    </div>
                  )}
                </div>

                {/* Recent Jobs */}
                <div className="card p-5 animate-fadeInUp" style={{ animationDelay: "300ms" }}>
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-[13px] uppercase tracking-wider text-[#6b7280]">Recent Jobs</h3>
                    <button
                      onClick={loadHistory}
                      className="flex items-center gap-1 text-xs text-[#6b7280] hover:text-white transition-colors"
                    >
                      <RefreshCw className={`w-3 h-3 ${historyLoading ? "animate-spin" : ""}`} />
                    </button>
                  </div>
                  {historyJobs.length > 0 ? (
                    <div className="space-y-2">
                      {historyJobs.slice(0, 5).map((job) => (
                        <div
                          key={job.id}
                          className="flex items-center justify-between p-3 rounded-lg bg-[#141414] hover:bg-[#1a1a1a] transition-all group"
                        >
                          <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded bg-[#0d0d0d] flex items-center justify-center">
                              <FileText className="w-3.5 h-3.5 text-[#6b7280]" />
                            </div>
                            <div>
                              <p className="text-sm text-[#e5e5e5]">{job.video_title}</p>
                              <p className="text-xs text-[#6b7280]">
                                {new Date(job.created_at).toLocaleDateString()}
                              </p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <StatusBadge status={job.status} />
                            {job.status === "done" && (
                              <button
                                onClick={() => loadHistoryJob(job.id)}
                                className="text-xs text-white opacity-0 group-hover:opacity-100 transition-opacity"
                              >
                                Load
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-12">
                      <FolderOpen className="w-10 h-10 mb-3 text-[#6b7280]" />
                      <p className="text-sm text-[#6b7280]">No jobs yet</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ═══════════════════════════════════════════════════════════════════ */}
          {/* NEW CLIP JOB PAGE */}
          {/* ═══════════════════════════════════════════════════════════════════ */}
          {activePage === "newjob" && (
            <div className="max-w-2xl mx-auto space-y-6 animate-fadeIn">
              {/* Page Title */}
              <h1 className="text-2xl font-bold text-white">New Clip Job</h1>

              {/* Upload Zone */}
              <div className="card p-6">
                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  className={`relative border-2 border-dashed rounded-lg p-10 text-center transition-all ${
                    isDragging
                      ? "border-[#7c3aed] bg-[#7c3aed]/5"
                      : file
                      ? "border-green-500/50 bg-green-500/5"
                      : "border-[rgba(255,255,255,0.1)] hover:border-[rgba(255,255,255,0.2)]"
                  }`}
                >
                  {file ? (
                    <div className="flex items-center justify-center gap-3">
                      <CheckCircle className="w-5 h-5 text-green-500" />
                      <span className="text-sm text-[#e5e5e5]">{file.name}</span>
                      <button
                        onClick={() => setFile(null)}
                        className="p-1 rounded hover:bg-[#141414] text-[#6b7280]"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ) : (
                    <>
                      <Upload className="w-10 h-10 mx-auto mb-3 text-[#6b7280]" />
                      <p className="text-sm text-[#e5e5e5] mb-1">Drag and drop your video here</p>
                      <p className="text-xs text-[#6b7280] mb-4">or</p>
                      <label className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#141414] hover:bg-[#1a1a1a] text-[#e5e5e5] text-sm cursor-pointer transition-colors border border-[rgba(255,255,255,0.06)]">
                        <Plus className="w-4 h-4" />
                        Browse Files
                        <input
                          type="file"
                          accept="video/*"
                          className="hidden"
                          onChange={(e) => e.target.files?.[0] && setFile(e.target.files[0])}
                        />
                      </label>
                    </>
                  )}
                </div>
              </div>

              {/* Form Fields */}
              <div className="card p-6 space-y-5">
                {/* Video Title */}
                <div>
                  <label className="block text-[13px] uppercase tracking-wider text-[#6b7280] mb-2">
                    Video Title <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="Enter video title..."
                    className="w-full px-4 py-3 rounded-lg bg-[#141414] border border-[rgba(255,255,255,0.06)] text-[#e5e5e5] placeholder-[#6b7280] text-sm transition-all"
                  />
                </div>

                {/* Guest Name */}
                <div>
                  <label className="block text-[13px] uppercase tracking-wider text-[#6b7280] mb-2">
                    Guest Name <span className="text-[#6b7280] text-xs normal-case">(optional)</span>
                  </label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#6b7280]" />
                    <input
                      type="text"
                      value={guestName}
                      onChange={(e) => setGuestName(e.target.value)}
                      placeholder="Enter guest name..."
                      className="w-full pl-10 pr-4 py-3 rounded-lg bg-[#141414] border border-[rgba(255,255,255,0.06)] text-[#e5e5e5] placeholder-[#6b7280] text-sm transition-all"
                    />
                  </div>
                </div>

                {/* Channel Select */}
                <div>
                  <label className="block text-[13px] uppercase tracking-wider text-[#6b7280] mb-2">
                    Channel
                  </label>
                  <div className="relative">
                    <select
                      value={selectedChannel}
                      onChange={(e) => setSelectedChannel(e.target.value)}
                      className="w-full px-4 py-3 rounded-lg bg-[#141414] border border-[rgba(255,255,255,0.06)] text-[#e5e5e5] text-sm appearance-none cursor-pointer transition-all"
                    >
                      {channels.map((ch) => (
                        <option key={ch.id} value={ch.id}>
                          {ch.name}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#6b7280] pointer-events-none" />
                  </div>
                </div>
              </div>

              {/* Submit Button */}
              <button
                onClick={startProcessing}
                disabled={!file || !title || appState === "uploading"}
                className="w-full py-3.5 rounded-lg bg-[#7c3aed] hover:bg-[#6d28d9] text-white font-semibold disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2"
              >
                {appState === "uploading" ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Uploading...
                  </>
                ) : (
                  <>
                    <Zap className="w-5 h-5" />
                    Start Processing
                  </>
                )}
              </button>

              {/* Recent Jobs Section */}
              {historyJobs.length > 0 && (
                <div className="card p-5">
                  <h3 className="text-[13px] uppercase tracking-wider text-[#6b7280] mb-4">Recent Jobs</h3>
                  <div className="space-y-2">
                    {historyJobs.slice(0, 3).map((job) => (
                      <div
                        key={job.id}
                        className="flex items-center justify-between p-3 rounded-lg bg-[#141414] hover:bg-[#1a1a1a] transition-all"
                      >
                        <div className="flex items-center gap-3">
                          <FileText className="w-4 h-4 text-[#6b7280]" />
                          <span className="text-sm text-[#e5e5e5]">{job.video_title}</span>
                        </div>
                        <StatusBadge status={job.status} />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ═══════════════════════════════════════════════════════════════════ */}
          {/* LIBRARY PAGE */}
          {/* ═══════════════════════════════════════════════════════════════════ */}
          {activePage === "library" && (
            <div className="space-y-6 animate-fadeIn">
              <h1 className="text-2xl font-bold text-white">Clip Library</h1>

              {clips.length > 0 ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {clips.map((clip, idx) => (
                    <button
                      key={idx}
                      onClick={() => setSelectedClip(clip)}
                      className="group card overflow-hidden text-left"
                    >
                      <div className="relative aspect-video bg-[#141414]">
                        <video
                          src={backendUrl(clip.path)}
                          className="w-full h-full object-cover"
                          muted
                          playsInline
                        />
                        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                          <div className="w-10 h-10 rounded-full bg-black/50 flex items-center justify-center">
                            <Play className="w-5 h-5 text-white fill-white" />
                          </div>
                        </div>
                        <div className="absolute top-2 right-2">
                          <span className="text-xs font-medium text-white bg-[#7c3aed] px-2 py-0.5 rounded">
                            {clip.score}
                          </span>
                        </div>
                      </div>
                      <div className="p-3">
                        <p className="text-sm text-[#e5e5e5] line-clamp-2">{clip.hook}</p>
                        <p className="text-xs text-[#6b7280] mt-1">Clip #{clip.index + 1}</p>
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="card p-12 flex flex-col items-center justify-center">
                  <Film className="w-12 h-12 mb-4 text-[#6b7280]" />
                  <p className="text-[#6b7280] mb-4">No clips yet</p>
                  <button
                    onClick={() => setActivePage("newjob")}
                    className="text-white hover:text-[#e5e5e5] transition-colors flex items-center gap-1"
                  >
                    Create your first clip <ArrowRight className="w-4 h-4" />
                  </button>
                </div>
              )}
            </div>
          )}

          {/* ═══════════════════════════════════════════════════════════════════ */}
          {/* OTHER PAGES (Placeholder) */}
          {/* ═══════════════════════════════════════════════════════════════════ */}
          {(activePage === "performance" || activePage === "memory" || activePage === "settings") && (
            <div className="space-y-6 animate-fadeIn">
              <h1 className="text-2xl font-bold text-white">
                {activePage === "performance" && "Performance"}
                {activePage === "memory" && "Channel Memory"}
                {activePage === "settings" && "Channel Settings"}
              </h1>
              <div className="card p-12 flex flex-col items-center justify-center">
                <div className="w-12 h-12 mb-4 rounded-lg bg-[#141414] flex items-center justify-center">
                  {activePage === "performance" && <BarChart3 className="w-6 h-6 text-[#6b7280]" />}
                  {activePage === "memory" && <Brain className="w-6 h-6 text-[#6b7280]" />}
                  {activePage === "settings" && <Settings className="w-6 h-6 text-[#6b7280]" />}
                </div>
                <p className="text-[#6b7280]">Coming soon</p>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* ── CLIP DETAIL MODAL ────────────────────────────────────────────────── */}
      {selectedClip && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/80"
            onClick={() => setSelectedClip(null)}
          />
          <div className="relative w-full max-w-5xl max-h-[90vh] bg-[#0d0d0d] rounded-lg border border-[rgba(255,255,255,0.06)] overflow-hidden animate-scaleIn">
            <div className="flex items-center justify-between p-4 border-b border-[rgba(255,255,255,0.06)]">
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-white bg-[#7c3aed] px-2 py-0.5 rounded">
                  Score: {selectedClip.score}
                </span>
              </div>
              <button
                onClick={() => setSelectedClip(null)}
                className="p-2 rounded hover:bg-[#141414] text-[#6b7280] hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 max-h-[calc(90vh-60px)] overflow-y-auto">
              {/* Video Player */}
              <div className="aspect-video bg-black">
                <video
                  src={backendUrl(selectedClip.path)}
                  controls
                  autoPlay
                  className="w-full h-full"
                />
              </div>

              {/* Details */}
              <div className="p-6 space-y-5 overflow-y-auto">
                {/* Hook */}
                <div>
                  <p className="text-[13px] uppercase tracking-wider text-[#6b7280] mb-2">Hook</p>
                  <p className="text-[#e5e5e5]">{selectedClip.hook}</p>
                </div>

                {/* Why Selected */}
                {selectedClip.why_selected && (
                  <div>
                    <p className="text-[13px] uppercase tracking-wider text-[#6b7280] mb-2">Why Selected</p>
                    <p className="text-[#e5e5e5] text-sm">{selectedClip.why_selected}</p>
                  </div>
                )}

                {/* Psychological Trigger */}
                {selectedClip.psychological_trigger && (
                  <div>
                    <p className="text-[13px] uppercase tracking-wider text-[#6b7280] mb-2">Psychological Trigger</p>
                    <span className="inline-block px-2 py-1 rounded bg-[#141414] text-sm text-[#e5e5e5]">
                      {selectedClip.psychological_trigger}
                    </span>
                  </div>
                )}

                {/* Suggested Title */}
                {selectedClip.suggested_title && (
                  <div>
                    <p className="text-[13px] uppercase tracking-wider text-[#6b7280] mb-2">Suggested Title</p>
                    <div className="flex items-start gap-2">
                      <p className="text-[#e5e5e5] text-sm flex-1">{selectedClip.suggested_title}</p>
                      <CopyButton text={selectedClip.suggested_title} />
                    </div>
                  </div>
                )}

                {/* Hashtags */}
                {selectedClip.suggested_hashtags && (
                  <div>
                    <p className="text-[13px] uppercase tracking-wider text-[#6b7280] mb-2">Hashtags</p>
                    <div className="flex items-start gap-2">
                      <p className="text-[#e5e5e5] text-sm flex-1">{selectedClip.suggested_hashtags}</p>
                      <CopyButton text={selectedClip.suggested_hashtags} />
                    </div>
                  </div>
                )}

                {/* Transcript */}
                {selectedClip.transcript_excerpt && (
                  <div>
                    <p className="text-[13px] uppercase tracking-wider text-[#6b7280] mb-2">Transcript</p>
                    <div className="p-3 rounded-lg bg-[#141414] border border-[rgba(255,255,255,0.06)]">
                      <p className="text-sm text-[#e5e5e5] whitespace-pre-wrap">{selectedClip.transcript_excerpt}</p>
                    </div>
                  </div>
                )}

                {/* Download Button */}
                <a
                  href={backendUrl(selectedClip.path)}
                  download
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#7c3aed] hover:bg-[#6d28d9] text-white text-sm font-medium transition-colors"
                >
                  <Download className="w-4 h-4" />
                  Download Clip
                </a>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
