"use client";

import { useState, useRef, useEffect, useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ═══════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════

interface DashboardData {
  period_days: number;
  pipeline: {
    summary: {
      total_jobs: number;
      completed: number;
      failed: number;
      avg_duration_min: number;
    };
    steps: { step_name: string; runs: number; avg_duration_s: number; errors: number }[];
  };
  clips: {
    analysis: {
      total_clips: number;
      avg_confidence: number;
      min_confidence: number;
      max_confidence: number;
      pass_count: number;
      fixable_count: number;
      fail_count: number;
    };
  };
  costs_ai: {
    totals: {
      input_tokens: number;
      output_tokens: number;
      total_tokens: number;
      cost_usd: number;
      avg_duration_ms: number;
    };
    by_step: Record<string, { count: number; total_input_tokens: number; total_output_tokens: number; total_cost_usd: number; avg_duration_ms: number }>;
  };
  costs_deepgram: {
    totals: {
      requests: number;
      audio_hours: number;
      audio_minutes: number;
      estimated_cost_usd: number;
    };
    balance: { amount: number; units: string } | null;
  };
  recommendations: {
    id: string;
    module_name: string;
    title: string;
    description: string;
    priority: number;
    impact: string;
    effort: string;
    status: string;
  }[];
  errors: { id?: string; title: string; culprit?: string; count?: number; level?: string; lastSeen?: string; error?: string; warning?: string }[];
  events: { module_name: string; event_type: string; payload: Record<string, unknown>; timestamp: string }[];
  modules: {
    overall_score: number;
    modules: Record<string, {
      name: string;
      score: number;
      status: string;
      status_color: string;
      metrics: Record<string, unknown>;
    }>;
  };
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCallItem[];
  isStreaming?: boolean;
}

interface ToolCallItem {
  tool: string;
  args: Record<string, unknown>;
  summary?: string;
}

// ═══════════════════════════════════════════════
// Design tokens
// ═══════════════════════════════════════════════

const C = {
  cyan: "#00d4ff",
  cyanDim: "rgba(0, 212, 255, 0.12)",
  cyanGlow: "0 0 20px rgba(0, 212, 255, 0.15)",
  cyanBorder: "rgba(0, 212, 255, 0.10)",
  cyanBorderHover: "rgba(0, 212, 255, 0.25)",
  sky: "#0ea5e9",
  bg: "#000000",
  surface: "#050a14",
  surfaceCard: "rgba(0, 212, 255, 0.02)",
  text: "#e5e7eb",
  textMuted: "#6b7280",
  red: "#ef4444",
  yellow: "#eab308",
  green: "#22c55e",
  orange: "#f97316",
};

// ═══════════════════════════════════════════════
// Utility
// ═══════════════════════════════════════════════

function genId() {
  return Math.random().toString(36).slice(2);
}

function statusColor(color: string) {
  const map: Record<string, string> = {
    green: C.green,
    cyan: C.cyan,
    yellow: C.yellow,
    orange: C.orange,
    red: C.red,
    gray: C.textMuted,
  };
  return map[color] || C.textMuted;
}

function formatCost(n: number) {
  if (n >= 1) return `$${n.toFixed(2)}`;
  if (n >= 0.01) return `$${n.toFixed(3)}`;
  return `$${n.toFixed(4)}`;
}

function formatNumber(n: number) {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return n.toString();
}

function timeAgo(ts: string) {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ═══════════════════════════════════════════════
// Small UI Components
// ═══════════════════════════════════════════════

function ScoreRing({ score, size = 80, strokeWidth = 6, color }: { score: number; size?: number; strokeWidth?: number; color?: string }) {
  const r = (size - strokeWidth) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  const fill = color || (score >= 85 ? C.green : score >= 71 ? C.cyan : score >= 56 ? C.yellow : score >= 36 ? C.orange : C.red);

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="transform -rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={strokeWidth} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={fill}
          strokeWidth={strokeWidth}
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 1s ease-out", filter: `drop-shadow(0 0 6px ${fill})` }}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-lg font-bold" style={{ color: fill }}>{score}</span>
      </div>
    </div>
  );
}

function GlowBar({ value, max, color, height = 6 }: { value: number; max: number; color: string; height?: number }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="w-full rounded-full overflow-hidden" style={{ height, background: "rgba(255,255,255,0.05)" }}>
      <div
        className="h-full rounded-full"
        style={{
          width: `${pct}%`,
          background: color,
          boxShadow: `0 0 8px ${color}`,
          transition: "width 1s ease-out",
        }}
      />
    </div>
  );
}

function StatCard({ label, value, sub, accent = false }: { label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <div className="glass-card rounded-xl p-4 relative overflow-hidden group transition-all duration-300">
      <div className="scan-line opacity-0 group-hover:opacity-100 transition-opacity" />
      <div className="text-xs font-medium mb-2" style={{ color: C.textMuted }}>{label}</div>
      <div className="text-2xl font-bold" style={{ color: accent ? C.cyan : C.text }}>{value}</div>
      {sub && <div className="text-xs mt-1" style={{ color: C.textMuted }}>{sub}</div>}
    </div>
  );
}

