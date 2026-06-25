"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Package, Plus, X } from "lucide-react";

const CATEGORIES = [
  { value: "telefon", label: "Telefon" },
  { value: "bilgisayar", label: "Bilgisayar" },
  { value: "tablet", label: "Tablet" },
  { value: "kulaklik", label: "Kulaklık" },
  { value: "konsol", label: "Konsol & Oyun" },
  { value: "aksesuar", label: "Aksesuar" },
  { value: "kamera", label: "Kamera" },
  { value: "dijital", label: "Dijital Ürün" },
  { value: "diger", label: "Diğer" },
];

const PLATFORMS = [
  { value: "kleinanzeigen", label: "Kleinanzeigen" },
  { value: "ebay", label: "eBay" },
  { value: "facebook", label: "Facebook Marketplace" },
  { value: "vinted", label: "Vinted" },
  { value: "diger", label: "Diğer" },
];

type Sale = {
  id: string;
  product_name: string | null;
  buy_price: number;
  sell_price: number;
  fees: number;
  net_profit: number;
  sold_at: string | null;
  days_to_sell: number | null;
  category: string | null;
  sell_platform: string | null;
};

export default function SalesPage() {
  const [sales, setSales] = useState<Sale[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [productName, setProductName] = useState("");
  const [buyPrice, setBuyPrice] = useState("");
  const [sellPrice, setSellPrice] = useState("");
  const [fees, setFees] = useState("");
  const [category, setCategory] = useState("telefon");
  const [sellPlatform, setSellPlatform] = useState("kleinanzeigen");
  const [daysToSell, setDaysToSell] = useState("");

  async function fetchSales() {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) { setLoading(false); return; }

    const { data } = await supabase
      .from("marketplace_sales")
      .select("*")
      .eq("user_id", user.id)
      .order("sold_at", { ascending: false });

    setSales(data ?? []);
    setLoading(false);
  }

  useEffect(() => { fetchSales(); }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);

    setError("");
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) {
      setError("Giriş yapman gerekiyor. Önce login ol.");
      setSaving(false);
      return;
    }

    const buy = Number(buyPrice);
    const sell = Number(sellPrice);
    const fee = fees ? Number(fees) : 0;

    const { error: insertError } = await supabase.from("marketplace_sales").insert({
      user_id: user.id,
      product_name: productName,
      buy_price: buy,
      sell_price: sell,
      fees: fee,
      sold_at: new Date().toISOString(),
      days_to_sell: daysToSell ? Number(daysToSell) : null,
      category,
      sell_platform: sellPlatform,
    });

    if (insertError) {
      setError(`Kayıt hatası: ${insertError.message}`);
      setSaving(false);
      return;
    }

    setProductName(""); setBuyPrice(""); setSellPrice("");
    setFees(""); setDaysToSell("");
    setCategory("telefon"); setSellPlatform("kleinanzeigen");
    setShowForm(false);
    setSaving(false);
    fetchSales();
  }

  const totalProfit = sales.reduce((s, r) => s + Number(r.net_profit), 0);
  const totalRevenue = sales.reduce((s, r) => s + Number(r.sell_price), 0);

  if (loading) {
    return <div className="flex h-64 items-center justify-center text-sm text-[#737373]">Loading...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[#171717]">Satışlar</h1>
          {sales.length > 0 && (
            <p className="mt-0.5 text-sm text-[#737373]">
              {sales.length} satış · Ciro: {totalRevenue.toFixed(0)}€ · Kar: <span className={totalProfit >= 0 ? "text-green-600 font-medium" : "text-red-600 font-medium"}>{totalProfit >= 0 ? "+" : ""}{totalProfit.toFixed(0)}€</span>
            </p>
          )}
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="inline-flex items-center gap-1.5 rounded-lg bg-[#171717] px-3.5 py-2 text-sm font-medium text-white hover:bg-[#333]"
        >
          <Plus size={16} />
          Satış Ekle
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="rounded-lg border border-[#e5e5e5] bg-white p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-[#171717]">Yeni Satış</h2>
            <button type="button" onClick={() => setShowForm(false)} className="text-[#737373] hover:text-[#171717]">
              <X size={18} />
            </button>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-[#525252]">Ürün Adı</label>
              <input
                type="text"
                value={productName}
                onChange={(e) => setProductName(e.target.value)}
                placeholder="iPhone 14 128GB"
                className="w-full rounded-md border border-[#e5e5e5] px-3 py-2 text-sm focus:border-[#171717] focus:outline-none"
                required
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-[#525252]">Kategori</label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full rounded-md border border-[#e5e5e5] bg-white px-3 py-2 text-sm focus:border-[#171717] focus:outline-none"
              >
                {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-[#525252]">Platform</label>
              <select
                value={sellPlatform}
                onChange={(e) => setSellPlatform(e.target.value)}
                className="w-full rounded-md border border-[#e5e5e5] bg-white px-3 py-2 text-sm focus:border-[#171717] focus:outline-none"
              >
                {PLATFORMS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-[#525252]">Alış Fiyatı (€)</label>
              <input
                type="number"
                value={buyPrice}
                onChange={(e) => setBuyPrice(e.target.value)}
                placeholder="180"
                className="w-full rounded-md border border-[#e5e5e5] px-3 py-2 text-sm focus:border-[#171717] focus:outline-none"
                required
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-[#525252]">Satış Fiyatı (€)</label>
              <input
                type="number"
                value={sellPrice}
                onChange={(e) => setSellPrice(e.target.value)}
                placeholder="245"
                className="w-full rounded-md border border-[#e5e5e5] px-3 py-2 text-sm focus:border-[#171717] focus:outline-none"
                required
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-[#525252]">Masraflar (€, opsiyonel)</label>
              <input
                type="number"
                value={fees}
                onChange={(e) => setFees(e.target.value)}
                placeholder="0"
                className="w-full rounded-md border border-[#e5e5e5] px-3 py-2 text-sm focus:border-[#171717] focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-[#525252]">Satış Süresi (gün)</label>
              <input
                type="number"
                value={daysToSell}
                onChange={(e) => setDaysToSell(e.target.value)}
                placeholder="3"
                className="w-full rounded-md border border-[#e5e5e5] px-3 py-2 text-sm focus:border-[#171717] focus:outline-none"
              />
            </div>
          </div>

          {buyPrice && sellPrice && (
            <div className="rounded-md bg-[#f5f5f5] px-4 py-2.5 text-sm">
              Net Kar: <span className={Number(sellPrice) - Number(buyPrice) - (fees ? Number(fees) : 0) >= 0 ? "font-semibold text-green-600" : "font-semibold text-red-600"}>
                {(Number(sellPrice) - Number(buyPrice) - (fees ? Number(fees) : 0)).toFixed(0)}€
              </span>
              <span className="ml-2 text-[#737373]">
                ({Number(buyPrice) > 0 ? ((Number(sellPrice) - Number(buyPrice) - (fees ? Number(fees) : 0)) / Number(buyPrice) * 100).toFixed(0) : "100"}% marj)
              </span>
            </div>
          )}

          {error && (
            <div className="rounded-md bg-red-50 border border-red-200 px-4 py-2.5 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-[#171717] px-4 py-2 text-sm font-medium text-white hover:bg-[#333] disabled:opacity-50"
            >
              {saving ? "Kaydediliyor..." : "Kaydet"}
            </button>
          </div>
        </form>
      )}

      {sales.length === 0 && !showForm ? (
        <div className="rounded-lg border border-dashed border-[#d4d4d4] bg-[#fafafa] p-8 text-center">
          <Package size={32} className="mx-auto mb-3 text-[#d4d4d4]" />
          <p className="text-sm text-[#737373]">Henüz satış kaydı yok.</p>
          <p className="mt-1 text-xs text-[#a3a3a3]">Ürün sattığında yukarıdan kayıt ekle veya Alımlar'dan "Satıldı" olarak işaretle.</p>
        </div>
      ) : sales.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-[#e5e5e5] text-xs text-[#737373]">
                <th className="pb-3 font-medium">Ürün</th>
                <th className="pb-3 font-medium">Alış</th>
                <th className="pb-3 font-medium">Satış</th>
                <th className="pb-3 font-medium">Net Kar</th>
                <th className="pb-3 font-medium">Gün</th>
                <th className="pb-3 font-medium">Platform</th>
                <th className="pb-3 font-medium">Tarih</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f5f5f5]">
              {sales.map((s) => (
                <tr key={s.id} className="hover:bg-[#fafafa]">
                  <td className="py-3 font-medium text-[#171717]">{s.product_name ?? "—"}</td>
                  <td className="py-3 text-[#737373]">{Number(s.buy_price).toFixed(0)}€</td>
                  <td className="py-3 text-[#737373]">{Number(s.sell_price).toFixed(0)}€</td>
                  <td className={`py-3 font-medium ${Number(s.net_profit) >= 0 ? "text-green-600" : "text-red-600"}`}>
                    {Number(s.net_profit) >= 0 ? "+" : ""}{Number(s.net_profit).toFixed(0)}€
                  </td>
                  <td className="py-3 text-[#737373]">{s.days_to_sell ?? "—"}</td>
                  <td className="py-3 text-[#737373]">
                    {PLATFORMS.find(p => p.value === s.sell_platform)?.label ?? s.sell_platform ?? "—"}
                  </td>
                  <td className="py-3 text-[#737373]">
                    {s.sold_at ? new Date(s.sold_at).toLocaleDateString("de-DE") : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
