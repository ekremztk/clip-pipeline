"use client";

import { useEffect, useState, useCallback } from "react";
import { supabase } from "@/lib/supabase";
import {
  ExternalLink,
  Tag,
  Battery,
  Shield,
  TrendingUp,
  ChevronLeft,
  ChevronRight,
  X,
  RefreshCw,
  Zap,
  User,
  MapPin,
  Clock,
  Package,
  AlertTriangle,
  CheckCircle,
  MessageSquare,
} from "lucide-react";

type SellerAnalysis = {
  effort_level: string;
  urgency: string;
  trust_score: number;
  reasoning: string;
};

type PriceBands = {
  low_range: string;
  low_pct: number;
  mid_range: string;
  mid_pct: number;
  high_range: string;
  high_pct: number;
  p25: number;
  p50: number;
  p75: number;
};

type AiAnalysis = {
  condition_notes: string;
  description_tr: string;
  verdict: string;
  suggested_offer: number | null;
  has_box: boolean | null;
  has_charger: boolean | null;
  has_receipt: boolean | null;
  flags: string[];
  price_assessment: {
    is_underpriced: boolean;
    why_cheap: string;
    risk_factors: string[];
    negotiation_tip: string;
  };
  price_bands: PriceBands | null;
};

type Deal = {
  id: string;
  score: number | null;
  estimated_profit: number | null;
  status: string;
  created_at: string;
  buy_price: number | null;
  sell_price: number | null;
  ai_analysis: AiAnalysis | null;
  seller_analysis: SellerAnalysis | null;
  estimated_min_sell: number | null;
  estimated_realistic_sell: number | null;
  estimated_max_sell: number | null;
  tier: string | null;
  model_parsed: string | null;
  storage_parsed: string | null;
  battery_pct: number | null;
  images: string[] | null;
  description: string | null;
  confidence: number | null;
  klein_url: string | null;
  seller_name: string | null;
  listing_location: string | null;
  listing: {
    title: string;
    price: number | null;
    location: string | null;
    url: string;
    thumbnail_url: string | null;
    platform: string;
  } | null;
};

const TIER_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  A: { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200" },
  B: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-200" },
  C: { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200" },
  D: { bg: "bg-orange-50", text: "text-orange-700", border: "border-orange-200" },
  E: { bg: "bg-red-50", text: "text-red-700", border: "border-red-200" },
};

const TIER_LABELS: Record<string, string> = {
  A: "Mükemmel",
  B: "İyi",
  C: "Orta",
  D: "Kötü",
  E: "Riskli",
};

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}dk`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}sa`;
  return `${Math.floor(hours / 24)}g`;
}