function SectionTitle({ children, count }: { children: React.ReactNode; count?: number }) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <div className="h-px flex-1 max-w-[20px]" style={{ background: C.cyan, opacity: 0.3 }} />
      <h2 className="text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: C.cyan }}>{children}</h2>
      {count !== undefined && (
        <span className="text-[10px] px-2 py-0.5 rounded-full font-mono" style={{ background: C.cyanDim, color: C.cyan }}>
          {count}
        </span>
      )}
      <div className="h-px flex-1" style={{ background: C.cyan, opacity: 0.1 }} />
    </div>
  );
}

function TimePeriodSelector({ value, onChange }: { value: number; onChange: (d: number) => void }) {
  const options = [
    { label: "24h", days: 1 },
    { label: "7d", days: 7 },
    { label: "30d", days: 30 },
  ];
  return (
    <div className="flex gap-1 p-0.5 rounded-lg" style={{ background: "rgba(255,255,255,0.03)" }}>
      {options.map((o) => (
        <button
          key={o.days}
          onClick={() => onChange(o.days)}
          className="px-3 py-1 rounded-md text-xs font-medium transition-all"
          style={{
            background: value === o.days ? C.cyanDim : "transparent",
            color: value === o.days ? C.cyan : C.textMuted,
          }}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════
// Module Detail Modal
// ═══════════════════════════════════════════════

function ModuleModal({
  module,
  data,
  onClose,
  onChatAbout,
}: {
  module: { key: string; name: string; score: number; status: string; status_color: string; metrics: Record<string, unknown> };
  data: DashboardData | null;
  onClose: () => void;
  onChatAbout: (prompt: string) => void;
}) {
  const [modalTab, setModalTab] = useState<"overview" | "costs" | "efficiency" | "errors">("overview");
  const sc = statusColor(module.status_color);

  // Extract module-specific costs from Langfuse by_step data
  const aiSteps = data?.costs_ai?.by_step || {};
  const isPipeline = module.key === "clip_pipeline";
  const isDirector = module.key === "director";

  const moduleCostEntries = Object.entries(aiSteps).filter(([name]) => {
    if (isPipeline) return name.startsWith("s0") || name.includes("pipeline") || name.includes("discovery") || name.includes("evaluation");
    if (isDirector) return name.includes("director");
    return name.includes("editor") || name.includes("reframe");
  });

  const moduleTotalCost = moduleCostEntries.reduce((sum, [, v]) => sum + (v.total_cost_usd || 0), 0);

  const metrics = module.metrics || {};
  const pipeline = data?.pipeline;
  const clips = data?.clips;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/80 backdrop-blur-md" />

      {/* Panel */}
      <div
        className="relative w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-2xl"
        style={{
          background: "linear-gradient(135deg, rgba(5, 10, 20, 0.98), rgba(0, 15, 30, 0.98))",
          border: `1px solid ${C.cyanBorder}`,
          boxShadow: `0 0 60px rgba(0, 212, 255, 0.08)`,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b" style={{ borderColor: C.cyanBorder }}>
          <div className="flex items-center gap-4">
            <ScoreRing score={module.score} size={56} strokeWidth={4} color={sc} />
            <div>
              <h2 className="text-lg font-bold" style={{ color: C.text }}>{module.name}</h2>
              <span className="text-xs font-mono px-2 py-0.5 rounded" style={{ background: `${sc}20`, color: sc }}>
                {module.status}
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-white/5 transition-colors"
            style={{ color: C.textMuted }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 p-2 mx-4 mt-4 rounded-lg" style={{ background: "rgba(255,255,255,0.03)" }}>
          {(["overview", "costs", "efficiency", "errors"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setModalTab(tab)}
              className="flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-all capitalize"
              style={{
                background: modalTab === tab ? C.cyanDim : "transparent",
                color: modalTab === tab ? C.cyan : C.textMuted,
              }}
            >
              {tab === "overview" ? "Genel" : tab === "costs" ? "Harcamalar" : tab === "efficiency" ? "Verimlilik" : "Hatalar"}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {modalTab === "overview" && (
            <>
              {isPipeline && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <StatCard label="Toplam Job" value={String(metrics.total_jobs || 0)} />
                  <StatCard label="Basari Orani" value={`${metrics.success_rate || 0}%`} accent />
                  <StatCard label="Ort. Sure" value={`${metrics.avg_duration_min || 0}dk`} />
                  <StatCard label="Toplam Klip" value={String(metrics.total_clips || 0)} />
                </div>
              )}
              {isPipeline && clips?.analysis && (
                <div>
                  <div className="text-xs font-medium mb-3" style={{ color: C.textMuted }}>Klip Kalitesi Dagilimi</div>
                  <div className="flex gap-3">
                    {[
                      { label: "Pass", count: clips.analysis.pass_count || 0, color: C.green },
                      { label: "Fixable", count: clips.analysis.fixable_count || 0, color: C.yellow },
                      { label: "Fail", count: clips.analysis.fail_count || 0, color: C.red },
                    ].map((v) => (
                      <div key={v.label} className="flex-1 glass-card rounded-lg p-3 text-center">
                        <div className="text-xl font-bold" style={{ color: v.color }}>{v.count}</div>
                        <div className="text-[10px] mt-1" style={{ color: C.textMuted }}>{v.label}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {isPipeline && pipeline?.steps && pipeline.steps.length > 0 && (
                <div>
                  <div className="text-xs font-medium mb-3" style={{ color: C.textMuted }}>Adim Bazli Performans</div>
                  <div className="space-y-2">
                    {pipeline.steps.map((step) => (
                      <div key={step.step_name} className="flex items-center gap-3 text-xs">
                        <span className="w-16 font-mono truncate" style={{ color: C.cyan }}>{step.step_name}</span>
                        <div className="flex-1">
                          <GlowBar value={step.runs} max={Math.max(...pipeline.steps.map((s) => s.runs))} color={C.cyan} height={4} />
                        </div>
                        <span style={{ color: C.textMuted }}>{step.avg_duration_s}s</span>
                        {step.errors > 0 && <span style={{ color: C.red }}>{step.errors} err</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {!isPipeline && (
                <div className="text-center py-8">
                  <div className="text-sm" style={{ color: C.textMuted }}>
                    {module.key === "editor" ? "Editor metrikleri kullanim verileriyle doldurulacak." : "Director oz-degerlendirmesi konusma gecmisi gerektirir."}
                  </div>
                </div>
              )}
            </>
          )}

          {modalTab === "costs" && (
            <>
              <div className="glass-card rounded-xl p-5">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-sm font-medium" style={{ color: C.text }}>Toplam AI Maliyeti</span>
                  <span className="text-xl font-bold" style={{ color: C.cyan }}>{formatCost(moduleTotalCost)}</span>
                </div>
                {moduleCostEntries.length > 0 ? (
                  <div className="space-y-3">
                    {moduleCostEntries.map(([name, v]) => (
                      <div key={name} className="flex items-center justify-between text-xs">
                        <span className="font-mono" style={{ color: C.textMuted }}>{name}</span>
                        <div className="flex items-center gap-4">
                          <span style={{ color: C.textMuted }}>{v.count} call</span>
                          <span style={{ color: C.textMuted }}>{formatNumber(v.total_input_tokens + v.total_output_tokens)} tok</span>
                          <span className="font-medium" style={{ color: C.text }}>{formatCost(v.total_cost_usd)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-center py-4" style={{ color: C.textMuted }}>Maliyet verisi bulunamadi</div>
                )}
              </div>
              {isPipeline && data?.costs_deepgram?.totals && (
                <div className="glass-card rounded-xl p-5">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium" style={{ color: C.text }}>Deepgram (Transkripsiyon)</span>
                    <span className="text-xl font-bold" style={{ color: C.cyan }}>
                      {formatCost(data.costs_deepgram.totals.estimated_cost_usd)}
                    </span>
                  </div>
                  <div className="flex gap-4 text-xs" style={{ color: C.textMuted }}>
                    <span>{data.costs_deepgram.totals.requests} istek</span>
                    <span>{data.costs_deepgram.totals.audio_hours?.toFixed(1)} saat ses</span>
                  </div>
                </div>
              )}
            </>
          )}

          {modalTab === "efficiency" && (
            <div className="space-y-4">
              {isPipeline ? (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="glass-card rounded-xl p-4">
                      <div className="text-xs mb-2" style={{ color: C.textMuted }}>Pass Orani</div>
                      <div className="text-2xl font-bold" style={{ color: C.green }}>{Number(metrics.pass_rate) || 0}%</div>
                      <GlowBar value={Number(metrics.pass_rate) || 0} max={100} color={C.green} />
                    </div>
                    <div className="glass-card rounded-xl p-4">
                      <div className="text-xs mb-2" style={{ color: C.textMuted }}>Ort. Guven</div>
                      <div className="text-2xl font-bold" style={{ color: C.cyan }}>{Number(metrics.avg_confidence) || 0}</div>
                      <GlowBar value={Number(metrics.avg_confidence) || 0} max={10} color={C.cyan} />
                    </div>
                  </div>
                  <div className="glass-card rounded-xl p-4">
                    <div className="text-xs mb-2" style={{ color: C.textMuted }}>Ort. Tamamlanma Suresi</div>
                    <div className="flex items-end gap-2">
                      <span className="text-3xl font-bold" style={{ color: C.text }}>{Number(metrics.avg_duration_min) || 0}</span>
                      <span className="text-sm mb-1" style={{ color: C.textMuted }}>dakika</span>
                    </div>
                    <GlowBar value={Math.max(0, 15 - Number(metrics.avg_duration_min || 0))} max={15} color={C.cyan} />
                    <div className="text-[10px] mt-1" style={{ color: C.textMuted }}>Hedef: &lt;6 dakika</div>
                  </div>
                </>
              ) : (
                <div className="text-center py-8 text-sm" style={{ color: C.textMuted }}>Verimlilik metrikleri henuz mevcut degil</div>
              )}
            </div>
          )}

          {modalTab === "errors" && (
            <div className="space-y-2">
              {(data?.errors || []).filter((e) => !e.error && !e.warning).length > 0 ? (
                data!.errors.filter((e) => !e.error && !e.warning).slice(0, 10).map((err, i) => (
                  <div key={i} className="glass-card rounded-lg p-3 flex items-start gap-3">
                    <div className="w-2 h-2 rounded-full mt-1.5 shrink-0" style={{ background: err.level === "error" ? C.red : C.yellow }} />
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium truncate" style={{ color: C.text }}>{err.title}</div>
                      {err.culprit && <div className="text-[10px] font-mono truncate" style={{ color: C.textMuted }}>{err.culprit}</div>}
                    </div>
                    <div className="text-[10px] shrink-0" style={{ color: C.textMuted }}>
                      {err.count && `${err.count}x`}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-8 text-sm" style={{ color: C.textMuted }}>Hata bulunamadi</div>
              )}
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="flex gap-3 p-6 pt-0">
          <button
            onClick={() => {
              onChatAbout(`${module.name} modulunun detayli analizini yap. Verimlilik, hatalar, maliyet ve gelistirme onerileri hakkinda rapor ver.`);
              onClose();
            }}
            className="flex-1 py-2.5 rounded-xl text-xs font-medium transition-all"
            style={{
              background: C.cyanDim,
              color: C.cyan,
              border: `1px solid ${C.cyanBorder}`,
            }}
          >
            Director ile Konusma Baslat
          </button>
          <button
            onClick={() => {
              onChatAbout(`${module.name} modulu icin tam analiz calistir. Tum boyutlari degerlendir, puan hesapla, gelistirme onerileri olustur.`);
              onClose();
            }}
            className="flex-1 py-2.5 rounded-xl text-xs font-medium transition-all"
            style={{
              background: "rgba(255,255,255,0.03)",
              color: C.textMuted,
              border: "1px solid rgba(255,255,255,0.06)",
            }}
          >
            Tam Analiz Calistir
          </button>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════
// Dashboard Tab
// ═══════════════════════════════════════════════

function DashboardTab({ data, loading, days, onDaysChange, onOpenModule, onChatAbout }: {
  data: DashboardData | null;
  loading: boolean;
  days: number;
  onDaysChange: (d: number) => void;
  onOpenModule: (key: string) => void;
  onChatAbout: (prompt: string) => void;
}) {
  if (loading && !data) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: `${C.cyan} transparent ${C.cyan} ${C.cyan}` }} />
          <span className="text-xs" style={{ color: C.textMuted }}>Sistem verileri yukleniyor...</span>
        </div>
      </div>
    );
  }

  const modules = data?.modules?.modules || {};
  const overall = data?.modules?.overall_score || 0;
  const overallColor = overall >= 85 ? C.green : overall >= 71 ? C.cyan : overall >= 56 ? C.yellow : overall >= 36 ? C.orange : C.red;

  const totalAiCost = data?.costs_ai?.totals?.cost_usd || 0;
  const totalDgCost = data?.costs_deepgram?.totals?.estimated_cost_usd || 0;
  const totalCost = totalAiCost + totalDgCost;

  const aiSteps = data?.costs_ai?.by_step || {};
  const sortedCostSteps = Object.entries(aiSteps).sort((a, b) => b[1].total_cost_usd - a[1].total_cost_usd);

  return (
    <div className="flex-1 overflow-y-auto px-4 md:px-8 py-6 space-y-8 grid-overlay">
      {/* ── System Health ── */}
      <div className="glass-card rounded-2xl p-6 relative overflow-hidden">
        <div className="scan-line" />
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wider" style={{ color: C.text }}>Sistem Sagligi</h2>
            <p className="text-xs mt-1" style={{ color: C.textMuted }}>Tum modullerin genel durumu</p>
          </div>
          <TimePeriodSelector value={days} onChange={onDaysChange} />
        </div>

        {/* Overall score bar */}
        <div className="flex items-center gap-6">
          <ScoreRing score={overall} size={100} strokeWidth={7} color={overallColor} />
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-3xl font-bold" style={{ color: overallColor }}>{overall}</span>
              <span className="text-sm" style={{ color: C.textMuted }}>/ 100</span>
            </div>
            <GlowBar value={overall} max={100} color={overallColor} height={8} />
            <div className="flex justify-between mt-2 text-[10px] font-mono" style={{ color: C.textMuted }}>
              <span>KRITIK</span>
              <span>ZAYIF</span>
              <span>ORTA</span>
              <span>IYI</span>
              <span>GUCLU</span>
            </div>
          </div>
        </div>
      </div>

      {/* ── Module Cards ── */}
      <SectionTitle>Moduller</SectionTitle>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {Object.entries(modules).map(([key, mod]) => {
          const sc2 = statusColor(mod.status_color);
          return (
            <button
              key={key}
              onClick={() => onOpenModule(key)}
              className="glass-card rounded-2xl p-5 text-left relative overflow-hidden group transition-all duration-300 hover:scale-[1.02]"
              style={{ cursor: "pointer" }}
            >
              <div className="scan-line opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
              {/* Corner accent */}
              <div className="absolute top-0 right-0 w-16 h-16 overflow-hidden">
                <div className="absolute top-0 right-0 w-[1px] h-8" style={{ background: `linear-gradient(to bottom, ${sc2}, transparent)` }} />
                <div className="absolute top-0 right-0 h-[1px] w-8" style={{ background: `linear-gradient(to left, ${sc2}, transparent)` }} />
              </div>

              <div className="flex items-center justify-between mb-4">
                <div>
                  <div className="text-sm font-semibold" style={{ color: C.text }}>{mod.name}</div>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded mt-1 inline-block" style={{ background: `${sc2}15`, color: sc2 }}>
                    {mod.status}
                  </span>
                </div>
                <ScoreRing score={mod.score} size={52} strokeWidth={4} color={sc2} />
              </div>

              {/* Quick metrics */}
              {key === "clip_pipeline" && mod.metrics && (
                <div className="grid grid-cols-3 gap-2 text-center">
                  {[
                    { label: "Basari", value: `${mod.metrics.success_rate || 0}%` },
                    { label: "Klip", value: String(mod.metrics.total_clips || 0) },
                    { label: "Sure", value: `${mod.metrics.avg_duration_min || 0}dk` },
                  ].map((m) => (
                    <div key={m.label}>
                      <div className="text-sm font-bold" style={{ color: C.text }}>{m.value}</div>
                      <div className="text-[9px]" style={{ color: C.textMuted }}>{m.label}</div>
                    </div>
                  ))}
                </div>
              )}
              {key !== "clip_pipeline" && (
                <div className="text-xs text-center py-2" style={{ color: C.textMuted }}>
                  Detaylar icin tiklayin
                </div>
              )}

              {/* Bottom glow line */}
              <div className="absolute bottom-0 left-0 right-0 h-[2px] opacity-0 group-hover:opacity-100 transition-opacity border-flow" />
            </button>
          );
        })}
      </div>

      {/* ── Costs ── */}
      <SectionTitle>Harcamalar</SectionTitle>
      <div className="glass-card rounded-2xl p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <span className="text-2xl font-bold" style={{ color: C.cyan }}>{formatCost(totalCost)}</span>
            <span className="text-xs ml-2" style={{ color: C.textMuted }}>toplam ({days} gun)</span>
          </div>
          <div className="flex gap-4 text-xs">
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full" style={{ background: C.cyan }} />
              <span style={{ color: C.textMuted }}>Gemini AI</span>
              <span className="font-medium" style={{ color: C.text }}>{formatCost(totalAiCost)}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full" style={{ background: C.sky }} />
              <span style={{ color: C.textMuted }}>Deepgram</span>
              <span className="font-medium" style={{ color: C.text }}>{formatCost(totalDgCost)}</span>
            </div>
          </div>
        </div>

        {/* Cost proportion bar */}
        <div className="flex rounded-full overflow-hidden mb-6" style={{ height: 8, background: "rgba(255,255,255,0.05)" }}>
          {totalCost > 0 && (
            <>
              <div style={{ width: `${(totalAiCost / totalCost) * 100}%`, background: C.cyan, boxShadow: `0 0 8px ${C.cyan}` }} />
              <div style={{ width: `${(totalDgCost / totalCost) * 100}%`, background: C.sky, boxShadow: `0 0 8px ${C.sky}` }} />
            </>
          )}
        </div>

        {/* Step breakdown */}
        {sortedCostSteps.length > 0 && (
          <div className="space-y-2">
            <div className="text-[10px] font-medium uppercase tracking-wider mb-2" style={{ color: C.textMuted }}>AI Adim Detaylari</div>
            {sortedCostSteps.slice(0, 8).map(([name, v]) => (
              <div key={name} className="flex items-center justify-between text-xs py-1">
                <span className="font-mono truncate max-w-[200px]" style={{ color: C.textMuted }}>{name}</span>
                <div className="flex items-center gap-4">
                  <span style={{ color: C.textMuted }}>{v.count}x</span>
                  <span style={{ color: C.textMuted }}>{formatNumber(v.total_input_tokens + v.total_output_tokens)} tok</span>
                  <span className="font-medium min-w-[60px] text-right" style={{ color: C.text }}>{formatCost(v.total_cost_usd)}</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Deepgram detail */}
        {data?.costs_deepgram?.totals && (
          <div className="mt-4 pt-4" style={{ borderTop: `1px solid ${C.cyanBorder}` }}>
            <div className="flex items-center justify-between text-xs">
              <div>
                <span className="font-medium" style={{ color: C.text }}>Deepgram Transkripsiyon</span>
                <span className="ml-2" style={{ color: C.textMuted }}>
                  {data.costs_deepgram.totals.requests} istek / {data.costs_deepgram.totals.audio_hours?.toFixed(1)} saat
                </span>
              </div>
              <span className="font-medium" style={{ color: C.text }}>{formatCost(data.costs_deepgram.totals.estimated_cost_usd)}</span>
            </div>
            {data.costs_deepgram.balance && (
              <div className="text-[10px] mt-1" style={{ color: C.textMuted }}>
                Bakiye: {data.costs_deepgram.balance.amount} {data.costs_deepgram.balance.units}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Recommendations ── */}
      <SectionTitle count={(data?.recommendations || []).length}>Aktif Oneriler</SectionTitle>
      {(data?.recommendations || []).length > 0 ? (
        <div className="space-y-3">
          {data!.recommendations.map((rec) => (
            <div key={rec.id} className="glass-card rounded-xl p-4 group">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                      style={{
                        background: rec.priority <= 2 ? `${C.red}15` : rec.priority <= 4 ? `${C.yellow}15` : `${C.cyan}15`,
                        color: rec.priority <= 2 ? C.red : rec.priority <= 4 ? C.yellow : C.cyan,
                      }}
                    >
                      P{rec.priority}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(255,255,255,0.05)", color: C.textMuted }}>
                      {rec.module_name}
                    </span>
                  </div>
                  <div className="text-sm font-medium" style={{ color: C.text }}>{rec.title}</div>
                  <div className="text-xs mt-1 line-clamp-2" style={{ color: C.textMuted }}>{rec.description}</div>
                </div>
                <div className="flex gap-2 shrink-0">
                  {rec.impact && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: `${C.green}15`, color: C.green }}>
                      {rec.impact}
                    </span>
                  )}
                  {rec.effort && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(255,255,255,0.05)", color: C.textMuted }}>
                      {rec.effort}
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="glass-card rounded-xl p-8 text-center">
          <div className="text-sm" style={{ color: C.textMuted }}>Henuz oneri bulunmuyor</div>
          <button
            onClick={() => onChatAbout("Tum sistemin analizini yap ve gelistirme onerileri olustur.")}
            className="mt-3 text-xs px-4 py-2 rounded-lg transition-all"
            style={{ background: C.cyanDim, color: C.cyan, border: `1px solid ${C.cyanBorder}` }}
          >
            Director&apos;dan Oneri Iste
          </button>
        </div>
      )}

      {/* ── Errors ── */}
      <SectionTitle count={(data?.errors || []).filter((e) => !e.error && !e.warning).length}>Hatalar</SectionTitle>
      {(data?.errors || []).filter((e) => !e.error && !e.warning).length > 0 ? (
        <div className="space-y-2">
          {data!.errors.filter((e) => !e.error && !e.warning).slice(0, 8).map((err, i) => (
            <div key={i} className="glass-card rounded-xl p-4 flex items-start gap-3">
              <div className="w-2 h-2 rounded-full mt-1.5 shrink-0 glow-pulse" style={{ background: err.level === "error" ? C.red : C.yellow }} />
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium truncate" style={{ color: C.text }}>{err.title}</div>
                {err.culprit && <div className="text-[10px] font-mono truncate mt-0.5" style={{ color: C.textMuted }}>{err.culprit}</div>}
              </div>
              <div className="flex items-center gap-3 shrink-0">
                {err.count && <span className="text-[10px] font-mono" style={{ color: C.red }}>{err.count}x</span>}
                {err.lastSeen && <span className="text-[10px]" style={{ color: C.textMuted }}>{timeAgo(err.lastSeen)}</span>}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="glass-card rounded-xl p-8 text-center">
          <div className="text-sm" style={{ color: C.green }}>Hata bulunamadi</div>
          <div className="text-xs mt-1" style={{ color: C.textMuted }}>
            {data?.errors?.[0]?.warning || data?.errors?.[0]?.error || "Sentry entegrasyonu aktif"}
          </div>
        </div>
      )}

      {/* ── Recent Events ── */}
      {(data?.events || []).length > 0 && (
        <>
          <SectionTitle count={data!.events.length}>Son Olaylar</SectionTitle>
          <div className="glass-card rounded-xl overflow-hidden">
            {data!.events.slice(0, 10).map((ev, i) => (
              <div
                key={i}
                className="flex items-center gap-3 px-4 py-3 text-xs transition-colors hover:bg-white/[0.02]"
                style={{ borderBottom: i < 9 ? `1px solid rgba(255,255,255,0.03)` : "none" }}
              >
                <span className="font-mono px-1.5 py-0.5 rounded text-[10px]" style={{ background: C.cyanDim, color: C.cyan }}>
                  {ev.module_name}
                </span>
                <span className="font-medium" style={{ color: C.text }}>{ev.event_type}</span>
                <span className="flex-1 truncate" style={{ color: C.textMuted }}>
                  {typeof ev.payload === "object" ? JSON.stringify(ev.payload).slice(0, 80) : String(ev.payload)}
                </span>
                <span className="shrink-0" style={{ color: C.textMuted }}>{timeAgo(ev.timestamp)}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Bottom spacer */}
      <div className="h-4" />
    </div>
  );
}

// ═══════════════════════════════════════════════
// Chat Tab (existing functionality, sci-fi themed)
// ═══════════════════════════════════════════════

function ToolCallBadge({ item }: { item: ToolCallItem }) {
  const argSummary = Object.entries(item.args)
    .map(([k, v]) => `${k}: ${String(v).slice(0, 40)}`)
    .join(", ");

  return (
    <div className="flex items-start gap-2 text-xs rounded-lg px-3 py-2 my-1" style={{ background: "rgba(0, 212, 255, 0.03)", border: `1px solid ${C.cyanBorder}` }}>
      <span className="shrink-0" style={{ color: C.cyan }}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="mt-0.5">
          <path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z" />
        </svg>
      </span>
      <div>
        <span className="font-mono" style={{ color: C.cyan }}>{item.tool}</span>
        {argSummary && <span className="ml-2" style={{ color: C.textMuted }}>({argSummary})</span>}
        {item.summary && <div className="mt-0.5" style={{ color: C.textMuted }}>{item.summary}</div>}
      </div>
    </div>
  );
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div className={`max-w-[80%] ${isUser ? "order-2" : "order-1"}`}>
        {!isUser && msg.toolCalls && msg.toolCalls.length > 0 && (
          <div className="mb-2">
            {msg.toolCalls.map((tc, i) => (
              <ToolCallBadge key={i} item={tc} />
            ))}
          </div>
        )}
        <div
          className="rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap"
          style={
            isUser
              ? {
                  background: `linear-gradient(135deg, ${C.cyan}, ${C.sky})`,
                  color: "#000",
                  borderTopRightRadius: "4px",
                }
              : {
                  background: "rgba(255,255,255,0.04)",
                  color: C.text,
                  border: `1px solid rgba(255,255,255,0.06)`,
                  borderTopLeftRadius: "4px",
                }
          }
        >
          {msg.content}
          {msg.isStreaming && (
            <span
              className="inline-block w-1.5 h-4 animate-pulse ml-1 align-middle"
              style={{ background: C.cyan }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function ChatTab({
  messages,
  setMessages,
  input,
  setInput,
  isLoading,
  setIsLoading,
  sessionId,
}: {
  messages: Message[];
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  input: string;
  setInput: React.Dispatch<React.SetStateAction<string>>;
  isLoading: boolean;
  setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
  sessionId: string;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendMessage(overrideText?: string) {
    const text = (overrideText || input).trim();
    if (!text || isLoading) return;

    const userMsg: Message = { id: genId(), role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    if (!overrideText) setInput("");
    setIsLoading(true);

    const assistantId = genId();
    const assistantMsg: Message = { id: assistantId, role: "assistant", content: "", toolCalls: [], isStreaming: true };
    setMessages((prev) => [...prev, assistantMsg]);

    try {
      const res = await fetch(`${API_URL}/director/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });

      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));

            if (event.type === "tool_call") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, toolCalls: [...(m.toolCalls || []), { tool: event.tool, args: event.args }] }
                    : m
                )
              );
            } else if (event.type === "tool_result") {
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== assistantId) return m;
                  const toolCalls = [...(m.toolCalls || [])];
                  const lastIdx = toolCalls.length - 1;
                  if (lastIdx >= 0 && toolCalls[lastIdx].tool === event.tool) {
                    toolCalls[lastIdx] = { ...toolCalls[lastIdx], summary: event.summary };
                  }
                  return { ...m, toolCalls };
                })
              );
            } else if (event.type === "text") {
              setMessages((prev) =>
                prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + event.text } : m))
              );
            } else if (event.type === "done") {
              setMessages((prev) =>
                prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m))
              );
            } else if (event.type === "error") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: `Hata: ${event.message}`, isStreaming: false } : m
                )
              );
            }
          } catch {
            // Skip malformed SSE
          }
        }
      }
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, content: `Baglanti hatasi: ${String(err)}`, isStreaming: false } : m
        )
      );
    } finally {
      setIsLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  const suggestedPrompts = [
    "Pipeline son 7 gunde nasil performans gosterdi?",
    "S05 neden yavas?",
    "Klip kalitesi analizi yap",
    "Tum sistem maliyetlerini goster",
    "Gelistirme onerileri olustur",
    "Son hatalari analiz et",
  ];

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-2">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}

        {messages.length === 1 && (
          <div className="flex flex-wrap gap-2 mt-4 justify-center">
            {suggestedPrompts.map((prompt) => (
              <button
                key={prompt}
                onClick={() => {
                  setInput(prompt);
                  inputRef.current?.focus();
                }}
                className="text-xs rounded-full px-3 py-1.5 transition-all"
                style={{
                  border: `1px solid ${C.cyanBorder}`,
                  color: C.textMuted,
                  background: "transparent",
                }}
              >
                {prompt}
              </button>
            ))}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-4 pb-4">
        <div
          className="flex gap-2 rounded-2xl p-2"
          style={{ background: "rgba(255,255,255,0.03)", border: `1px solid ${C.cyanBorder}` }}
        >
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Director'a sor..."
            rows={1}
            className="flex-1 bg-transparent text-sm placeholder-gray-500 resize-none outline-none px-2 py-1.5 max-h-32"
            style={{ minHeight: "36px", color: C.text }}
            disabled={isLoading}
          />
          <button
            onClick={() => sendMessage()}
            disabled={isLoading || !input.trim()}
            className="w-9 h-9 rounded-xl flex items-center justify-center transition-all shrink-0 disabled:opacity-30"
            style={{ background: C.cyan, color: "#000" }}
          >
            {isLoading ? (
              <div className="w-4 h-4 border-2 border-black/30 border-t-black rounded-full animate-spin" />
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M2 21L23 12 2 3V10L17 12 2 14Z" />
              </svg>
            )}
          </button>
        </div>
        <p className="text-center text-xs mt-2" style={{ color: C.textMuted }}>
          Enter ile gonder / Shift+Enter yeni satir
        </p>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════
// Main Page
// ═══════════════════════════════════════════════

export default function DirectorPage() {
  const [activeTab, setActiveTab] = useState<"dashboard" | "chat">("dashboard");
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [days, setDays] = useState(7);
  const [openModuleKey, setOpenModuleKey] = useState<string | null>(null);

  // Chat state
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "Merhaba. Ben Director — sistemin AI CEO'su.\n\nPipeline performansini, klip kalitesini, Gemini kararlarini analiz edebilirim. Kod okuyabilir, veritabanini sorgulayabilirim. Ne ogrenmek istiyorsun?",
    },
  ]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [sessionId] = useState(() => genId());

  const fetchDashboard = useCallback(async (d: number) => {
    setDashboardLoading(true);
    try {
      const res = await fetch(`${API_URL}/director/dashboard?days=${d}`, { cache: "no-store" });
      if (res.ok) {
        setDashboardData(await res.json());
      }
    } catch (err) {
      console.error("Dashboard fetch error:", err);
    } finally {
      setDashboardLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboard(days);
  }, [days, fetchDashboard]);

  function handleDaysChange(d: number) {
    setDays(d);
  }

  function handleChatAbout(prompt: string) {
    setActiveTab("chat");
    setChatInput(prompt);
  }

  const openModule = openModuleKey && dashboardData?.modules?.modules?.[openModuleKey]
    ? { key: openModuleKey, ...dashboardData.modules.modules[openModuleKey] }
    : null;

  return (
    <div className="flex flex-col h-screen" style={{ background: C.bg, color: C.text }}>
      {/* ── Header ── */}
      <div
        className="flex items-center justify-between px-6 py-3 shrink-0"
        style={{ borderBottom: `1px solid ${C.cyanBorder}`, background: "rgba(0, 5, 15, 0.8)", backdropFilter: "blur(12px)" }}
      >
        <div className="flex items-center gap-3">
          {/* Logo */}
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold relative overflow-hidden"
            style={{
              background: `linear-gradient(135deg, ${C.cyan}20, ${C.sky}10)`,
              border: `1px solid ${C.cyanBorder}`,
              color: C.cyan,
            }}
          >
            D
            <div className="absolute inset-0 glow-pulse" style={{ background: `radial-gradient(circle, ${C.cyan}10, transparent)` }} />
          </div>
          <div>
            <h1 className="font-semibold text-sm tracking-wide" style={{ color: C.text }}>
              DIRECTOR
            </h1>
            <p className="text-[10px] font-mono" style={{ color: C.textMuted }}>AI SYSTEM CONTROLLER v1.0</p>
          </div>
        </div>

        {/* Nav Tabs */}
        <div className="flex gap-1 p-0.5 rounded-lg" style={{ background: "rgba(255,255,255,0.03)" }}>
          {(["dashboard", "chat"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className="px-4 py-1.5 rounded-md text-xs font-medium transition-all relative"
              style={{
                background: activeTab === tab ? C.cyanDim : "transparent",
                color: activeTab === tab ? C.cyan : C.textMuted,
              }}
            >
              {tab === "dashboard" ? "Dashboard" : "Chat"}
              {activeTab === tab && (
                <div
                  className="absolute bottom-0 left-1/2 -translate-x-1/2 w-4 h-[2px] rounded-full"
                  style={{ background: C.cyan, boxShadow: `0 0 8px ${C.cyan}` }}
                />
              )}
            </button>
          ))}
        </div>

        {/* Status indicator */}
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full glow-pulse" style={{ background: C.green, boxShadow: `0 0 6px ${C.green}` }} />
          <span className="text-[10px] font-mono" style={{ color: C.textMuted }}>ONLINE</span>
        </div>
      </div>

      {/* ── Content ── */}
      {activeTab === "dashboard" ? (
        <DashboardTab
          data={dashboardData}
          loading={dashboardLoading}
          days={days}
          onDaysChange={handleDaysChange}
          onOpenModule={setOpenModuleKey}
          onChatAbout={handleChatAbout}
        />
      ) : (
        <ChatTab
          messages={messages}
          setMessages={setMessages}
          input={chatInput}
          setInput={setChatInput}
          isLoading={chatLoading}
          setIsLoading={setChatLoading}
          sessionId={sessionId}
        />
      )}

      {/* ── Module Modal ── */}
      {openModule && (
        <ModuleModal
          module={openModule}
          data={dashboardData}
          onClose={() => setOpenModuleKey(null)}
          onChatAbout={handleChatAbout}
        />
      )}
    </div>
  );
}
