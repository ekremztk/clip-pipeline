"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { ShoppingCart, Plus, X, Check } from "lucide-react";

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

type Purchase = {
  id: string;
  product_name: string;
  buy_price: number;
  platform: string | null;
  status: string;
  bought_at: string | null;
  notes: string | null;
  category: string | null;
  condition: string | null;
  asking_price: number | null;
  created_at: string;
};

export default function PurchasesPage() {
  const [purchases, setPurchases] = useState<Purchase[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"bought" | "planned">("bought");
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [productName, setProductName] = useState("");
  const [buyPrice, setBuyPrice] = useState("");
  const [askingPrice, setAskingPrice] = useState("");
  const [platform, setPlatform] = useState("kleinanzeigen");
  const [category, setCategory] = useState("telefon");
  const [condition, setCondition] = useState("gut");
  const [notes, setNotes] = useState("");
  const [formStatus, setFormStatus] = useState<"bought" | "planned">("bought");

  async function fetchPurchases() {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) { setLoading(false); return; }

    const { data } = await supabase
      .from("marketplace_purchases")
      .select("*")
      .eq("user_id", user.id)
      .order("created_at", { ascending: false });

    setPurchases(data ?? []);
    setLoading(false);
  }

  useEffect(() => { fetchPurchases(); }, []);

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

    const { error: insertError } = await supabase.from("marketplace_purchases").insert({
      user_id: user.id,
      product_name: productName,
      buy_price: Number(buyPrice),
      asking_price: askingPrice ? Number(askingPrice) : null,
      platform,
      category,
      condition,
      notes: notes || null,
      status: formStatus,
      bought_at: formStatus === "bought" ? new Date().toISOString() : null,
    });

    if (insertError) {
      setError(`Kayıt hatası: ${insertError.message}`);
      setSaving(false);
      return;
    }

    setProductName(""); setBuyPrice(""); setAskingPrice("");
    setNotes(""); setPlatform("kleinanzeigen");
    setCategory("telefon"); setCondition("gut");
    setShowForm(false);
    setSaving(false);
    fetchPurchases();
  }

  async function markAsSold(purchase: Purchase) {
    const sellPrice = prompt("Satış fiyatı (€):");
    if (!sellPrice) return;

    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return;

    const sell = Number(sellPrice);
    const boughtDate = purchase.bought_at ? new Date(purchase.bought_at) : new Date(purchase.created_at);
    const daysToSell = Math.ceil((Date.now() - boughtDate.getTime()) / (1000 * 60 * 60 * 24));

    await supabase.from("marketplace_sales").insert({
      user_id: user.id,
      product_name: purchase.product_name,
      buy_price: purchase.buy_price,
      sell_price: sell,
      days_to_sell: daysToSell,
      sold_at: new Date().toISOString(),
      category: purchase.category,
    });

    await supabase.from("marketplace_purchases").update({ status: "sold" }).eq("id", purchase.id);
    fetchPurchases();
  }

  async function markAsListed(id: string) {
    await supabase.from("marketplace_purchases").update({
      status: "listed",
      listed_at: new Date().toISOString(),
    }).eq("id", id);
    fetchPurchases();
  }

  async function deletePurchase(id: string) {
    await supabase.from("marketplace_purchases").delete().eq("id", id);
    setPurchases(purchases.filter(p => p.id !== id));
  }

  const filteredPurchases = purchases.filter((p) =>
    tab === "bought"
      ? p.status === "bought" || p.status === "listed" || p.status === "sold"
      : p.status === "planned"
  );

  if (loading) {
    return <div className="flex h-64 items-center justify-center text-sm text-[#737373]">Loading...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-[#171717]">Alımlar</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="inline-flex items-center gap-1.5 rounded-lg bg-[#171717] px-3.5 py-2 text-sm font-medium text-white hover:bg-[#333]"
        >
          <Plus size={16} />
          Alım Ekle
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="rounded-lg border border-[#e5e5e5] bg-white p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-[#171717]">Yeni Alım</h2>
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
                placeholder="iPhone 14 128GB Schwarz"
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
                value={platform}
                onChange={(e) => setPlatform(e.target.value)}
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
              <label className="mb-1 block text-xs font-medium text-[#525252]">İlan Fiyatı (€, opsiyonel)</label>
              <input
                type="number"
                value={askingPrice}
                onChange={(e) => setAskingPrice(e.target.value)}
                placeholder="200"
                className="w-full rounded-md border border-[#e5e5e5] px-3 py-2 text-sm focus:border-[#171717] focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-[#525252]">Durum</label>
              <select
                value={condition}
                onChange={(e) => setCondition(e.target.value)}
                className="w-full rounded-md border border-[#e5e5e5] bg-white px-3 py-2 text-sm focus:border-[#171717] focus:outline-none"
              >
                <option value="neuwertig">Sıfır Gibi</option>
                <option value="gut">İyi</option>
                <option value="akzeptabel">Orta</option>
                <option value="defekt">Hasarlı</option>
              </select>
            </div>
            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs font-medium text-[#525252]">Not (opsiyonel)</label>
              <input
                type="text"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Pil %92, çizik yok, faturalı..."
                className="w-full rounded-md border border-[#e5e5e5] px-3 py-2 text-sm focus:border-[#171717] focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-[#525252]">Durum</label>
              <select
                value={formStatus}
                onChange={(e) => setFormStatus(e.target.value as "bought" | "planned")}
                className="w-full rounded-md border border-[#e5e5e5] bg-white px-3 py-2 text-sm focus:border-[#171717] focus:outline-none"
              >
                <option value="bought">Aldım</option>
                <option value="planned">Almayı Planlıyorum</option>
              </select>
            </div>
          </div>

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

      <div className="flex gap-2 border-b border-[#e5e5e5] pb-px">
        <button
          onClick={() => setTab("bought")}
          className={`border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
            tab === "bought" ? "border-[#171717] text-[#171717]" : "border-transparent text-[#737373] hover:text-[#171717]"
          }`}
        >
          Aldıklarım
        </button>
        <button
          onClick={() => setTab("planned")}
          className={`border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
            tab === "planned" ? "border-[#171717] text-[#171717]" : "border-transparent text-[#737373] hover:text-[#171717]"
          }`}
        >
          Almayı Planladıklarım
        </button>
      </div>

      {filteredPurchases.length === 0 ? (
        <div className="rounded-lg border border-dashed border-[#d4d4d4] bg-[#fafafa] p-8 text-center">
          <ShoppingCart size={32} className="mx-auto mb-3 text-[#d4d4d4]" />
          <p className="text-sm text-[#737373]">
            {tab === "bought" ? "Henüz alım kaydı yok." : "Planlanan alım yok."}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredPurchases.map((p) => (
            <div key={p.id} className="flex items-center justify-between rounded-lg border border-[#e5e5e5] bg-white p-4">
              <div>
                <p className="text-sm font-medium text-[#171717]">{p.product_name}</p>
                <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-[#737373]">
                  {p.platform && <span className="rounded bg-[#f5f5f5] px-1.5 py-0.5">{p.platform}</span>}
                  {p.category && <span>{CATEGORIES.find(c => c.value === p.category)?.label}</span>}
                  {p.bought_at && <span>{new Date(p.bought_at).toLocaleDateString("de-DE")}</span>}
                  {p.notes && <span className="truncate max-w-[250px]">{p.notes}</span>}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <p className="text-sm font-semibold text-[#171717]">{p.buy_price}€</p>
                  <span className={`text-xs ${
                    p.status === "sold" ? "text-green-600" :
                    p.status === "listed" ? "text-blue-600" :
                    p.status === "bought" ? "text-orange-600" :
                    "text-[#737373]"
                  }`}>
                    {{"planned":"Planlandı","bought":"Alındı","listed":"Satışta","sold":"Satıldı"}[p.status] ?? p.status}
                  </span>
                </div>
                {p.status === "bought" && (
                  <div className="flex gap-1">
                    <button
                      onClick={() => markAsListed(p.id)}
                      title="Satışa koy"
                      className="rounded-md border border-[#e5e5e5] p-1.5 text-blue-600 hover:bg-blue-50"
                    >
                      <ShoppingCart size={14} />
                    </button>
                    <button
                      onClick={() => markAsSold(p)}
                      title="Satıldı olarak işaretle"
                      className="rounded-md border border-[#e5e5e5] p-1.5 text-green-600 hover:bg-green-50"
                    >
                      <Check size={14} />
                    </button>
                  </div>
                )}
                {p.status === "listed" && (
                  <button
                    onClick={() => markAsSold(p)}
                    title="Satıldı olarak işaretle"
                    className="rounded-md border border-[#e5e5e5] p-1.5 text-green-600 hover:bg-green-50"
                  >
                    <Check size={14} />
                  </button>
                )}
                {(p.status === "planned" || p.status === "bought") && (
                  <button
                    onClick={() => deletePurchase(p.id)}
                    title="Sil"
                    className="rounded-md border border-[#e5e5e5] p-1.5 text-red-500 hover:bg-red-50"
                  >
                    <X size={14} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
