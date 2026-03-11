"use client";

import { useState, useEffect, useRef, useCallback } from "react";

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
  // DB'den gelen (geçmiş projeler)
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

type ModalTab = "video" | "analysis" | "metadata" | "transcript" | "feedback";
type PageMode = "new" | "history";

// ─── İKONLAR ─────────────────────────────────────────────────────────────────
const Icons = {
  Menu: () => (
    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  ),
  Upload: () => (
    <svg className="w-10 h-10 text-blue-500 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
    </svg>
  ),
  Play: () => (
    <svg className="w-8 h-8 text-white" fill="currentColor" viewBox="0 0 20 20">
      <path d="M4 4l12 6-12 6V4z" />
    </svg>
  ),
  Close: () => (
    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
    </svg>
  ),
  Download: () => (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
    </svg>
  ),
  Copy: () => (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
    </svg>
  ),
  Check: () => (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
    </svg>
  ),
  FileText: () => (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  ),
  Trash: () => (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  ),
  Plus: () => (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
    </svg>
  ),
  Clock: () => (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
};

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
    <button onClick={handleCopy} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-all bg-gray-100 hover:bg-gray-200 text-gray-600">
      {copied ? <Icons.Check /> : <Icons.Copy />}
      {copied ? "Kopyalandı" : label || "Kopyala"}
    </button>
  );
}

function ScoreBadge({ score, size = "md" }: { score: number; size?: "sm" | "md" | "lg" }) {
  const bg = score >= 85 ? "from-green-400 to-green-600" : score >= 70 ? "from-yellow-400 to-yellow-600" : "from-red-400 to-red-600";
  const cls = size === "lg" ? "w-16 h-16 text-xl" : size === "sm" ? "w-8 h-8 text-xs" : "w-12 h-12 text-base";
  return <div className={`${cls} rounded-2xl flex items-center justify-center font-bold text-white shadow-lg bg-gradient-to-br ${bg}`}>{score}</div>;
}

