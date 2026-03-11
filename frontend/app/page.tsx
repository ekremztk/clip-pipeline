"use client";

import { useState, useEffect, useRef } from "react";

// Railway Backend URL'in (Vercel Environment Variable'dan alır veya manuel girilir)
const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "https://clip-pipeline-production.up.railway.app";
const HISTORY_KEY = "prognot_industrial_history";

// --- TİPLER ---
type ClipResult = {
  index: number;
  hook: string;
  score: number;
  path: string; // Railway'deki ham MP4 yolu
};

type JobStatus = {
  status: "uploading" | "running" | "done" | "error";
  step: string;
  progress: number;
  result: {
    clips: ClipResult[];
    original_title: string;
  } | null;
  error: string | null;
};

// --- YARDIMCI BİLEŞEN: KLİP KARTI ---
function RawClipCard({ clip, backendUrl }: { clip: ClipResult; backendUrl: string }) {
  const videoUrl = `${backendUrl}${clip.path}`;
  
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden transition-all hover:shadow-md">
      <div className="bg-black aspect-video relative group">
        <video controls className="w-full h-full object-contain">
          <source src={videoUrl} type="video/mp4" />
        </video>
        <div className="absolute top-2 right-2 bg-black/60 backdrop-blur-md px-2 py-1 rounded-lg">
          <span className="text-[10px] font-bold text-white">SCORE: {clip.score}</span>
        </div>
      </div>
      <div className="p-4">
        <div className="flex items-center gap-2 mb-3">
          <div className={`w-2 h-2 rounded-full ${clip.score >= 85 ? 'bg-green-500' : 'bg-orange-500'}`} />
          <span className="text-xs font-bold text-gray-500 uppercase tracking-tighter">KLİP #{clip.index}</span>
        </div>
        <p className="text-sm font-medium text-gray-800 line-clamp-2 mb-4">"{clip.hook}"</p>
        <a 
          href={videoUrl} 
          download 
          className="block w-full text-center py-2.5 bg-blue-600 text-white rounded-xl text-xs font-bold hover:bg-blue-700 transition-colors shadow-lg shadow-blue-200"
        >
          KAYIPSIZ MP4 İNDİR
        </a>
      </div>
    </div>
  );
}

// --- ANA SAYFA ---
export default function IndustrialPipeline() {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState(false);

  // Polling: Durum kontrolü
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (jobId && status?.status !== "done" && status?.status !== "error") {
      interval = setInterval(async () => {
        try {
          const res = await fetch(`${BACKEND_URL}/status/${jobId}`);
          const data = await res.json();
          setStatus(data);
          if (data.status === "done") setLoading(false);
        } catch (e) {
          console.error("Status check failed", e);
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [jobId, status]);

  const startProcessing = async () => {
    if (!file || !title) return alert("Dosya ve Başlık zorunludur!");
    
    setLoading(true);
    setStatus({ status: "uploading", step: "Dosya sunucuya transfer ediliyor...", progress: 5, result: null, error: null });

    const formData = new FormData();
    formData.append("video", file);
    formData.append("title", title);
    formData.append("description", description);

    try {
      const res = await fetch(`${BACKEND_URL}/upload`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      setJobId(data.job_id);
    } catch (e) {
      alert("Bağlantı Hatası: Railway sunucusu yanıt vermiyor.");
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F5F5F7] text-[#1D1D1F] p-6 md:p-12 font-sans">
      <div className="max-w-5xl mx-auto">
        
        {/* HEADER */}
        <header className="flex justify-between items-end mb-12">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight">PROGNOT <span className="text-blue-600">RAW</span></h1>
            <p className="text-sm text-gray-500 font-medium">Endüstriyel Viral Klip Üretim Hattı</p>
          </div>
          <div className="text-right">
            <span className="text-[10px] font-bold bg-gray-200 px-2 py-1 rounded-md">V1.2 ENGINE</span>
          </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          
          {/* SOL PANEL: INPUT */}
          <div className="lg:col-span-5 space-y-6">
            <div className="bg-white p-8 rounded-[2rem] shadow-sm border border-gray-200/50">
              <h2 className="text-sm font-bold uppercase tracking-widest text-gray-400 mb-6">Veri Girişi</h2>
              
              <div className="space-y-4">
                {/* File Upload */}
                <div className="relative group">
                  <label className="block text-xs font-bold text-gray-500 mb-2">MP4 / MP3 DOSYASI</label>
                  <input 
                    type="file" 
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                    className="w-full text-xs text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-xs file:font-bold file:bg-blue-50 file:text-blue-600 hover:file:bg-blue-100 cursor-pointer"
                  />
                </div>

                {/* Title */}
                <div>
                  <label className="block text-xs font-bold text-gray-500 mb-2">VİDEO BAŞLIĞI (RAG İÇİN)</label>
                  <input 
                    type="text" 
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="Örn: Joe Rogan Ep #2100 - Elon Musk"
                    className="w-full px-4 py-3 bg-gray-50 border border-gray-100 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition-all"
                  />
                </div>

                {/* Description */}
                <div>
                  <label className="block text-xs font-bold text-gray-500 mb-2">AÇIKLAMA (OPSİYONEL)</label>
                  <textarea 
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Gemini'ye içerik hakkında ipucu ver..."
                    className="w-full px-4 py-3 bg-gray-50 border border-gray-100 rounded-xl text-sm h-28 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition-all"
                  />
                </div>

                <button 
                  onClick={startProcessing}
                  disabled={loading || !file}
                  className={`w-full py-4 rounded-2xl font-bold text-sm transition-all shadow-lg ${
                    loading ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : 'bg-blue-600 text-white hover:bg-blue-700 shadow-blue-200'
                  }`}
                >
                  {loading ? "FABRİKA ÇALIŞIYOR..." : "ANALİZİ BAŞLAT"}
                </button>
              </div>
            </div>
          </div>

          {/* SAĞ PANEL: DURUM VE SONUÇLAR */}
          <div className="lg:col-span-7 space-y-6">
            
            {/* PROGRESS CARD */}
            {status && (
              <div className="bg-white p-8 rounded-[2rem] shadow-sm border border-gray-200/50">
                <div className="flex justify-between items-center mb-4">
                  <span className="text-xs font-bold text-blue-600 uppercase tracking-widest">Sistem Durumu</span>
                  <span className="text-xs font-mono font-bold">{status.progress}%</span>
                </div>
                <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden mb-4">
                  <div 
                    className="h-full bg-blue-600 transition-all duration-700 ease-out" 
                    style={{ width: `${status.progress}%` }}
                  />
                </div>
                <p className="text-sm font-medium text-gray-700 animate-pulse">{status.step}</p>
              </div>
            )}

            {/* RESULTS GRID */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {status?.result?.clips.map((clip) => (
                <RawClipCard key={clip.index} clip={clip} backendUrl={BACKEND_URL} />
              ))}
            </div>

            {/* EMPTY STATE */}
            {!status && (
              <div className="h-64 border-2 border-dashed border-gray-200 rounded-[2rem] flex flex-col items-center justify-center text-gray-400">
                <span className="text-4xl mb-2">🔬</span>
                <p className="text-xs font-bold uppercase tracking-widest">Klip Bekleniyor</p>
                <p className="text-[10px]">Dosya yüklediğinizde analiz burada görünecek</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}