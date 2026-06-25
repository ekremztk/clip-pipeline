"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { TrendingUp } from "lucide-react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

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
};

type Expense = {
  id: string;
  amount: number;
  category: string;
  expense_date: string;
};

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-[#e5e5e5] bg-white px-3 py-2 shadow-sm">
      <p className="text-xs font-medium text-[#525252]">{label}</p>
      {payload.map((item: any) => (
        <p key={item.name} className="text-xs" style={{ color: item.color }}>
          {item.name}: {item.value.toFixed(0)}€
        </p>
      ))}
    </div>
  );
}

export default function EarningsPage() {
  const [sales, setSales] = useState<Sale[]>([]);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetch() {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) { setLoading(false); return; }

      const [salesRes, expensesRes] = await Promise.all([
        supabase.from("marketplace_sales").select("*").eq("user_id", user.id).order("sold_at", { ascending: true }),
        supabase.from("marketplace_expenses").select("*").eq("user_id", user.id),
      ]);

      setSales(salesRes.data ?? []);
      setExpenses(expensesRes.data ?? []);
      setLoading(false);
    }
    fetch();
  }, []);

  if (loading) {
    return <div className="flex h-64 items-center justify-center text-sm text-[#737373]">Loading...</div>;
  }

  if (sales.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-lg font-semibold text-[#171717]">Kazanç</h1>
        <div className="rounded-xl border border-dashed border-[#d4d4d4] bg-[#fafafa] p-10 text-center">
          <TrendingUp size={36} className="mx-auto mb-3 text-[#d4d4d4]" />
          <p className="text-sm font-medium text-[#525252]">Henüz kazanç verisi yok</p>
          <p className="mt-1 text-xs text-[#a3a3a3]">İlk satışını yaptığında kar/zarar analizi burada görünecek.</p>
        </div>
      </div>
    );
  }

  const totalRevenue = sales.reduce((s, r) => s + Number(r.sell_price), 0);
  const totalCost = sales.reduce((s, r) => s + Number(r.buy_price), 0);
  const totalFees = sales.reduce((s, r) => s + Number(r.fees || 0), 0);
  const netProfit = sales.reduce((s, r) => s + Number(r.net_profit), 0);
  const totalExpenses = expenses.reduce((s, e) => s + Number(e.amount), 0);
  const realProfit = netProfit - totalExpenses;
  const avgMargin = sales.length > 0
    ? sales.reduce((s, r) => {
        const buy = Number(r.buy_price);
        return s + (buy > 0 ? (Number(r.net_profit) / buy) * 100 : 100);
      }, 0) / sales.length
    : 0;
  const avgProfitPerSale = netProfit / sales.length;
  const daysArr = sales.filter(s => s.days_to_sell).map(s => s.days_to_sell!);
  const avgDays = daysArr.length > 0 ? daysArr.reduce((a, b) => a + b, 0) / daysArr.length : 0;
  const roi = totalCost > 0 ? (netProfit / totalCost) * 100 : 100;

  const perSaleData = sales.map((s, i) => ({
    name: s.product_name ? (s.product_name.length > 12 ? s.product_name.slice(0, 12) + "…" : s.product_name) : `#${i + 1}`,
    profit: Number(s.net_profit),
    buy: Number(s.buy_price),
    sell: Number(s.sell_price),
  }));

  const cumulativeData = sales.reduce<{ name: string; cumProfit: number }[]>((acc, s, i) => {
    const prev = i > 0 ? acc[i - 1].cumProfit : 0;
    const label = s.sold_at ? formatDateLabel(s.sold_at.split("T")[0]) : `#${i + 1}`;
    acc.push({ name: label, cumProfit: prev + Number(s.net_profit) });
    return acc;
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-[#171717]">Kazanç</h1>
        <p className="mt-0.5 text-sm text-[#a3a3a3]">Detaylı kar/zarar analizi</p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <SummaryCard label="Ciro" value={`${totalRevenue.toFixed(0)}€`} />
        <SummaryCard label="Maliyet" value={`${totalCost.toFixed(0)}€`} />
        <SummaryCard label="Masraflar" value={`${(totalFees + totalExpenses).toFixed(0)}€`} color="red" />
        <SummaryCard label="Net Kar" value={`${realProfit.toFixed(0)}€`} color={realProfit >= 0 ? "green" : "red"} />
        <SummaryCard label="ROI" value={`${roi.toFixed(0)}%`} color={roi >= 0 ? "green" : "red"} />
        <SummaryCard label="Ort. Marj" value={`${avgMargin.toFixed(0)}%`} color={avgMargin >= 0 ? "green" : "red"} />
      </div>

      {/* Secondary metrics */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-xl border border-[#e5e5e5] bg-white px-4 py-3">
          <p className="text-xs text-[#a3a3a3]">Satış Sayısı</p>
          <p className="mt-1 text-lg font-semibold text-[#171717]">{sales.length}</p>
        </div>
        <div className="rounded-xl border border-[#e5e5e5] bg-white px-4 py-3">
          <p className="text-xs text-[#a3a3a3]">Ort. Kar/Ürün</p>
          <p className="mt-1 text-lg font-semibold text-[#171717]">{avgProfitPerSale.toFixed(0)}€</p>
        </div>
        <div className="rounded-xl border border-[#e5e5e5] bg-white px-4 py-3">
          <p className="text-xs text-[#a3a3a3]">Ort. Satış Süresi</p>
          <p className="mt-1 text-lg font-semibold text-[#171717]">{avgDays.toFixed(0)} gün</p>
        </div>
        <div className="rounded-xl border border-[#e5e5e5] bg-white px-4 py-3">
          <p className="text-xs text-[#a3a3a3]">Toplam Gider</p>
          <p className="mt-1 text-lg font-semibold text-[#dc2626]">{totalExpenses.toFixed(0)}€</p>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Per-sale profit */}
        <div className="rounded-xl border border-[#e5e5e5] bg-white p-5">
          <h3 className="mb-1 text-sm font-semibold text-[#171717]">Ürün Bazlı Kar</h3>
          <p className="mb-4 text-xs text-[#a3a3a3]">Her satışın net karı</p>
          <div className="h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={perSaleData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                <XAxis
                  dataKey="name"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#a3a3a3", fontSize: 10 }}
                  interval={0}
                  angle={-20}
                  textAnchor="end"
                  height={50}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#a3a3a3", fontSize: 11 }}
                  tickFormatter={(v) => `${v}€`}
                />
                <Tooltip content={<CustomTooltip />} cursor={false} />
                <Bar dataKey="profit" name="Kar" radius={[4, 4, 0, 0]} maxBarSize={36}>
                  {perSaleData.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={entry.profit >= 0 ? "#16a34a" : "#dc2626"}
                      fillOpacity={0.85}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Cumulative profit */}
        <div className="rounded-xl border border-[#e5e5e5] bg-white p-5">
          <h3 className="mb-1 text-sm font-semibold text-[#171717]">Kümülatif Kar</h3>
          <p className="mb-4 text-xs text-[#a3a3a3]">Toplam kar büyümesi</p>
          <div className="h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={cumulativeData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                <XAxis
                  dataKey="name"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#a3a3a3", fontSize: 11 }}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#a3a3a3", fontSize: 11 }}
                  tickFormatter={(v) => `${v}€`}
                />
                <Tooltip content={<CustomTooltip />} cursor={false} />
                <Line
                  type="monotone"
                  dataKey="cumProfit"
                  name="Toplam Kar"
                  stroke="#6366f1"
                  strokeWidth={2.5}
                  dot={false}
                  activeDot={{ r: 5, fill: "#6366f1" }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Breakdown table */}
      <div className="rounded-xl border border-[#e5e5e5] bg-white p-5">
        <h3 className="mb-4 text-sm font-semibold text-[#171717]">Kar/Zarar Dökümü</h3>
        <div className="space-y-2">
          <BreakdownRow label="Toplam Satış Geliri" value={totalRevenue} color="default" />
          <BreakdownRow label="Toplam Alış Maliyeti" value={-totalCost} color="red" />
          <BreakdownRow label="Satış Masrafları (komisyon vb.)" value={-totalFees} color="red" />
          <BreakdownRow label="Genel Giderler (kargo, benzin vb.)" value={-totalExpenses} color="red" />
          <div className="border-t border-[#e5e5e5] pt-2">
            <BreakdownRow label="NET KAR" value={realProfit} color={realProfit >= 0 ? "green" : "red"} bold />
          </div>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({ label, value, color }: { label: string; value: string; color?: string }) {
  const textColor =
    color === "green" ? "text-[#16a34a]" :
    color === "red" ? "text-[#dc2626]" :
    "text-[#171717]";
  return (
    <div className="rounded-xl border border-[#e5e5e5] bg-white px-4 py-3">
      <p className="text-[11px] font-medium text-[#a3a3a3] uppercase tracking-wide">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${textColor}`}>{value}</p>
    </div>
  );
}

function BreakdownRow({ label, value, color, bold }: { label: string; value: number; color: string; bold?: boolean }) {
  const textColor =
    color === "green" ? "text-[#16a34a]" :
    color === "red" ? "text-[#dc2626]" :
    "text-[#171717]";
  return (
    <div className={`flex items-center justify-between py-1 ${bold ? "font-semibold" : ""}`}>
      <span className={`text-sm ${bold ? "text-[#171717]" : "text-[#525252]"}`}>{label}</span>
      <span className={`text-sm font-medium ${textColor}`}>
        {value >= 0 ? "+" : ""}{value.toFixed(0)}€
      </span>
    </div>
  );
}

function formatDateLabel(date: string): string {
  const d = new Date(date);
  const day = d.getDate();
  const months = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"];
  return `${day} ${months[d.getMonth()]}`;
}
