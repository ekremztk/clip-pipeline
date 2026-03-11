"use client";

import { useState, useEffect, useRef } from "react";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "https://clip-pipeline-production.up.railway.app";

// --- TİPLER ---
type ClipResult = {
  index: number;
  hook: string;
  score: number;
  path: string;
  psychological_trigger?: string;
  rag_reference_used?: string;
};

type JobStatus = {
  status: "uploading" | "running" | "done" | "error";
  step: string;
  progress: number;
  result: { clips: ClipResult[]; original_title: string } | null;
  error: string | null;
};

// --- YARDIMCI İKONLAR ---
const Icons = {
  Menu: () => <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" /></svg>,
  Upload: () => <svg className="w-10 h-10 text-blue-500 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>,
  Play: () => <svg className="w-8 h-8 text-white" fill="currentColor" viewBox="0 0 20 20"><path d="M4 4l12 6-12 6V4z" /></svg>,
  Close: () => <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>,
};

export default function IndustrialPipeline() {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  
  const [isSidebarOpen, setSidebarOpen] = useState(true);
  const [isDragging, setIsDragging] = useState(false);
  const [selectedClip, setSelectedClip] = useState<ClipResult | null>(null);

  const logsEndRef = useRef<HTMLDivElement>(null);

  // Durum Kontrolü (Polling)
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (jobId && status?.status !== "done" && status?.status !== "error") {
      interval = setInterval(async () => {
        try {
          const res = await fetch(`${BACKEND_URL}/status/${jobId}`);
          const data = await res.json();
          setStatus(data);
          
          // Yeni adımları loglara ekle
          if (data.step) {
            setLogs((prev) => {
              if (prev[prev.length - 1] !== data.step) return [...prev, data.step];
              return prev;
            });
          }
          
          if (data.status === "done" || data.status === "error") setLoading(false);
        } catch (e) {
          console.error("Status check failed", e);
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [jobId, status]);

  // Loglar güncellendikçe aşağı kaydır
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // Sürükle Bırak İşlemleri
  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = () => setIsDragging(false);
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setFile(e.dataTransfer.files[0]);
    }
  };

  const startProcessing = async () => {
    if (!file || !title) return alert("Dosya ve Başlık zorunludur!");
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
    } catch (e) {
      alert("Bağlantı Hatası: Railway sunucusu yanıt vermiyor.");
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-[#F8F9FA] text-gray-800 font-sans overflow-hidden">
      
      {/* SIDEBAR */}
      <div className={`bg-gray-900 text-white transition-all duration-300 flex flex-col ${isSidebarOpen ? 'w-64' : 'w-20'}`}>
        <div className="h-20 flex items-center justify-between px-6 border-b border-gray-800">
          {isSidebarOpen && <span className="font-extrabold text-xl tracking-wider">PROGNOT<span className="text-blue-500">.AI</span></span>}
          <button onClick={() => setSidebarOpen(!isSidebarOpen)} className="text-gray-400 hover:text-white transition">
            <Icons.Menu />
          </button>
        </div>
        <div className="p-4 flex-1">
          <div className="flex items-center gap-4 p-3 bg-blue-600/20 text-blue-400 rounded-xl cursor-pointer">
            <span className="text-xl">✂️</span>
            {isSidebarOpen && <span className="font-bold text-sm">Klip Çıkarıcı</span>}
          </div>
          <div className="flex items-center gap-4 p-3 text-gray-500 hover:text-white transition cursor-not-allowed mt-2">
            <span className="text-xl">📝</span>
            {isSidebarOpen && <span className="font-medium text-sm">Altyazı Stüdyosu (Yakında)</span>}
          </div>
        </div>
      </div>

      {/* ANA İÇERİK */}
      <div className="flex-1 overflow-y-auto">
        <header className="h-20 bg-white border-b border-gray-200 flex items-center px-10 justify-between sticky top-0 z-10">
          <h1 className="text-2xl font-bold text-gray-800">Yeni Proje Oluştur</h1>
          <span className="px-3 py-1 bg-gray-100 text-gray-600 text-xs font-bold rounded-full border border-gray-200">V1.5 ENDÜSTRİYEL</span>
        </header>

        <div className="p-10 max-w-7xl mx-auto grid grid-cols-1 xl:grid-cols-12 gap-8">
          
          {/* SOL PANEL (GİRDİLER) */}
          <div className="xl:col-span-4 space-y-6">
            <div className="bg-white p-6 rounded-3xl border border-gray-100 shadow-sm">
              <h2 className="text-sm font-bold text-gray-400 tracking-widest uppercase mb-6">Medya Yükle</h2>
              
              {/* DRAG & DROP ZONE */}
              <div 
                onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}
                className={`border-2 border-dashed rounded-2xl p-8 flex flex-col items-center justify-center text-center transition-all cursor-pointer ${isDragging ? 'border-blue-500 bg-blue-50' : 'border-gray-200 bg-gray-50 hover:bg-gray-100'}`}
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
                <button onClick={startProcessing} disabled={loading || !file || !title} className={`w-full py-4 rounded-xl font-bold text-sm transition-all ${loading || !file || !title ? 'bg-gray-200 text-gray-400' : 'bg-blue-600 text-white hover:bg-blue-700 shadow-lg shadow-blue-600/30'}`}>
                  {loading ? "SİSTEM ÇALIŞIYOR..." : "VİRAL ANALİZİ BAŞLAT"}
                </button>
              </div>
            </div>
          </div>

          {/* SAĞ PANEL (DURUM & SONUÇLAR) */}
          <div className="xl:col-span-8 space-y-6">
            
            {/* LOG TERMİNALİ */}
            {(loading || status) && (
              <div className="bg-[#0D1117] rounded-3xl border border-gray-800 p-6 shadow-xl overflow-hidden relative">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex gap-2">
                    <div className="w-3 h-3 rounded-full bg-red-500"></div>
                    <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
                    <div className="w-3 h-3 rounded-full bg-green-500"></div>
                  </div>
                  <span className="text-xs font-mono text-gray-400">Prognot İşlem Günlüğü | %{status?.progress || 0}</span>
                </div>
                
                {/* Progress Bar */}
                <div className="w-full bg-gray-800 h-1.5 rounded-full mb-4 overflow-hidden">
                  <div className="bg-blue-500 h-full transition-all duration-500 ease-out" style={{ width: `${status?.progress || 0}%` }}></div>
                </div>

                <div className="h-40 overflow-y-auto font-mono text-xs text-green-400 space-y-2 pr-2 custom-scrollbar">
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

            {/* KLİP KARTLARI (GRID) */}
            {status?.result?.clips && (
              <div>
                <h3 className="text-xl font-bold text-gray-800 mb-6">Gelişmiş AI Seçimleri <span className="text-blue-600">({status.result.clips.length} Klip)</span></h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {status.result.clips.map((clip) => (
                    <div key={clip.index} onClick={() => setSelectedClip(clip)} className="bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all cursor-pointer group">
                      <div className="aspect-[9/16] bg-gray-900 relative flex items-center justify-center overflow-hidden">
                        <video src={`${BACKEND_URL.replace(/\/$/, "")}${clip.path}`} className="absolute w-full h-full object-cover opacity-50 group-hover:opacity-80 transition" />
                        <div className="z-10 w-14 h-14 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center group-hover:scale-110 transition">
                          <Icons.Play />
                        </div>
                        <div className="absolute top-3 right-3 bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-lg border border-white/10">
                          <span className="text-xs font-bold text-green-400">{clip.score}/100</span>
                        </div>
                      </div>
                      <div className="p-5">
                        <div className="text-[10px] font-bold text-blue-500 tracking-widest uppercase mb-2">KLİP #{clip.index}</div>
                        <p className="text-sm font-semibold text-gray-800 line-clamp-3 italic">"{clip.hook}"</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* KLİP DETAY MODALI */}
      {selectedClip && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-10 bg-black/60 backdrop-blur-sm">
          <div className="bg-white rounded-[2rem] shadow-2xl w-full max-w-5xl max-h-[90vh] overflow-hidden flex flex-col md:flex-row relative">
            <button onClick={() => setSelectedClip(null)} className="absolute top-4 right-4 z-50 p-2 bg-black/10 hover:bg-black/20 rounded-full transition">
              <Icons.Close />
            </button>
            
            {/* Modal Sol: Video Oynatıcı */}
            <div className="md:w-5/12 bg-black flex items-center justify-center">
              <video controls autoPlay className="w-full max-h-[90vh] object-contain">
                <source src={`${BACKEND_URL.replace(/\/$/, "")}${selectedClip.path}`} type="video/mp4" />
              </video>
            </div>
            
            {/* Modal Sağ: Yapay Zeka Detayları */}
            <div className="md:w-7/12 p-8 md:p-12 overflow-y-auto">
              <div className="flex items-center gap-4 mb-8">
                <div className={`w-16 h-16 rounded-2xl flex items-center justify-center text-xl font-bold text-white shadow-lg ${selectedClip.score >= 85 ? 'bg-gradient-to-br from-green-400 to-green-600' : 'bg-gradient-to-br from-yellow-400 to-yellow-600'}`}>
                  {selectedClip.score}
                </div>
                <div>
                  <h2 className="text-2xl font-extrabold text-gray-800">Klip #{selectedClip.index} Analizi</h2>
                  <p className="text-sm text-gray-500 font-medium">Viral Potansiyel Skoru</p>
                </div>
              </div>

              <div className="space-y-8">
                <div>
                  <h3 className="text-xs font-bold text-gray-400 tracking-widest uppercase mb-3 flex items-center gap-2">
                    <span>🎣</span> İLK 3 SANİYE KANCASI (HOOK)
                  </h3>
                  <div className="p-4 bg-gray-50 border border-gray-100 rounded-xl">
                    <p className="text-lg font-medium text-gray-800 italic">"{selectedClip.hook}"</p>
                  </div>
                </div>

                {selectedClip.psychological_trigger && (
                  <div>
                    <h3 className="text-xs font-bold text-blue-500 tracking-widest uppercase mb-3 flex items-center gap-2">
                      <span>🧠</span> NEDEN SEÇİLDİ? (PSİKOLOJİK TETİKLEYİCİ)
                    </h3>
                    <p className="text-sm text-gray-700 leading-relaxed bg-blue-50/50 p-4 rounded-xl border border-blue-100">
                      {selectedClip.psychological_trigger}
                    </p>
                  </div>
                )}

                {selectedClip.rag_reference_used && (
                  <div>
                    <h3 className="text-xs font-bold text-purple-500 tracking-widest uppercase mb-3 flex items-center gap-2">
                      <span>📚</span> RAG BAŞARI REFERANSI
                    </h3>
                    <p className="text-sm text-gray-600 bg-purple-50/50 p-4 rounded-xl border border-purple-100">
                      Sistem bu klibi geçmişteki şu başarılı örneğe benzeterek kesti: <br/>
                      <span className="font-semibold text-gray-800 mt-1 block">{selectedClip.rag_reference_used}</span>
                    </p>
                  </div>
                )}

                <div className="pt-6">
                  <a 
                    href={`${BACKEND_URL.replace(/\/$/, "")}${selectedClip.path}`} 
                    download 
                    className="w-full flex items-center justify-center gap-2 py-4 bg-gray-900 text-white rounded-xl font-bold hover:bg-black transition shadow-xl shadow-gray-900/20"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                    KAYIPSIZ HAM (RAW) DOSYAYI İNDİR
                  </a>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}