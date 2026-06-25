"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Receipt, Plus, X } from "lucide-react";

const EXPENSE_CATEGORIES = [
  { value: "kargo", label: "Kargo" },
  { value: "benzin", label: "Benzin / Yol" },
  { value: "paketleme", label: "Paketleme" },
  { value: "tamir", label: "Tamir / Bakım" },
  { value: "reklam", label: "Reklam" },
  { value: "arac", label: "Araç / Gereç" },
  { value: "abonelik", label: "Abonelik" },
  { value: "diger", label: "Diğer" },
];

type Expense = {
  id: string;
  title: string;
  amount: number;
  category: string;
  notes: string | null;
  expense_date: string;
};

export default function ExpensesPage() {
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);

  const [title, setTitle] = useState("");
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("benzin");
  const [notes, setNotes] = useState("");
  const [expenseDate, setExpenseDate] = useState(new Date().toISOString().split("T")[0]);

  async function fetchExpenses() {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) { setLoading(false); return; }

    const { data } = await supabase
      .from("marketplace_expenses")
      .select("*")
      .eq("user_id", user.id)
      .order("expense_date", { ascending: false });

    setExpenses(data ?? []);
    setLoading(false);
  }

  useEffect(() => { fetchExpenses(); }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);

    const { data: { user } } = await supabase.auth.getUser();
    if (!user) { setSaving(false); return; }

    await supabase.from("marketplace_expenses").insert({
      user_id: user.id,
      title,
      amount: Number(amount),
      category,
      notes: notes || null,
      expense_date: expenseDate,
    });

    setTitle(""); setAmount(""); setNotes("");
    setCategory("benzin");
    setExpenseDate(new Date().toISOString().split("T")[0]);
    setShowForm(false);
    setSaving(false);
    fetchExpenses();
  }

  async function handleDelete(id: string) {
    await supabase.from("marketplace_expenses").delete().eq("id", id);
    setExpenses(expenses.filter(e => e.id !== id));
  }

  const totalExpenses = expenses.reduce((sum, e) => sum + Number(e.amount), 0);

  if (loading) {
    return <div className="flex h-64 items-center justify-center text-sm text-[#737373]">Loading...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[#171717]">Giderler</h1>
          {expenses.length > 0 && (
            <p className="mt-0.5 text-sm text-[#737373]">Toplam: <span className="font-medium text-red-600">{totalExpenses.toFixed(0)}€</span></p>
          )}
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="inline-flex items-center gap-1.5 rounded-lg bg-[#171717] px-3.5 py-2 text-sm font-medium text-white hover:bg-[#333]"
        >
          <Plus size={16} />
          Gider Ekle
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="rounded-lg border border-[#e5e5e5] bg-white p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-[#171717]">Yeni Gider</h2>
            <button type="button" onClick={() => setShowForm(false)} className="text-[#737373] hover:text-[#171717]">
              <X size={18} />
            </button>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-[#525252]">Başlık</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Benzin Mannheim yol"
                className="w-full rounded-md border border-[#e5e5e5] px-3 py-2 text-sm focus:border-[#171717] focus:outline-none"
                required
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-[#525252]">Tutar (€)</label>
              <input
                type="number"
                step="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="15"
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
                {EXPENSE_CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-[#525252]">Tarih</label>
              <input
                type="date"
                value={expenseDate}
                onChange={(e) => setExpenseDate(e.target.value)}
                className="w-full rounded-md border border-[#e5e5e5] px-3 py-2 text-sm focus:border-[#171717] focus:outline-none"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs font-medium text-[#525252]">Not (opsiyonel)</label>
              <input
                type="text"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Detay..."
                className="w-full rounded-md border border-[#e5e5e5] px-3 py-2 text-sm focus:border-[#171717] focus:outline-none"
              />
            </div>
          </div>

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

      {expenses.length === 0 && !showForm ? (
        <div className="rounded-lg border border-dashed border-[#d4d4d4] bg-[#fafafa] p-8 text-center">
          <Receipt size={32} className="mx-auto mb-3 text-[#d4d4d4]" />
          <p className="text-sm text-[#737373]">Henüz gider kaydı yok.</p>
          <p className="mt-1 text-xs text-[#a3a3a3]">Benzin, kargo, tamir gibi giderleri buraya ekle.</p>
        </div>
      ) : expenses.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-[#e5e5e5] text-xs text-[#737373]">
                <th className="pb-3 font-medium">Gider</th>
                <th className="pb-3 font-medium">Kategori</th>
                <th className="pb-3 font-medium">Tutar</th>
                <th className="pb-3 font-medium">Tarih</th>
                <th className="pb-3 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f5f5f5]">
              {expenses.map((exp) => (
                <tr key={exp.id} className="hover:bg-[#fafafa]">
                  <td className="py-3">
                    <span className="font-medium text-[#171717]">{exp.title}</span>
                    {exp.notes && <p className="text-xs text-[#a3a3a3] mt-0.5">{exp.notes}</p>}
                  </td>
                  <td className="py-3 text-[#737373]">
                    {EXPENSE_CATEGORIES.find(c => c.value === exp.category)?.label ?? exp.category}
                  </td>
                  <td className="py-3 font-medium text-red-600">-{Number(exp.amount).toFixed(0)}€</td>
                  <td className="py-3 text-[#737373]">
                    {new Date(exp.expense_date).toLocaleDateString("de-DE")}
                  </td>
                  <td className="py-3">
                    <button
                      onClick={() => handleDelete(exp.id)}
                      className="text-xs text-red-500 hover:text-red-700"
                    >
                      Sil
                    </button>
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
