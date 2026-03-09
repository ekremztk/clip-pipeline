"use client";

import { useState, useEffect, useRef } from "react";

const BACKEND = "/api/backend";
const HISTORY_KEY = "clip_pipeline_history";

type ClipResult = {
  index: number;
  title: string;
  description: string;
  hashtags: string;
  start: number;
  end: number;
  mp4: string;
  srt: string;
  score?: number;
  clip_text?: string;
  trim_note?: string;
  why_selected?: string;
  recommendation?: string;
};

type JobResult = {
  title: string;
  job_id: string;
  pdf?: string; // PDF raporu için opsiyonel alan
  clips: ClipResult[];
};

type JobStatus = {
  status: "queued" | "running" | "done" | "error";
  step: string;
  progress: number;
  result: JobResult | null;
  error: string | null;
};

type HistoryItem = {
  job_id: string;
  title: string;
  clip_count: number;
  date: string;
  result: JobResult;
};

type LogEntry = {
  time: string;
  message: string;
  type: "info" | "success" | "error";
};

function formatTime(sec: number) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  return [h, m, s].map((v) => String(v).padStart(2, "0")).join(":");
}

function timeNow() {
  return new Date().toLocaleTimeString("tr-TR", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

// ── CLIP CARD ─────────────────────────────────────────────────────────────────
function ClipCard({ clip, selected, onSelect }: {
  clip: ClipResult; selected: boolean; onSelect: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const score = clip.score;
  const sc = score === undefined ? "#8e8e93" : score >= 85 ? "#30d158" : score >= 70 ? "#ff9f0a" : "#ff453a";

  return (
    <div
      className="rounded-2xl overflow-hidden transition-all cursor-pointer"
      style={{
        background: "white",
        border: selected ? "1.5px solid #007aff" : "1px solid rgba(0,0,0,0.06)",
        boxShadow: selected ? "0 0 0 3px rgba(0,122,255,0.08)" : "none",
      }}
    >
      <div
        className="flex items-center gap-3 px-4 py-3.5 hover:bg-black/[0.02] transition-all"
        onClick={() => { setExpanded(!expanded); onSelect(); }}
      >
        <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: sc }} />
        <span className="text-xs font-bold flex-shrink-0" style={{ color: "#007aff", minWidth: 40 }}>
          Klip {clip.index}
        </span>
        <span className="flex-1 text-sm font-medium truncate" style={{ color: "#1c1c1e" }}>
          {clip.title}
        </span>
        <span className="text-xs font-mono flex-shrink-0" style={{ color: "#8e8e93" }}>
          {formatTime(clip.start)}–{formatTime(clip.end)}
        </span>
        {score !== undefined && (
          <span className="text-xs font-bold flex-shrink-0" style={{ color: sc }}>{score}</span>
        )}
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none"
          className="flex-shrink-0 transition-transform"
          style={{ transform: expanded ? "rotate(180deg)" : "rotate(0)", color: "#aeaeb2" }}>
          <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>

      {expanded && (
        <div onClick={(e) => e.stopPropagation()}>
          <div className="bg-black">
            <video controls className="w-full" style={{ maxHeight: 260, display: "block" }}>
              <source src={`http://localhost:8000${clip.mp4}`} type="video/mp4" />
            </video>
          </div>
          <div className="px-4 py-4 space-y-4">
            <div>
              <p className="text-xs font-semibold mb-1 uppercase tracking-wider" style={{ color: "#8e8e93" }}>
                Önerilen Başlık
              </p>
              <p className="text-sm font-medium" style={{ color: "#1c1c1e" }}>{clip.title}</p>
            </div>
            <div>
              <p className="text-xs font-semibold mb-1 uppercase tracking-wider" style={{ color: "#8e8e93" }}>
                Önerilen Açıklama
              </p>
              <p className="text-sm leading-relaxed" style={{ color: "#3a3a3c" }}>{clip.description}</p>
              <p className="text-xs mt-2" style={{ color: "#007aff" }}>{clip.hashtags}</p>
            </div>
            <div className="flex gap-2 pt-1">
              <a href={`http://localhost:8000${clip.mp4}`} download
                className="flex-1 text-center py-2.5 rounded-xl text-xs font-semibold text-white"
                style={{ background: "#007aff" }}>
                MP4 İndir
              </a>
              <a href={`http://localhost:8000${clip.srt}`} download
                className="flex-1 text-center py-2.5 rounded-xl text-xs font-semibold"
                style={{ background: "#f2f2f7", color: "#3a3a3c", border: "1px solid rgba(0,0,0,0.06)" }}>
                SRT İndir
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── ANALYSIS PANEL ────────────────────────────────────────────────────────────
function AnalysisPanel({ clip, result, logs, loading, progress, currentStep }: {
  clip: ClipResult | null;
  result: JobResult | null;
  logs: LogEntry[];
  loading: boolean;
  progress: number;
  currentStep: string;
}) {
  const logRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* PDF Raporu İndirme Butonu */}
      {result && result.pdf && !loading && (
        <div className="px-5 py-3 border-b bg-white flex justify-between items-center" style={{borderColor: "rgba(0,0,0,0.06)"}}>
          <div className="flex items-center gap-2">
            <span className="text-lg">📄</span>
            <span className="text-xs font-bold uppercase tracking-wider" style={{color: "#1c1c1e"}}>Analiz Raporu</span>
          </div>
          <a 
            href={`http://localhost:8000${result.pdf}`} 
            download 
            className="px-4 py-2 rounded-xl text-xs font-bold text-white transition-all hover:opacity-90 active:scale-95 shadow-sm"
            style={{ background: "#30d158" }}
          >
            PDF İNDİR
          </a>
        </div>
      )}

      {/* Activity log */}
      {(loading || logs.length > 0) && (
        <div className="flex-shrink-0 border-b" style={{ borderColor: "rgba(0,0,0,0.06)", background: "#f5f5f7" }}>
          <div className="px-5 pt-4 pb-2 flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "#8e8e93" }}>Aktivite</p>
            {loading && (
              <div className="flex items-center gap-2">
                <span className="text-xs" style={{ color: "#8e8e93" }}>{progress}%</span>
                <div className="w-20 h-1 rounded-full overflow-hidden" style={{ background: "#e5e5ea" }}>
                  <div className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${progress}%`, background: "#007aff" }} />
                </div>
              </div>
            )}
          </div>
          <div ref={logRef} className="px-5 pb-4 space-y-1.5 overflow-y-auto" style={{ maxHeight: 150 }}>
            {logs.map((log, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="text-xs flex-shrink-0 font-mono" style={{ color: "#aeaeb2" }}>{log.time}</span>
                <span className="text-xs leading-relaxed" style={{
                  color: log.type === "success" ? "#30d158" : log.type === "error" ? "#ff3b30" : "#3a3a3c"
                }}>{log.message}</span>
              </div>
            ))}
            {loading && (
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono flex-shrink-0" style={{ color: "#aeaeb2" }}>{timeNow()}</span>
                <span className="text-xs animate-pulse" style={{ color: "#007aff" }}>{currentStep}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 overflow-y-auto px-5 py-5">

        {/* Empty state */}
        {!loading && !result && logs.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4"
              style={{ background: "rgba(0,122,255,0.08)" }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path d="M9 17H7A5 5 0 0 1 7 7h2M15 7h2a5 5 0 0 1 0 10h-2M8 12h8"
                  stroke="#007aff" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </div>
            <p className="text-sm font-medium" style={{ color: "#1c1c1e" }}>Analiz bekleniyor</p>
            <p className="text-xs mt-1" style={{ color: "#8e8e93" }}>Video işlenince rapor burada görünür</p>
          </div>
        )}

        {/* Loading */}
        {loading && !result && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-12 h-12 mb-4">
              <svg className="animate-spin" width="48" height="48" viewBox="0 0 48 48" fill="none">
                <circle cx="24" cy="24" r="20" stroke="#e5e5ea" strokeWidth="3" />
                <path d="M24 4a20 20 0 0 1 20 20" stroke="#007aff" strokeWidth="3" strokeLinecap="round" />
              </svg>
            </div>
            <p className="text-sm font-medium" style={{ color: "#1c1c1e" }}>Analiz ediliyor</p>
            <p className="text-xs mt-1" style={{ color: "#8e8e93" }}>{currentStep}</p>
          </div>
        )}

        {/* No clip selected */}
        {!clip && result && !loading && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <p className="text-sm font-medium" style={{ color: "#1c1c1e" }}>Bir klip seç</p>
            <p className="text-xs mt-1" style={{ color: "#8e8e93" }}>Sol taraftan klibi tıkla, analizi burada görürsün</p>
          </div>
        )}

        {/* Clip analysis */}
        {clip && (
          <div className="space-y-5">

            {/* Header + score bar */}
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "#8e8e93" }}>
                Klip {clip.index} · Analiz
              </p>
              {clip.score !== undefined && (
                <span className="text-xs font-bold" style={{
                  color: clip.score >= 85 ? "#30d158" : clip.score >= 70 ? "#ff9f0a" : "#ff453a"
                }}>
                  {clip.score}/100
                </span>
              )}
            </div>
            {clip.score !== undefined && (
              <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: "#e5e5ea" }}>
                <div className="h-full rounded-full transition-all duration-700"
                  style={{
                    width: `${clip.score}%`,
                    background: clip.score >= 85 ? "#30d158" : clip.score >= 70 ? "#ff9f0a" : "#ff453a"
                  }} />
              </div>
            )}

            {/* Zaman aralığı + süre */}
            <div className="rounded-xl p-3 flex gap-6"
              style={{ background: "#f5f5f7", border: "1px solid rgba(0,0,0,0.06)" }}>
              <div>
                <p className="text-xs font-semibold mb-0.5" style={{ color: "#8e8e93" }}>Zaman Aralığı</p>
                <p className="text-sm font-mono font-medium" style={{ color: "#1c1c1e" }}>
                  {formatTime(clip.start)} – {formatTime(clip.end)}
                </p>
              </div>
              <div>
                <p className="text-xs font-semibold mb-0.5" style={{ color: "#8e8e93" }}>Klip Süresi</p>
                <p className="text-sm font-mono font-medium" style={{ color: "#1c1c1e" }}>
                  ~{clip.end - clip.start}s
                </p>
              </div>
            </div>

            {/* Kırpma notu */}
            {clip.trim_note && clip.trim_note.toLowerCase() !== "none" ? (
              <div className="rounded-xl p-3"
                style={{ background: "rgba(255,159,10,0.06)", border: "1px solid rgba(255,159,10,0.2)" }}>
                <p className="text-xs font-semibold mb-1" style={{ color: "#ff9f0a" }}>✂️ Kırpma Notu</p>
                <p className="text-xs leading-relaxed" style={{ color: "#3a3a3c" }}>{clip.trim_note}</p>
              </div>
            ) : (
              <p className="text-xs font-medium" style={{ color: "#30d158" }}>✓ Kırpma gerekmiyor</p>
            )}

            {/* Klip metni */}
            {clip.clip_text && (
              <div>
                <p className="text-xs font-semibold mb-2" style={{ color: "#8e8e93" }}>📝 Klip Metni</p>
                <p className="text-xs leading-relaxed p-3 rounded-xl"
                  style={{
                    color: "#3a3a3c",
                    background: "white",
                    border: "1px solid rgba(0,0,0,0.06)",
                    whiteSpace: "pre-wrap",
                    fontFamily: "inherit",
                    lineHeight: "1.6",
                  }}>
                  {clip.clip_text}
                </p>
              </div>
            )}

            {/* Neden seçildi */}
            {clip.why_selected && (
              <div>
                <p className="text-xs font-semibold mb-1.5" style={{ color: "#8e8e93" }}>🎯 Neden Seçildi & Potansiyel</p>
                <p className="text-sm leading-relaxed" style={{ color: "#3a3a3c" }}>{clip.why_selected}</p>
              </div>
            )}

          </div>
        )}
      </div>
    </div>
  );
}

function HistoryRow({ item, active, onClick }: { item: HistoryItem; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className="w-full text-left px-3 py-2.5 rounded-xl transition-all"
      style={{ background: active ? "rgba(0,122,255,0.1)" : "transparent", color: active ? "#007aff" : "#3a3a3c" }}>
      <p className="text-xs font-medium truncate">{item.title}</p>
      <p className="text-xs mt-0.5" style={{ color: active ? "#007aff" : "#aeaeb2" }}>
        {item.clip_count} klip · {item.date}
      </p>
    </button>
  );
}

// ── MAIN ──────────────────────────────────────────────────────────────────────
export default function Home() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [url, setUrl] = useState("");
  const [clipCount, setClipCount] = useState<number | "auto">("auto");
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);
  const [selectedClipIndex, setSelectedClipIndex] = useState<number | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [activeResult, setActiveResult] = useState<JobResult | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(HISTORY_KEY);
      if (stored) setHistory(JSON.parse(stored));
    } catch {}
  }, []);

  const saveToHistory = (result: JobResult) => {
    const item: HistoryItem = {
      job_id: result.job_id,
      title: result.title,
      clip_count: result.clips.length,
      date: new Date().toLocaleDateString("tr-TR", { day: "numeric", month: "short" }),
      result,
    };
    setHistory((prev) => {
      const updated = [item, ...prev.filter((h) => h.job_id !== result.job_id)].slice(0, 20);
      try { localStorage.setItem(HISTORY_KEY, JSON.stringify(updated)); } catch {}
      return updated;
    });
    setActiveHistoryId(result.job_id);
  };

  const addLog = (message: string, type: LogEntry["type"] = "info") =>
    setLogs((prev) => [...prev, { time: timeNow(), message, type }]);

  const startJob = async () => {
    if (!url.trim()) return;
    setError(null);
    setLoading(true);
    setJobStatus(null);
    setJobId(null);
    setSelectedClipIndex(null);
    setActiveResult(null);
    setLogs([]);
    addLog("İş kuyruğa alındı...");

    try {
      const res = await fetch(`${BACKEND}/process`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim(), clip_count: clipCount === "auto" ? 0 : clipCount }),
      });
      const data = await res.json();
      if (data.job_id) {
        setJobId(data.job_id);
        addLog(`Job başlatıldı: ${data.job_id.slice(0, 8)}...`);
      } else {
        addLog("İş başlatılamadı.", "error");
        setLoading(false);
      }
    } catch {
      addLog("Backend'e bağlanılamadı.", "error");
      setError("Backend'e bağlanılamadı. localhost:8000 çalışıyor mu?");
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!jobId) return;
    let lastStep = "";
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${BACKEND}/status/${jobId}`);
        const data: JobStatus = await res.json();
        setJobStatus(data);
        if (data.step && data.step !== lastStep) {
          lastStep = data.step;
          addLog(data.step);
        }
        if (data.status === "done" && data.result) {
          clearInterval(pollRef.current!);
          setLoading(false);
          addLog(`Tamamlandı! ${data.result.clips.length} klip oluşturuldu.`, "success");
          setActiveResult(data.result);
          saveToHistory(data.result);
          setSelectedClipIndex(0);
        }
        if (data.status === "error") {
          clearInterval(pollRef.current!);
          setLoading(false);
          addLog(data.error || "Bilinmeyen hata.", "error");
        }
      } catch {
        clearInterval(pollRef.current!);
        addLog("Durum alınamadı.", "error");
        setLoading(false);
      }
    }, 1500);
    return () => clearInterval(pollRef.current!);
  }, [jobId]);

  const loadFromHistory = (item: HistoryItem) => {
    setActiveResult(item.result);
    setActiveHistoryId(item.job_id);
    setSelectedClipIndex(0);
    setLogs([{ time: timeNow(), message: `Geçmişten yüklendi: ${item.title}`, type: "info" }]);
    setLoading(false);
    setJobStatus(null);
    setError(null);
  };

  const selectedClip = activeResult && selectedClipIndex !== null
    ? activeResult.clips[selectedClipIndex] : null;

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: "#f2f2f7" }}>

      {/* SIDEBAR */}
      <aside className="flex-shrink-0 flex flex-col border-r transition-all duration-300"
        style={{
          width: sidebarOpen ? "220px" : "64px",
          background: "rgba(255,255,255,0.8)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
          borderColor: "rgba(0,0,0,0.08)",
        }}>
        <div className="flex items-center h-14 px-4 flex-shrink-0">
          <button onClick={() => setSidebarOpen(!sidebarOpen)}
            className="w-9 h-9 flex flex-col items-center justify-center gap-1.5 rounded-xl transition-all hover:bg-black/[0.05]">
            {[0,1,2].map(i => (
              <span key={i} className="block rounded-full" style={{ width: 18, height: 1.5, background: "#3a3a3c" }} />
            ))}
          </button>
          {sidebarOpen && (
            <span className="ml-3 font-semibold text-sm" style={{ color: "#1c1c1e", letterSpacing: "-0.01em" }}>
              Clip Pipeline
            </span>
          )}
        </div>

        <nav className="px-2 py-1 flex-shrink-0">
          <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl"
            style={{ background: "rgba(0,122,255,0.1)", color: "#007aff" }}>
            <span className="text-base flex-shrink-0">✂️</span>
            {sidebarOpen && <span className="text-sm font-medium">Klip Çıkartıcı</span>}
          </button>
        </nav>

        {sidebarOpen && history.length > 0 && (
          <div className="flex-1 overflow-y-auto px-2 py-3">
            <p className="text-xs font-semibold uppercase tracking-wider px-3 mb-2" style={{ color: "#aeaeb2" }}>
              Geçmiş
            </p>
            <div className="space-y-0.5">
              {history.map((item) => (
                <HistoryRow key={item.job_id} item={item}
                  active={activeHistoryId === item.job_id}
                  onClick={() => loadFromHistory(item)} />
              ))}
            </div>
          </div>
        )}

        {sidebarOpen && (
          <div className="px-5 py-4 flex-shrink-0">
            <p className="text-xs" style={{ color: "#aeaeb2" }}>v1.0 · Local</p>
          </div>
        )}
      </aside>

      {/* MAIN */}
      <div className="flex-1 flex flex-col overflow-hidden">

        <div className="flex-shrink-0 flex items-center justify-between px-6 h-14 border-b"
          style={{ background: "rgba(255,255,255,0.8)", borderColor: "rgba(0,0,0,0.06)", backdropFilter: "blur(20px)" }}>
          <h1 className="text-base font-semibold" style={{ color: "#1c1c1e", letterSpacing: "-0.01em" }}>
            Klip Çıkartıcı
          </h1>
        </div>

        <div className="flex-1 flex overflow-hidden">

          {/* LEFT: Input + Clips */}
          <div className="flex flex-col overflow-hidden border-r" style={{ width: "50%", borderColor: "rgba(0,0,0,0.06)" }}>
            <div className="flex-1 overflow-y-auto px-5 py-5">

              {!activeResult ? (
                <div className="rounded-2xl p-5" style={{ background: "white", border: "1px solid rgba(0,0,0,0.06)" }}>
                  <label className="block text-xs font-semibold mb-2 uppercase tracking-wider" style={{ color: "#8e8e93" }}>
                    YouTube URL
                  </label>
                  <input type="text" value={url} onChange={(e) => setUrl(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && !loading && startJob()}
                    placeholder="https://youtube.com/watch?v=..." disabled={loading}
                    className="w-full px-4 py-3 rounded-xl text-sm transition-all mb-4 disabled:opacity-50"
                    style={{ background: "#f2f2f7", border: "1px solid rgba(0,0,0,0.06)", color: "#1c1c1e" }} />

                  <label className="block text-xs font-semibold mb-2 uppercase tracking-wider" style={{ color: "#8e8e93" }}>
                    Klip Sayısı
                  </label>
                  <div className="flex gap-2 mb-4">
                    {(["auto", 1, 2, 3] as const).map((n) => (
                      <button key={n} onClick={() => setClipCount(n)} disabled={loading}
                        className="flex-1 py-2 rounded-xl text-sm font-medium transition-all disabled:opacity-50"
                        style={{
                          background: clipCount === n ? "#007aff" : "#f2f2f7",
                          color: clipCount === n ? "white" : "#3a3a3c",
                          border: clipCount === n ? "1px solid transparent" : "1px solid rgba(0,0,0,0.06)",
                        }}>
                        {n === "auto" ? "Auto" : n}
                      </button>
                    ))}
                  </div>

                  {clipCount === "auto" && (
                    <p className="text-xs mb-4 px-3 py-2 rounded-lg"
                      style={{ color: "#007aff", background: "rgba(0,122,255,0.06)", border: "1px solid rgba(0,122,255,0.1)" }}>
                      AI, içeriğe göre en uygun klip sayısını belirler.
                    </p>
                  )}

                  <button onClick={startJob} disabled={loading || !url.trim()}
                    className="w-full py-3 rounded-xl text-sm font-semibold text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                    style={{ background: "#007aff" }}>
                    {loading ? "İşleniyor..." : "Klipleri Oluştur"}
                  </button>

                  {error && (
                    <div className="mt-3 px-4 py-3 rounded-xl text-xs"
                      style={{ background: "rgba(255,59,48,0.06)", border: "1px solid rgba(255,59,48,0.15)", color: "#ff3b30" }}>
                      {error}
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="rounded-xl p-3" style={{ background: "white", border: "1px solid rgba(0,0,0,0.06)" }}>
                    <p className="text-xs mb-0.5" style={{ color: "#8e8e93" }}>Kaynak Video</p>
                    <p className="text-sm font-semibold truncate mb-3" style={{ color: "#1c1c1e" }}>{activeResult.title}</p>
                    <div className="flex gap-2">
                      <input type="text" value={url} onChange={(e) => setUrl(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && !loading && startJob()}
                        placeholder="Yeni YouTube URL..." disabled={loading}
                        className="flex-1 px-3 py-2 rounded-lg text-xs disabled:opacity-50"
                        style={{ background: "#f2f2f7", border: "1px solid rgba(0,0,0,0.06)", color: "#1c1c1e" }} />
                      <button onClick={startJob} disabled={loading || !url.trim()}
                        className="px-3 py-2 rounded-lg text-xs font-semibold text-white disabled:opacity-40"
                        style={{ background: "#007aff" }}>
                        {loading ? "..." : "Çıkart"}
                      </button>
                    </div>
                  </div>

                  {loading && (
                    <div className="space-y-2">
                      {[1,2,3].map(i => (
                        <div key={i} className="rounded-2xl h-14 animate-pulse"
                          style={{ background: "white", border: "1px solid rgba(0,0,0,0.06)" }} />
                      ))}
                    </div>
                  )}

                  {activeResult.clips.map((clip, i) => (
                    <ClipCard key={clip.index} clip={clip}
                      selected={selectedClipIndex === i}
                      onSelect={() => setSelectedClipIndex(i)} />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* RIGHT: Analysis */}
          <div className="flex flex-col overflow-hidden" style={{ width: "50%", background: "#fafafa" }}>
            <AnalysisPanel
              clip={selectedClip}
              result={activeResult}
              logs={logs}
              loading={loading}
              progress={jobStatus?.progress || 0}
              currentStep={jobStatus?.step || ""}
            />
          </div>

        </div>
      </div>
    </div>
  );
}