function DealCard({ deal, onClick }: { deal: Deal; onClick: () => void }) {
  const price = deal.buy_price ?? deal.listing?.price ?? 0;
  const profit = deal.estimated_profit;
  const tier = deal.tier;
  const tierStyle = tier ? TIER_COLORS[tier] : null;
  const mainImage = deal.images?.[0] ?? deal.listing?.thumbnail_url;
  const verdict = deal.ai_analysis?.verdict;

  return (
    <div
      onClick={onClick}
      className="group cursor-pointer rounded-xl border border-[#e5e5e5] bg-white transition-all hover:border-[#c5c5c5] hover:shadow-lg"
    >
      <div className="relative aspect-[4/3] overflow-hidden rounded-t-xl bg-[#f5f5f5]">
        {mainImage ? (
          <img
            src={mainImage}
            alt=""
            className="h-full w-full object-cover transition-transform group-hover:scale-[1.02]"
          />
        ) : (
          <div className="flex h-full items-center justify-center">
            <Tag size={32} className="text-[#d4d4d4]" />
          </div>
        )}
        {tier && tierStyle && (
          <span className={`absolute left-2 top-2 rounded-md border px-2 py-0.5 text-[11px] font-bold ${tierStyle.bg} ${tierStyle.text} ${tierStyle.border}`}>
            {tier} — {TIER_LABELS[tier]}
          </span>
        )}
        {profit != null && profit > 0 && (
          <span className="absolute right-2 top-2 rounded-md bg-emerald-500 px-2 py-0.5 text-[11px] font-bold text-white">
            +{profit.toFixed(0)}€ kar
          </span>
        )}
      </div>

      <div className="p-3">
        <div className="flex items-start justify-between gap-1">
          <p className="line-clamp-1 text-sm font-semibold text-[#171717]">
            {deal.model_parsed || deal.listing?.title || "—"}
          </p>
          {deal.storage_parsed && (
            <span className="shrink-0 rounded bg-[#f0f0f0] px-1.5 py-0.5 text-[10px] font-medium text-[#525252]">
              {deal.storage_parsed}
            </span>
          )}
        </div>

        <div className="mt-2 flex items-center justify-between">
          <span className="text-xl font-bold text-[#171717]">{price}€</span>
          <div className="flex items-center gap-2">
            {deal.ai_analysis?.suggested_offer && (
              <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-700">
                Teklif: {deal.ai_analysis.suggested_offer}€
              </span>
            )}
          </div>
        </div>

        {verdict && (
          <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-[#525252]">{verdict}</p>
        )}

        <div className="mt-2 flex items-center gap-2 text-[11px] text-[#a3a3a3]">
          {deal.listing_location && (
            <span className="flex items-center gap-0.5">
              <MapPin size={10} />
              {deal.listing_location.split(",")[0]}
            </span>
          )}
          <span className="flex items-center gap-0.5">
            <Clock size={10} />
            {timeAgo(deal.created_at)}
          </span>
          {deal.seller_analysis && (
            <span className="flex items-center gap-0.5">
              <Shield size={10} />
              {deal.seller_analysis.trust_score}/10
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function PriceBandBar({ bands, buyPrice }: { bands: PriceBands; buyPrice: number }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1 rounded-lg bg-[#f8f8f8] p-3">
        <div className="flex-1">
          <div className="flex h-6 overflow-hidden rounded-full">
            <div
              className="flex items-center justify-center bg-red-100 text-[9px] font-bold text-red-700"
              style={{ width: `${bands.low_pct}%` }}
            >
              {bands.low_pct}%
            </div>
            <div
              className="flex items-center justify-center bg-amber-100 text-[9px] font-bold text-amber-700"
              style={{ width: `${bands.mid_pct}%` }}
            >
              {bands.mid_pct}%
            </div>
            <div
              className="flex items-center justify-center bg-emerald-100 text-[9px] font-bold text-emerald-700"
              style={{ width: `${bands.high_pct}%` }}
            >
              {bands.high_pct}%
            </div>
          </div>
          <div className="mt-1 flex justify-between text-[10px] text-[#737373]">
            <span>{bands.low_range}</span>
            <span>{bands.mid_range}</span>
            <span>{bands.high_range}</span>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded-lg border border-red-100 bg-red-50/50 p-2">
          <p className="text-[10px] text-red-600">Düşük Satış</p>
          <p className="text-sm font-bold text-red-700">{bands.low_range}</p>
          <p className="text-[10px] text-[#a3a3a3]">
            Kar: {bands.p25 - buyPrice > 0 ? "+" : ""}{(bands.p25 - buyPrice).toFixed(0)}€
          </p>
        </div>
        <div className="rounded-lg border border-amber-100 bg-amber-50/50 p-2">
          <p className="text-[10px] text-amber-600">Gerçekçi</p>
          <p className="text-sm font-bold text-amber-700">{bands.p50}€</p>
          <p className="text-[10px] text-[#a3a3a3]">
            Kar: {bands.p50 - buyPrice > 0 ? "+" : ""}{(bands.p50 - buyPrice).toFixed(0)}€
          </p>
        </div>
        <div className="rounded-lg border border-emerald-100 bg-emerald-50/50 p-2">
          <p className="text-[10px] text-emerald-600">Yüksek Satış</p>
          <p className="text-sm font-bold text-emerald-700">{bands.high_range}</p>
          <p className="text-[10px] text-[#a3a3a3]">
            Kar: {bands.p75 - buyPrice > 0 ? "+" : ""}{(bands.p75 - buyPrice).toFixed(0)}€
          </p>
        </div>
      </div>
    </div>
  );
}

function DealModal({ deal, onClose, onAction }: { deal: Deal; onClose: () => void; onAction: (status: string) => void }) {
  const [imgIdx, setImgIdx] = useState(0);
  const images = deal.images?.length ? deal.images : deal.listing?.thumbnail_url ? [deal.listing.thumbnail_url] : [];
  const price = deal.buy_price ?? deal.listing?.price ?? 0;
  const ai = deal.ai_analysis;
  const seller = deal.seller_analysis;

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") setImgIdx((i) => Math.max(0, i - 1));
      if (e.key === "ArrowRight") setImgIdx((i) => Math.min(images.length - 1, i + 1));
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [images.length, onClose]);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div className="absolute inset-0" />
      <div
        className="relative mx-4 flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute right-3 top-3 z-10 rounded-full bg-white/90 p-1.5 shadow-sm hover:bg-white">
          <X size={18} />
        </button>

        <div className="flex-1 overflow-y-auto">
          <div className="grid grid-cols-1 gap-0 md:grid-cols-5">
            {/* Left: Image + Basic Info */}
            <div className="md:col-span-2 border-r border-[#f0f0f0]">
              {images.length > 0 && (
                <div className="relative aspect-square bg-[#f5f5f5]">
                  <img src={images[imgIdx]} alt="" className="h-full w-full object-contain" />
                  {images.length > 1 && (
                    <>
                      <button
                        onClick={() => setImgIdx((i) => Math.max(0, i - 1))}
                        className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-white/90 p-1.5 shadow-sm hover:bg-white disabled:opacity-30"
                        disabled={imgIdx === 0}
                      >
                        <ChevronLeft size={16} />
                      </button>
                      <button
                        onClick={() => setImgIdx((i) => Math.min(images.length - 1, i + 1))}
                        className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-white/90 p-1.5 shadow-sm hover:bg-white disabled:opacity-30"
                        disabled={imgIdx === images.length - 1}
                      >
                        <ChevronRight size={16} />
                      </button>
                      <div className="absolute bottom-2 right-2 rounded-md bg-black/60 px-2 py-0.5 text-[10px] text-white">
                        {imgIdx + 1}/{images.length}
                      </div>
                    </>
                  )}
                </div>
              )}

              <div className="p-4 space-y-3">
                <div>
                  <h2 className="text-lg font-bold text-[#171717]">{deal.model_parsed || deal.listing?.title}</h2>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    {deal.storage_parsed && (
                      <span className="rounded bg-[#f0f0f0] px-2 py-0.5 text-xs font-medium">{deal.storage_parsed}</span>
                    )}
                    {deal.tier && (
                      <span className={`rounded border px-2 py-0.5 text-[11px] font-bold ${TIER_COLORS[deal.tier]?.bg} ${TIER_COLORS[deal.tier]?.text} ${TIER_COLORS[deal.tier]?.border}`}>
                        {deal.tier} — {TIER_LABELS[deal.tier]}
                      </span>
                    )}
                    {deal.battery_pct && (
                      <span className="flex items-center gap-0.5 text-xs text-[#525252]">
                        <Battery size={12} /> %{deal.battery_pct}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-3 rounded-lg bg-[#f8f8f8] p-3">
                  <div>
                    <p className="text-[10px] text-[#a3a3a3]">İlan Fiyatı</p>
                    <p className="text-2xl font-bold text-[#171717]">{price}€</p>
                  </div>
                  {ai?.suggested_offer && (
                    <div className="border-l border-[#e5e5e5] pl-3">
                      <p className="text-[10px] text-blue-600">Teklif Et</p>
                      <p className="text-2xl font-bold text-blue-700">{ai.suggested_offer}€</p>
                    </div>
                  )}
                </div>

                {/* Accessories */}
                <div className="flex gap-2 text-[11px]">
                  {ai?.has_box != null && (
                    <span className={`flex items-center gap-0.5 rounded px-2 py-0.5 ${ai.has_box ? "bg-emerald-50 text-emerald-700" : "bg-[#f5f5f5] text-[#a3a3a3]"}`}>
                      <Package size={10} /> Kutu {ai.has_box ? "✓" : "✗"}
                    </span>
                  )}
                  {ai?.has_charger != null && (
                    <span className={`flex items-center gap-0.5 rounded px-2 py-0.5 ${ai.has_charger ? "bg-emerald-50 text-emerald-700" : "bg-[#f5f5f5] text-[#a3a3a3]"}`}>
                      <Zap size={10} /> Şarj {ai.has_charger ? "✓" : "✗"}
                    </span>
                  )}
                  {ai?.has_receipt != null && (
                    <span className={`flex items-center gap-0.5 rounded px-2 py-0.5 ${ai.has_receipt ? "bg-emerald-50 text-emerald-700" : "bg-[#f5f5f5] text-[#a3a3a3]"}`}>
                      <CheckCircle size={10} /> Fatura {ai.has_receipt ? "✓" : "✗"}
                    </span>
                  )}
                </div>

                {/* Seller */}
                {(deal.seller_name || deal.listing_location) && (
                  <div className="text-[11px] text-[#737373] space-y-0.5">
                    {deal.seller_name && (
                      <p className="flex items-center gap-1"><User size={10} /> {deal.seller_name}</p>
                    )}
                    {deal.listing_location && (
                      <p className="flex items-center gap-1"><MapPin size={10} /> {deal.listing_location}</p>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Right: Analysis */}
            <div className="md:col-span-3 p-5 space-y-4">
              {/* Verdict */}
              {ai?.verdict && (
                <div className="rounded-lg border-2 border-blue-100 bg-blue-50/50 p-4">
                  <h3 className="mb-1 flex items-center gap-1.5 text-xs font-bold text-blue-800">
                    <MessageSquare size={14} />
                    AI Kararı
                  </h3>
                  <p className="text-sm font-medium text-blue-900 leading-relaxed">{ai.verdict}</p>
                </div>
              )}

              {/* eBay Price Distribution */}
              {ai?.price_bands && (
                <div className="space-y-2">
                  <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase text-[#525252]">
                    <TrendingUp size={14} />
                    eBay Satış Dağılımı ({ai.price_bands.low_pct + ai.price_bands.mid_pct + ai.price_bands.high_pct > 0 ? "son satışlar" : ""})
                  </h3>
                  <PriceBandBar bands={ai.price_bands} buyPrice={price} />
                </div>
              )}

              {/* Simple price estimate fallback */}
              {!ai?.price_bands && (deal.estimated_min_sell || deal.estimated_realistic_sell) && (
                <div className="rounded-lg border border-[#e5e5e5] bg-[#fafafa] p-4">
                  <h3 className="mb-2 flex items-center gap-1.5 text-xs font-bold uppercase text-[#525252]">
                    <TrendingUp size={14} />
                    eBay Satış Tahmini
                  </h3>
                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div>
                      <p className="text-[10px] text-[#a3a3a3]">Minimum</p>
                      <p className="text-lg font-bold text-[#525252]">{deal.estimated_min_sell ?? "—"}€</p>
                    </div>
                    <div>
                      <p className="text-[10px] text-[#a3a3a3]">Gerçekçi</p>
                      <p className="text-lg font-bold text-emerald-600">{deal.estimated_realistic_sell ?? "—"}€</p>
                    </div>
                    <div>
                      <p className="text-[10px] text-[#a3a3a3]">Optimistik</p>
                      <p className="text-lg font-bold text-[#525252]">{deal.estimated_max_sell ?? "—"}€</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Seller Psychology */}
              {seller && (
                <div className="rounded-lg border border-[#e5e5e5] bg-[#fafafa] p-4">
                  <h3 className="mb-2 flex items-center gap-1.5 text-xs font-bold uppercase text-[#525252]">
                    <User size={14} />
                    Satıcı Profili
                  </h3>
                  <div className="grid grid-cols-3 gap-3 text-center mb-3">
                    <div>
                      <p className="text-[10px] text-[#a3a3a3]">Emek</p>
                      <p className="text-sm font-semibold capitalize">{seller.effort_level}</p>
                    </div>
                    <div>
                      <p className="text-[10px] text-[#a3a3a3]">Aciliyet</p>
                      <p className={`text-sm font-semibold capitalize ${
                        seller.urgency === "yüksek" || seller.urgency === "high" ? "text-red-600" :
                        seller.urgency === "orta" || seller.urgency === "medium" ? "text-amber-600" : ""
                      }`}>
                        {seller.urgency}
                      </p>
                    </div>
                    <div>
                      <p className="text-[10px] text-[#a3a3a3]">Güven</p>
                      <p className="text-sm font-semibold">{seller.trust_score}/10</p>
                    </div>
                  </div>
                  {seller.reasoning && (
                    <p className="text-xs text-[#525252] bg-white rounded p-2 border border-[#f0f0f0]">{seller.reasoning}</p>
                  )}
                </div>
              )}

              {/* Negotiation Tip */}
              {ai?.price_assessment?.negotiation_tip && (
                <div className="rounded-lg border border-emerald-100 bg-emerald-50/50 p-3">
                  <h3 className="mb-1 text-[11px] font-bold text-emerald-800">Pazarlık Tavsiyesi</h3>
                  <p className="text-xs text-emerald-900">{ai.price_assessment.negotiation_tip}</p>
                </div>
              )}

              {/* Condition + Flags */}
              {ai?.condition_notes && (
                <div className="rounded-lg border border-[#e5e5e5] bg-[#fafafa] p-4">
                  <h3 className="mb-1 text-xs font-bold uppercase text-[#525252]">Fiziksel Durum</h3>
                  <p className="text-xs text-[#525252]">{ai.condition_notes}</p>
                  {ai.flags?.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {ai.flags.map((flag) => (
                        <span key={flag} className="rounded bg-[#e5e5e5] px-2 py-0.5 text-[10px] text-[#525252]">
                          {flag.replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Risk Factors */}
              {ai?.price_assessment?.risk_factors && ai.price_assessment.risk_factors.length > 0 && (
                <div className="rounded-lg border border-red-100 bg-red-50/50 p-3">
                  <h3 className="mb-1 flex items-center gap-1 text-[11px] font-bold text-red-700">
                    <AlertTriangle size={12} /> Risk Faktörleri
                  </h3>
                  <ul className="space-y-0.5">
                    {ai.price_assessment.risk_factors.map((risk, i) => (
                      <li key={i} className="text-xs text-red-700">• {risk}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Description (Turkish translation) */}
              {(ai?.description_tr || deal.description) && (
                <div className="rounded-lg border border-[#e5e5e5] p-3">
                  <h3 className="mb-1 text-xs font-bold uppercase text-[#525252]">İlan Açıklaması</h3>
                  <p className="text-xs text-[#525252] leading-relaxed whitespace-pre-line">
                    {ai?.description_tr || deal.description}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 border-t border-[#e5e5e5] p-4 bg-[#fafafa]">
          <button
            onClick={() => onAction("interested")}
            className="flex-1 rounded-lg bg-[#171717] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#2a2a2a]"
          >
            İlgileniyorum
          </button>
          <button
            onClick={() => onAction("contacted")}
            className="flex-1 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700"
          >
            Mesaj Attım
          </button>
          <button
            onClick={() => onAction("skipped")}
            className="rounded-lg border border-[#e5e5e5] px-4 py-2.5 text-sm font-medium text-[#525252] hover:bg-[#f5f5f5]"
          >
            Geç
          </button>
          {deal.klein_url && (
            <a
              href={deal.klein_url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-lg border border-[#e5e5e5] p-2.5 text-[#737373] hover:bg-[#f5f5f5] hover:text-[#171717]"
            >
              <ExternalLink size={18} />
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

export default function DealsPage() {
  const [deals, setDeals] = useState<Deal[]>([]);
  const [loading, setLoading] = useState(true);
  const [hunting, setHunting] = useState(false);
  const [filter, setFilter] = useState<string>("all");
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);

  const fetchDeals = useCallback(async () => {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) { setLoading(false); return; }

    let query = supabase
      .from("marketplace_deals")
      .select("*,listing:marketplace_listings(title, price, location, url, thumbnail_url, platform)")
      .eq("user_id", user.id)
      .order("created_at", { ascending: false });

    if (filter !== "all") {
      query = query.eq("status", filter);
    }

    const { data } = await query;
    setDeals((data as unknown as Deal[]) ?? []);
    setLoading(false);
  }, [filter]);

  useEffect(() => { fetchDeals(); }, [fetchDeals]);

  const triggerHunt = async () => {
    setHunting(true);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) return;
      await fetch(`${process.env.NEXT_PUBLIC_API_URL}/marketplace/deals/hunt`, {
        method: "POST",
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      setTimeout(() => { fetchDeals(); setHunting(false); }, 5000);
    } catch {
      setHunting(false);
    }
  };

  const handleAction = async (dealId: string, status: string) => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;
    await fetch(`${process.env.NEXT_PUBLIC_API_URL}/marketplace/deals/${dealId}/action`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${session.access_token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ status }),
    });
    setSelectedDeal(null);
    fetchDeals();
  };

  const statuses = [
    { key: "all", label: "Tümü" },
    { key: "new", label: "Yeni" },
    { key: "interested", label: "İlgileniyor" },
    { key: "contacted", label: "Mesaj Atıldı" },
    { key: "bought", label: "Alındı" },
    { key: "skipped", label: "Atlandı" },
  ];

  if (loading) {
    return <div className="flex h-64 items-center justify-center text-sm text-[#737373]">Yükleniyor...</div>;
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[#171717]">Fırsat Avcısı</h1>
          <p className="text-xs text-[#a3a3a3]">iPhone 14 & 14 Pro — Kleinanzeigen</p>
        </div>
        <button
          onClick={triggerHunt}
          disabled={hunting}
          className="flex items-center gap-1.5 rounded-lg bg-[#171717] px-3 py-2 text-xs font-medium text-white hover:bg-[#2a2a2a] disabled:opacity-50"
        >
          <RefreshCw size={14} className={hunting ? "animate-spin" : ""} />
          {hunting ? "Taranıyor..." : "Şimdi Tara"}
        </button>
      </div>

      <div className="flex gap-2 flex-wrap">
        {statuses.map((s) => (
          <button
            key={s.key}
            onClick={() => setFilter(s.key)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              filter === s.key
                ? "bg-[#171717] text-white"
                : "bg-[#f5f5f5] text-[#525252] hover:bg-[#e5e5e5]"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {deals.length === 0 ? (
        <div className="rounded-lg border border-dashed border-[#d4d4d4] bg-[#fafafa] p-8 text-center">
          <Tag size={32} className="mx-auto mb-3 text-[#d4d4d4]" />
          <p className="text-sm text-[#737373]">Henüz fırsat bulunamadı.</p>
          <p className="mt-1 text-xs text-[#a3a3a3]">
            Her 10 dakikada Kleinanzeigen taranıyor. &ldquo;Şimdi Tara&rdquo; ile manuel başlat.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {deals.map((deal) => (
            <DealCard key={deal.id} deal={deal} onClick={() => setSelectedDeal(deal)} />
          ))}
        </div>
      )}

      {selectedDeal && (
        <DealModal
          deal={selectedDeal}
          onClose={() => setSelectedDeal(null)}
          onAction={(status) => handleAction(selectedDeal.id, status)}
        />
      )}
    </div>
  );
}
