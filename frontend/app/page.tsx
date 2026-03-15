"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  Upload,
  Settings,
  Play,
  X,
  Download,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Zap,
  Sparkles,
  FileText,
  Brain,
  BarChart3,
  Database,
  Plus,
  Trash2,
  TrendingUp,
} from "lucide-react";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://clip-pipeline-production.up.railway.app";

// ─── TİPLER ──────────────────────────────────────────────────────────────────
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
  real_retention?: number | null;
  real_swipe_rate?: number | null;
  feedback_score?: number | null;
  feedback_submitted_at?: string | null;
};

type JobResult = {
  clips: ClipResult[];
  original_title: string;
  clips_count: number;
  metadata_path?: string | null;
  pdf_path?: string | null;
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
  metadata_path?: string | null;
  pdf_path?: string | null;
};

type AppState = "idle" | "uploading" | "processing" | "success" | "error";

// ─── YARDIMCI COMPONENTS ─────────────────────────────────────────────────────

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
      {copied ? "Kopyalandı" : label || "Kopyala"}
    </button>
  );
}

function StatusBadge({ state }: { state: AppState }) {
  const config = {
    idle: { text: "Hazır", bg: "bg-gray-600", textColor: "text-gray-300" },
    uploading: { text: "Yükleniyor", bg: "bg-blue-600", textColor: "text-blue-100" },
    processing: { text: "Analiz Ediliyor", bg: "bg-purple-600", textColor: "text-purple-100" },
    success: { text: "Tamamlandı", bg: "bg-green-600", textColor: "text-green-100" },
    error: { text: "Hata", bg: "bg-red-600", textColor: "text-red-100" },
  };
  const { text, bg, textColor } = config[state];
  return (
    <span className={`px-3 py-1 text-xs font-semibold rounded-full ${bg} ${textColor}`}>
      {text}
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
      <Zap className="w-3 h-3" />
      DNA Match
    </div>
  );
}

function formatDate(dateStr: string) {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("tr-TR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch {
    return dateStr;
  }
}

// ─── GENOME & HEALTH TYPES ───────────────────────────────────────────────────
type GenomeData = {
  version_id?: number;
  mode?: string;
  calculated_at?: string;
  tier_thresholds?: { tier5?: number; tier4?: number; tier3?: number };
  golden_duration?: { min?: number; max?: number; avg?: number };
  content_type_weights?: Record<string, number>;
};

type HealthData = {
  status?: "green" | "yellow" | "red";
  override_rate?: number;
  signal_accuracy?: number;
  drift_alerts?: { rule_key?: string }[];
  stale_feedback_count?: number;
};

