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
  Play,
  Download,
  Clock,
  CheckCircle,
  XCircle,
  Loader2,
  Sparkles,
  Plus,
  Upload,
  X,
  Copy,
  Check,
  RefreshCw,
  Dna,
  FileText,
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

// ─── HELPER COMPONENTS ──────────────────────────────────────────────────────

function AnimatedNumber({ value, duration = 1500 }: { value: number; duration?: number }) {
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

function CircularProgress({ value, size = 80, strokeWidth = 6 }: { value: number; size?: number; strokeWidth?: number }) {
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (value / 100) * circumference;

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg className="circular-progress" width={size} height={size}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="#1f1f2e"
          strokeWidth={strokeWidth}
          fill="none"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="url(#progress-gradient)"
          strokeWidth={strokeWidth}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-1000 ease-out"
          style={{ transform: "rotate(-90deg)", transformOrigin: "center" }}
        />
        <defs>
          <linearGradient id="progress-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#7c3aed" />
            <stop offset="100%" stopColor="#06b6d4" />
          </linearGradient>
        </defs>
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-lg font-bold text-white">{value}%</span>
      </div>
    </div>
  );
}

function Sparkline({ data }: { data: number[] }) {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const width = 100;
  const height = 30;
  const points = data.map((d, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((d - min) / range) * height;
    return `${x},${y}`;
  }).join(" ");

  return (
    <svg width={width} height={height} className="overflow-visible">
      <defs>
        <linearGradient id="sparkline-fill" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#7c3aed" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#7c3aed" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon
        points={`0,${height} ${points} ${width},${height}`}
        fill="url(#sparkline-fill)"
      />
      <polyline
        points={points}
        fill="none"
        stroke="#7c3aed"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function MiniLineChart() {
  const data = [30, 45, 35, 60, 55, 70, 65, 80, 75, 90, 85, 95];
  const width = 320;
  const height = 120;
  const padding = 10;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;

  const points = data.map((d, i) => {
    const x = padding + (i / (data.length - 1)) * (width - padding * 2);
    const y = padding + (1 - (d - min) / range) * (height - padding * 2);
    return `${x},${y}`;
  }).join(" ");

  const areaPoints = `${padding},${height - padding} ${points} ${width - padding},${height - padding}`;

  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id="chart-gradient" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#7c3aed" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#7c3aed" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="line-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#7c3aed" />
          <stop offset="100%" stopColor="#06b6d4" />
        </linearGradient>
      </defs>
      <polygon points={areaPoints} fill="url(#chart-gradient)" />
      <polyline
        points={points}
        fill="none"
        stroke="url(#line-gradient)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
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
    <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium ${bg} ${text}`}>
      {icon}
      {status === "running" ? "Processing" : status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

function ViralityBadge({ score }: { score: number }) {
  const gradient = score >= 85 ? "from-red-500 to-orange-500" : score >= 70 ? "from-orange-500 to-yellow-500" : "from-yellow-500 to-green-500";
  return (
    <div className={`flex items-center gap-1 px-2 py-1 rounded-lg bg-gradient-to-r ${gradient} text-white text-xs font-bold`}>
      <Sparkles className="w-3 h-3" />
      {score}
    </div>
  );
}

function DnaBadge() {
  return (
    <div className="flex items-center gap-1 px-2 py-1 rounded-lg bg-cyan-500/20 text-cyan-400 text-xs font-medium border border-cyan-500/30">
      <Dna className="w-3 h-3" />
      DNA
    </div>
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
      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-all bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white border border-white/10"
    >
      {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
      {copied ? "Copied" : label || "Copy"}
    </button>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═════════════════════════════════════════════════════════════════════════════
export default function PrognotStudio() {
  // --- State ---
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeNav, setActiveNav] = useState("dashboard");
  const [showNewJobModal, setShowNewJobModal] = useState(false);

  // --- Job State ---
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [appState, setAppState] = useState<AppState>("idle");
  const [logs, setLogs] = useState<string[]>([]);
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
          if (data.step) {
            setLogs((prev) => {
              if (prev[prev.length - 1] !== data.step) return [...prev, data.step];
              return prev;
            });
          }
          if (data.status === "running") setAppState("processing");
          if (data.status === "done") {
            setAppState("success");
            loadHistory();
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
    setLogs(["[SYSTEM] Pipeline starting...", "[UPLOAD] Transferring file to server..."]);
    setStatus({ status: "uploading", step: "Uploading...", progress: 5, result: null, error: null });
    const formData = new FormData();
    formData.append("video", file);
    formData.append("title", title);
    formData.append("description", description);
    try {
      const res = await fetch(`${BACKEND_URL}/upload`, { method: "POST", body: formData });
      const data = await res.json();
      setJobId(data.job_id);
      setShowNewJobModal(false);
    } catch {
      setAppState("error");
      setLogs((prev) => [...prev, "[ERROR] Connection failed: Server not responding."]);
    }
  };

  const resetForm = () => {
    setFile(null);
    setTitle("");
    setDescription("");
    setJobId(null);
    setStatus(null);
    setAppState("idle");
    setLogs([]);
  };

  const loadHistoryJob = async (jobIdToLoad: string) => {
    try {
      const res = await fetch(`${BACKEND_URL}/history/${jobIdToLoad}`);
      const data = await res.json();
      setStatus(data);
      setAppState("success");
      setActiveNav("library");
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
  const sparklineData = [12, 19, 15, 25, 22, 30, 28, 35, 32, 40, 38, 45];

  // ── Active Jobs (running jobs from history) ─────────────────────────────────
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

  // ── Recent Clips (last 4 from all completed jobs) ───────────────────────────
  const recentClips = clips.slice(0, 4);

  // ── Navigation Items ────────────────────────────────────────────────────────
  const navItems = [
    { id: "dashboard", icon: Zap, label: "Dashboard" },
    { id: "newjob", icon: Film, label: "New Clip Job" },
    { id: "library", icon: FolderOpen, label: "Clip Library" },
    { id: "performance", icon: BarChart3, label: "Performance" },
    { id: "memory", icon: Brain, label: "Channel Memory" },
    { id: "settings", icon: Settings, label: "Channel Settings" },
  ];

  // ═══════════════════════════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════════════════════════
  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white flex relative">
      {/* Background Orbs */}
      <div className="orb orb-1" />
      <div className="orb orb-2" />
      <div className="orb orb-3" />

      {/* ── SIDEBAR ──────────────────────────────────────────────────────────── */}
      <aside
        className={`fixed left-0 top-0 bottom-0 bg-[#0d0d14]/80 backdrop-blur-xl border-r border-white/5 z-40 flex flex-col transition-all duration-300 ease-in-out ${sidebarCollapsed ? "w-[72px]" : "w-[260px]"}`}
      >
        {/* Logo */}
        <div className="h-16 flex items-center justify-between px-4 border-b border-white/5">
          {!sidebarCollapsed && (
            <div className="flex items-center gap-1 animate-fadeIn">
              <span className="text-xl font-bold text-white">PROGNOT</span>
              <span className="text-xl font-bold gradient-text-purple">STUDIO</span>
            </div>
          )}
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="p-2 rounded-lg hover:bg-white/5 text-gray-400 hover:text-white transition-all"
          >
            {sidebarCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-3 space-y-1">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => {
                if (item.id === "newjob") {
                  setShowNewJobModal(true);
                } else {
                  setActiveNav(item.id);
                }
              }}
              className={`sidebar-item w-full ${activeNav === item.id ? "active" : ""}`}
            >
              <item.icon className="w-5 h-5 flex-shrink-0" />
              {!sidebarCollapsed && (
                <span className="text-sm font-medium whitespace-nowrap overflow-hidden animate-fadeIn">
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
        style={{ marginLeft: sidebarCollapsed ? 72 : 260 }}
      >
        {/* Top Bar */}
        <header className="h-16 bg-[#0d0d14]/60 backdrop-blur-xl border-b border-white/5 flex items-center justify-between px-6 sticky top-0 z-30">
          {/* Channel Selector */}
          <div className="flex items-center gap-3">
            <button className="flex items-center gap-2 px-4 py-2 rounded-full bg-purple-600/20 text-purple-400 border border-purple-500/30 text-sm font-medium hover:bg-purple-600/30 transition-all">
              <Film className="w-4 h-4" />
              <span>Speedy Cast Clip</span>
            </button>
          </div>

          {/* Right Side */}
          <div className="flex items-center gap-4">
            <button className="p-2 rounded-lg hover:bg-white/5 text-gray-400 hover:text-white transition-all relative">
              <Bell className="w-5 h-5" />
              <span className="absolute top-1 right-1 w-2 h-2 bg-purple-500 rounded-full" />
            </button>
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-cyan-500 flex items-center justify-center text-xs font-bold">
              SC
            </div>
          </div>
        </header>

        {/* Content Area */}
        <div className="p-6 relative z-10">
          <div className="space-y-6">
            {/* ── ROW 1: STATS CARDS ─────────────────────────────────────────── */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Total Clips */}
              <div className="card-gradient-border p-5 animate-fadeInUp" style={{ animationDelay: "0ms" }}>
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wider">Total Clips</p>
                    <p className="text-3xl font-bold text-white mt-1">
                      <AnimatedNumber value={totalClips || 47} />
                    </p>
                    <p className="text-xs text-green-400 mt-1 flex items-center gap-1">
                      <TrendingUp className="w-3 h-3" />
                      +12 this week
                    </p>
                  </div>
                  <div className="p-2 rounded-lg bg-purple-500/10">
                    <Film className="w-5 h-5 text-purple-400" />
                  </div>
                </div>
              </div>

              {/* This Month Views */}
              <div className="card-gradient-border p-5 animate-fadeInUp" style={{ animationDelay: "100ms" }}>
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wider">This Month Views</p>
                    <p className="text-3xl font-bold text-white mt-1">
                      <AnimatedNumber value={thisMonthViews} />
                    </p>
                    <div className="mt-2">
                      <Sparkline data={sparklineData} />
                    </div>
                  </div>
                  <div className="p-2 rounded-lg bg-cyan-500/10">
                    <TrendingUp className="w-5 h-5 text-cyan-400" />
                  </div>
                </div>
              </div>

              {/* Avg Performance */}
              <div className="card-gradient-border p-5 animate-fadeInUp" style={{ animationDelay: "200ms" }}>
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wider">Avg Performance</p>
                    <div className="mt-2">
                      <CircularProgress value={avgPerformance} />
                    </div>
                  </div>
                  <div className="p-2 rounded-lg bg-green-500/10">
                    <Sparkles className="w-5 h-5 text-green-400" />
                  </div>
                </div>
              </div>

              {/* Pipeline Cost */}
              <div className="card-gradient-border p-5 animate-fadeInUp" style={{ animationDelay: "300ms" }}>
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wider">Pipeline Cost</p>
                    <p className="text-3xl font-bold text-white mt-1">
                      ${pipelineCost.toFixed(2)}
                    </p>
                    <p className="text-xs text-gray-400 mt-1">This billing cycle</p>
                  </div>
                  <div className="p-2 rounded-lg bg-orange-500/10">
                    <Zap className="w-5 h-5 text-orange-400" />
                  </div>
                </div>
              </div>
            </div>

            {/* ── ROW 2: ACTIVE JOBS ────────────────────────────────────────── */}
            {(activeJobs.length > 0 || appState === "processing" || appState === "uploading") && (
              <div className="card-gradient-border p-5 animate-fadeInUp" style={{ animationDelay: "400ms" }}>
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                  <h3 className="text-lg font-semibold text-white">Active Jobs</h3>
                </div>
                <div className="space-y-4">
                  {activeJobs.map((job) => (
                    <div key={job.id} className="p-4 rounded-xl bg-white/5 border border-white/5">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center">
                            <Film className="w-5 h-5 text-purple-400" />
                          </div>
                          <div>
                            <p className="text-sm font-medium text-white">{job.video_title}</p>
                            <p className="text-xs text-gray-500">{status?.step || "Processing..."}</p>
                          </div>
                        </div>
                        <StatusBadge status={job.status} />
                      </div>
                      <div className="relative h-2 rounded-full bg-[#1a1a2e] overflow-hidden">
                        <div
                          className="absolute left-0 top-0 h-full bg-gradient-to-r from-purple-500 to-cyan-500 rounded-full progress-shimmer transition-all duration-500"
                          style={{ width: `${job.progress}%` }}
                        />
                      </div>
                      <div className="flex items-center justify-between mt-2">
                        <span className="text-xs text-gray-500">Progress</span>
                        <span className="text-xs text-white font-medium">{job.progress}%</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ── ROW 3: TWO COLUMNS ────────────────────────────────────────── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Recent Clips */}
              <div className="card-gradient-border p-5 animate-fadeInUp" style={{ animationDelay: "500ms" }}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-white">Recent Clips</h3>
                  <button
                    onClick={() => setActiveNav("library")}
                    className="text-xs text-purple-400 hover:text-purple-300 transition-colors"
                  >
                    View All
                  </button>
                </div>
                {recentClips.length > 0 ? (
                  <div className="grid grid-cols-2 gap-3">
                    {recentClips.map((clip, idx) => (
                      <button
                        key={idx}
                        onClick={() => setSelectedClip(clip)}
                        className="group relative aspect-video rounded-xl overflow-hidden bg-[#1a1a2e] hover:ring-2 hover:ring-purple-500/50 transition-all"
                      >
                        <video
                          src={backendUrl(clip.path)}
                          className="w-full h-full object-cover"
                          muted
                          playsInline
                        />
                        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent" />
                        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                          <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur flex items-center justify-center">
                            <Play className="w-5 h-5 text-white fill-white" />
                          </div>
                        </div>
                        <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between">
                          <ViralityBadge score={clip.score} />
                          {clip.rag_reference_used && <DnaBadge />}
                        </div>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center py-12 text-gray-500">
                    <Film className="w-12 h-12 mb-3 opacity-50" />
                    <p className="text-sm">No clips yet</p>
                    <button
                      onClick={() => setShowNewJobModal(true)}
                      className="mt-3 text-sm text-purple-400 hover:text-purple-300 transition-colors"
                    >
                      Create your first clip
                    </button>
                  </div>
                )}
              </div>

              {/* Channel Performance Chart */}
              <div className="card-gradient-border p-5 animate-fadeInUp" style={{ animationDelay: "600ms" }}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-white">Channel Performance</h3>
                  <select className="text-xs bg-white/5 border border-white/10 rounded-lg px-2 py-1 text-gray-400 focus:outline-none focus:ring-1 focus:ring-purple-500">
                    <option>Last 7 days</option>
                    <option>Last 30 days</option>
                    <option>Last 90 days</option>
                  </select>
                </div>
                <MiniLineChart />
                <div className="grid grid-cols-3 gap-4 mt-4 pt-4 border-t border-white/5">
                  <div>
                    <p className="text-xs text-gray-500">Total Views</p>
                    <p className="text-lg font-bold text-white">24.8K</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Avg. Watch Time</p>
                    <p className="text-lg font-bold text-white">2:34</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Engagement</p>
                    <p className="text-lg font-bold text-white">4.2%</p>
                  </div>
                </div>
              </div>
            </div>

            {/* ── ROW 4: HISTORY TABLE ──────────────────────────────────────── */}
            <div className="card-gradient-border p-5 animate-fadeInUp" style={{ animationDelay: "700ms" }}>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white">Past Projects</h3>
                <button
                  onClick={loadHistory}
                  className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white transition-colors"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${historyLoading ? "animate-spin" : ""}`} />
                  Refresh
                </button>
              </div>
              {historyJobs.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-left text-xs text-gray-500 uppercase tracking-wider border-b border-white/5">
                        <th className="pb-3 font-medium">Title</th>
                        <th className="pb-3 font-medium">Status</th>
                        <th className="pb-3 font-medium">Created</th>
                        <th className="pb-3 font-medium text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {historyJobs.slice(0, 5).map((job) => (
                        <tr key={job.id} className="group">
                          <td className="py-3">
                            <div className="flex items-center gap-3">
                              <div className="w-8 h-8 rounded-lg bg-purple-500/10 flex items-center justify-center">
                                <FileText className="w-4 h-4 text-purple-400" />
                              </div>
                              <span className="text-sm text-white">{job.video_title}</span>
                            </div>
                          </td>
                          <td className="py-3">
                            <StatusBadge status={job.status} />
                          </td>
                          <td className="py-3">
                            <span className="text-sm text-gray-400">
                              {new Date(job.created_at).toLocaleDateString()}
                            </span>
                          </td>
                          <td className="py-3 text-right">
                            {job.status === "done" && (
                              <button
                                onClick={() => loadHistoryJob(job.id)}
                                className="text-xs text-purple-400 hover:text-purple-300 transition-colors opacity-0 group-hover:opacity-100"
                              >
                                Load Results
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-8 text-gray-500">
                  <FolderOpen className="w-10 h-10 mb-2 opacity-50" />
                  <p className="text-sm">No past projects</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>

      {/* ── NEW JOB MODAL ─────────────────────────────────────────────────────── */}
      {showNewJobModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setShowNewJobModal(false)}
          />
          <div className="relative w-full max-w-lg bg-[#0d0d14] rounded-2xl border border-white/10 overflow-hidden animate-scaleIn">
            <div className="flex items-center justify-between p-4 border-b border-white/5">
              <h2 className="text-lg font-semibold text-white">New Clip Job</h2>
              <button
                onClick={() => setShowNewJobModal(false)}
                className="p-2 rounded-lg hover:bg-white/5 text-gray-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-6 space-y-4">
              {/* Upload Zone */}
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-all ${
                  isDragging
                    ? "border-cyan-500 bg-cyan-500/10"
                    : file
                    ? "border-green-500/50 bg-green-500/5"
                    : "border-white/10 hover:border-purple-500/50"
                }`}
              >
                {file ? (
                  <div className="flex items-center justify-center gap-3">
                    <CheckCircle className="w-6 h-6 text-green-400" />
                    <span className="text-sm text-white">{file.name}</span>
                    <button
                      onClick={() => setFile(null)}
                      className="p-1 rounded hover:bg-white/10 text-gray-400"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ) : (
                  <>
                    <Upload className="w-10 h-10 mx-auto mb-3 text-gray-500" />
                    <p className="text-sm text-gray-400 mb-2">
                      Drag and drop your video here
                    </p>
                    <label className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-sm font-medium cursor-pointer transition-colors">
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

              {/* Title Input */}
              <div>
                <label className="block text-xs text-gray-500 uppercase tracking-wider mb-2">
                  Video Title
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Enter video title..."
                  className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition-all"
                />
              </div>

              {/* Description Input */}
              <div>
                <label className="block text-xs text-gray-500 uppercase tracking-wider mb-2">
                  Description (Optional)
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Enter video description..."
                  rows={3}
                  className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition-all resize-none"
                />
              </div>

              {/* Submit Button */}
              <button
                onClick={startProcessing}
                disabled={!file || !title || appState === "uploading"}
                className="w-full py-3 rounded-xl bg-gradient-to-r from-purple-600 to-cyan-600 text-white font-semibold disabled:opacity-50 disabled:cursor-not-allowed hover:shadow-lg hover:shadow-purple-500/25 transition-all flex items-center justify-center gap-2"
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
            </div>
          </div>
        </div>
      )}

      {/* ── CLIP DETAIL MODAL ────────────────────────────────────────────────── */}
      {selectedClip && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/80 backdrop-blur-sm"
            onClick={() => setSelectedClip(null)}
          />
          <div className="relative w-full max-w-5xl max-h-[90vh] bg-[#0d0d14] rounded-2xl border border-white/10 overflow-hidden animate-scaleIn">
            <div className="flex items-center justify-between p-4 border-b border-white/5">
              <div className="flex items-center gap-3">
                <ViralityBadge score={selectedClip.score} />
                {selectedClip.rag_reference_used && <DnaBadge />}
              </div>
              <button
                onClick={() => setSelectedClip(null)}
                className="p-2 rounded-lg hover:bg-white/5 text-gray-400 hover:text-white transition-colors"
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
              <div className="p-6 space-y-6 overflow-y-auto">
                {/* Viral Score Ring */}
                <div className="flex items-center gap-6">
                  <CircularProgress value={selectedClip.score} size={100} strokeWidth={8} />
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wider">Virality Score</p>
                    <p className="text-2xl font-bold text-white">{selectedClip.score}/100</p>
                    <p className="text-xs text-gray-400 mt-1">Top {100 - selectedClip.score}% potential</p>
                  </div>
                </div>

                {/* Hook */}
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Hook</p>
                  <p className="text-white font-medium">{selectedClip.hook}</p>
                </div>

                {/* Why Selected */}
                {selectedClip.why_selected && (
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Why Selected</p>
                    <p className="text-sm text-gray-300">{selectedClip.why_selected}</p>
                  </div>
                )}

                {/* Psychological Trigger */}
                {selectedClip.psychological_trigger && (
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Psychological Trigger</p>
                    <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-purple-500/20 text-purple-400 text-sm">
                      <Brain className="w-4 h-4" />
                      {selectedClip.psychological_trigger}
                    </span>
                  </div>
                )}

                {/* RAG Reference */}
                {selectedClip.rag_reference_used && (
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">DNA Reference</p>
                    <blockquote className="pl-4 border-l-2 border-cyan-500 text-sm text-gray-300 italic">
                      {selectedClip.rag_reference_used}
                    </blockquote>
                  </div>
                )}

                {/* Suggested Content */}
                {selectedClip.suggested_title && (
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-xs text-gray-500 uppercase tracking-wider">Suggested Title</p>
                      <CopyButton text={selectedClip.suggested_title} />
                    </div>
                    <p className="text-sm text-white bg-white/5 p-3 rounded-lg">{selectedClip.suggested_title}</p>
                  </div>
                )}

                {selectedClip.suggested_hashtags && (
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-xs text-gray-500 uppercase tracking-wider">Hashtags</p>
                      <CopyButton text={selectedClip.suggested_hashtags} />
                    </div>
                    <p className="text-sm text-cyan-400">{selectedClip.suggested_hashtags}</p>
                  </div>
                )}

                {/* Transcript */}
                {selectedClip.transcript_excerpt && (
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-xs text-gray-500 uppercase tracking-wider">Transcript</p>
                      <CopyButton text={selectedClip.transcript_excerpt} />
                    </div>
                    <p className="text-sm text-gray-400 bg-white/5 p-3 rounded-lg font-mono">
                      {selectedClip.transcript_excerpt}
                    </p>
                  </div>
                )}

                {/* Download Button */}
                <a
                  href={backendUrl(selectedClip.path)}
                  download
                  className="flex items-center justify-center gap-2 w-full py-3 rounded-xl bg-gradient-to-r from-purple-600 to-cyan-600 text-white font-semibold hover:shadow-lg hover:shadow-purple-500/25 transition-all"
                >
                  <Download className="w-5 h-5" />
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
