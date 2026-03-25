"use client";

import { useState, useRef, useEffect, useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ═══════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════

interface Subscore { score: number; max: number; }

interface ModuleData {
  name: string;
  score: number | null;
  status: string;
  status_color: string;
  metrics: Record<string, unknown>;
  subscores: Record<string, Subscore>;
}

interface DashboardData {
  period_days: number;
  pipeline: {
    summary: {
      total_jobs: number; completed: number; failed: number; avg_duration_min: number;
    };
    steps: { step_name: string; runs: number; avg_duration_s: number; errors: number }[];
  };
  clips: {
    analysis: {
      total_clips: number; avg_confidence: number;
      pass_count: number; fixable_count: number; fail_count: number;
    };
  };
  costs_ai: {
    totals: { input_tokens: number; output_tokens: number; total_tokens: number; cost_usd: number; avg_duration_ms: number; };
    by_step: Record<string, { count: number; total_input_tokens: number; total_output_tokens: number; total_cost_usd: number; avg_duration_ms: number }>;
  };
  costs_deepgram: {
    totals: { requests: number; audio_hours: number; audio_minutes: number; estimated_cost_usd: number; };
    balance: { amount: number; units: string } | null;
  };
  recommendations: Recommendation[];
  errors: SentryError[];
  events: DirectorEvent[];
  modules: { overall_score: number | null; modules: Record<string, ModuleData> };
}

interface Recommendation {
  id: string;
  module_name: string;
  title: string;
  description: string;
  priority: number;
  impact: string;
  effort: string;
  status: string;
  metadata?: {
    what_it_solves?: string;
    how_to_integrate?: string;
    why_recommended?: string;
  };
  created_at?: string;
}

interface SentryError {
  id?: string; title: string; culprit?: string; count?: number;
  level?: string; lastSeen?: string; error?: string; warning?: string;
}

interface DirectorEvent {
  module_name: string; event_type: string;
  payload: Record<string, unknown>; timestamp: string;
}

interface Decision {
  id: string;
  decision: string;
  context?: string;
  alternatives?: string[];
  expected_impact?: string;
  actual_impact?: string;
  status: string;
  channel_id?: string;
  timestamp: string;
  measured_at?: string;
}

interface Message {
  id: string; role: "user" | "assistant";
  content: string; toolCalls?: ToolCallItem[]; isStreaming?: boolean;
}

interface ToolCallItem { tool: string; args: Record<string, unknown>; summary?: string; }

// ═══════════════════════════════════════════════
// Design tokens
// ═══════════════════════════════════════════════

const C = {
  cyan: "#00d4ff", cyanDim: "rgba(0,212,255,0.10)", cyanBorder: "rgba(0,212,255,0.10)",
  sky: "#0ea5e9", bg: "#000000", surface: "rgba(0,212,255,0.02)",
  text: "#e5e7eb", textMuted: "#6b7280",
  red: "#ef4444", yellow: "#eab308", green: "#22c55e", orange: "#f97316",
};

function genId() { return Math.random().toString(36).slice(2); }

function scColor(color: string) {
  return { green: C.green, cyan: C.cyan, yellow: C.yellow, orange: C.orange, red: C.red, gray: C.textMuted }[color] ?? C.textMuted;
}

function fmtCost(n: number) {
  if (!n) return "$0.00";
  if (n >= 1) return `$${n.toFixed(2)}`;
  if (n >= 0.01) return `$${n.toFixed(3)}`;
  return `$${n.toFixed(4)}`;
}

function fmtNum(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function timeAgo(ts: string) {
  const d = Date.now() - new Date(ts).getTime();
  const m = Math.floor(d / 60000);
  if (m < 1) return "az önce";
  if (m < 60) return `${m}dk`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}s`;
  return `${Math.floor(h / 24)}g`;
}

// ═══════════════════════════════════════════════
// Small Components
// ═══════════════════════════════════════════════

function ScoreRing({ score, size = 80, sw = 6 }: { score: number | null; size?: number; sw?: number }) {
  const r = (size - sw) / 2;
  const circ = 2 * Math.PI * r;

  if (score === null || score === undefined) {
    return (
      <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
        <svg width={size} height={size}>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={sw} />
        </svg>
        <div className="absolute text-lg font-bold" style={{ color: C.textMuted }}>?</div>
      </div>
    );
  }

  const fill = score >= 85 ? C.green : score >= 71 ? C.cyan : score >= 56 ? C.yellow : score >= 36 ? C.orange : C.red;
  const offset = circ - (score / 100) * circ;

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={sw} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={fill} strokeWidth={sw}
          strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 1s ease-out", filter: `drop-shadow(0 0 6px ${fill})` }} />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="font-bold" style={{ color: fill, fontSize: size > 60 ? 18 : 13 }}>{score}</span>
      </div>
    </div>
  );
}

function GlowBar({ value, max, color, h = 6 }: { value: number; max: number; color: string; h?: number }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="w-full rounded-full overflow-hidden" style={{ height: h, background: "rgba(255,255,255,0.05)" }}>
      <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color, boxShadow: `0 0 8px ${color}`, transition: "width 1s ease-out" }} />
    </div>
  );
}

function SectionTitle({ children, count, action }: { children: React.ReactNode; count?: number; action?: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 mb-5">
      <div className="h-px w-5" style={{ background: C.cyan, opacity: 0.4 }} />
      <h2 className="text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: C.cyan }}>{children}</h2>
      {count !== undefined && (
        <span className="text-[10px] px-2 py-0.5 rounded-full font-mono" style={{ background: C.cyanDim, color: C.cyan }}>{count}</span>
      )}
      <div className="h-px flex-1" style={{ background: C.cyan, opacity: 0.07 }} />
      {action}
    </div>
  );
}

function PeriodSelector({ value, onChange, includeAll = false }: { value: number; onChange: (d: number) => void; includeAll?: boolean }) {
  const opts = [{ l: "24s", d: 1 }, { l: "7g", d: 7 }, { l: "30g", d: 30 }, ...(includeAll ? [{ l: "Tümü", d: 365 }] : [])];
  return (
    <div className="flex gap-1 p-0.5 rounded-lg" style={{ background: "rgba(255,255,255,0.03)" }}>
      {opts.map((o) => (
        <button key={o.d} onClick={() => onChange(o.d)}
          className="px-3 py-1 rounded-md text-xs font-medium transition-all"
          style={{ background: value === o.d ? C.cyanDim : "transparent", color: value === o.d ? C.cyan : C.textMuted }}>
          {o.l}
        </button>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════
// Recommendation Detail Modal
// ═══════════════════════════════════════════════

function RecommendationModal({ rec, onClose, onDismiss }: {
  rec: Recommendation; onClose: () => void; onDismiss: (id: string) => void;
}) {
  const priorityLabel = rec.priority <= 1 ? "KRİTİK" : rec.priority <= 2 ? "YÜKSEK" : rec.priority <= 3 ? "ORTA" : "DÜŞÜK";
  const priorityColor = rec.priority <= 1 ? C.red : rec.priority <= 2 ? C.orange : rec.priority <= 3 ? C.yellow : C.textMuted;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/85 backdrop-blur-lg" />
      <div className="relative w-full max-w-2xl max-h-[80vh] overflow-y-auto rounded-2xl"
        style={{ background: "linear-gradient(135deg,rgba(5,10,20,0.99),rgba(0,15,30,0.99))", border: `1px solid ${C.cyanBorder}` }}
        onClick={(e) => e.stopPropagation()}>

        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b" style={{ borderColor: C.cyanBorder }}>
          <div className="flex-1 pr-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] font-mono px-2 py-0.5 rounded" style={{ background: `${priorityColor}20`, color: priorityColor }}>
                P{rec.priority} {priorityLabel}
              </span>
              <span className="text-[10px] px-2 py-0.5 rounded" style={{ background: "rgba(255,255,255,0.05)", color: C.textMuted }}>
                {rec.module_name}
              </span>
              {rec.impact && (
                <span className="text-[10px] px-2 py-0.5 rounded" style={{ background: `${C.green}15`, color: C.green }}>
                  Etki: {rec.impact}
                </span>
              )}
              {rec.effort && (
                <span className="text-[10px] px-2 py-0.5 rounded" style={{ background: "rgba(255,255,255,0.05)", color: C.textMuted }}>
                  Çaba: {rec.effort}
                </span>
              )}
            </div>
            <h2 className="text-base font-semibold" style={{ color: C.text }}>{rec.title}</h2>
          </div>
          <button onClick={onClose} className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-white/5 transition-colors shrink-0" style={{ color: C.textMuted }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-5">
          {rec.description && (
            <div>
              <div className="text-[10px] uppercase tracking-wider mb-2" style={{ color: C.cyan }}>Açıklama</div>
              <p className="text-sm leading-relaxed" style={{ color: C.text }}>{rec.description}</p>
            </div>
          )}

          {rec.metadata?.what_it_solves && (
            <div className="glass-card rounded-xl p-4">
              <div className="text-[10px] uppercase tracking-wider mb-2" style={{ color: C.yellow }}>Ne Çözüyor / Ne Getirir</div>
              <p className="text-sm" style={{ color: C.text }}>{rec.metadata.what_it_solves}</p>
            </div>
          )}

          {rec.metadata?.how_to_integrate && (
            <div className="glass-card rounded-xl p-4">
              <div className="text-[10px] uppercase tracking-wider mb-2" style={{ color: C.cyan }}>Nasıl Entegre Edilir</div>
              <p className="text-sm leading-relaxed" style={{ color: C.text }}>{rec.metadata.how_to_integrate}</p>
            </div>
          )}

          {rec.metadata?.why_recommended && (
            <div className="glass-card rounded-xl p-4">
              <div className="text-[10px] uppercase tracking-wider mb-2" style={{ color: C.textMuted }}>Neden Öneriliyor</div>
              <p className="text-sm leading-relaxed" style={{ color: C.text }}>{rec.metadata.why_recommended}</p>
            </div>
          )}

          {!rec.metadata?.what_it_solves && !rec.metadata?.how_to_integrate && (
            <div className="text-xs text-center py-4" style={{ color: C.textMuted }}>
              Bu öneri Director tarafından araştırma yapılarak detaylandırılabilir.
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex gap-3 p-6 pt-0">
          <button onClick={() => { onDismiss(rec.id); onClose(); }}
            className="flex-1 py-2.5 rounded-xl text-xs font-medium transition-all"
            style={{ background: `${C.red}10`, color: C.red, border: `1px solid ${C.red}20` }}>
            Reddet
          </button>
          <button onClick={onClose}
            className="flex-1 py-2.5 rounded-xl text-xs font-medium transition-all"
            style={{ background: C.cyanDim, color: C.cyan, border: `1px solid ${C.cyanBorder}` }}>
            Tamam
          </button>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════
// Module Detail Modal
// ═══════════════════════════════════════════════

function ModuleModal({ mod, modKey, data, onClose, onChatAbout }: {
  mod: ModuleData; modKey: string; data: DashboardData | null;
  onClose: () => void; onChatAbout: (prompt: string) => void;
}) {
  const [tab, setTab] = useState<"overview" | "costs" | "efficiency" | "errors">("overview");
  const [modalDays, setModalDays] = useState(7);
  const sc = scColor(mod.status_color);
  const isPipeline = modKey === "clip_pipeline";

  const aiSteps = data?.costs_ai?.by_step || {};
  const moduleCostEntries = Object.entries(aiSteps).filter(([name]) => {
    if (isPipeline) return /^s0[0-9]|pipeline|discovery|evaluation/.test(name);
    if (modKey === "director") return name.includes("director");
    return name.includes("editor") || name.includes("reframe");
  });
  const moduleTotalCost = moduleCostEntries.reduce((s, [, v]) => s + (v.total_cost_usd || 0), 0);
  const pipeline = data?.pipeline;
  const clips = data?.clips;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/85 backdrop-blur-lg" />
      <div className="relative w-full max-w-3xl max-h-[88vh] overflow-y-auto rounded-2xl"
        style={{ background: "linear-gradient(135deg,rgba(5,10,20,0.99),rgba(0,15,30,0.99))", border: `1px solid ${C.cyanBorder}`, boxShadow: `0 0 60px rgba(0,212,255,0.06)` }}
        onClick={(e) => e.stopPropagation()}>

        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b" style={{ borderColor: C.cyanBorder }}>
          <div className="flex items-center gap-4">
            <ScoreRing score={mod.score} size={56} sw={4} />
            <div>
              <h2 className="text-lg font-bold" style={{ color: C.text }}>{mod.name}</h2>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded inline-block mt-1" style={{ background: `${sc}20`, color: sc }}>{mod.status}</span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <PeriodSelector value={modalDays} onChange={setModalDays} includeAll />
            <button onClick={onClose} className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-white/5 transition-colors" style={{ color: C.textMuted }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12" /></svg>
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 p-2 mx-4 mt-4 rounded-lg" style={{ background: "rgba(255,255,255,0.03)" }}>
          {(["overview", "costs", "efficiency", "errors"] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className="flex-1 py-1.5 rounded-md text-xs font-medium transition-all"
              style={{ background: tab === t ? C.cyanDim : "transparent", color: tab === t ? C.cyan : C.textMuted }}>
              {t === "overview" ? "Genel" : t === "costs" ? "Harcamalar" : t === "efficiency" ? "Verimlilik" : "Hatalar"}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="p-6 space-y-5">
          {/* ── Overview ── */}
          {tab === "overview" && isPipeline && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { l: "Toplam Job", v: String(Number(mod.metrics.total_jobs) || 0) },
                  { l: "Başarı Oranı", v: `${Number(mod.metrics.success_rate) || 0}%` },
                  { l: "Ort. Süre", v: `${Number(mod.metrics.avg_duration_min) || 0}dk` },
                  { l: "Toplam Klip", v: String(Number(mod.metrics.total_clips) || 0) },
                ].map((m) => (
                  <div key={m.l} className="glass-card rounded-xl p-4 text-center">
                    <div className="text-xl font-bold" style={{ color: C.cyan }}>{m.v}</div>
                    <div className="text-[10px] mt-1" style={{ color: C.textMuted }}>{m.l}</div>
                  </div>
                ))}
              </div>

              {clips?.analysis && (
                <div>
                  <div className="text-xs mb-3" style={{ color: C.textMuted }}>Klip Kalite Dağılımı</div>
                  <div className="flex gap-3">
                    {[
                      { l: "Pass", v: clips.analysis.pass_count || 0, c: C.green },
                      { l: "Fixable", v: clips.analysis.fixable_count || 0, c: C.yellow },
                      { l: "Fail", v: clips.analysis.fail_count || 0, c: C.red },
                    ].map((x) => (
                      <div key={x.l} className="flex-1 glass-card rounded-xl p-4 text-center">
                        <div className="text-2xl font-bold" style={{ color: x.c }}>{x.v}</div>
                        <div className="text-[10px] mt-1" style={{ color: C.textMuted }}>{x.l}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Subscores from DIRECTOR_MODULE.md */}
              {mod.subscores && Object.keys(mod.subscores).length > 0 && (
                <div>
                  <div className="text-xs mb-3" style={{ color: C.textMuted }}>Boyut Puanları (DIRECTOR_MODULE.md)</div>
                  <div className="space-y-3">
                    {Object.entries(mod.subscores).map(([key, sub]) => {
                      const pct = (sub.score / sub.max) * 100;
                      const c = pct >= 80 ? C.green : pct >= 60 ? C.cyan : pct >= 40 ? C.yellow : C.red;
                      const label = key === "teknik_saglik" ? "Teknik Sağlık" : key === "ai_karar_kalitesi" ? "AI Karar Kalitesi" : key === "cikti_kalitesi" ? "Çıktı Kalitesi" : "Öğrenme & Strateji";
                      return (
                        <div key={key}>
                          <div className="flex items-center justify-between text-xs mb-1">
                            <span style={{ color: C.textMuted }}>{label}</span>
                            <span className="font-mono" style={{ color: c }}>{sub.score}/{sub.max}</span>
                          </div>
                          <GlowBar value={sub.score} max={sub.max} color={c} h={5} />
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {pipeline?.steps && pipeline.steps.length > 0 && (
                <div>
                  <div className="text-xs mb-3" style={{ color: C.textMuted }}>Pipeline Adım Süreleri</div>
                  <div className="space-y-2">
                    {pipeline.steps.map((step) => (
                      <div key={step.step_name} className="flex items-center gap-3 text-xs">
                        <span className="w-20 font-mono truncate" style={{ color: C.cyan }}>{step.step_name}</span>
                        <div className="flex-1"><GlowBar value={step.runs} max={Math.max(...pipeline.steps.map((s) => s.runs))} color={C.cyan} h={4} /></div>
                        <span style={{ color: C.textMuted }}>{step.avg_duration_s}s</span>
                        {step.errors > 0 && <span style={{ color: C.red }}>{step.errors} err</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {tab === "overview" && !isPipeline && (
            <div className="text-center py-10">
              <div className="text-4xl mb-3">🔭</div>
              <div className="text-sm" style={{ color: C.textMuted }}>
                {modKey === "editor" ? "Editor metrikleri kullanım verileriyle dolacak." : "Director öz-değerlendirmesi için 'Director ile Konuş' butonuna tıkla."}
              </div>
            </div>
          )}

          {/* ── Costs ── */}
          {tab === "costs" && (
            <>
              <div className="glass-card rounded-xl p-5">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-sm font-medium" style={{ color: C.text }}>Toplam AI Maliyeti</span>
                  <span className="text-xl font-bold" style={{ color: C.cyan }}>{fmtCost(moduleTotalCost)}</span>
                </div>
                {moduleCostEntries.length > 0 ? (
                  <div className="space-y-2">
                    {moduleCostEntries.sort((a, b) => b[1].total_cost_usd - a[1].total_cost_usd).map(([name, v]) => (
                      <div key={name} className="flex items-center justify-between text-xs py-1 border-b" style={{ borderColor: "rgba(255,255,255,0.03)" }}>
                        <span className="font-mono" style={{ color: C.textMuted }}>{name}</span>
                        <div className="flex items-center gap-4">
                          <span style={{ color: C.textMuted }}>{v.count}x</span>
                          <span style={{ color: C.textMuted }}>{fmtNum(v.total_input_tokens + v.total_output_tokens)} tok</span>
                          <span className="font-medium" style={{ color: C.text }}>{fmtCost(v.total_cost_usd)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-center py-4" style={{ color: C.textMuted }}>Bu modüle ait Langfuse trace bulunamadı</div>
                )}
              </div>

              {isPipeline && data?.costs_deepgram?.totals && (
                <div className="glass-card rounded-xl p-5">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium" style={{ color: C.text }}>Deepgram Transkripsiyon</span>
                    <span className="text-xl font-bold" style={{ color: C.cyan }}>{fmtCost(data.costs_deepgram.totals.estimated_cost_usd)}</span>
                  </div>
                  <div className="flex gap-4 text-xs" style={{ color: C.textMuted }}>
                    <span>{data.costs_deepgram.totals.requests} istek</span>
                    <span>{data.costs_deepgram.totals.audio_hours?.toFixed(1)} saat ses</span>
                  </div>
                </div>
              )}
            </>
          )}

          {/* ── Efficiency ── */}
          {tab === "efficiency" && isPipeline && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="glass-card rounded-xl p-4">
                  <div className="text-xs mb-2" style={{ color: C.textMuted }}>Pass Oranı</div>
                  <div className="text-2xl font-bold mb-2" style={{ color: C.green }}>{Number(mod.metrics.pass_rate) || 0}%</div>
                  <GlowBar value={Number(mod.metrics.pass_rate) || 0} max={100} color={C.green} />
                  <div className="text-[10px] mt-1" style={{ color: C.textMuted }}>Hedef: &gt;50%</div>
                </div>
                <div className="glass-card rounded-xl p-4">
                  <div className="text-xs mb-2" style={{ color: C.textMuted }}>Ort. Güven Puanı</div>
                  <div className="text-2xl font-bold mb-2" style={{ color: C.cyan }}>{Number(mod.metrics.avg_confidence) || 0}</div>
                  <GlowBar value={Number(mod.metrics.avg_confidence) || 0} max={10} color={C.cyan} />
                  <div className="text-[10px] mt-1" style={{ color: C.textMuted }}>Hedef: &gt;7.0 / 10</div>
                </div>
              </div>
              <div className="glass-card rounded-xl p-4">
                <div className="text-xs mb-2" style={{ color: C.textMuted }}>Ortalama Tamamlanma Süresi</div>
                <div className="flex items-end gap-2 mb-2">
                  <span className="text-3xl font-bold" style={{ color: C.text }}>{Number(mod.metrics.avg_duration_min) || 0}</span>
                  <span className="text-sm mb-1" style={{ color: C.textMuted }}>dakika</span>
                </div>
                <GlowBar value={Math.max(0, 15 - (Number(mod.metrics.avg_duration_min) || 0))} max={15} color={C.cyan} />
                <div className="text-[10px] mt-1" style={{ color: C.textMuted }}>Hedef: &lt;6 dakika (0dk = veri yok)</div>
              </div>
            </div>
          )}

          {tab === "efficiency" && !isPipeline && (
            <div className="text-center py-10 text-sm" style={{ color: C.textMuted }}>Verimlilik metrikleri henüz mevcut değil</div>
          )}

          {/* ── Errors ── */}
          {tab === "errors" && (
            <div className="space-y-2">
              {(data?.errors || []).filter((e) => !e.error && !e.warning).length > 0 ? (
                data!.errors.filter((e) => !e.error && !e.warning).slice(0, 10).map((err, i) => (
                  <div key={i} className="glass-card rounded-lg p-3 flex items-start gap-3">
                    <div className="w-2 h-2 rounded-full mt-1.5 shrink-0" style={{ background: err.level === "error" ? C.red : C.yellow }} />
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium truncate" style={{ color: C.text }}>{err.title}</div>
                      {err.culprit && <div className="text-[10px] font-mono truncate" style={{ color: C.textMuted }}>{err.culprit}</div>}
                    </div>
                    {err.count && <div className="text-[10px] font-mono shrink-0" style={{ color: C.red }}>{err.count}x</div>}
                  </div>
                ))
              ) : (
                <div className="text-center py-8 text-sm" style={{ color: C.textMuted }}>Hata bulunamadı veya Sentry bağlı değil</div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex gap-3 p-6 pt-0">
          <button onClick={() => { onChatAbout(`${mod.name} modülünün detaylı analizini yap. Verimlilik boyutlarını hesapla, önce get_pipeline_stats ve get_clip_analysis araçlarını kullan, sonra geliştirme önerileri oluşturup create_recommendation ile kaydet.`); onClose(); }}
            className="flex-1 py-2.5 rounded-xl text-xs font-medium transition-all"
            style={{ background: C.cyanDim, color: C.cyan, border: `1px solid ${C.cyanBorder}` }}>
            Director ile Konuş
          </button>
          <button onClick={() => { onChatAbout(`${mod.name} modülü için önce get_director_self_analysis ile kendini tanı, sonra web_search ile bu modül için en iyi pratikleri araştır, ardından create_recommendation ile 3 cesur öneri oluştur.`); onClose(); }}
            className="flex-1 py-2.5 rounded-xl text-xs font-medium transition-all"
            style={{ background: "rgba(255,255,255,0.03)", color: C.textMuted, border: "1px solid rgba(255,255,255,0.06)" }}>
            İnternet Araştır + Öneri Oluştur
          </button>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════
// Dashboard Tab
// ═══════════════════════════════════════════════

function DashboardTab({ data, loading, days, onDaysChange, onOpenModule, onChatAbout, onRefresh }: {
  data: DashboardData | null; loading: boolean; days: number;
  onDaysChange: (d: number) => void; onOpenModule: (key: string) => void;
  onChatAbout: (p: string) => void; onRefresh: () => void;
}) {
  const [costsExpanded, setCostsExpanded] = useState(false);
  const [selectedRec, setSelectedRec] = useState<Recommendation | null>(null);
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());

  async function dismissRec(id: string) {
    setDismissedIds((prev) => { const next = new Set(prev); next.add(id); return next; });
    try {
      await fetch(`${API_URL}/director/recommendations/${id}/dismiss`, { method: "POST" });
    } catch { /* silent */ }
  }

  if (loading && !data) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: `${C.cyan} transparent ${C.cyan} ${C.cyan}` }} />
          <span className="text-xs font-mono" style={{ color: C.textMuted }}>SİSTEM VERİLERİ YÜKLENİYOR...</span>
        </div>
      </div>
    );
  }

  const modules = data?.modules?.modules || {};
  const overall = data?.modules?.overall_score ?? null;
  const overallColor = overall === null ? C.textMuted : overall >= 85 ? C.green : overall >= 71 ? C.cyan : overall >= 56 ? C.yellow : overall >= 36 ? C.orange : C.red;

  const totalAiCost = data?.costs_ai?.totals?.cost_usd || 0;
  const totalDgCost = data?.costs_deepgram?.totals?.estimated_cost_usd || 0;
  const totalCost = totalAiCost + totalDgCost;
  const aiSteps = data?.costs_ai?.by_step || {};
  const sortedCostSteps = Object.entries(aiSteps).sort((a, b) => b[1].total_cost_usd - a[1].total_cost_usd);

  const visibleRecs = (data?.recommendations || []).filter((r) => !dismissedIds.has(r.id));

  return (
    <div className="flex-1 overflow-y-auto px-4 md:px-8 py-6 space-y-8 grid-overlay">

      {/* ── System Health ── */}
      <div className="glass-card rounded-2xl p-6 relative overflow-hidden">
        <div className="scan-line" />
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wider" style={{ color: C.text }}>Sistem Sağlığı</h2>
            <p className="text-xs mt-0.5" style={{ color: C.textMuted }}>
              {overall === null ? "Yeterli veri yok — önce bir klip oluşturun" : "Tüm modüllerin ağırlıklı ortalaması"}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <PeriodSelector value={days} onChange={onDaysChange} includeAll />
            <button onClick={onRefresh} className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-white/5 transition-colors" style={{ color: C.textMuted }} title="Yenile">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M1 4v6h6M23 20v-6h-6" /><path d="M20.49 9A9 9 0 005.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 013.51 15" /></svg>
            </button>
          </div>
        </div>

        <div className="flex items-center gap-8">
          <ScoreRing score={overall} size={100} sw={7} />
          <div className="flex-1">
            {overall !== null ? (
              <>
                <div className="flex items-baseline gap-2 mb-3">
                  <span className="text-4xl font-bold" style={{ color: overallColor }}>{overall}</span>
                  <span className="text-sm" style={{ color: C.textMuted }}>/ 100</span>
                </div>
                <GlowBar value={overall} max={100} color={overallColor} h={8} />
                <div className="flex justify-between mt-2 text-[10px] font-mono" style={{ color: C.textMuted }}>
                  <span>KRİTİK</span><span>ZAYIF</span><span>ORTA</span><span>İYİ</span><span>GÜÇLÜ</span>
                </div>
              </>
            ) : (
              <div className="space-y-2">
                <div className="text-sm font-medium" style={{ color: C.textMuted }}>Henüz puan hesaplanamıyor</div>
                <div className="text-xs" style={{ color: C.textMuted }}>Pipeline en az 1 job tamamlandığında skor otomatik hesaplanır.</div>
                <button onClick={() => onChatAbout("Sistemi analiz et ve mevcut durumu değerlendir. get_pipeline_stats, get_clip_analysis ve get_langfuse_data araçlarını kullan.")}
                  className="text-xs px-3 py-1.5 rounded-lg mt-2 inline-block"
                  style={{ background: C.cyanDim, color: C.cyan, border: `1px solid ${C.cyanBorder}` }}>
                  Director ile Durum Analizi Yap
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Module sub-scores row */}
        {Object.entries(modules).length > 0 && (
          <div className="flex gap-3 mt-6 pt-5" style={{ borderTop: `1px solid rgba(255,255,255,0.04)` }}>
            {Object.entries(modules).map(([key, m]) => {
              const c = scColor(m.status_color);
              return (
                <button key={key} onClick={() => onOpenModule(key)}
                  className="flex-1 flex items-center gap-2 p-2 rounded-lg hover:bg-white/[0.02] transition-colors text-left">
                  <div className="w-6 h-6 rounded-full border flex items-center justify-center shrink-0 text-[9px] font-bold"
                    style={{ borderColor: `${c}40`, color: c, background: `${c}10` }}>
                    {m.score ?? "?"}
                  </div>
                  <div>
                    <div className="text-[10px] font-medium" style={{ color: C.text }}>{m.name}</div>
                    <div className="text-[9px]" style={{ color: c }}>{m.status}</div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Modules ── */}
      <SectionTitle>Modüller</SectionTitle>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {Object.entries(modules).map(([key, mod]) => {
          const sc2 = scColor(mod.status_color);
          return (
            <button key={key} onClick={() => onOpenModule(key)}
              className="glass-card rounded-2xl p-5 text-left relative overflow-hidden group transition-all duration-300 hover:scale-[1.02]">
              <div className="scan-line opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
              <div className="absolute top-0 right-0 overflow-hidden" style={{ width: 48, height: 48 }}>
                <div className="absolute top-0 right-0 w-px h-8" style={{ background: `linear-gradient(to bottom,${sc2},transparent)` }} />
                <div className="absolute top-0 right-0 h-px w-8" style={{ background: `linear-gradient(to left,${sc2},transparent)` }} />
              </div>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <div className="text-sm font-semibold" style={{ color: C.text }}>{mod.name}</div>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded mt-1 inline-block" style={{ background: `${sc2}15`, color: sc2 }}>{mod.status}</span>
                </div>
                <ScoreRing score={mod.score} size={52} sw={4} />
              </div>

              {key === "clip_pipeline" && mod.score !== null && (
                <div className="grid grid-cols-3 gap-2 text-center">
                  {[
                    { l: "Başarı", v: `${Number(mod.metrics.success_rate) || 0}%` },
                    { l: "Klip", v: String(Number(mod.metrics.total_clips) || 0) },
                    { l: "Süre", v: `${Number(mod.metrics.avg_duration_min) || 0}dk` },
                  ].map((m2) => (
                    <div key={m2.l}>
                      <div className="text-sm font-bold" style={{ color: C.text }}>{m2.v}</div>
                      <div className="text-[9px]" style={{ color: C.textMuted }}>{m2.l}</div>
                    </div>
                  ))}
                </div>
              )}

              {(key !== "clip_pipeline" || mod.score === null) && (
                <div className="text-xs text-center py-1" style={{ color: C.textMuted }}>
                  {mod.score === null ? "Veri birikmesi bekleniyor" : "Detay için tıklayın"}
                </div>
              )}
              <div className="absolute bottom-0 left-0 right-0 h-[2px] opacity-0 group-hover:opacity-100 transition-opacity border-flow" />
            </button>
          );
        })}
      </div>

      {/* ── Costs (Expandable) ── */}
      <SectionTitle>
        Harcamalar
      </SectionTitle>
      <div className="glass-card rounded-2xl overflow-hidden">
        {/* Summary row — always visible, clickable */}
        <button className="w-full p-5 flex items-center justify-between hover:bg-white/[0.01] transition-colors" onClick={() => setCostsExpanded((v) => !v)}>
          <div className="flex items-center gap-6">
            <div>
              <div className="text-2xl font-bold" style={{ color: C.cyan }}>{fmtCost(totalCost)}</div>
              <div className="text-xs mt-0.5" style={{ color: C.textMuted }}>toplam ({days} gün)</div>
            </div>
            <div className="flex gap-4 text-xs">
              <div className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full" style={{ background: C.cyan }} />
                <span style={{ color: C.textMuted }}>Gemini AI</span>
                <span className="font-medium" style={{ color: C.text }}>{fmtCost(totalAiCost)}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full" style={{ background: C.sky }} />
                <span style={{ color: C.textMuted }}>Deepgram</span>
                <span className="font-medium" style={{ color: C.text }}>{fmtCost(totalDgCost)}</span>
              </div>
            </div>
          </div>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            style={{ color: C.textMuted, transform: costsExpanded ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>

        {/* Proportion bar */}
        {totalCost > 0 && (
          <div className="flex mx-5 mb-1 rounded-full overflow-hidden" style={{ height: 4, background: "rgba(255,255,255,0.04)" }}>
            <div style={{ width: `${(totalAiCost / totalCost) * 100}%`, background: C.cyan, boxShadow: `0 0 6px ${C.cyan}` }} />
            <div style={{ width: `${(totalDgCost / totalCost) * 100}%`, background: C.sky, boxShadow: `0 0 6px ${C.sky}` }} />
          </div>
        )}

        {/* Expanded detail */}
        {costsExpanded && (
          <div className="px-5 pb-5 space-y-4 mt-2">
            {/* Per-module breakdown */}
            {sortedCostSteps.length > 0 && (
              <div>
                <div className="text-[10px] uppercase tracking-wider mb-3" style={{ color: C.textMuted }}>AI Adım Detayları (Langfuse)</div>
                <div className="space-y-1">
                  {sortedCostSteps.slice(0, 12).map(([name, v]) => (
                    <div key={name} className="flex items-center justify-between text-xs py-1.5 border-b" style={{ borderColor: "rgba(255,255,255,0.03)" }}>
                      <span className="font-mono" style={{ color: C.textMuted }}>{name}</span>
                      <div className="flex items-center gap-5">
                        <span style={{ color: C.textMuted }}>{v.count}x çağrı</span>
                        <span style={{ color: C.textMuted }}>{fmtNum(v.total_input_tokens)} in / {fmtNum(v.total_output_tokens)} out</span>
                        <span className="font-medium w-16 text-right" style={{ color: C.text }}>{fmtCost(v.total_cost_usd)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Deepgram detail */}
            {data?.costs_deepgram?.totals && (
              <div className="pt-2">
                <div className="text-[10px] uppercase tracking-wider mb-3" style={{ color: C.textMuted }}>Deepgram Transkripsiyon</div>
                <div className="flex items-center justify-between text-sm">
                  <div>
                    <span className="font-medium" style={{ color: C.text }}>Ses İşleme</span>
                    <span className="ml-3 text-xs" style={{ color: C.textMuted }}>
                      {data.costs_deepgram.totals.requests} istek · {data.costs_deepgram.totals.audio_hours?.toFixed(1)} saat
                    </span>
                  </div>
                  <span className="font-bold" style={{ color: C.cyan }}>{fmtCost(data.costs_deepgram.totals.estimated_cost_usd)}</span>
                </div>
                {data.costs_deepgram.balance && (
                  <div className="text-[10px] mt-1" style={{ color: C.textMuted }}>
                    Bakiye: {data.costs_deepgram.balance.amount} {data.costs_deepgram.balance.units}
                  </div>
                )}
              </div>
            )}

            {totalCost === 0 && (
              <div className="text-center py-4 text-xs" style={{ color: C.textMuted }}>
                Harcama verisi bulunamadı — Langfuse ve Deepgram bağlantısını kontrol et
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Recommendations ── */}
      <SectionTitle count={visibleRecs.length}
        action={
          <button onClick={() => onChatAbout("Tüm sistemi araştır: önce get_director_self_analysis, sonra get_pipeline_stats, get_clip_analysis, get_langfuse_data araçlarını kullan. Ardından web_search ile benzer sistemlerdeki en iyi pratikleri araştır. Son olarak create_recommendation ile en az 5 cesur, araştırmaya dayalı öneri oluştur.")}
            className="text-[10px] px-3 py-1 rounded-lg flex items-center gap-1.5 transition-all"
            style={{ background: C.cyanDim, color: C.cyan, border: `1px solid ${C.cyanBorder}` }}>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 5v14M5 12h14" /></svg>
            Yeni Analiz + Öneri
          </button>
        }>
        Aktif Öneriler
      </SectionTitle>

      {visibleRecs.length > 0 ? (
        <div className="space-y-3">
          {visibleRecs.map((rec) => {
            const pc = rec.priority <= 1 ? C.red : rec.priority <= 2 ? C.orange : rec.priority <= 3 ? C.yellow : C.textMuted;
            return (
              <div key={rec.id} className="glass-card rounded-xl p-4 group cursor-pointer hover:bg-white/[0.02] transition-colors"
                onClick={() => setSelectedRec(rec)}>
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ background: `${pc}15`, color: pc }}>P{rec.priority}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(255,255,255,0.05)", color: C.textMuted }}>{rec.module_name}</span>
                      {rec.impact && <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: `${C.green}15`, color: C.green }}>{rec.impact} etki</span>}
                      {rec.effort && <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(255,255,255,0.04)", color: C.textMuted }}>{rec.effort}</span>}
                    </div>
                    <div className="text-sm font-medium" style={{ color: C.text }}>{rec.title}</div>
                    <div className="text-xs mt-1 line-clamp-1" style={{ color: C.textMuted }}>{rec.description}</div>
                  </div>
                  <div className="flex gap-2 shrink-0 items-start">
                    <button onClick={(e) => { e.stopPropagation(); setSelectedRec(rec); }}
                      className="text-[10px] px-2 py-1 rounded transition-all" style={{ background: C.cyanDim, color: C.cyan }}>
                      Detay
                    </button>
                    <button onClick={(e) => { e.stopPropagation(); dismissRec(rec.id); }}
                      className="text-[10px] px-2 py-1 rounded transition-all" style={{ background: `${C.red}10`, color: C.red }}>
                      Reddet
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="glass-card rounded-xl p-8 text-center">
          <div className="text-sm" style={{ color: C.textMuted }}>Henüz öneri yok</div>
          <button onClick={() => onChatAbout("Sistemi analiz et ve araştırmaya dayalı geliştirme önerileri oluştur.")}
            className="mt-3 text-xs px-4 py-2 rounded-lg transition-all inline-block"
            style={{ background: C.cyanDim, color: C.cyan, border: `1px solid ${C.cyanBorder}` }}>
            Director&apos;dan Öneri İste
          </button>
        </div>
      )}

      {/* ── Errors ── */}
      <SectionTitle count={(data?.errors || []).filter((e) => !e.error && !e.warning).length}>Sistem Hataları</SectionTitle>
      {(data?.errors || []).filter((e) => !e.error && !e.warning).length > 0 ? (
        <div className="space-y-2">
          {data!.errors.filter((e) => !e.error && !e.warning).slice(0, 8).map((err, i) => (
            <div key={i} className="glass-card rounded-xl p-4 flex items-start gap-3">
              <div className="w-2 h-2 rounded-full mt-1.5 shrink-0 glow-pulse" style={{ background: err.level === "error" ? C.red : C.yellow }} />
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium truncate" style={{ color: C.text }}>{err.title}</div>
                {err.culprit && <div className="text-[10px] font-mono truncate mt-0.5" style={{ color: C.textMuted }}>{err.culprit}</div>}
              </div>
              <div className="flex items-center gap-3 shrink-0 text-[10px]">
                {err.count && <span className="font-mono" style={{ color: C.red }}>{err.count}x</span>}
                {err.lastSeen && <span style={{ color: C.textMuted }}>{timeAgo(err.lastSeen)}</span>}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="glass-card rounded-xl p-8 text-center">
          <div className="text-sm" style={{ color: (data?.errors?.[0]?.warning) ? C.yellow : C.green }}>
            {data?.errors?.[0]?.warning ? "Sentry API bağlantısı eksik" : "Hata bulunamadı ✓"}
          </div>
          {data?.errors?.[0]?.warning && (
            <div className="text-xs mt-1" style={{ color: C.textMuted }}>{data.errors[0].warning}</div>
          )}
        </div>
      )}

      {/* ── Events ── */}
      {(data?.events || []).length > 0 && (
        <>
          <SectionTitle count={data!.events.length}>Son Olaylar</SectionTitle>
          <div className="glass-card rounded-xl overflow-hidden">
            {data!.events.slice(0, 10).map((ev, i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-3 text-xs hover:bg-white/[0.01] transition-colors"
                style={{ borderBottom: i < 9 ? "1px solid rgba(255,255,255,0.03)" : "none" }}>
                <span className="font-mono px-1.5 py-0.5 rounded text-[10px] shrink-0" style={{ background: C.cyanDim, color: C.cyan }}>{ev.module_name}</span>
                <span className="font-medium shrink-0" style={{ color: C.text }}>{ev.event_type}</span>
                <span className="flex-1 truncate" style={{ color: C.textMuted }}>
                  {typeof ev.payload === "object" ? JSON.stringify(ev.payload).slice(0, 80) : String(ev.payload)}
                </span>
                <span className="shrink-0" style={{ color: C.textMuted }}>{timeAgo(ev.timestamp)}</span>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="h-8" />

      {/* Recommendation detail modal */}
      {selectedRec && (
        <RecommendationModal rec={selectedRec} onClose={() => setSelectedRec(null)} onDismiss={dismissRec} />
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════
// Chat Tab
// ═══════════════════════════════════════════════

function ToolBadge({ item }: { item: ToolCallItem }) {
  const argStr = Object.entries(item.args).map(([k, v]) => `${k}: ${String(v).slice(0, 40)}`).join(", ");
  return (
    <div className="flex items-start gap-2 text-xs rounded-lg px-3 py-2 my-1" style={{ background: "rgba(0,212,255,0.03)", border: `1px solid ${C.cyanBorder}` }}>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={C.cyan} strokeWidth="2" className="mt-0.5 shrink-0">
        <path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z" />
      </svg>
      <div>
        <span className="font-mono" style={{ color: C.cyan }}>{item.tool}</span>
        {argStr && <span className="ml-2" style={{ color: C.textMuted }}>({argStr})</span>}
        {item.summary && <div className="mt-0.5" style={{ color: C.textMuted }}>{item.summary}</div>}
      </div>
    </div>
  );
}

function MsgBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div className={`max-w-[80%] ${isUser ? "order-2" : "order-1"}`}>
        {!isUser && msg.toolCalls && msg.toolCalls.length > 0 && (
          <div className="mb-2">{msg.toolCalls.map((tc, i) => <ToolBadge key={i} item={tc} />)}</div>
        )}
        <div className="rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap"
          style={isUser
            ? { background: `linear-gradient(135deg,${C.cyan},${C.sky})`, color: "#000", borderTopRightRadius: 4 }
            : { background: "rgba(255,255,255,0.04)", color: C.text, border: "1px solid rgba(255,255,255,0.06)", borderTopLeftRadius: 4 }}>
          {msg.content}
          {msg.isStreaming && <span className="inline-block w-1.5 h-4 animate-pulse ml-1 align-middle" style={{ background: C.cyan }} />}
        </div>
      </div>
    </div>
  );
}

function ChatTab({ messages, setMessages, input, setInput, isLoading, setIsLoading, sessionId }: {
  messages: Message[]; setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  input: string; setInput: React.Dispatch<React.SetStateAction<string>>;
  isLoading: boolean; setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
  sessionId: string;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function sendMessage(override?: string) {
    const text = (override ?? input).trim();
    if (!text || isLoading) return;
    const userMsg: Message = { id: genId(), role: "user", content: text };
    setMessages((p) => [...p, userMsg]);
    if (!override) setInput("");
    setIsLoading(true);
    const aId = genId();
    setMessages((p) => [...p, { id: aId, role: "assistant", content: "", toolCalls: [], isStreaming: true }]);

    try {
      const res = await fetch(`${API_URL}/director/chat`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });
      if (!res.body) throw new Error("No body");
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() || "";
        for (const part of parts) {
          if (!part.startsWith("data: ")) continue;
          try {
            const ev = JSON.parse(part.slice(6));
            if (ev.type === "tool_call") {
              setMessages((p) => p.map((m) => m.id === aId ? { ...m, toolCalls: [...(m.toolCalls || []), { tool: ev.tool, args: ev.args }] } : m));
            } else if (ev.type === "tool_result") {
              setMessages((p) => p.map((m) => {
                if (m.id !== aId) return m;
                const tc = [...(m.toolCalls || [])];
                const li = tc.length - 1;
                if (li >= 0 && tc[li].tool === ev.tool) tc[li] = { ...tc[li], summary: ev.summary };
                return { ...m, toolCalls: tc };
              }));
            } else if (ev.type === "text") {
              setMessages((p) => p.map((m) => m.id === aId ? { ...m, content: m.content + ev.text } : m));
            } else if (ev.type === "done") {
              setMessages((p) => p.map((m) => m.id === aId ? { ...m, isStreaming: false } : m));
            } else if (ev.type === "error") {
              setMessages((p) => p.map((m) => m.id === aId ? { ...m, content: `Hata: ${ev.message}`, isStreaming: false } : m));
            }
          } catch { /* skip */ }
        }
      }
    } catch (err) {
      setMessages((p) => p.map((m) => m.id === aId ? { ...m, content: `Bağlantı hatası: ${String(err)}`, isStreaming: false } : m));
    } finally {
      setIsLoading(false);
    }
  }

  const suggested = [
    "Kendini analiz et — yeteneklerin, limitlern, ne eklememi önerirsin?",
    "Pipeline son 7 günde nasıl performans gösterdi?",
    "Tüm sistemi araştır ve 5 cesur öneri oluştur",
    "Maliyetleri analiz et, nerede tasarruf edebiliriz?",
    "Son hataları analiz et",
    "Kodu tara, zayıf noktaları bul",
  ];

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto px-4 py-6">
        {messages.map((m) => <MsgBubble key={m.id} msg={m} />)}
        {messages.length === 1 && (
          <div className="flex flex-wrap gap-2 mt-4 justify-center">
            {suggested.map((p) => (
              <button key={p} onClick={() => { setInput(p); inputRef.current?.focus(); }}
                className="text-xs rounded-full px-3 py-1.5 transition-all"
                style={{ border: `1px solid ${C.cyanBorder}`, color: C.textMuted }}>
                {p}
              </button>
            ))}
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="px-4 pb-4">
        <div className="flex gap-2 rounded-2xl p-2" style={{ background: "rgba(255,255,255,0.03)", border: `1px solid ${C.cyanBorder}` }}>
          <textarea ref={inputRef} value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
            placeholder="Director'a sor..." rows={1} disabled={isLoading}
            className="flex-1 bg-transparent text-sm placeholder-gray-600 resize-none outline-none px-2 py-1.5 max-h-32"
            style={{ minHeight: 36, color: C.text }} />
          <button onClick={() => sendMessage()} disabled={isLoading || !input.trim()}
            className="w-9 h-9 rounded-xl flex items-center justify-center transition-all shrink-0 disabled:opacity-30"
            style={{ background: C.cyan, color: "#000" }}>
            {isLoading
              ? <div className="w-4 h-4 border-2 border-black/30 border-t-black rounded-full animate-spin" />
              : <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M2 21L23 12 2 3V10L17 12 2 14Z" /></svg>
            }
          </button>
        </div>
        <p className="text-center text-xs mt-2" style={{ color: C.textMuted }}>Enter ile gönder · Shift+Enter yeni satır</p>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════
// Decisions Tab
// ═══════════════════════════════════════════════

function DecisionsTab() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ decision: "", context: "", expected_impact: "", alternatives: "" });
  const [submitting, setSubmitting] = useState(false);

  const fetchDecisions = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/director/decisions?limit=50`, { cache: "no-store" });
      if (res.ok) setDecisions(await res.json());
    } catch { /* silent */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchDecisions(); }, [fetchDecisions]);

  async function submitDecision() {
    if (!form.decision.trim()) return;
    setSubmitting(true);
    try {
      await fetch(`${API_URL}/director/decisions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          decision: form.decision,
          context: form.context || null,
          expected_impact: form.expected_impact || null,
          alternatives: form.alternatives ? form.alternatives.split("\n").filter(Boolean) : [],
        }),
      });
      setForm({ decision: "", context: "", expected_impact: "", alternatives: "" });
      setShowForm(false);
      fetchDecisions();
    } catch { /* silent */ } finally { setSubmitting(false); }
  }

  const statusColor: Record<string, string> = {
    active: C.cyan, evaluated: C.green, cancelled: C.textMuted,
  };

  return (
    <div className="flex-1 overflow-y-auto p-6" style={{ background: C.bg }}>
      <div className="max-w-4xl mx-auto space-y-4">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-semibold tracking-wider" style={{ color: C.text }}>DECISION JOURNAL</h2>
          <button onClick={() => setShowForm(!showForm)}
            className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
            style={{ background: C.cyanDim, color: C.cyan, border: `1px solid ${C.cyanBorder}` }}>
            + New Decision
          </button>
        </div>

        {showForm && (
          <div className="rounded-xl p-4 space-y-3" style={{ background: C.panel, border: `1px solid ${C.border}` }}>
            <textarea value={form.decision} onChange={e => setForm(f => ({ ...f, decision: e.target.value }))}
              placeholder="Decision made..." rows={2}
              className="w-full bg-transparent text-sm outline-none resize-none rounded-lg px-3 py-2"
              style={{ border: `1px solid ${C.border}`, color: C.text }} />
            <textarea value={form.context} onChange={e => setForm(f => ({ ...f, context: e.target.value }))}
              placeholder="Context / why..." rows={2}
              className="w-full bg-transparent text-sm outline-none resize-none rounded-lg px-3 py-2"
              style={{ border: `1px solid ${C.border}`, color: C.text }} />
            <textarea value={form.expected_impact} onChange={e => setForm(f => ({ ...f, expected_impact: e.target.value }))}
              placeholder="Expected impact..." rows={1}
              className="w-full bg-transparent text-sm outline-none resize-none rounded-lg px-3 py-2"
              style={{ border: `1px solid ${C.border}`, color: C.text }} />
            <textarea value={form.alternatives} onChange={e => setForm(f => ({ ...f, alternatives: e.target.value }))}
              placeholder="Alternatives considered (one per line)..." rows={2}
              className="w-full bg-transparent text-sm outline-none resize-none rounded-lg px-3 py-2"
              style={{ border: `1px solid ${C.border}`, color: C.text }} />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowForm(false)} className="px-3 py-1.5 rounded-lg text-xs"
                style={{ color: C.textMuted }}>Cancel</button>
              <button onClick={submitDecision} disabled={submitting || !form.decision.trim()}
                className="px-4 py-1.5 rounded-lg text-xs font-medium disabled:opacity-40"
                style={{ background: C.cyan, color: "#000" }}>
                {submitting ? "Saving..." : "Save Decision"}
              </button>
            </div>
          </div>
        )}

        {loading ? (
          <div className="text-xs text-center py-8" style={{ color: C.textMuted }}>Loading decisions...</div>
        ) : decisions.length === 0 ? (
          <div className="text-xs text-center py-8" style={{ color: C.textMuted }}>No decisions recorded yet.</div>
        ) : (
          <div className="space-y-3">
            {decisions.map(d => (
              <div key={d.id} className="rounded-xl p-4" style={{ background: C.panel, border: `1px solid ${C.border}` }}>
                <div className="flex items-start justify-between gap-3 mb-2">
                  <p className="text-sm font-medium" style={{ color: C.text }}>{d.decision}</p>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full shrink-0"
                    style={{ color: statusColor[d.status] || C.textMuted, background: `${statusColor[d.status] || C.textMuted}15` }}>
                    {d.status}
                  </span>
                </div>
                {d.context && <p className="text-xs mb-1" style={{ color: C.textMuted }}>{d.context}</p>}
                {d.expected_impact && (
                  <p className="text-xs" style={{ color: C.text }}>
                    <span style={{ color: C.cyan }}>Expected:</span> {d.expected_impact}
                  </p>
                )}
                {d.actual_impact && (
                  <p className="text-xs mt-1" style={{ color: C.text }}>
                    <span style={{ color: C.green }}>Actual:</span> {d.actual_impact}
                  </p>
                )}
                {d.alternatives && d.alternatives.length > 0 && (
                  <div className="mt-2">
                    <p className="text-[10px] mb-1" style={{ color: C.textMuted }}>Alternatives considered:</p>
                    <ul className="space-y-0.5">
                      {d.alternatives.map((alt, i) => (
                        <li key={i} className="text-xs" style={{ color: C.text }}>• {alt}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <p className="text-[10px] mt-2" style={{ color: C.textMuted }}>
                  {new Date(d.timestamp).toLocaleDateString("tr-TR", { day: "2-digit", month: "short", year: "numeric" })}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════
// Main Page
// ═══════════════════════════════════════════════

export default function DirectorPage() {
  const [activeTab, setActiveTab] = useState<"dashboard" | "chat" | "decisions">("dashboard");
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(7);
  const [openModuleKey, setOpenModuleKey] = useState<string | null>(null);

  const [messages, setMessages] = useState<Message[]>([{
    id: "welcome", role: "assistant",
    content: "Merhaba. Ben Director — sistemin AI CEO'su.\n\nPipeline, maliyetler, klip kalitesi, kod tabanı — hepsini analiz edebilirim. İnternet araştırması yapabilirim. Hafızama kaydedebilirim. Öneri oluşturabilirim.\n\nNe öğrenmek istiyorsun?",
  }]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [sessionId] = useState(() => genId());

  const fetchDashboard = useCallback(async (d: number) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/director/dashboard?days=${d}`, { cache: "no-store" });
      if (res.ok) setDashboardData(await res.json());
    } catch { /* silent */ } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchDashboard(days); }, [days, fetchDashboard]);

  function handleChatAbout(prompt: string) {
    setChatInput(prompt);
    setActiveTab("chat");
  }

  const openModule = openModuleKey && dashboardData?.modules?.modules?.[openModuleKey]
    ? { key: openModuleKey, ...dashboardData.modules.modules[openModuleKey] }
    : null;

  return (
    <div className="flex flex-col h-screen" style={{ background: C.bg, color: C.text }}>
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3 shrink-0"
        style={{ borderBottom: `1px solid ${C.cyanBorder}`, background: "rgba(0,5,15,0.9)", backdropFilter: "blur(12px)" }}>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold relative overflow-hidden"
            style={{ background: `linear-gradient(135deg,${C.cyan}20,${C.sky}10)`, border: `1px solid ${C.cyanBorder}`, color: C.cyan }}>
            D
          </div>
          <div>
            <h1 className="font-semibold text-sm tracking-wider" style={{ color: C.text }}>DIRECTOR</h1>
            <p className="text-[10px] font-mono" style={{ color: C.textMuted }}>AI SYSTEM CONTROLLER v1.0</p>
          </div>
        </div>

        <div className="flex gap-1 p-0.5 rounded-lg" style={{ background: "rgba(255,255,255,0.03)" }}>
          {(["dashboard", "chat", "decisions"] as const).map((tab) => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              className="px-4 py-1.5 rounded-md text-xs font-medium transition-all relative"
              style={{ background: activeTab === tab ? C.cyanDim : "transparent", color: activeTab === tab ? C.cyan : C.textMuted }}>
              {tab === "dashboard" ? "Dashboard" : tab === "chat" ? "Chat" : "Decisions"}
              {activeTab === tab && (
                <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-4 h-[2px] rounded-full"
                  style={{ background: C.cyan, boxShadow: `0 0 8px ${C.cyan}` }} />
              )}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full glow-pulse" style={{ background: C.green, boxShadow: `0 0 6px ${C.green}` }} />
          <span className="text-[10px] font-mono" style={{ color: C.textMuted }}>ONLINE</span>
        </div>
      </div>

      {/* Content */}
      {activeTab === "dashboard" ? (
        <DashboardTab
          data={dashboardData} loading={loading} days={days}
          onDaysChange={setDays} onOpenModule={setOpenModuleKey}
          onChatAbout={handleChatAbout} onRefresh={() => fetchDashboard(days)}
        />
      ) : activeTab === "decisions" ? (
        <DecisionsTab />
      ) : (
        <ChatTab
          messages={messages} setMessages={setMessages}
          input={chatInput} setInput={setChatInput}
          isLoading={chatLoading} setIsLoading={setChatLoading}
          sessionId={sessionId}
        />
      )}

      {/* Module Modal */}
      {openModule && (
        <ModuleModal
          mod={openModule} modKey={openModule.key}
          data={dashboardData} onClose={() => setOpenModuleKey(null)}
          onChatAbout={handleChatAbout}
        />
      )}
    </div>
  );
}
