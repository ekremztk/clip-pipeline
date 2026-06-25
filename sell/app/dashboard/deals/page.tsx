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
} from "lucide-react";

type SellerAnalysis = {
  effort_level: string;
  urgency: string;
  trust_score: number;
  reasoning: string;
};

type AiAnalysis = {
  condition_notes: string;
  has_box: boolean | null;
  has_charger: boolean | null;
  has_receipt: boolean | null;
  flags: string[];
  price_assessment: {
    is_underpriced: boolean;
    why_cheap: string;
    risk_factors: string[];
  };
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

const TIER_COLORS: Record<string, string> = {
  A: "bg-emerald-100 text-emerald-700 border-emerald-200",
  B: "bg-blue-100 text-blue-700 border-blue-200",
  C: "bg-amber-100 text-amber-700 border-amber-200",
  D: "bg-orange-100 text-orange-700 border-orange-200",
  E: "bg-red-100 text-red-700 border-red-200",
};

const URGENCY_COLORS: Record<string, string> = {
  high: "text-red-600",
  medium: "text-amber-600",
  low: "text-blue-600",
  none: "text-gray-500",
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
  const mainImage = deal.images?.[0] ?? deal.listing?.thumbnail_url;

  return (
    <div
      onClick={onClick}
      className="group cursor-pointer rounded-xl border border-[#e5e5e5] bg-white transition-all hover:border-[#c5c5c5] hover:shadow-md"
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
        {tier && (
          <span
            className={`absolute left-2 top-2 rounded-md border px-2 py-0.5 text-[11px] font-bold ${TIER_COLORS[tier] || "bg-gray-100 text-gray-600 border-gray-200"}`}
          >
            Tier {tier}
          </span>
        )}
        {profit && profit > 0 && (
          <span className="absolute right-2 top-2 rounded-md bg-emerald-500 px-2 py-0.5 text-[11px] font-bold text-white">
            +{profit.toFixed(0)}€
          </span>
        )}
      </div>

      <div className="p-3">
        <div className="flex items-start justify-between gap-1">
          <p className="line-clamp-1 text-sm font-medium text-[#171717]">
            {deal.model_parsed || deal.listing?.title || "—"}
          </p>
          {deal.storage_parsed && (
            <span className="shrink-0 rounded bg-[#f0f0f0] px-1.5 py-0.5 text-[10px] font-medium text-[#525252]">
              {deal.storage_parsed}
            </span>
          )}
        </div>

        <div className="mt-2 flex items-center justify-between">
          <span className="text-lg font-bold text-[#171717]">{price}€</span>
          {deal.seller_analysis?.trust_score != null && (
            <div className="flex items-center gap-1">
              <Shield size={12} className="text-[#a3a3a3]" />
              <span className="text-[11px] text-[#737373]">{deal.seller_analysis.trust_score}/10</span>
            </div>
          )}
        </div>

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
        </div>

        {deal.seller_analysis?.urgency && deal.seller_analysis.urgency !== "none" && (
          <div className={`mt-2 text-[11px] font-medium ${URGENCY_COLORS[deal.seller_analysis.urgency]}`}>
            <Zap size={10} className="mr-0.5 inline" />
            {deal.seller_analysis.urgency === "high" ? "Acil satış!" : "Urgency sinyali"}
          </div>
        )}
      </div>
    </div>
  );
}

function DealModal({ deal, onClose, onAction }: { deal: Deal; onClose: () => void; onAction: (status: string) => void }) {
  const [imgIdx, setImgIdx] = useState(0);
  const images = deal.images?.length ? deal.images : deal.listing?.thumbnail_url ? [deal.listing.thumbnail_url] : [];
  const price = deal.buy_price ?? deal.listing?.price ?? 0;

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
    <div className="fixed inset-0 z-[100] flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
      <div
        className="relative mx-4 flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute right-3 top-3 z-10 rounded-full bg-white/90 p-1.5 shadow-sm hover:bg-white">
          <X size={18} />
        </button>

        <div className="flex-1 overflow-y-auto">
          {/* Images */}
          {images.length > 0 && (
            <div className="relative aspect-[16/10] bg-[#f5f5f5]">
              <img src={images[imgIdx]} alt="" className="h-full w-full object-contain" />
              {images.length > 1 && (
                <>
                  <button
                    onClick={() => setImgIdx((i) => Math.max(0, i - 1))}
                    className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-white/90 p-2 shadow-sm hover:bg-white disabled:opacity-30"
                    disabled={imgIdx === 0}
                  >
                    <ChevronLeft size={18} />
                  </button>
                  <button
                    onClick={() => setImgIdx((i) => Math.min(images.length - 1, i + 1))}
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-white/90 p-2 shadow-sm hover:bg-white disabled:opacity-30"
                    disabled={imgIdx === images.length - 1}
                  >
                    <ChevronRight size={18} />
                  </button>
                  <div className="absolute bottom-2 left-1/2 flex -translate-x-1/2 gap-1.5">
                    {images.map((_, i) => (
                      <button
                        key={i}
                        onClick={() => setImgIdx(i)}
                        className={`h-1.5 rounded-full transition-all ${i === imgIdx ? "w-4 bg-[#171717]" : "w-1.5 bg-[#171717]/30"}`}
                      />
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          <div className="space-y-5 p-5">
            {/* Header */}
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-xl font-bold text-[#171717]">{deal.model_parsed || deal.listing?.title}</h2>
                <div className="mt-1 flex items-center gap-2 text-sm text-[#737373]">
                  {deal.storage_parsed && <span>{deal.storage_parsed}</span>}
                  {deal.tier && (
                    <span className={`rounded border px-1.5 py-0.5 text-[11px] font-bold ${TIER_COLORS[deal.tier]}`}>
                      Tier {deal.tier}
                    </span>
                  )}
                  {deal.battery_pct && (
                    <span className="flex items-center gap-0.5">
                      <Battery size={12} />
                      {deal.battery_pct}%
                    </span>
                  )}
                </div>
              </div>
              <div className="text-right">
                <p className="text-2xl font-bold text-[#171717]">{price}€</p>
                {deal.estimated_profit && deal.estimated_profit > 0 && (
                  <p className="text-sm font-medium text-emerald-600">+{deal.estimated_profit.toFixed(0)}€ kar</p>
                )}
              </div>
            </div>

            {/* Price Comparison */}
            {(deal.estimated_min_sell || deal.estimated_realistic_sell || deal.estimated_max_sell) && (
              <div className="rounded-lg border border-[#e5e5e5] bg-[#fafafa] p-4">
                <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-[#737373]">
                  <TrendingUp size={14} />
                  eBay Satış Tahmini
                </h3>
                <div className="grid grid-cols-3 gap-3">
                  <div className="text-center">
                    <p className="text-xs text-[#a3a3a3]">Minimum</p>
                    <p className="text-lg font-bold text-[#525252]">{deal.estimated_min_sell ?? "—"}€</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-[#a3a3a3]">Gerçekçi</p>
                    <p className="text-lg font-bold text-emerald-600">{deal.estimated_realistic_sell ?? "—"}€</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-[#a3a3a3]">Optimistik</p>
                    <p className="text-lg font-bold text-[#525252]">{deal.estimated_max_sell ?? "—"}€</p>
                  </div>
                </div>
                {deal.estimated_realistic_sell && price > 0 && (
                  <div className="mt-3 rounded-md bg-emerald-50 px-3 py-2 text-center text-sm font-medium text-emerald-700">
                    Tahmini Kar: {(deal.estimated_realistic_sell - price).toFixed(0)}€ ({((deal.estimated_realistic_sell - price) / price * 100).toFixed(0)}% marj)
                  </div>
                )}
              </div>
            )}

            {/* Seller Psychology */}
            {deal.seller_analysis && (
              <div className="rounded-lg border border-[#e5e5e5] bg-[#fafafa] p-4">
                <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-[#737373]">
                  <User size={14} />
                  Satıcı Analizi
                </h3>
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div>
                    <p className="text-[11px] text-[#a3a3a3]">Emek</p>
                    <p className="text-sm font-medium capitalize">{deal.seller_analysis.effort_level}</p>
                  </div>
                  <div>
                    <p className="text-[11px] text-[#a3a3a3]">Aciliyet</p>
                    <p className={`text-sm font-medium capitalize ${URGENCY_COLORS[deal.seller_analysis.urgency] || ""}`}>
                      {deal.seller_analysis.urgency}
                    </p>
                  </div>
                  <div>
                    <p className="text-[11px] text-[#a3a3a3]">Güven</p>
                    <p className="text-sm font-medium">{deal.seller_analysis.trust_score}/10</p>
                  </div>
                </div>
                {deal.seller_analysis.reasoning && (
                  <p className="mt-3 text-xs text-[#525252] italic">&ldquo;{deal.seller_analysis.reasoning}&rdquo;</p>
                )}
              </div>
            )}

            {/* AI Condition Notes */}
            {deal.ai_analysis?.condition_notes && (
              <div className="rounded-lg border border-[#e5e5e5] bg-[#fafafa] p-4">
                <h3 className="mb-2 text-xs font-semibold uppercase text-[#737373]">Durum Notu</h3>
                <p className="text-sm text-[#525252]">{deal.ai_analysis.condition_notes}</p>
                {deal.ai_analysis.flags?.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {deal.ai_analysis.flags.map((flag) => (
                      <span key={flag} className="rounded bg-[#e5e5e5] px-2 py-0.5 text-[10px] text-[#525252]">
                        {flag.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Risk Factors */}
            {deal.ai_analysis?.price_assessment?.risk_factors && deal.ai_analysis.price_assessment.risk_factors.length > 0 && (
              <div className="rounded-lg border border-red-100 bg-red-50/50 p-4">
                <h3 className="mb-2 text-xs font-semibold uppercase text-red-600">Risk Faktörleri</h3>
                <ul className="space-y-1">
                  {deal.ai_analysis.price_assessment.risk_factors.map((risk, i) => (
                    <li key={i} className="text-xs text-red-700">• {risk}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Description */}
            {deal.description && (
              <div>
                <h3 className="mb-1 text-xs font-semibold uppercase text-[#737373]">İlan Açıklaması</h3>
                <p className="text-xs text-[#525252] leading-relaxed">{deal.description}</p>
              </div>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 border-t border-[#e5e5e5] p-4">
          <button
            onClick={() => onAction("interested")}
            className="flex-1 rounded-lg bg-[#171717] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#2a2a2a]"
          >
            İlgileniyorum
          </button>
          <button
            onClick={() => onAction("skipped")}
            className="flex-1 rounded-lg border border-[#e5e5e5] px-4 py-2.5 text-sm font-medium text-[#525252] hover:bg-[#f5f5f5]"
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
      setTimeout(() => { fetchDeals(); setHunting(false); }, 3000);
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
    { key: "interested", label: "İlgileniyorum" },
    { key: "contacted", label: "İletişim" },
    { key: "bought", label: "Alındı" },
    { key: "skipped", label: "Atlandı" },
  ];

  if (loading) {
    return <div className="flex h-64 items-center justify-center text-sm text-[#737373]">Loading...</div>;
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-[#171717]">Fırsat Ürünler</h1>
        <button
          onClick={triggerHunt}
          disabled={hunting}
          className="flex items-center gap-1.5 rounded-lg bg-[#171717] px-3 py-2 text-xs font-medium text-white hover:bg-[#2a2a2a] disabled:opacity-50"
        >
          <RefreshCw size={14} className={hunting ? "animate-spin" : ""} />
          {hunting ? "Taranıyor..." : "Şimdi Tara"}
        </button>
      </div>

      <div className="flex gap-2">
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
          <p className="text-sm text-[#737373]">Henüz fırsat ürün bulunamadı.</p>
          <p className="mt-1 text-xs text-[#a3a3a3]">
            Her 10 dakikada Kleinanzeigen taranıyor. &ldquo;Şimdi Tara&rdquo; ile manuel başlatabilirsin.
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