// ─── GENOME CARD ──────────────────────────────────────────────────────────────
function GenomeCard({ channelId }: { channelId: string }) {
  const [data, setData] = useState<GenomeData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState(false);

  const load = async () => {
    if (open) { setOpen(false); return; }
    setOpen(true);
    if (data || loading) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/backend/v2/genome/${channelId}`);
      if (!res.ok) throw new Error();
      const json = await res.json();
      setData(json);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  const modeBadge = (mode?: string) => {
    const cfg: Record<string, { color: string; label: string }> = {
      real:      { color: "bg-green-500/20 text-green-400 border-green-500/30",  label: "Real" },
      bootstrap: { color: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30", label: "Bootstrap" },
      proxy:     { color: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",    label: "Proxy" },
    };
    const m = (mode || "real").toLowerCase();
    const { color, label } = cfg[m] || cfg["real"];
    return <span className={`px-2 py-0.5 rounded-full text-xs font-semibold border ${color}`}>{label}</span>;
  };

  const fmtDate = (d?: string) => {
    if (!d) return "—";
    try { return new Date(d).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" }); }
    catch { return d; }
  };

  const weights = data?.content_type_weights ? Object.entries(data.content_type_weights).sort((a, b) => b[1] - a[1]).slice(0, 6) : [];

  return (
    <div className="bg-[#111111] rounded-2xl border border-white/5 overflow-hidden">
      <button
        onClick={load}
        className="w-full flex items-center gap-3 p-6 hover:bg-white/[0.02] transition-all text-left"
      >
        <Brain className="w-8 h-8 text-purple-500 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-white">Channel Genome</h3>
          <p className="text-xs text-gray-500 mt-0.5">Tier thresholds, golden duration & content weights</p>
        </div>
        {open ? <ChevronUp className="w-4 h-4 text-gray-500" /> : <ChevronDown className="w-4 h-4 text-gray-500" />}
      </button>

      {open && (
        <div className="px-6 pb-6 border-t border-white/5 pt-4">
          {loading && <p className="text-sm text-gray-500">Loading...</p>}
          {error && <p className="text-sm text-gray-500">No data yet</p>}
          {data && !loading && (
            <div className="space-y-4">
              {/* Version + Mode */}
              <div className="flex items-center gap-3 flex-wrap">
                {modeBadge(data.mode)}
                {data.version_id != null && <span className="text-xs text-gray-500">v{data.version_id}</span>}
                {data.calculated_at && <span className="text-xs text-gray-600">{fmtDate(data.calculated_at)}</span>}
              </div>

              {/* Tier Thresholds */}
              {data.tier_thresholds && (
                <div>
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Tier Thresholds</p>
                  <div className="grid grid-cols-3 gap-2">
                    {(["tier5", "tier4", "tier3"] as const).map((t) => (
                      <div key={t} className="bg-black/30 rounded-lg p-2 text-center">
                        <p className="text-xs text-gray-500">{t.toUpperCase()}</p>
                        <p className="text-sm font-bold text-white mt-0.5">{data.tier_thresholds![t]?.toLocaleString() ?? "—"}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Golden Duration */}
              {data.golden_duration && (
                <div>
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Golden Duration</p>
                  <div className="flex items-center gap-2">
                    <Zap className="w-3.5 h-3.5 text-yellow-400" />
                    <span className="text-sm text-white">
                      {Math.round(data.golden_duration.min ?? 0)}s – {Math.round(data.golden_duration.max ?? 0)}s
                    </span>
                    <span className="text-xs text-gray-500">(avg {Math.round(data.golden_duration.avg ?? 0)}s)</span>
                  </div>
                </div>
              )}

              {/* Content Type Weights */}
              {weights.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Content Type Weights</p>
                  <div className="space-y-1.5">
                    {weights.map(([ctype, w]) => (
                      <div key={ctype}>
                        <div className="flex justify-between text-xs mb-0.5">
                          <span className="text-gray-400 capitalize">{ctype.replace(/_/g, " ")}</span>
                          <span className="text-gray-300">{(w * 100).toFixed(0)}%</span>
                        </div>
                        <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-purple-500 to-cyan-400 rounded-full"
                            style={{ width: `${Math.min(w * 100, 100)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── HEALTH CARD ──────────────────────────────────────────────────────────────
function HealthCard({ channelId }: { channelId: string }) {
  const [data, setData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState(false);

  const load = async () => {
    if (open) { setOpen(false); return; }
    setOpen(true);
    if (data || loading) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/backend/v2/health/${channelId}`);
      if (!res.ok) throw new Error();
      const json = await res.json();
      setData(json);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  const statusDot = (s?: string) => {
    const cfg: Record<string, string> = {
      green:  "bg-green-500",
      yellow: "bg-yellow-400",
      red:    "bg-red-500",
    };
    return <span className={`inline-block w-2.5 h-2.5 rounded-full ${cfg[s || "green"] || cfg.green} flex-shrink-0`} />;
  };

  const pct = (v?: number) => v != null ? `${(v * 100).toFixed(1)}%` : "—";

  return (
    <div className="bg-[#111111] rounded-2xl border border-white/5 overflow-hidden">
      <button
        onClick={load}
        className="w-full flex items-center gap-3 p-6 hover:bg-white/[0.02] transition-all text-left"
      >
        <BarChart3 className="w-8 h-8 text-cyan-500 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-white">System Health</h3>
          <p className="text-xs text-gray-500 mt-0.5">Override rate, signal accuracy & drift alerts</p>
        </div>
        {open ? <ChevronUp className="w-4 h-4 text-gray-500" /> : <ChevronDown className="w-4 h-4 text-gray-500" />}
      </button>

      {open && (
        <div className="px-6 pb-6 border-t border-white/5 pt-4">
          {loading && <p className="text-sm text-gray-500">Loading...</p>}
          {error && <p className="text-sm text-gray-500">No data yet</p>}
          {data && !loading && (
            <div className="space-y-4">
              {/* Status */}
              <div className="flex items-center gap-2">
                {statusDot(data.status)}
                <span className="text-sm font-semibold text-white capitalize">{data.status ?? "—"}</span>
              </div>

              {/* Stats Grid */}
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-black/30 rounded-lg p-3">
                  <p className="text-xs text-gray-500 mb-1">Override Rate</p>
                  <p className="text-lg font-bold text-white">{pct(data.override_rate)}</p>
                </div>
                <div className="bg-black/30 rounded-lg p-3">
                  <p className="text-xs text-gray-500 mb-1">Signal Accuracy</p>
                  <p className="text-lg font-bold text-white">{pct(data.signal_accuracy)}</p>
                </div>
                <div className="bg-black/30 rounded-lg p-3">
                  <p className="text-xs text-gray-500 mb-1">Stale Feedback</p>
                  <p className="text-lg font-bold text-white">{data.stale_feedback_count ?? 0}</p>
                </div>
                <div className="bg-black/30 rounded-lg p-3">
                  <p className="text-xs text-gray-500 mb-1">Drift Alerts</p>
                  <p className="text-lg font-bold text-white">{data.drift_alerts?.length ?? 0}</p>
                </div>
              </div>

              {/* Drift Alert Keys */}
              {data.drift_alerts && data.drift_alerts.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-yellow-400 uppercase tracking-wider mb-2">Drift Keys</p>
                  <div className="flex flex-wrap gap-1.5">
                    {data.drift_alerts.map((a, i) => (
                      <span key={i} className="px-2 py-0.5 bg-yellow-500/10 text-yellow-400 text-xs rounded border border-yellow-500/20">
                        {a.rule_key ?? `alert-${i + 1}`}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── PERFORMANCE MODAL ───────────────────────────────────────────────────────
type PerformanceFormData = {
  views: string;
  views_48h: string;
  views_7d: string;
  avg_watch_pct: string;
  first_3s_retention: string;
  swipe_away_rate: string;
};

function PerformanceModal({
  clip,
  jobId,
  onClose,
  onSuccess,
  onError,
}: {
  clip: ClipResult;
  jobId: string;
  onClose: () => void;
  onSuccess: () => void;
  onError: () => void;
}) {
  const [form, setForm] = useState<PerformanceFormData>({
    views: "",
    views_48h: "",
    views_7d: "",
    avg_watch_pct: "",
    first_3s_retention: "",
    swipe_away_rate: "",
  });
  const [submitting, setSubmitting] = useState(false);

  const fields: { key: keyof PerformanceFormData; label: string; placeholder: string }[] = [
    { key: "views", label: "Total Views", placeholder: "Total views" },
    { key: "views_48h", label: "Views in First 48h", placeholder: "Views in first 48h" },
    { key: "views_7d", label: "Views in 7 Days", placeholder: "Views in 7 days" },
    { key: "avg_watch_pct", label: "Avg Watch %", placeholder: "Avg watch %" },
    { key: "first_3s_retention", label: "First 3s Retention %", placeholder: "First 3s retention %" },
    { key: "swipe_away_rate", label: "Swipe Away Rate %", placeholder: "Swipe away rate %" },
  ];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    const clipId = clip.id ?? clip.clip_index ?? clip.index;
    try {
      const res = await fetch(`/api/backend/v2/feedback/${clipId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          clip_id: clipId,
          job_id: jobId,
          views: form.views ? Number(form.views) : undefined,
          views_48h: form.views_48h ? Number(form.views_48h) : undefined,
          views_7d: form.views_7d ? Number(form.views_7d) : undefined,
          avg_watch_pct: form.avg_watch_pct ? Number(form.avg_watch_pct) : undefined,
          first_3s_retention: form.first_3s_retention ? Number(form.first_3s_retention) : undefined,
          swipe_rate: form.swipe_away_rate ? Number(form.swipe_away_rate) : undefined,
        }),
      });
      if (res.ok) {
        onSuccess();
        onClose();
      } else {
        onError();
      }
    } catch {
      onError();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="bg-[#141414] rounded-2xl shadow-2xl w-full max-w-md border border-white/10">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-green-400" />
            <span className="font-semibold text-white">Update Performance</span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 bg-white/5 hover:bg-white/10 rounded-lg transition-all"
          >
            <X className="w-4 h-4 text-gray-400" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            {fields.map(({ key, label, placeholder }) => (
              <div key={key}>
                <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">
                  {label}
                </label>
                <input
                  type="number"
                  step="any"
                  min="0"
                  value={form[key]}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                  placeholder={placeholder}
                  className="w-full bg-[#1a1a1a] border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:border-green-500/60 focus:outline-none transition-all"
                />
              </div>
            ))}
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full mt-2 py-3 rounded-xl font-semibold text-sm bg-gradient-to-r from-green-600 to-emerald-500 text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-[0_0_15px_rgba(34,197,94,0.2)]"
          >
            {submitting ? "Submitting..." : "Submit Performance Data"}
          </button>
        </form>
      </div>
    </div>
  );
}

// ─── TOAST ────────────────────────────────────────────────────────────────────
function Toast({ type, onDone }: { type: "success" | "error"; onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3500);
    return () => clearTimeout(t);
  }, [onDone]);
  return (
    <div
      className={`fixed bottom-6 right-6 z-[70] flex items-center gap-3 px-5 py-3 rounded-xl shadow-2xl text-sm font-medium transition-all ${
        type === "success"
          ? "bg-green-600/90 text-white border border-green-500/40"
          : "bg-red-600/90 text-white border border-red-500/40"
      }`}
    >
      {type === "success" ? (
        <><Check className="w-5 h-5" /> Performance data saved successfully!</>
      ) : (
        <><X className="w-5 h-5" /> Failed to save performance data. Try again.</>
      )}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// ANA COMPONENT
// =════════════════════════════════════════════════════════════════════════════
export default function PrognotStudio() {
  // --- Yeni Proje State ---
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [appState, setAppState] = useState<AppState>("idle");
  const [logs, setLogs] = useState<string[]>([]);

  // --- UI State ---
  const [isDragging, setIsDragging] = useState(false);
  const [selectedClip, setSelectedClip] = useState<ClipResult | null>(null);
  const [historyExpanded, setHistoryExpanded] = useState(false);
  const [showPerfModal, setShowPerfModal] = useState(false);
  const [toast, setToast] = useState<"success" | "error" | null>(null);

  // --- Geçmiş Projeler State ---
  const [historyJobs, setHistoryJobs] = useState<HistoryJob[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const logsEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const terminalContainerRef = useRef<HTMLDivElement>(null);

  // ── Geçmiş Projeleri Yükle ─────────────────────────────────────────────────
  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/jobs?channel_id=speedy_cast`);
      const data = await res.json();
      setHistoryJobs(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error("History load failed", e);
    }
    setHistoryLoading(false);
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // ── Polling ────────────────────────────────────────────────────────────────
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
          if (data.status === "running") {
            setAppState("processing");
          }
          if (data.status === "done") {
            setAppState("success");
            loadHistory();
          }
          if (data.status === "error") {
            setAppState("error");
          }
        } catch (e) {
          console.error("Status check failed", e);
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [jobId, status, loadHistory]);

  useEffect(() => {
    if (terminalContainerRef.current) {
      terminalContainerRef.current.scrollTop = terminalContainerRef.current.scrollHeight;
    }
  }, [logs]);

  // ── Handlers ───────────────────────────────────────────────────────────────
  const deleteHistoryJob = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (window.confirm("Bu geçmiş projesini silmek istediğinize emin misiniz?")) {
      try {
        await fetch(`${BACKEND_URL}/jobs/${id}`, { method: "DELETE" });
        loadHistory();
      } catch (err) {
        console.error("Delete job failed", err);
      }
    }
  };

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
    setLogs(["[SİSTEM] Pipeline başlatılıyor...", "[UPLOAD] Dosya sunucuya transfer ediliyor..."]);
    setStatus({ status: "uploading", step: "Yükleniyor...", progress: 5, result: null, error: null });
    const formData = new FormData();
    formData.append("video", file);
    formData.append("title", title);
    formData.append("description", description);
    formData.append("channel_id", "speedy_cast");
    try {
      const res = await fetch(`${BACKEND_URL}/upload`, { method: "POST", body: formData });
      const data = await res.json();
      setJobId(data.job_id);
    } catch {
      setAppState("error");
      setLogs((prev) => [...prev, "[HATA] Bağlantı hatası: Sunucu yanıt vermiyor."]);
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
      const res = await fetch(`${BACKEND_URL}/status/${jobIdToLoad}`);
      const data: JobStatus = await res.json();
      if (data.status === "done" && data.result?.clips?.length) {
        setStatus(data);
        setJobId(jobIdToLoad);
        setAppState("success");
        setLogs([`[GEÇMİŞ] "${data.result.original_title}" yüklendi — ${data.result.clips_count} klip`]);
        window.scrollTo({ top: 0, behavior: "smooth" });
      } else {
        console.warn("Job done değil veya klip yok:", data.status);
      }
    } catch (e) {
      console.error("History detail failed", e);
    }
  };

  const backendUrl = (path: string) => `${BACKEND_URL.replace(/\/$/, "")}${path}`;

  const clips = status?.result?.clips?.map(c => ({
    ...c,
    index: c.index ?? c.clip_index ?? 0,
  })) || [];

  // ═══════════════════════════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════════════════════════
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      {/* ── TOP NAVBAR ─────────────────────────────────────────────────────── */}
      <nav className="fixed top-0 left-0 right-0 z-50 h-16 bg-[#0a0a0a]/80 backdrop-blur-xl border-b border-white/5">
        <div className="max-w-7xl mx-auto h-full px-6 flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-2">
            <span className="text-xl font-bold text-white">PROGNOT</span>
            <span className="text-xl font-bold bg-gradient-to-r from-purple-500 to-cyan-400 bg-clip-text text-transparent">
              STUDIO
            </span>
          </div>

          {/* Channel Tabs */}
          <div className="flex items-center gap-2">
            <button className="flex items-center gap-2 px-4 py-2 rounded-full bg-purple-600/20 text-purple-400 border border-purple-500/30 glow-purple text-sm font-medium">
              <span>🎬</span>
              <span>Speedy Cast Clip</span>
            </button>
            <button
              className="flex items-center justify-center w-9 h-9 rounded-full bg-white/5 text-gray-500 border border-white/10 cursor-not-allowed"
              title="Yakında"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>

          {/* Right Side */}
          <div className="flex items-center gap-4">
            <button className="p-2 rounded-lg hover:bg-white/5 text-gray-400 hover:text-white transition-all">
              <Settings className="w-5 h-5" />
            </button>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-green-500/10 border border-green-500/20">
              <span className="w-2 h-2 rounded-full bg-green-500 pulse-live" />
              <span className="text-xs font-medium text-green-400">Live</span>
            </div>
          </div>
        </div>
      </nav>

      {/* ── MAIN CONTENT ───────────────────────────────────────────────────── */}
      <main className="pt-24 pb-16 px-6 max-w-7xl mx-auto">
        {/* ── SECTION 1: UPLOAD AREA ───────────────────────────────────────── */}
        {appState === "idle" && (
          <section className="slide-in mb-12">
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`relative border-2 border-dashed rounded-2xl p-16 flex flex-col items-center justify-center text-center cursor-pointer transition-all ${isDragging
                ? "border-cyan-400 bg-cyan-400/5 glow-cyan"
                : file
                  ? "border-green-500 bg-green-500/5"
                  : "border-purple-500/50 bg-[#111111] hover:border-purple-500 hover:glow-purple"
                }`}
            >
              {file ? (
                <>
                  <Check className="w-16 h-16 mb-4 text-green-500" />
                  <h2 className="text-xl font-semibold text-white mb-2">
                    {file.name}
                  </h2>
                  <p className="text-sm text-green-400 font-medium">
                    {(file.size / (1024 * 1024)).toFixed(2)} MB
                  </p>
                </>
              ) : (
                <>
                  <Upload className={`w-16 h-16 mb-4 ${isDragging ? "text-cyan-400" : "text-purple-500"}`} />
                  <h2 className="text-xl font-semibold text-white mb-2">
                    Videoyu buraya bırak
                  </h2>
                  <p className="text-sm text-gray-500">
                    veya dosya seç • MP4, MOV desteklenir
                  </p>
                </>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept="video/mp4,video/quicktime,video/mov"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="hidden"
              />
            </div>

            {/* Input Fields */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
              <div>
                <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                  Video Başlığı <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Örn: Joe Rogan - Elon Musk Röportajı"
                  className="w-full bg-[#141414] border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-gray-600 focus:border-purple-500 transition-all"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                  Açıklama <span className="text-gray-600">(Opsiyonel)</span>
                </label>
                <input
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Videonun içeriği hakkında kısa bilgi..."
                  className="w-full bg-[#141414] border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-gray-600 focus:border-purple-500 transition-all"
                />
              </div>
            </div>

            {/* Submit Button */}
            <button
              onClick={startProcessing}
              disabled={!file || !title}
              className={`w-full mt-6 py-4 rounded-xl font-bold text-sm transition-all ${file && title
                ? "bg-gradient-to-r from-green-500 to-green-600 text-white hover:opacity-90 shadow-[0_0_15px_rgba(34,197,94,0.3)]"
                : "bg-gray-800 text-gray-500 cursor-not-allowed"
                }`}
            >
              🚀 Analizi Başlat
            </button>
          </section>
        )}

        {/* ── SECTION 2: LIVE ANALYSIS TERMINAL ────────────────────────────── */}
        {(appState === "uploading" || appState === "processing" || appState === "error") && (
          <section className="slide-in mb-12">
            <div className="bg-[#111111] rounded-2xl border border-white/5 overflow-hidden">
              {/* Terminal Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
                <div className="flex items-center gap-3">
                  <Sparkles className="w-5 h-5 text-purple-500" />
                  <span className="font-semibold text-white">Pipeline Terminali</span>
                </div>
                <StatusBadge state={appState} />
              </div>

              {/* Progress Bar */}
              <div className="px-6 py-4">
                <div className="w-full h-2 bg-[#1a1a1a] rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${appState === "error" ? "bg-red-500" : "progress-shimmer"
                      }`}
                    style={{ width: `${status?.progress || 0}%` }}
                  />
                </div>
                <p className="text-xs text-gray-500 mt-2">
                  {status?.step || "Başlatılıyor..."}
                </p>
              </div>

              {/* Terminal Output */}
              <div ref={terminalContainerRef} className="bg-black rounded-xl mx-6 mb-6 p-4 h-64 max-h-96 overflow-y-auto font-mono text-xs scroll-smooth">
                {logs.map((log, i) => {
                  const isError = log.toLowerCase().includes("hata") || log.toLowerCase().includes("error");
                  const isWarning = log.toLowerCase().includes("uyarı") || log.toLowerCase().includes("warning");
                  const color = isError ? "text-red-500" : isWarning ? "text-yellow-500" : "text-green-500";
                  return (
                    <div key={i} className={`${color} mb-1`}>
                      {log}
                    </div>
                  );
                })}
                {appState === "processing" && (
                  <span className="text-green-500 animate-pulse">_</span>
                )}
                <div ref={logsEndRef} />
              </div>

              {/* Error Retry Button */}
              {appState === "error" && (
                <div className="px-6 pb-6">
                  <button
                    onClick={resetForm}
                    className="flex items-center justify-center gap-2 w-full py-3 rounded-xl bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 transition-all"
                  >
                    <RefreshCw className="w-4 h-4" />
                    Tekrar Dene
                  </button>
                </div>
              )}
            </div>
          </section>
        )}

        {/* ── SECTION 3: CLIP RESULTS ──────────────────────────────────────── */}
        {appState === "success" && clips.length > 0 && (
          <section className="slide-in mb-12">
            {/* Section Header */}
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <span className="text-2xl">🎯</span>
                <h2 className="text-xl font-bold text-white">Bulunan Klipler</h2>
                <span className="px-2 py-1 bg-purple-500/20 text-purple-400 text-xs font-semibold rounded-full">
                  {clips.length}
                </span>
              </div>
              <div className="flex items-center gap-3">
                {status?.result?.pdf_path && (
                  <button
                    onClick={() => window.open(backendUrl(status.result!.pdf_path!), "_blank")}
                    className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-all border border-red-500/30"
                  >
                    <FileText className="w-4 h-4" />
                    PDF Rapor İndir
                  </button>
                )}
                {status?.result?.metadata_path && (
                  <button
                    onClick={() => window.open(backendUrl(status.result!.metadata_path!), "_blank")}
                    className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 transition-all border border-cyan-500/30"
                  >
                    <Database className="w-4 h-4" />
                    Metadata İndir
                  </button>
                )}
                <button
                  onClick={resetForm}
                  className="px-4 py-2 text-sm font-medium rounded-lg bg-white/5 text-gray-400 hover:text-white hover:bg-white/10 transition-all"
                >
                  + Yeni Video
                </button>
              </div>
            </div>

            {/* Clips Horizontal Scroll */}
            <div className="flex gap-6 overflow-x-auto pb-4 scrollbar-hide">
              {clips.map((clip, idx) => {
                const clipData = { ...clip, index: clip.index || clip.clip_index || idx + 1 };
                return (
                  <div
                    key={clipData.index}
                    onClick={() => setSelectedClip(clipData)}
                    className="min-w-[300px] max-w-[300px] bg-[#111111] rounded-2xl border border-white/5 overflow-hidden cursor-pointer card-hover group"
                  >
                    {/* Thumbnail */}
                    <div className="relative aspect-video bg-[#0a0a0a]">
                      <video
                        src={backendUrl(clipData.path)}
                        className="w-full h-full object-cover opacity-60 group-hover:opacity-80 transition-all"
                      />
                      <div className="absolute inset-0 flex items-center justify-center">
                        <div className="w-12 h-12 rounded-full bg-white/10 backdrop-blur-sm flex items-center justify-center group-hover:scale-110 transition-all">
                          <Play className="w-5 h-5 text-white ml-0.5" fill="white" />
                        </div>
                      </div>
                      {/* Badges */}
                      <div className="absolute top-3 right-3 flex flex-col gap-2">
                        <ViralityBadge score={clipData.score} />
                        {clipData.rag_reference_used && clipData.rag_reference_used.toLowerCase() !== "none" && (
                          <DnaBadge />
                        )}
                      </div>
                    </div>

                    {/* Body */}
                    <div className="p-4">
                      <p className="text-sm text-gray-300 italic line-clamp-2 mb-2">
                        &ldquo;{clipData.hook}&rdquo;
                      </p>
                      {clipData.suggested_title && (
                        <p className="text-xs text-gray-500 line-clamp-1">{clipData.suggested_title}</p>
                      )}
                      {clipData.suggested_hashtags && (
                        <div className="flex flex-wrap gap-1 mt-3">
                          {clipData.suggested_hashtags.split(" ").slice(0, 3).map((tag, i) => (
                            <span key={i} className="px-2 py-0.5 bg-purple-500/20 text-purple-400 text-xs rounded-full">
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Footer */}
                    <div className="px-4 pb-4">
                      <button className="w-full py-2 text-xs font-medium text-purple-400 hover:text-purple-300 transition-all">
                        Detayları Gör →
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* ── SECTION 4: PAST PROJECTS ─────────────────────────────────────── */}
        <section className="mb-12">
          <button
            onClick={() => setHistoryExpanded(!historyExpanded)}
            className="w-full flex items-center justify-between p-4 bg-[#111111] rounded-2xl border border-white/5 hover:border-white/10 transition-all"
          >
            <div className="flex items-center gap-3">
              <span className="text-xl">📁</span>
              <span className="font-semibold text-white">Geçmiş Projeler</span>
              <span className="px-2 py-0.5 bg-white/5 text-gray-400 text-xs rounded-full">
                {historyJobs.length}
              </span>
            </div>
            {historyExpanded ? (
              <ChevronUp className="w-5 h-5 text-gray-500" />
            ) : (
              <ChevronDown className="w-5 h-5 text-gray-500" />
            )}
          </button>

          {historyExpanded && (
            <div className="mt-4 bg-[#111111] rounded-2xl border border-white/5 overflow-hidden slide-in">
              {historyLoading ? (
                <div className="p-8 text-center">
                  <RefreshCw className="w-6 h-6 text-gray-500 animate-spin mx-auto" />
                </div>
              ) : historyJobs.length === 0 ? (
                <div className="p-12 text-center">
                  <FileText className="w-12 h-12 text-gray-700 mx-auto mb-3" />
                  <p className="text-sm text-gray-500">Henüz proje yok</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-white/5">
                        <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-6 py-4">
                          Video Başlığı
                        </th>
                        <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-6 py-4">
                          Tarih
                        </th>
                        <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-6 py-4">
                          Durum
                        </th>
                        <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-6 py-4">
                          İşlem
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {historyJobs.map((job) => (
                        <tr key={job.id} className="border-b border-white/5 hover:bg-white/[0.02] transition-all">
                          <td className="px-6 py-4">
                            <span className="text-sm text-white font-medium">{job.video_title}</span>
                          </td>
                          <td className="px-6 py-4">
                            <span className="text-sm text-gray-400">{formatDate(job.created_at)}</span>
                          </td>
                          <td className="px-6 py-4">
                            {job.status === "done" ? (
                              <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-green-500/20 text-green-400 text-xs font-medium">
                                <Check className="w-3 h-3" />
                                Tamamlandı
                              </span>
                            ) : job.status === "running" ? (
                              <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-purple-500/20 text-purple-400 text-xs font-medium">
                                <RefreshCw className="w-3 h-3 animate-spin" />
                                İşleniyor
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-red-500/20 text-red-400 text-xs font-medium">
                                <X className="w-3 h-3" />
                                Hata
                              </span>
                            )}
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-4">
                              <button
                                onClick={() => loadHistoryJob(job.id)}
                                className="text-sm font-medium text-purple-400 hover:text-purple-300 transition-all"
                              >
                                Sonuçları Yükle
                              </button>
                              <button
                                onClick={(e) => deleteHistoryJob(job.id, e)}
                                className="p-1 text-gray-500 hover:text-red-500 transition-all rounded hover:bg-white/5"
                                title="Sil"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </section>

        {/* ── ACTIVE INFO CARDS ─────────────────────────────────────────────── */}
        <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <GenomeCard channelId="speedy_cast" />
          <HealthCard channelId="speedy_cast" />
        </section>
      </main>

      {/* ═══════════════════════════════════════════════════════════════════════
          KLİP DETAY MODALI
          ═══════════════════════════════════════════════════════════════════════ */}
      {selectedClip && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="bg-[#111111] rounded-2xl shadow-2xl w-full max-w-5xl max-h-[90vh] overflow-hidden flex flex-col md:flex-row relative border border-white/10">
            {/* Close Button */}
            <button
              onClick={() => setSelectedClip(null)}
              className="absolute top-4 right-4 z-50 p-2 bg-white/10 hover:bg-white/20 rounded-full transition-all"
            >
              <X className="w-5 h-5 text-white" />
            </button>

            {/* Left: Video Player */}
            <div className="md:w-5/12 bg-black flex items-center justify-center">
              <video controls autoPlay className="w-full max-h-[90vh] object-contain">
                <source src={backendUrl(selectedClip.path)} type="video/mp4" />
              </video>
            </div>

            {/* Right: Details */}
            <div className="md:w-7/12 flex flex-col overflow-hidden">
              {/* Header */}
              <div className="p-6 border-b border-white/5">
                <div className="flex items-center gap-4">
                  {/* Virality Score Ring */}
                  <div className="relative w-20 h-20">
                    <svg className="w-full h-full transform -rotate-90">
                      <circle
                        cx="40"
                        cy="40"
                        r="36"
                        fill="none"
                        stroke="#1a1a1a"
                        strokeWidth="6"
                      />
                      <circle
                        cx="40"
                        cy="40"
                        r="36"
                        fill="none"
                        stroke={selectedClip.score >= 85 ? "#22c55e" : selectedClip.score >= 70 ? "#eab308" : "#ef4444"}
                        strokeWidth="6"
                        strokeDasharray={`${(selectedClip.score / 100) * 226} 226`}
                        strokeLinecap="round"
                      />
                    </svg>
                    <span className="absolute inset-0 flex items-center justify-center text-2xl font-bold text-white">
                      {selectedClip.score}
                    </span>
                  </div>
                  <div>
                    <h2 className="text-xl font-bold text-white">
                      {selectedClip.suggested_title || `Klip #${selectedClip.index}`}
                    </h2>
                    <p className="text-sm text-gray-500">Viral Potansiyel Skoru</p>
                  </div>
                </div>
              </div>

              {/* Scrollable Content */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {/* Why Selected */}
                {selectedClip.why_selected && (
                  <div>
                    <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                      Neden Seçildi
                    </h3>
                    <p className="text-sm text-gray-300 leading-relaxed bg-white/5 p-4 rounded-xl">
                      {selectedClip.why_selected}
                    </p>
                  </div>
                )}

                {/* Psychological Trigger */}
                {selectedClip.psychological_trigger && (
                  <div>
                    <h3 className="text-xs font-semibold text-purple-400 uppercase tracking-wider mb-3">
                      🧠 Psikolojik Tetikleyici
                    </h3>
                    <span className="inline-block px-3 py-1.5 bg-purple-500/20 text-purple-300 text-sm rounded-lg border border-purple-500/30">
                      {selectedClip.psychological_trigger}
                    </span>
                  </div>
                )}

                {/* RAG Reference */}
                {selectedClip.rag_reference_used && selectedClip.rag_reference_used.toLowerCase() !== "none" && (
                  <div>
                    <h3 className="text-xs font-semibold text-cyan-400 uppercase tracking-wider mb-3">
                      🧬 RAG Referansı
                    </h3>
                    <div className="p-4 bg-cyan-500/10 rounded-xl border-l-4 border-cyan-500">
                      <p className="text-sm text-cyan-200 italic">&ldquo;{selectedClip.rag_reference_used}&rdquo;</p>
                    </div>
                  </div>
                )}

                {/* Transcript */}
                {selectedClip.transcript_excerpt && (
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                        Transkript
                      </h3>
                      <CopyButton text={selectedClip.transcript_excerpt} />
                    </div>
                    <div className="p-4 bg-black rounded-xl font-mono text-xs text-gray-400 max-h-40 overflow-y-auto">
                      {selectedClip.transcript_excerpt}
                    </div>
                  </div>
                )}

                {/* Metadata */}
                <div className="space-y-4">
                  {selectedClip.suggested_title && (
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Önerilen Başlık</span>
                        <CopyButton text={selectedClip.suggested_title} />
                      </div>
                      <p className="text-sm text-white bg-white/5 p-3 rounded-lg">{selectedClip.suggested_title}</p>
                    </div>
                  )}
                  {selectedClip.suggested_description && (
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Önerilen Açıklama</span>
                        <CopyButton text={selectedClip.suggested_description} />
                      </div>
                      <p className="text-sm text-gray-300 bg-white/5 p-3 rounded-lg">{selectedClip.suggested_description}</p>
                    </div>
                  )}
                  {selectedClip.suggested_hashtags && (
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Hashtagler</span>
                        <CopyButton text={selectedClip.suggested_hashtags} />
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {selectedClip.suggested_hashtags.split(" ").map((tag, i) => (
                          <span key={i} className="px-3 py-1 bg-purple-500/20 text-purple-300 text-sm rounded-full">
                            {tag}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Footer Buttons */}
              <div className="p-6 border-t border-white/5 space-y-3">
                <button
                  onClick={() => setShowPerfModal(true)}
                  className="flex items-center justify-center gap-2 w-full py-3 bg-green-600/20 text-green-400 rounded-xl font-semibold hover:bg-green-600/30 transition-all border border-green-500/30"
                >
                  <TrendingUp className="w-5 h-5" />
                  Update Performance
                </button>
                <a
                  href={backendUrl(selectedClip.path)}
                  download
                  className="flex items-center justify-center gap-2 w-full py-3 bg-gradient-to-r from-purple-600 to-cyan-500 text-white rounded-xl font-semibold hover:opacity-90 transition-all"
                >
                  <Download className="w-5 h-5" />
                  Klibi İndir
                </a>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Performance Modal */}
      {selectedClip && showPerfModal && jobId && (
        <PerformanceModal
          clip={selectedClip}
          jobId={jobId}
          onClose={() => setShowPerfModal(false)}
          onSuccess={() => setToast("success")}
          onError={() => setToast("error")}
        />
      )}

      {/* Toast */}
      {toast && <Toast type={toast} onDone={() => setToast(null)} />}
    </div>
  );
}