function TabButton({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: string; label: string }) {
  return (
    <button onClick={onClick} className={`flex items-center gap-2 px-4 py-2.5 text-sm font-semibold rounded-xl transition-all whitespace-nowrap ${active ? "bg-gray-900 text-white shadow-md" : "text-gray-500 hover:text-gray-800 hover:bg-gray-100"}`}>
      <span>{icon}</span>
      <span className="hidden sm:inline">{label}</span>
    </button>
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

// ═════════════════════════════════════════════════════════════════════════════
// ANA COMPONENT
// ═════════════════════════════════════════════════════════════════════════════
export default function IndustrialPipeline() {
  // --- Yeni Proje State ---
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);

  // --- UI State ---
  const [isSidebarOpen, setSidebarOpen] = useState(true);
  const [isDragging, setIsDragging] = useState(false);
  const [selectedClip, setSelectedClip] = useState<ClipResult | null>(null);
  const [activeTab, setActiveTab] = useState<ModalTab>("video");
  const [pageMode, setPageMode] = useState<PageMode>("new");

  // --- Geçmiş Projeler State ---
  const [historyJobs, setHistoryJobs] = useState<HistoryJob[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedHistoryJob, setSelectedHistoryJob] = useState<JobStatus | null>(null);
  const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(null);

  // --- Feedback State ---
  const [feedbackViews, setFeedbackViews] = useState("");
  const [feedbackRetention, setFeedbackRetention] = useState("");
  const [feedbackSwipeRate, setFeedbackSwipeRate] = useState("");
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [feedbackResult, setFeedbackResult] = useState<{ score: number; flywheel: boolean } | null>(null);

  const logsEndRef = useRef<HTMLDivElement>(null);

  // ── Geçmiş Projeleri Yükle ─────────────────────────────────────────────────
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
          if (data.status === "done" || data.status === "error") {
            setLoading(false);
            loadHistory(); // İşlem bitince sidebar'ı güncelle
          }
        } catch (e) {
          console.error("Status check failed", e);
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [jobId, status, loadHistory]);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  useEffect(() => {
    if (selectedClip) {
      setActiveTab("video");
      setFeedbackResult(null);
      setFeedbackViews("");
      setFeedbackRetention("");
      setFeedbackSwipeRate("");
    }
  }, [selectedClip]);

  // ── Handlers ───────────────────────────────────────────────────────────────
  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = () => setIsDragging(false);
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); setIsDragging(false);
    if (e.dataTransfer.files?.length) setFile(e.dataTransfer.files[0]);
  };

  const startProcessing = async () => {
    if (!file || !title) return alert("Dosya ve Başlık zorunludur!");
    setPageMode("new");
    setLoading(true);
    setLogs(["Sistem başlatılıyor...", "Dosya sunucuya transfer ediliyor..."]);
    setStatus({ status: "uploading", step: "Yükleniyor...", progress: 5, result: null, error: null });
    const formData = new FormData();
    formData.append("video", file);
    formData.append("title", title);
    formData.append("description", description);
    try {
      const res = await fetch(`${BACKEND_URL}/upload`, { method: "POST", body: formData });
      const data = await res.json();
      setJobId(data.job_id);
    } catch {
      alert("Bağlantı Hatası: Railway sunucusu yanıt vermiyor.");
      setLoading(false);
    }
  };

  const loadHistoryDetail = async (jobIdToLoad: string) => {
    setPageMode("history");
    setSelectedHistoryId(jobIdToLoad);
    setSelectedHistoryJob(null);
    try {
      const res = await fetch(`${BACKEND_URL}/history/${jobIdToLoad}`);
      const data = await res.json();
      setSelectedHistoryJob(data);
    } catch (e) {
      console.error("History detail failed", e);
    }
  };

  const deleteProject = async (jobIdToDelete: string) => {
    if (!confirm("Bu projeyi ve tüm kliplerini silmek istediğinize emin misiniz?")) return;
    try {
      await fetch(`${BACKEND_URL}/delete/${jobIdToDelete}`, { method: "DELETE" });
      loadHistory();
      if (selectedHistoryId === jobIdToDelete) {
        setPageMode("new");
        setSelectedHistoryJob(null);
      }
    } catch (e) {
      console.error("Delete failed", e);
    }
  };

  const submitFeedback = async () => {
    if (!selectedClip?.id) {
      alert("Bu klip henüz veritabanına kaydedilmemiş. Geçmiş projelerden açın.");
      return;
    }
    setFeedbackLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          clip_id: selectedClip.id,
          job_id: selectedHistoryId || jobId,
          views: feedbackViews ? parseInt(feedbackViews) : null,
          retention: feedbackRetention ? parseFloat(feedbackRetention) : null,
          swipe_rate: feedbackSwipeRate ? parseFloat(feedbackSwipeRate) : null,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setFeedbackResult({ score: data.feedback_score, flywheel: data.flywheel_added });
      }
    } catch (e) {
      console.error("Feedback failed", e);
    }
    setFeedbackLoading(false);
  };

  const backendUrl = (path: string) => `${BACKEND_URL.replace(/\/$/, "")}${path}`;

  // Hangi klip listesini gösteriyoruz?
  const activeResult = pageMode === "history" ? selectedHistoryJob?.result : status?.result;
  const activeStatus = pageMode === "history" ? selectedHistoryJob : status;

  // ═══════════════════════════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════════════════════════
  return (
    <div className="flex h-screen bg-[#F8F9FA] text-gray-800 font-sans overflow-hidden">
      {/* ── SIDEBAR ────────────────────────────────────────────────────────── */}
      <div className={`bg-gray-900 text-white transition-all duration-300 flex flex-col ${isSidebarOpen ? "w-72" : "w-20"}`}>
        <div className="h-20 flex items-center justify-between px-6 border-b border-gray-800 shrink-0">
          {isSidebarOpen && <span className="font-extrabold text-xl tracking-wider">PROGNOT<span className="text-blue-500">.AI</span></span>}
          <button onClick={() => setSidebarOpen(!isSidebarOpen)} className="text-gray-400 hover:text-white transition"><Icons.Menu /></button>
        </div>

        <div className="p-4 space-y-2 shrink-0">
          {/* Yeni Proje Butonu */}
          <button
            onClick={() => { setPageMode("new"); setSelectedHistoryId(null); setSelectedHistoryJob(null); }}
            className={`w-full flex items-center gap-3 p-3 rounded-xl transition cursor-pointer ${pageMode === "new" ? "bg-blue-600/20 text-blue-400" : "text-gray-400 hover:text-white hover:bg-gray-800"}`}
          >
            <Icons.Plus />
            {isSidebarOpen && <span className="font-bold text-sm">Yeni Proje</span>}
          </button>
        </div>

        {/* Geçmiş Projeler */}
        {isSidebarOpen && (
          <div className="flex-1 overflow-y-auto px-4 pb-4">
            <div className="flex items-center justify-between mb-3 mt-2">
              <span className="text-[10px] font-bold text-gray-500 tracking-widest uppercase">Geçmiş Projeler</span>
              <button onClick={loadHistory} className="text-gray-500 hover:text-white transition p-1">
                <svg className={`w-3.5 h-3.5 ${historyLoading ? "animate-spin" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </button>
            </div>

            {historyJobs.length === 0 && !historyLoading && (
              <p className="text-xs text-gray-600 text-center py-4">Henüz proje yok</p>
            )}

            <div className="space-y-1.5">
              {historyJobs.map((job) => (
                <div
                  key={job.id}
                  className={`group relative rounded-xl p-3 cursor-pointer transition-all ${selectedHistoryId === job.id ? "bg-gray-700/80 ring-1 ring-blue-500/40" : "hover:bg-gray-800"}`}
                  onClick={() => loadHistoryDetail(job.id)}
                >
                  <p className="text-xs font-semibold text-gray-200 truncate pr-6">{job.video_title}</p>
                  <div className="flex items-center gap-2 mt-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full ${job.status === "done" ? "bg-green-400" : job.status === "error" ? "bg-red-400" : "bg-yellow-400"}`} />
                    <span className="text-[10px] text-gray-500">{formatDate(job.created_at)}</span>
                  </div>
                  {/* Silme butonu */}
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteProject(job.id); }}
                    className="absolute top-2.5 right-2 opacity-0 group-hover:opacity-100 p-1 text-gray-500 hover:text-red-400 transition"
                  >
                    <Icons.Trash />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── ANA İÇERİK ────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        <header className="h-20 bg-white border-b border-gray-200 flex items-center px-10 justify-between sticky top-0 z-10">
          <h1 className="text-2xl font-bold text-gray-800">
            {pageMode === "new" ? "Yeni Proje Oluştur" : (selectedHistoryJob?.result?.original_title || "Proje Detayı")}
          </h1>
          <span className="px-3 py-1 bg-gray-100 text-gray-600 text-xs font-bold rounded-full border border-gray-200">V2.0 ENDÜSTRİYEL</span>
        </header>

        <div className="p-10 max-w-7xl mx-auto grid grid-cols-1 xl:grid-cols-12 gap-8">

          {/* ── SOL PANEL ──────────────────────────────────────────────────── */}
          {pageMode === "new" && (
            <div className="xl:col-span-4 space-y-6">
              <div className="bg-white p-6 rounded-3xl border border-gray-100 shadow-sm">
                <h2 className="text-sm font-bold text-gray-400 tracking-widest uppercase mb-6">Medya Yükle</h2>
                <div
                  onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}
                  className={`relative overflow-hidden border-2 border-dashed rounded-2xl p-8 flex flex-col items-center justify-center text-center transition-all cursor-pointer ${isDragging ? "border-blue-500 bg-blue-50" : "border-gray-200 bg-gray-50 hover:bg-gray-100"}`}
                >
                  <Icons.Upload />
                  <p className="text-sm font-medium text-gray-600">{file ? file.name : "Videonuzu buraya sürükleyin"}</p>
                  <p className="text-xs text-gray-400 mt-2">veya tıklayıp seçin (MP4/MP3)</p>
                  <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" />
                </div>
                <div className="mt-6 space-y-4">
                  <div>
                    <label className="block text-xs font-bold text-gray-500 mb-2">VİDEO BAŞLIĞI (Zorunlu)</label>
                    <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Örn: Joe Rogan - Elon Musk" className="w-full bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-blue-500 outline-none transition" />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-gray-500 mb-2">AÇIKLAMA / BAĞLAM (Opsiyonel)</label>
                    <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="AI'a videonun içeriği hakkında ipucu ver..." className="w-full bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 text-sm h-24 resize-none focus:ring-2 focus:ring-blue-500 outline-none transition" />
                  </div>
                  <button onClick={startProcessing} disabled={loading || !file || !title} className={`w-full py-4 rounded-xl font-bold text-sm transition-all ${loading || !file || !title ? "bg-gray-200 text-gray-400" : "bg-blue-600 text-white hover:bg-blue-700 shadow-lg shadow-blue-600/30"}`}>
                    {loading ? "SİSTEM ÇALIŞIYOR..." : "VİRAL ANALİZİ BAŞLAT"}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* ── SAĞ PANEL ──────────────────────────────────────────────────── */}
          <div className={pageMode === "new" ? "xl:col-span-8 space-y-6" : "xl:col-span-12 space-y-6"}>

            {/* Log Terminali (sadece yeni proje modunda) */}
            {pageMode === "new" && (loading || status) && (
              <div className="bg-[#0D1117] rounded-3xl border border-gray-800 p-6 shadow-xl overflow-hidden">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex gap-2">
                    <div className="w-3 h-3 rounded-full bg-red-500" />
                    <div className="w-3 h-3 rounded-full bg-yellow-500" />
                    <div className="w-3 h-3 rounded-full bg-green-500" />
                  </div>
                  <span className="text-xs font-mono text-gray-400">Prognot İşlem Günlüğü | %{activeStatus?.progress || 0}</span>
                </div>
                <div className="w-full bg-gray-800 h-1.5 rounded-full mb-4 overflow-hidden">
                  <div className="bg-blue-500 h-full transition-all duration-500 ease-out" style={{ width: `${activeStatus?.progress || 0}%` }} />
                </div>
                <div className="h-40 overflow-y-auto font-mono text-xs text-green-400 space-y-2 pr-2">
                  {logs.map((log, i) => (
                    <div key={i} className="flex gap-3 opacity-80 hover:opacity-100 transition">
                      <span className="text-gray-500">[{new Date().toLocaleTimeString()}]</span>
                      <span>{log}</span>
                    </div>
                  ))}
                  {loading && <div className="animate-pulse">_</div>}
                  <div ref={logsEndRef} />
                </div>
              </div>
            )}

            {/* Rapor İndirme + Başlık */}
            {activeResult && (
              <div className="flex flex-wrap items-center gap-3">
                <h3 className="text-xl font-bold text-gray-800 flex-1">
                  {pageMode === "history" ? "Proje Klipleri" : "Gelişmiş AI Seçimleri"}{" "}
                  <span className="text-blue-600">({activeResult.clips.length} Klip)</span>
                </h3>
                {activeResult.pdf_path && (
                  <a href={backendUrl(activeResult.pdf_path)} download className="inline-flex items-center gap-2 px-4 py-2.5 bg-red-50 text-red-600 border border-red-200 rounded-xl text-xs font-bold hover:bg-red-100 transition">
                    <Icons.FileText /> PDF Rapor
                  </a>
                )}
                {activeResult.metadata_path && (
                  <a href={backendUrl(activeResult.metadata_path)} download className="inline-flex items-center gap-2 px-4 py-2.5 bg-gray-50 text-gray-600 border border-gray-200 rounded-xl text-xs font-bold hover:bg-gray-100 transition">
                    <Icons.FileText /> Metadata TXT
                  </a>
                )}
              </div>
            )}

            {/* Klip Kartları */}
            {activeResult?.clips && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {activeResult.clips.map((clip, idx) => {
                  const clipData = { ...clip, index: clip.index || clip.clip_index || idx + 1 };
                  return (
                    <div key={clipData.index} onClick={() => setSelectedClip(clipData)} className="bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all cursor-pointer group">
                      <div className="aspect-[9/16] bg-gray-900 relative flex items-center justify-center overflow-hidden">
                        <video src={backendUrl(clipData.path)} className="absolute w-full h-full object-cover opacity-50 group-hover:opacity-80 transition" />
                        <div className="z-10 w-14 h-14 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center group-hover:scale-110 transition">
                          <Icons.Play />
                        </div>
                        <div className="absolute top-3 right-3 bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-lg border border-white/10">
                          <span className={`text-xs font-bold ${clipData.score >= 85 ? "text-green-400" : clipData.score >= 70 ? "text-yellow-400" : "text-red-400"}`}>{clipData.score}/100</span>
                        </div>
                        {clipData.feedback_score && (
                          <div className="absolute top-3 left-3 bg-emerald-600/80 backdrop-blur-md px-2 py-1 rounded-lg">
                            <span className="text-[10px] font-bold text-white">GERÇEK: {clipData.feedback_score}</span>
                          </div>
                        )}
                      </div>
                      <div className="p-5">
                        <div className="text-[10px] font-bold text-blue-500 tracking-widest uppercase mb-1">KLİP #{clipData.index}</div>
                        {clipData.suggested_title ? (
                          <p className="text-sm font-bold text-gray-800 line-clamp-2 mb-2">{clipData.suggested_title}</p>
                        ) : (
                          <p className="text-sm font-semibold text-gray-800 line-clamp-2 italic mb-2">&ldquo;{clipData.hook}&rdquo;</p>
                        )}
                        {clipData.why_selected && <p className="text-xs text-gray-500 line-clamp-2">{clipData.why_selected}</p>}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Geçmiş proje yükleniyor */}
            {pageMode === "history" && !selectedHistoryJob && selectedHistoryId && (
              <div className="flex items-center justify-center py-20">
                <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
              </div>
            )}

            {/* Boş durum */}
            {pageMode === "history" && selectedHistoryJob && !activeResult && (
              <div className="text-center py-20 text-gray-400">
                <p className="text-4xl mb-3">📁</p>
                <p className="text-sm">Bu proje henüz tamamlanmamış veya klip üretilmemiş.</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════════════
          KLİP DETAY MODALI (5 SEKMELİ)
          ═══════════════════════════════════════════════════════════════════════ */}
      {selectedClip && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-10 bg-black/60 backdrop-blur-sm">
          <div className="bg-white rounded-[2rem] shadow-2xl w-full max-w-5xl max-h-[90vh] overflow-hidden flex flex-col md:flex-row relative">
            <button onClick={() => setSelectedClip(null)} className="absolute top-4 right-4 z-50 p-2 bg-black/10 hover:bg-black/20 rounded-full transition"><Icons.Close /></button>

            {/* Sol: Video */}
            <div className="md:w-5/12 bg-black flex items-center justify-center">
              <video controls autoPlay className="w-full max-h-[90vh] object-contain">
                <source src={backendUrl(selectedClip.path)} type="video/mp4" />
              </video>
            </div>

            {/* Sağ: Sekmeli İçerik */}
            <div className="md:w-7/12 flex flex-col overflow-hidden">
              <div className="flex items-center gap-4 px-8 pt-8 pb-4">
                <ScoreBadge score={selectedClip.score} size="lg" />
                <div className="flex-1 min-w-0">
                  <h2 className="text-xl font-extrabold text-gray-800 truncate">{selectedClip.suggested_title || `Klip #${selectedClip.index}`}</h2>
                  <p className="text-sm text-gray-500">Viral Potansiyel: {selectedClip.score}/100</p>
                </div>
              </div>

              <div className="flex gap-1 px-8 pb-4 border-b border-gray-100 overflow-x-auto">
                <TabButton active={activeTab === "video"} onClick={() => setActiveTab("video")} icon="🎬" label="Video" />
                <TabButton active={activeTab === "analysis"} onClick={() => setActiveTab("analysis")} icon="🧠" label="Analiz" />
                <TabButton active={activeTab === "metadata"} onClick={() => setActiveTab("metadata")} icon="📋" label="Yayın" />
                <TabButton active={activeTab === "transcript"} onClick={() => setActiveTab("transcript")} icon="📝" label="Transkript" />
                <TabButton active={activeTab === "feedback"} onClick={() => setActiveTab("feedback")} icon="📊" label="Performans" />
              </div>

              <div className="flex-1 overflow-y-auto px-8 py-6">

                {/* SEKME 1: Video & Hook */}
                {activeTab === "video" && (
                  <div className="space-y-6">
                    <div>
                      <h3 className="text-xs font-bold text-gray-400 tracking-widest uppercase mb-3 flex items-center gap-2"><span>🎣</span> HOOK</h3>
                      <div className="p-4 bg-gray-50 border border-gray-100 rounded-xl">
                        <p className="text-lg font-medium text-gray-800 italic">&ldquo;{selectedClip.hook}&rdquo;</p>
                      </div>
                    </div>
                    {selectedClip.why_selected && (
                      <div>
                        <h3 className="text-xs font-bold text-gray-400 tracking-widest uppercase mb-3 flex items-center gap-2"><span>🎯</span> NEDEN SEÇİLDİ?</h3>
                        <p className="text-sm text-gray-700 leading-relaxed bg-gray-50 p-4 rounded-xl border border-gray-100">{selectedClip.why_selected}</p>
                      </div>
                    )}
                    <a href={backendUrl(selectedClip.path)} download className="w-full flex items-center justify-center gap-2 py-4 bg-gray-900 text-white rounded-xl font-bold hover:bg-black transition shadow-xl shadow-gray-900/20">
                      <Icons.Download /> HAM DOSYAYI İNDİR
                    </a>
                  </div>
                )}

                {/* SEKME 2: AI Analizi */}
                {activeTab === "analysis" && (
                  <div className="space-y-6">
                    {selectedClip.psychological_trigger && (
                      <div>
                        <h3 className="text-xs font-bold text-blue-500 tracking-widest uppercase mb-3">🧠 PSİKOLOJİK TETİKLEYİCİ</h3>
                        <p className="text-sm text-gray-700 bg-blue-50/50 p-4 rounded-xl border border-blue-100">{selectedClip.psychological_trigger}</p>
                      </div>
                    )}
                    {selectedClip.rag_reference_used && selectedClip.rag_reference_used.toLowerCase() !== "none" && (
                      <div>
                        <h3 className="text-xs font-bold text-purple-500 tracking-widest uppercase mb-3">📚 RAG REFERANSI</h3>
                        <p className="text-sm text-gray-600 bg-purple-50/50 p-4 rounded-xl border border-purple-100">
                          Referans: <span className="font-semibold text-gray-800 block mt-1">{selectedClip.rag_reference_used}</span>
                        </p>
                      </div>
                    )}
                    {selectedClip.audio_energy_note && (
                      <div>
                        <h3 className="text-xs font-bold text-orange-500 tracking-widest uppercase mb-3">🎵 ENERJİ ANALİZİ</h3>
                        <p className="text-sm text-gray-700 bg-orange-50/50 p-4 rounded-xl border border-orange-100">{selectedClip.audio_energy_note}</p>
                      </div>
                    )}
                    {!selectedClip.psychological_trigger && !selectedClip.rag_reference_used && (
                      <div className="text-center py-12 text-gray-400"><p className="text-4xl mb-3">🧠</p><p className="text-sm">Detaylı analiz mevcut değil.</p></div>
                    )}
                  </div>
                )}

                {/* SEKME 3: Yayın Metadatası */}
                {activeTab === "metadata" && (
                  <div className="space-y-6">
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="text-xs font-bold text-gray-400 tracking-widest uppercase">📌 BAŞLIK</h3>
                        {selectedClip.suggested_title && <CopyButton text={selectedClip.suggested_title} />}
                      </div>
                      <div className="p-4 bg-gray-50 border border-gray-100 rounded-xl">
                        <p className="text-base font-bold text-gray-800">{selectedClip.suggested_title || "Üretilmedi"}</p>
                      </div>
                    </div>
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="text-xs font-bold text-gray-400 tracking-widest uppercase">📝 AÇIKLAMA</h3>
                        {selectedClip.suggested_description && <CopyButton text={selectedClip.suggested_description} />}
                      </div>
                      <div className="p-4 bg-gray-50 border border-gray-100 rounded-xl">
                        <p className="text-sm text-gray-700 leading-relaxed">{selectedClip.suggested_description || "Üretilmedi"}</p>
                      </div>
                    </div>
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="text-xs font-bold text-gray-400 tracking-widest uppercase">#️⃣ HASHTAGLER</h3>
                        {selectedClip.suggested_hashtags && <CopyButton text={selectedClip.suggested_hashtags} />}
                      </div>
                      <div className="p-4 bg-blue-50/50 border border-blue-100 rounded-xl">
                        <p className="text-sm text-blue-600 font-medium">{selectedClip.suggested_hashtags || "Üretilmedi"}</p>
                      </div>
                    </div>
                    {selectedClip.suggested_title && selectedClip.suggested_description && (
                      <CopyButton text={[selectedClip.suggested_title, "", selectedClip.suggested_description, "", selectedClip.suggested_hashtags].join("\n")} label="Tümünü Kopyala" />
                    )}
                  </div>
                )}

                {/* SEKME 4: Transkript */}
                {activeTab === "transcript" && (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-bold text-gray-400 tracking-widest uppercase">📝 TRANSKRİPT</h3>
                      {selectedClip.transcript_excerpt && <CopyButton text={selectedClip.transcript_excerpt} />}
                    </div>
                    {selectedClip.transcript_excerpt ? (
                      <div className="p-5 bg-gray-50 border border-gray-100 rounded-xl">
                        <p className="text-sm text-gray-700 leading-relaxed font-mono whitespace-pre-wrap">{selectedClip.transcript_excerpt}</p>
                      </div>
                    ) : (
                      <div className="text-center py-12 text-gray-400"><p className="text-4xl mb-3">📝</p><p className="text-sm">Transkript mevcut değil.</p></div>
                    )}
                  </div>
                )}

                {/* SEKME 5: Performans Bildir (Data Flywheel) */}
                {activeTab === "feedback" && (
                  <div className="space-y-6">
                    <div className="p-4 bg-gradient-to-br from-emerald-50 to-blue-50 border border-emerald-200 rounded-xl">
                      <h3 className="text-sm font-bold text-emerald-700 mb-1">Data Flywheel Sistemi</h3>
                      <p className="text-xs text-emerald-600 leading-relaxed">
                        Klibi yayınladıktan sonra gerçek performans metriklerini girin. Skor yeterince yüksekse 
                        bu klibin başarı formülü otomatik olarak RAG hafızasına eklenir ve gelecekteki kesimler daha akıllı olur.
                      </p>
                    </div>

                    {/* Zaten geri bildirim verilmişse */}
                    {(selectedClip.feedback_submitted_at || feedbackResult) && (
                      <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl">
                        <div className="flex items-center gap-3">
                          <div className="w-12 h-12 rounded-xl bg-emerald-500 flex items-center justify-center text-white font-bold text-lg">
                            {feedbackResult?.score ?? selectedClip.feedback_score ?? "?"}
                          </div>
                          <div>
                            <p className="text-sm font-bold text-emerald-800">Gerçek Dünya Skoru</p>
                            {(feedbackResult?.flywheel) && (
                              <p className="text-xs text-emerald-600 mt-0.5">✅ RAG kütüphanesine eklendi!</p>
                            )}
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Form */}
                    <div className="space-y-4">
                      <div>
                        <label className="block text-xs font-bold text-gray-500 mb-2">İZLENME SAYISI</label>
                        <input type="number" value={feedbackViews} onChange={(e) => setFeedbackViews(e.target.value)} placeholder="Örn: 15000" className="w-full bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-emerald-500 transition" />
                      </div>
                      <div>
                        <label className="block text-xs font-bold text-gray-500 mb-2">ORTALAMA İZLENME SÜRESİ / RETENTION (%)</label>
                        <input type="number" step="0.1" value={feedbackRetention} onChange={(e) => setFeedbackRetention(e.target.value)} placeholder="Örn: 45.5" className="w-full bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-emerald-500 transition" />
                      </div>
                      <div>
                        <label className="block text-xs font-bold text-gray-500 mb-2">GEÇİLME ORANI / SWIPE RATE (%)</label>
                        <input type="number" step="0.1" value={feedbackSwipeRate} onChange={(e) => setFeedbackSwipeRate(e.target.value)} placeholder="Örn: 22.3 (düşük = iyi)" className="w-full bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-emerald-500 transition" />
                      </div>
                      <button
                        onClick={submitFeedback}
                        disabled={feedbackLoading || (!feedbackViews && !feedbackRetention && !feedbackSwipeRate)}
                        className={`w-full py-4 rounded-xl font-bold text-sm transition-all ${feedbackLoading || (!feedbackViews && !feedbackRetention && !feedbackSwipeRate) ? "bg-gray-200 text-gray-400" : "bg-emerald-600 text-white hover:bg-emerald-700 shadow-lg shadow-emerald-600/30"}`}
                      >
                        {feedbackLoading ? "KAYDEDİLİYOR..." : "PERFORMANSI KAYDET"}
                      </button>
                    </div>
                  </div>
                )}

              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}