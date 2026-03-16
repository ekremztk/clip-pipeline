"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
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

// ─── ANIMATION VARIANTS ─────────────────────────────────────────────────────
const fadeInUp = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 },
};

const staggerContainer = {
  animate: {
    transition: {
      staggerChildren: 0.1,
    },
  },
};

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
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="url(#progress-gradient)"
          strokeWidth={strokeWidth}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.5, ease: "easeOut" }}
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
      </defs>
      <polygon points={areaPoints} fill="url(#chart-gradient)" />
      <polyline
        points={points}
        fill="none"
        stroke="url(#progress-gradient)"
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
      <motion.aside
        initial={false}
        animate={{ width: sidebarCollapsed ? 72 : 260 }}
        transition={{ duration: 0.3, ease: "easeInOut" }}
        className="fixed left-0 top-0 bottom-0 bg-[#0d0d14]/80 backdrop-blur-xl border-r border-white/5 z-40 flex flex-col"
      >
        {/* Logo */}
        <div className="h-16 flex items-center justify-between px-4 border-b border-white/5">
          <AnimatePresence mode="wait">
            {!sidebarCollapsed && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex items-center gap-1"
              >
                <span className="text-xl font-bold text-white">PROGNOT</span>
                <span className="text-xl font-bold gradient-text-purple">STUDIO</span>
              </motion.div>
            )}
          </AnimatePresence>
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
              <AnimatePresence mode="wait">
                {!sidebarCollapsed && (
                  <motion.span
                    initial={{ opacity: 0, width: 0 }}
                    animate={{ opacity: 1, width: "auto" }}
                    exit={{ opacity: 0, width: 0 }}
                    className="text-sm font-medium whitespace-nowrap overflow-hidden"
                  >
                    {item.label}
                  </motion.span>
                )}
              </AnimatePresence>
            </button>
          ))}
        </nav>
      </motion.aside>

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
          <motion.div
            variants={staggerContainer}
            initial="initial"
            animate="animate"
            className="space-y-6"
          >
            {/* ── ROW 1: STATS CARDS ─────────────────────────────────────────── */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Total Clips */}
              <motion.div variants={fadeInUp} className="card-gradient-border p-5">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">Total Clips</p>
                    <p className="text-3xl font-bold text-white">
                      <AnimatedNumber value={totalClips || 127} />
                    </p>
                  </div>
                  <div className="flex items-center gap-1 px-2 py-1 rounded-full bg-green-500/20 text-green-400 text-xs font-medium">
                    <TrendingUp className="w-3 h-3" />
                    +12%
                  </div>
                </div>
                <div className="mt-4">
                  <Sparkline data={sparklineData} />
                </div>
              </motion.div>

              {/* This Month Views */}
              <motion.div variants={fadeInUp} className="card-gradient-border p-5">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">This Month Views</p>
                    <p className="text-3xl font-bold text-white">
                      <AnimatedNumber value={thisMonthViews} />
                    </p>
                  </div>
                  <div className="flex items-center gap-1 px-2 py-1 rounded-full bg-green-500/20 text-green-400 text-xs font-medium">
                    <TrendingUp className="w-3 h-3" />
                    +28%
                  </div>
                </div>
                <p className="text-xs text-gray-500 mt-2">vs last month: 10,034</p>
              </motion.div>

              {/* Avg Performance */}
              <motion.div variants={fadeInUp} className="card-gradient-border p-5">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">Avg Performance</p>
                    <p className="text-sm text-gray-500 mt-1">Viral score average</p>
                  </div>
                  <CircularProgress value={avgPerformance} />
                </div>
              </motion.div>

              {/* Pipeline Cost */}
              <motion.div variants={fadeInUp} className="card-gradient-border p-5">
                <div>
                  <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">Pipeline Cost</p>
                  <p className="text-3xl font-bold text-white">
                    $<AnimatedNumber value={Math.floor(pipelineCost)} />.50
                  </p>
                </div>
                <p className="text-xs text-gray-500 mt-2">this month</p>
              </motion.div>
            </div>

            {/* ── ROW 2: ACTIVE JOBS ─────────────────────────────────────────── */}
            <motion.div variants={fadeInUp} className="card-gradient-border p-5">
              <div className="flex items-center gap-3 mb-4">
                <h2 className="text-lg font-semibold text-white">Active Jobs</h2>
                <span className="w-2 h-2 rounded-full bg-green-500 pulse-live" />
              </div>

              {activeJobs.length === 0 && appState === "idle" ? (
                <div className="text-center py-8">
                  <p className="text-gray-500 text-sm">No active jobs</p>
                  <button
                    onClick={() => setShowNewJobModal(true)}
                    className="mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-600/20 text-purple-400 border border-purple-500/30 hover:bg-purple-600/30 transition-all text-sm font-medium"
                  >
                    <Plus className="w-4 h-4" />
                    Start New Job
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  {activeJobs.map((job) => (
                    <div
                      key={job.id}
                      className="flex items-center gap-4 p-4 bg-[#0d0d14] rounded-xl border border-white/5"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-white truncate">{job.video_title}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <div className="flex-1 h-2 bg-[#1a1a24] rounded-full overflow-hidden">
                            <motion.div
                              className="h-full progress-shimmer"
                              initial={{ width: 0 }}
                              animate={{ width: `${job.progress}%` }}
                              transition={{ duration: 0.5 }}
                            />
                          </div>
                          <span className="text-xs text-gray-500">{job.progress}%</span>
                        </div>
                        <p className="text-xs text-gray-500 mt-1">{status?.step || "Analyzing signals..."}</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="flex items-center gap-1.5 text-xs text-gray-500">
                          <Clock className="w-3.5 h-3.5" />
                          <span>2m 34s</span>
                        </div>
                        <StatusBadge status={job.status} />
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Processing Logs */}
              {(appState === "processing" || appState === "uploading" || appState === "error") && logs.length > 0 && (
                <div className="mt-4 bg-black rounded-xl p-4 max-h-40 overflow-y-auto font-mono text-xs">
                  {logs.map((log, i) => {
                    const isError = log.toLowerCase().includes("error") || log.toLowerCase().includes("hata");
                    const isWarning = log.toLowerCase().includes("warning") || log.toLowerCase().includes("uyarı");
                    const color = isError ? "text-red-500" : isWarning ? "text-yellow-500" : "text-green-500";
                    return (
                      <div key={i} className={`${color} mb-1`}>
                        {log}
                      </div>
                    );
                  })}
                  {appState === "processing" && <span className="text-green-500 animate-pulse">_</span>}
                </div>
              )}

              {appState === "error" && (
                <button
                  onClick={resetForm}
                  className="mt-4 flex items-center justify-center gap-2 w-full py-3 rounded-xl bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 transition-all"
                >
                  <RefreshCw className="w-4 h-4" />
                  Retry
                </button>
              )}
            </motion.div>

            {/* ── ROW 3: TWO COLUMNS ─────────────────────────────────────────── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Recent Clips */}
              <motion.div variants={fadeInUp} className="card-gradient-border p-5">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold text-white">Recent Clips</h2>
                  {clips.length > 0 && (
                    <button
                      onClick={() => setActiveNav("library")}
                      className="text-xs text-purple-400 hover:text-purple-300 transition-all"
                    >
                      View All
                    </button>
                  )}
                </div>

                {recentClips.length === 0 ? (
                  <div className="grid grid-cols-2 gap-3">
                    {[1, 2, 3, 4].map((i) => (
                      <div
                        key={i}
                        className="aspect-video bg-[#0d0d14] rounded-xl border border-white/5 flex items-center justify-center"
                      >
                        <Film className="w-8 h-8 text-gray-700" />
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    {recentClips.map((clip, idx) => {
                      const clipData = { ...clip, index: clip.index || clip.clip_index || idx + 1 };
                      return (
                        <div
                          key={clipData.index}
                          onClick={() => setSelectedClip(clipData)}
                          className="relative aspect-video bg-[#0d0d14] rounded-xl border border-white/5 overflow-hidden cursor-pointer group"
                        >
                          <video
                            src={backendUrl(clipData.path)}
                            className="w-full h-full object-cover opacity-60 group-hover:opacity-80 transition-all"
                          />
                          <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all">
                            <div className="w-10 h-10 rounded-full bg-white/10 backdrop-blur-sm flex items-center justify-center">
                              <Play className="w-4 h-4 text-white ml-0.5" fill="white" />
                            </div>
                          </div>
                          <div className="absolute top-2 right-2 flex gap-1">
                            <ViralityBadge score={clipData.score} />
                          </div>
                          <div className="absolute bottom-0 left-0 right-0 p-2 bg-gradient-to-t from-black/80 to-transparent">
                            <p className="text-xs text-white truncate">{clipData.hook}</p>
                          </div>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              window.open(backendUrl(clipData.path), "_blank");
                            }}
                            className="absolute bottom-2 right-2 p-1.5 rounded-lg bg-white/10 backdrop-blur-sm opacity-0 group-hover:opacity-100 transition-all hover:bg-white/20"
                          >
                            <Download className="w-3.5 h-3.5 text-white" />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </motion.div>

              {/* Channel Performance */}
              <motion.div variants={fadeInUp} className="card-gradient-border p-5">
                <h2 className="text-lg font-semibold text-white mb-4">Channel Performance</h2>
                <div className="h-32">
                  <MiniLineChart />
                </div>
                <div className="flex items-center justify-between mt-4 pt-4 border-t border-white/5">
                  <div>
                    <p className="text-xs text-gray-500">Total Views</p>
                    <p className="text-lg font-bold text-white">48.2K</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Avg. Watch Time</p>
                    <p className="text-lg font-bold text-white">1m 24s</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Engagement</p>
                    <p className="text-lg font-bold text-white">8.4%</p>
                  </div>
                </div>
              </motion.div>
            </div>

            {/* ── CLIP RESULTS (when in library view or success state) ───────── */}
            {(activeNav === "library" || appState === "success") && clips.length > 0 && (
              <motion.div variants={fadeInUp} className="card-gradient-border p-5">
                <div className="flex items-center justify-between mb-6">
                  <div className="flex items-center gap-3">
                    <Sparkles className="w-5 h-5 text-purple-500" />
                    <h2 className="text-lg font-semibold text-white">Clip Results</h2>
                    <span className="px-2 py-1 bg-purple-500/20 text-purple-400 text-xs font-semibold rounded-full">
                      {clips.length}
                    </span>
                  </div>
                  <button
                    onClick={resetForm}
                    className="px-4 py-2 text-sm font-medium rounded-lg bg-white/5 text-gray-400 hover:text-white hover:bg-white/10 transition-all"
                  >
                    + New Video
                  </button>
                </div>

                <div className="flex gap-4 overflow-x-auto pb-4 scrollbar-hide">
                  {clips.map((clip, idx) => {
                    const clipData = { ...clip, index: clip.index || clip.clip_index || idx + 1 };
                    return (
                      <div
                        key={clipData.index}
                        onClick={() => setSelectedClip(clipData)}
                        className="min-w-[280px] max-w-[280px] bg-[#0d0d14] rounded-xl border border-white/5 overflow-hidden cursor-pointer group hover:border-purple-500/30 transition-all"
                      >
                        <div className="relative aspect-video bg-black">
                          <video
                            src={backendUrl(clipData.path)}
                            className="w-full h-full object-cover opacity-60 group-hover:opacity-80 transition-all"
                          />
                          <div className="absolute inset-0 flex items-center justify-center">
                            <div className="w-12 h-12 rounded-full bg-white/10 backdrop-blur-sm flex items-center justify-center group-hover:scale-110 transition-all">
                              <Play className="w-5 h-5 text-white ml-0.5" fill="white" />
                            </div>
                          </div>
                          <div className="absolute top-3 right-3 flex flex-col gap-2">
                            <ViralityBadge score={clipData.score} />
                            {clipData.rag_reference_used && clipData.rag_reference_used.toLowerCase() !== "none" && (
                              <DnaBadge />
                            )}
                          </div>
                        </div>
                        <div className="p-4">
                          <p className="text-sm font-medium text-white line-clamp-2 mb-2">{clipData.hook}</p>
                          {clipData.suggested_hashtags && (
                            <p className="text-xs text-gray-500 truncate">{clipData.suggested_hashtags}</p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </motion.div>
            )}

            {/* ── HISTORY TABLE ──────────────────────────────────────────────── */}
            {historyJobs.filter(j => j.status === "done").length > 0 && (
              <motion.div variants={fadeInUp} className="card-gradient-border p-5">
                <h2 className="text-lg font-semibold text-white mb-4">Past Projects</h2>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-left text-xs text-gray-500 uppercase tracking-wider border-b border-white/5">
                        <th className="pb-3 pr-4">Title</th>
                        <th className="pb-3 pr-4">Status</th>
                        <th className="pb-3 pr-4">Date</th>
                        <th className="pb-3">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {historyJobs.filter(j => j.status === "done").slice(0, 5).map((job) => (
                        <tr key={job.id} className="border-b border-white/5 last:border-0">
                          <td className="py-3 pr-4">
                            <p className="text-sm text-white truncate max-w-[200px]">{job.video_title}</p>
                          </td>
                          <td className="py-3 pr-4">
                            <StatusBadge status={job.status} />
                          </td>
                          <td className="py-3 pr-4 text-sm text-gray-500">
                            {new Date(job.created_at).toLocaleDateString()}
                          </td>
                          <td className="py-3">
                            <button
                              onClick={() => loadHistoryJob(job.id)}
                              className="text-xs text-purple-400 hover:text-purple-300 transition-all"
                            >
                              Load Results
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </motion.div>
            )}
          </motion.div>
        </div>
      </main>

      {/* ── NEW JOB MODAL ─────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {showNewJobModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
            onClick={() => setShowNewJobModal(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="w-full max-w-lg bg-[#13131a] rounded-2xl border border-white/10 overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
                <h2 className="text-lg font-semibold text-white">New Clip Job</h2>
                <button
                  onClick={() => setShowNewJobModal(false)}
                  className="p-2 rounded-lg hover:bg-white/5 text-gray-400 hover:text-white transition-all"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="p-6 space-y-4">
                {/* Upload Area */}
                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onClick={() => document.getElementById("file-input")?.click()}
                  className={`relative border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center text-center cursor-pointer transition-all ${
                    isDragging
                      ? "border-cyan-400 bg-cyan-400/5 glow-cyan"
                      : "border-purple-500/50 bg-[#0d0d14] hover:border-purple-500 hover:glow-purple-soft"
                  }`}
                >
                  <Upload className={`w-10 h-10 mb-3 ${isDragging ? "text-cyan-400" : "text-purple-500"}`} />
                  <p className="text-sm font-medium text-white mb-1">
                    {file ? file.name : "Drop video here"}
                  </p>
                  <p className="text-xs text-gray-500">or click to browse • MP4, MOV supported</p>
                  <input
                    id="file-input"
                    type="file"
                    accept="video/mp4,video/quicktime,video/mov"
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                    className="hidden"
                  />
                </div>

                {/* Title Input */}
                <div>
                  <label className="block text-xs font-medium text-gray-400 uppercase tracking-wider mb-2">
                    Video Title <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="e.g. Joe Rogan - Elon Musk Interview"
                    className="w-full bg-[#0d0d14] border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-gray-600 focus:border-purple-500 transition-all"
                  />
                </div>

                {/* Description Input */}
                <div>
                  <label className="block text-xs font-medium text-gray-400 uppercase tracking-wider mb-2">
                    Description <span className="text-gray-600">(optional)</span>
                  </label>
                  <input
                    type="text"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Brief description about the video..."
                    className="w-full bg-[#0d0d14] border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-gray-600 focus:border-purple-500 transition-all"
                  />
                </div>

                {/* Submit Button */}
                <button
                  onClick={startProcessing}
                  disabled={!file || !title}
                  className={`w-full py-3 rounded-xl font-semibold text-sm transition-all ${
                    file && title
                      ? "bg-gradient-to-r from-purple-600 to-cyan-500 text-white hover:opacity-90 glow-purple"
                      : "bg-gray-800 text-gray-500 cursor-not-allowed"
                  }`}
                >
                  Start Analysis
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── CLIP DETAIL MODAL ────────────────────────────────────────────────── */}
      <AnimatePresence>
        {selectedClip && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/90 backdrop-blur-sm"
            onClick={() => setSelectedClip(null)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="w-full max-w-5xl max-h-[90vh] overflow-y-auto bg-[#13131a] rounded-2xl border border-white/10"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="grid grid-cols-1 lg:grid-cols-2">
                {/* Video Player */}
                <div className="relative aspect-[9/16] lg:aspect-auto lg:h-full bg-black">
                  <video
                    src={backendUrl(selectedClip.path)}
                    controls
                    autoPlay
                    className="w-full h-full object-contain"
                  />
                  <button
                    onClick={() => setSelectedClip(null)}
                    className="absolute top-4 right-4 p-2 rounded-full bg-black/50 text-white hover:bg-black/70 transition-all lg:hidden"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>

                {/* Details */}
                <div className="p-6 space-y-6">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <CircularProgress value={selectedClip.score} size={60} strokeWidth={5} />
                      <div>
                        <p className="text-xs text-gray-500 uppercase tracking-wider">Viral Score</p>
                        <p className="text-2xl font-bold text-white">{selectedClip.score}/100</p>
                      </div>
                    </div>
                    <button
                      onClick={() => setSelectedClip(null)}
                      className="p-2 rounded-lg hover:bg-white/5 text-gray-400 hover:text-white transition-all hidden lg:block"
                    >
                      <X className="w-5 h-5" />
                    </button>
                  </div>

                  {/* Hook */}
                  <div>
                    <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Hook</h3>
                    <p className="text-white font-medium">{selectedClip.hook}</p>
                  </div>

                  {/* Why Selected */}
                  {selectedClip.why_selected && (
                    <div>
                      <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Why Selected</h3>
                      <p className="text-gray-300 text-sm">{selectedClip.why_selected}</p>
                    </div>
                  )}

                  {/* Psychological Trigger */}
                  {selectedClip.psychological_trigger && (
                    <div>
                      <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Psychological Trigger</h3>
                      <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-purple-500/20 text-purple-400 text-sm font-medium">
                        <Brain className="w-3.5 h-3.5" />
                        {selectedClip.psychological_trigger}
                      </span>
                    </div>
                  )}

                  {/* RAG Reference */}
                  {selectedClip.rag_reference_used && selectedClip.rag_reference_used.toLowerCase() !== "none" && (
                    <div>
                      <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">DNA Reference</h3>
                      <div className="p-3 bg-cyan-500/10 border-l-2 border-cyan-500 rounded-r-lg">
                        <p className="text-sm text-cyan-300 italic">{selectedClip.rag_reference_used}</p>
                      </div>
                    </div>
                  )}

                  {/* Transcript */}
                  {selectedClip.transcript_excerpt && (
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider">Transcript</h3>
                        <CopyButton text={selectedClip.transcript_excerpt} />
                      </div>
                      <div className="p-3 bg-[#0d0d14] rounded-lg border border-white/5 max-h-32 overflow-y-auto">
                        <p className="text-sm text-gray-400 font-mono">{selectedClip.transcript_excerpt}</p>
                      </div>
                    </div>
                  )}

                  {/* Hashtags */}
                  {selectedClip.suggested_hashtags && (
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider">Hashtags</h3>
                        <CopyButton text={selectedClip.suggested_hashtags} />
                      </div>
                      <p className="text-sm text-purple-400">{selectedClip.suggested_hashtags}</p>
                    </div>
                  )}

                  {/* Download Button */}
                  <a
                    href={backendUrl(selectedClip.path)}
                    download
                    className="flex items-center justify-center gap-2 w-full py-3 rounded-xl bg-gradient-to-r from-purple-600 to-cyan-500 text-white font-semibold hover:opacity-90 transition-all"
                  >
                    <Download className="w-4 h-4" />
                    Download Clip
                  </a>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
