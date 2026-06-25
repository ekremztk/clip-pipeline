"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { supabase } from "@/lib/supabase";
import { Box, Plus, X, ImagePlus, Trash2, ChevronLeft, ChevronRight, Tag, Clock } from "lucide-react";

const CATEGORIES = [
  { value: "electronics", label: "Elektronik" },
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

type Product = {
  id: string;
  product_name: string;
  buy_price: number;
  asking_price: number | null;
  platform: string | null;
  sell_platform: string | null;
  status: string;
  condition: string | null;
  category: string | null;
  notes: string | null;
  listed_at: string | null;
  images: string[];
};

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploadProgress, setUploadProgress] = useState("");
  const [error, setError] = useState("");
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);

  const [productName, setProductName] = useState("");
  const [buyPrice, setBuyPrice] = useState("");
  const [askingPrice, setAskingPrice] = useState("");
  const [category, setCategory] = useState("electronics");
  const [condition, setCondition] = useState("like_new");
  const [sellPlatform, setSellPlatform] = useState("kleinanzeigen");
  const [notes, setNotes] = useState("");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);

  async function fetchProducts() {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) { setLoading(false); return; }

    const { data } = await supabase
      .from("marketplace_purchases")
      .select("*")
      .eq("user_id", user.id)
      .in("status", ["bought", "listed"])
      .order("created_at", { ascending: false });

    setProducts((data ?? []).map(p => ({ ...p, images: p.images ?? [] })));
    setLoading(false);
  }

  useEffect(() => { fetchProducts(); }, []);

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    const allowed = files.slice(0, 10 - selectedFiles.length);
    if (selectedFiles.length + files.length > 10) {
      setError("Maksimum 10 fotoğraf ekleyebilirsin.");
    }
    setSelectedFiles(prev => [...prev, ...allowed]);
    setPreviews(prev => [...prev, ...allowed.map(f => URL.createObjectURL(f))]);
    e.target.value = "";
  }

  function removeFile(index: number) {
    URL.revokeObjectURL(previews[index]);
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
    setPreviews(prev => prev.filter((_, i) => i !== index));
  }

  async function uploadFiles(): Promise<string[]> {
    const urls: string[] = [];
    for (let i = 0; i < selectedFiles.length; i++) {
      const file = selectedFiles[i];
      setUploadProgress(`Fotoğraf yükleniyor ${i + 1}/${selectedFiles.length}...`);
      const res = await fetch("/api/media", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: file.name, content_type: file.type }),
      });
      if (!res.ok) throw new Error(`Upload URL alınamadı: ${res.statusText}`);
      const { upload_url, public_url } = await res.json();
      const putRes = await fetch(upload_url, { method: "PUT", headers: { "Content-Type": file.type }, body: file });
      if (!putRes.ok) throw new Error(`Fotoğraf yüklenemedi: ${putRes.statusText}`);
      urls.push(public_url);
    }
    setUploadProgress("");
    return urls;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) { setError("Giriş yapman gerekiyor."); setSaving(false); return; }

    try {
      const imageUrls = selectedFiles.length > 0 ? await uploadFiles() : [];
      const { error: insertError } = await supabase.from("marketplace_purchases").insert({
        user_id: user.id,
        product_name: productName,
        buy_price: Number(buyPrice) || 0,
        asking_price: askingPrice ? Number(askingPrice) : null,
        category, condition,
        sell_platform: sellPlatform,
        status: "listed",
        listed_at: new Date().toISOString(),
        notes: notes || null,
        images: imageUrls,
      });
      if (insertError) { setError(`Kayıt hatası: ${insertError.message}`); setSaving(false); return; }

      setProductName(""); setBuyPrice(""); setAskingPrice("");
      setCategory("electronics"); setCondition("like_new");
      setSellPlatform("kleinanzeigen"); setNotes("");
      previews.forEach(p => URL.revokeObjectURL(p));
      setSelectedFiles([]); setPreviews([]);
      setShowForm(false); setSaving(false);
      fetchProducts();
    } catch (err: any) {
      setError(err.message ?? "Upload hatası"); setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    await supabase.from("marketplace_purchases").delete().eq("id", id);
    setProducts(products.filter(p => p.id !== id));
    setSelectedProduct(null);
  }

  if (loading) {
    return <div className="flex h-64 items-center justify-center text-sm text-[#737373]">Loading...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[#171717]">Ürünler</h1>
          <p className="text-xs text-[#a3a3a3]">{products.length} aktif ürün</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="inline-flex items-center gap-1.5 rounded-lg bg-[#171717] px-3.5 py-2 text-sm font-medium text-white hover:bg-[#333]"
        >
          <Plus size={16} />
          Ürün Ekle
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="rounded-xl border border-[#e5e5e5] bg-white p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-[#171717]">Yeni Ürün</h2>
            <button type="button" onClick={() => setShowForm(false)} className="text-[#737373] hover:text-[#171717]">
              <X size={18} />
            </button>
          </div>

          <div>
            <label className="mb-2 block text-xs font-medium text-[#525252]">
              Fotoğraflar <span className="text-[#a3a3a3]">({selectedFiles.length}/10)</span>
            </label>
            <div className="flex flex-wrap gap-2">
              {previews.map((src, i) => (
                <div key={i} className="group relative h-16 w-16 overflow-hidden rounded-lg border border-[#e5e5e5]">
                  <img src={src} alt="" className="h-full w-full object-cover" />
                  <button type="button" onClick={() => removeFile(i)} className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 transition-opacity group-hover:opacity-100">
                    <X size={14} className="text-white" />
                  </button>
                </div>
              ))}
              {selectedFiles.length < 10 && (
                <label className="flex h-16 w-16 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-[#d4d4d4] hover:border-[#a3a3a3] transition-colors">
                  <ImagePlus size={16} className="text-[#a3a3a3]" />
                  <input type="file" accept="image/*" multiple onChange={handleFileSelect} className="hidden" />
                </label>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="sm:col-span-2 lg:col-span-3">
              <label className="mb-1 block text-xs font-medium text-[#525252]">Ürün Adı</label>
              <input type="text" value={productName} onChange={(e) => setProductName(e.target.value)} placeholder="Crucial P310 1TB SSD + UGREEN Enclosure" className="w-full rounded-md border border-[#e5e5e5] px-3 py-2 text-sm focus:border-[#171717] focus:outline-none" required />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-[#525252]">Alış Fiyatı (€)</label>
              <input type="number" value={buyPrice} onChange={(e) => setBuyPrice(e.target.value)} placeholder="144" className="w-full rounded-md border border-[#e5e5e5] px-3 py-2 text-sm focus:border-[#171717] focus:outline-none" required />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-[#525252]">Satış Fiyatı (€)</label>
              <input type="number" value={askingPrice} onChange={(e) => setAskingPrice(e.target.value)} placeholder="125" className="w-full rounded-md border border-[#e5e5e5] px-3 py-2 text-sm focus:border-[#171717] focus:outline-none" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-[#525252]">Kategori</label>
              <select value={category} onChange={(e) => setCategory(e.target.value)} className="w-full rounded-md border border-[#e5e5e5] bg-white px-3 py-2 text-sm focus:border-[#171717] focus:outline-none">
                {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-[#525252]">Durum</label>
              <select value={condition} onChange={(e) => setCondition(e.target.value)} className="w-full rounded-md border border-[#e5e5e5] bg-white px-3 py-2 text-sm focus:border-[#171717] focus:outline-none">
                <option value="new">Sıfır</option>
                <option value="like_new">Sıfır Gibi</option>
                <option value="good">İyi</option>
                <option value="fair">Orta</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-[#525252]">Platform</label>
              <select value={sellPlatform} onChange={(e) => setSellPlatform(e.target.value)} className="w-full rounded-md border border-[#e5e5e5] bg-white px-3 py-2 text-sm focus:border-[#171717] focus:outline-none">
                <option value="kleinanzeigen">Kleinanzeigen</option>
                <option value="ebay">eBay</option>
                <option value="other">Diğer</option>
              </select>
            </div>
            <div className="sm:col-span-2 lg:col-span-3">
              <label className="mb-1 block text-xs font-medium text-[#525252]">Notlar</label>
              <input type="text" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Kullanım detayları, kutu durumu vb." className="w-full rounded-md border border-[#e5e5e5] px-3 py-2 text-sm focus:border-[#171717] focus:outline-none" />
            </div>
          </div>

          {error && <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">{error}</div>}
          {uploadProgress && <div className="rounded-md bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-700">{uploadProgress}</div>}

          <div className="flex justify-end">
            <button type="submit" disabled={saving} className="rounded-lg bg-[#171717] px-4 py-2 text-sm font-medium text-white hover:bg-[#333] disabled:opacity-50">
              {saving ? "Kaydediliyor..." : "Kaydet"}
            </button>
          </div>
        </form>
      )}

      {products.length === 0 && !showForm ? (
        <div className="rounded-xl border border-dashed border-[#d4d4d4] bg-[#fafafa] p-8 text-center">
          <Box size={32} className="mx-auto mb-3 text-[#d4d4d4]" />
          <p className="text-sm text-[#737373]">Henüz ürün eklenmedi.</p>
          <p className="mt-1 text-xs text-[#a3a3a3]">Satılık ürünlerini ekle, fotoğrafları yükle.</p>
        </div>
      ) : products.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {products.map((p) => (
            <ProductCard key={p.id} product={p} onClick={() => setSelectedProduct(p)} />
          ))}
        </div>
      )}

      {selectedProduct && (
        <ProductModal
          product={selectedProduct}
          onClose={() => setSelectedProduct(null)}
          onDelete={handleDelete}
        />
      )}
    </div>
  );
}

function ProductCard({ product, onClick }: { product: Product; onClick: () => void }) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const hasImages = product.images.length > 0;

  const startSlide = useCallback(() => {
    if (product.images.length <= 1) return;
    intervalRef.current = setInterval(() => {
      setCurrentIndex(prev => (prev + 1) % product.images.length);
    }, 1500);
  }, [product.images.length]);

  const stopSlide = useCallback(() => {
    if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
    setCurrentIndex(0);
  }, []);

  useEffect(() => { return () => { if (intervalRef.current) clearInterval(intervalRef.current); }; }, []);

  return (
    <div
      className="cursor-pointer overflow-hidden rounded-xl border border-[#e5e5e5] bg-white transition-all hover:shadow-lg hover:border-[#d4d4d4]"
      onClick={onClick}
      onMouseEnter={startSlide}
      onMouseLeave={stopSlide}
    >
      <div className="relative aspect-square overflow-hidden bg-[#fafafa]">
        {hasImages ? (
          <>
            <div className="flex h-full transition-transform duration-300 ease-in-out" style={{ transform: `translateX(-${currentIndex * 100}%)` }}>
              {product.images.map((url, i) => (
                <img key={i} src={url} alt={product.product_name} className="h-full w-full flex-shrink-0 object-cover" />
              ))}
            </div>
            {product.images.length > 1 && (
              <div className="absolute bottom-1.5 left-1/2 flex -translate-x-1/2 gap-1">
                {product.images.map((_, i) => (
                  <div key={i} className={`h-1 w-1 rounded-full transition-colors ${i === currentIndex ? "bg-white" : "bg-white/50"}`} />
                ))}
              </div>
            )}
          </>
        ) : (
          <div className="flex h-full items-center justify-center">
            <Box size={24} className="text-[#e5e5e5]" />
          </div>
        )}
        <div className="absolute top-1.5 right-1.5">
          <span className={`rounded-full px-1.5 py-0.5 text-[9px] font-medium backdrop-blur-sm ${
            product.status === "listed" ? "bg-green-500/90 text-white" : "bg-yellow-500/90 text-white"
          }`}>
            {product.status === "listed" ? "Satışta" : "Beklemede"}
          </span>
        </div>
      </div>
      <div className="p-2.5">
        <p className="text-xs font-medium text-[#171717] truncate">{product.product_name}</p>
        <div className="mt-1 flex items-center justify-between">
          <span className="text-sm font-bold text-[#171717]">{product.asking_price ?? product.buy_price}€</span>
          {product.sell_platform && (
            <span className="text-[9px] text-[#a3a3a3] uppercase">{product.sell_platform}</span>
          )}
        </div>
      </div>
    </div>
  );
}

function ProductModal({ product, onClose, onDelete }: { product: Product; onClose: () => void; onDelete: (id: string) => void }) {
  const [imgIndex, setImgIndex] = useState(0);
  const hasImages = product.images.length > 0;

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft" && imgIndex > 0) setImgIndex(imgIndex - 1);
      if (e.key === "ArrowRight" && imgIndex < product.images.length - 1) setImgIndex(imgIndex + 1);
    }
    window.addEventListener("keydown", handleKey);
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", handleKey); document.body.style.overflow = ""; };
  }, [imgIndex, product.images.length, onClose]);

  const conditionLabels: Record<string, string> = { new: "Sıfır", like_new: "Sıfır Gibi", good: "İyi", fair: "Orta" };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4" onClick={onClose}>
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative z-10 w-full max-w-2xl overflow-hidden rounded-2xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#f0f0f0] px-6 py-4">
          <h2 className="text-base font-semibold text-[#171717]">{product.product_name}</h2>
          <button onClick={onClose} className="rounded-full p-1 hover:bg-[#f5f5f5] transition-colors">
            <X size={20} className="text-[#737373]" />
          </button>
        </div>

        <div className="flex flex-col sm:flex-row">
          {/* Image Gallery */}
          <div className="relative aspect-square w-full sm:w-1/2 bg-[#fafafa]">
            {hasImages ? (
              <>
                <img
                  src={product.images[imgIndex]}
                  alt={product.product_name}
                  className="h-full w-full object-contain p-4"
                />
                {product.images.length > 1 && (
                  <>
                    {imgIndex > 0 && (
                      <button onClick={() => setImgIndex(imgIndex - 1)} className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-white/90 p-1.5 shadow-md hover:bg-white transition-colors">
                        <ChevronLeft size={16} className="text-[#171717]" />
                      </button>
                    )}
                    {imgIndex < product.images.length - 1 && (
                      <button onClick={() => setImgIndex(imgIndex + 1)} className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-white/90 p-1.5 shadow-md hover:bg-white transition-colors">
                        <ChevronRight size={16} className="text-[#171717]" />
                      </button>
                    )}
                    <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 gap-1.5">
                      {product.images.map((_, i) => (
                        <button key={i} onClick={() => setImgIndex(i)} className={`h-2 w-2 rounded-full transition-all ${i === imgIndex ? "bg-[#171717] scale-125" : "bg-[#d4d4d4]"}`} />
                      ))}
                    </div>
                  </>
                )}
              </>
            ) : (
              <div className="flex h-full items-center justify-center">
                <Box size={48} className="text-[#e5e5e5]" />
              </div>
            )}
          </div>

          {/* Details */}
          <div className="flex-1 p-6 space-y-4">
            <div className="flex items-center gap-2">
              <span className="text-2xl font-bold text-[#171717]">{product.asking_price ?? "—"}€</span>
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                product.status === "listed" ? "bg-green-50 text-green-700" : "bg-yellow-50 text-yellow-700"
              }`}>
                {product.status === "listed" ? "Satışta" : "Beklemede"}
              </span>
            </div>

            <div className="space-y-2.5">
              <DetailRow label="Alış Fiyatı" value={`${product.buy_price}€`} />
              {product.asking_price && product.buy_price > 0 && (
                <DetailRow label="Potansiyel Kar" value={`${product.asking_price - product.buy_price}€`} valueColor={product.asking_price >= product.buy_price ? "green" : "red"} />
              )}
              {product.condition && <DetailRow label="Durum" value={conditionLabels[product.condition] ?? product.condition} />}
              {product.category && <DetailRow label="Kategori" value={CATEGORIES.find(c => c.value === product.category)?.label ?? product.category} />}
              {product.sell_platform && <DetailRow label="Platform" value={product.sell_platform.charAt(0).toUpperCase() + product.sell_platform.slice(1)} />}
              {product.listed_at && <DetailRow label="İlan Tarihi" value={new Date(product.listed_at).toLocaleDateString("tr-TR")} />}
            </div>

            {product.notes && (
              <div className="rounded-lg bg-[#fafafa] p-3">
                <p className="text-[10px] font-medium text-[#a3a3a3] uppercase mb-1">Notlar</p>
                <p className="text-xs text-[#525252]">{product.notes}</p>
              </div>
            )}

            <div className="pt-2 border-t border-[#f0f0f0]">
              <button
                onClick={() => onDelete(product.id)}
                className="inline-flex items-center gap-1.5 text-xs text-red-500 hover:text-red-700 transition-colors"
              >
                <Trash2 size={12} />
                Ürünü Sil
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function DetailRow({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  const color = valueColor === "green" ? "text-green-600" : valueColor === "red" ? "text-red-600" : "text-[#171717]";
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-[#a3a3a3]">{label}</span>
      <span className={`text-xs font-medium ${color}`}>{value}</span>
    </div>
  );
}
