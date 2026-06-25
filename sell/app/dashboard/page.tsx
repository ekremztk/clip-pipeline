"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import {
  ArrowDown,
  ArrowUp,
  Minus,
  Package,
  ShoppingCart,
  TrendingUp,
  Wallet,
} from "lucide-react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

type Sale = {
  id: string;
  product_name: string | null;
  buy_price: number;
  sell_price: number;
  fees: number;
  net_profit: number;
  sold_at: string | null;
  category: string | null;
  days_to_sell: number | null;
};

type Purchase = {
  id: string;
  product_name: string;
  buy_price: number;
  status: string;
  bought_at: string | null;
  category: string | null;
  created_at: string;
};

type Expense = {
  id: string;
  amount: number;
  category: string;
  expense_date: string;
};

type DailyData = {
  date: string;
  label: string;
  revenue: number;
  profit: number;
  expenses: number;
};

type CategoryData = {
  name: string;
  profit: number;
  count: number;
};

function MetricCard({
  label,
  value,
  change,
  icon: Icon,
  prefix,
  suffix,
}: {
  label: string;
  value: string;
  change?: number;
  icon: typeof TrendingUp;
  prefix?: string;
  suffix?: string;
}) {
  return (
    <div className="rounded-xl border border-[#e5e5e5] bg-white p-5">
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-medium text-[#737373]">{label}</span>
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#f5f5f5]">
          <Icon size={16} className="text-[#525252]" />
        </div>
      </div>
      <p className="mt-3 text-[28px] font-semibold leading-none tracking-tight text-[#171717]">
        {prefix}{value}{suffix}
      </p>
      {change !== undefined && (
        <div className="mt-2 flex items-center gap-1">
          {change > 0 ? (
            <ArrowUp size={14} className="text-[#16a34a]" />
          ) : change < 0 ? (
            <ArrowDown size={14} className="text-[#dc2626]" />
          ) : (
            <Minus size={14} className="text-[#737373]" />
          )}
          <span
            className={`text-xs font-medium ${
              change > 0
                ? "text-[#16a34a]"
                : change < 0
                ? "text-[#dc2626]"
                : "text-[#737373]"
            }`}
          >
            {change > 0 ? "+" : ""}
            {change.toFixed(0)}%
          </span>
          <span className="text-xs text-[#a3a3a3]">vs. önceki dönem</span>
        </div>
      )}
    </div>
  );
}

function ChartCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[#e5e5e5] bg-white p-5">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-[#171717]">{title}</h3>
        {subtitle && (
          <p className="mt-0.5 text-xs text-[#a3a3a3]">{subtitle}</p>
        )}
      </div>
      {children}
    </div>
  );
}

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

export default function OverviewPage() {
  const [sales, setSales] = useState<Sale[]>([]);
  const [purchases, setPurchases] = useState<Purchase[]>([]);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchAll() {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) { setLoading(false); return; }

      const [salesRes, purchasesRes, expensesRes] = await Promise.all([
        supabase.from("marketplace_sales").select("*").eq("user_id", user.id).order("sold_at", { ascending: true }),
        supabase.from("marketplace_purchases").select("*").eq("user_id", user.id).order("created_at", { ascending: false }),
        supabase.from("marketplace_expenses").select("*").eq("user_id", user.id).order("expense_date", { ascending: true }),
      ]);

      setSales(salesRes.data ?? []);
      setPurchases(purchasesRes.data ?? []);
      setExpenses(expensesRes.data ?? []);
      setLoading(false);
    }
    fetchAll();
  }, []);

  if (loading) {
    return <div className="flex h-64 items-center justify-center text-sm text-[#737373]">Loading...</div>;
  }

  const totalRevenue = sales.reduce((s, r) => s + Number(r.sell_price), 0);
  const totalProfit = sales.reduce((s, r) => s + Number(r.net_profit), 0);
  const totalExpenses = expenses.reduce((s, e) => s + Number(e.amount), 0);
  const totalInvested = purchases.filter(p => p.status === "bought" || p.status === "listed").reduce((s, p) => s + Number(p.buy_price), 0);
  const avgDaysToSell = sales.filter(s => s.days_to_sell).length > 0
    ? sales.filter(s => s.days_to_sell).reduce((s, r) => s + (r.days_to_sell ?? 0), 0) / sales.filter(s => s.days_to_sell).length
    : 0;
  const avgMargin = sales.length > 0
    ? sales.reduce((s, r) => {
        const buy = Number(r.buy_price);
        return s + (buy > 0 ? (Number(r.net_profit) / buy) * 100 : 100);
      }, 0) / sales.length
    : 0;

  const dailyData: DailyData[] = buildDailyData(sales, expenses);
  const categoryData: CategoryData[] = buildCategoryData(sales);
  const recentSales = [...sales].reverse().slice(0, 5);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-[#171717]">Overview</h1>
        <p className="mt-0.5 text-sm text-[#a3a3a3]">
          Genel bakış ve performans metrikleri
        </p>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Toplam Gelir"
          value={totalRevenue.toFixed(0)}
          suffix="€"
          icon={TrendingUp}
        />
        <MetricCard
          label="Net Kar"
          value={totalProfit.toFixed(0)}
          suffix="€"
          icon={Wallet}
        />
        <MetricCard
          label="Aktif Yatırım"
          value={totalInvested.toFixed(0)}
          suffix="€"
          icon={ShoppingCart}
        />
        <MetricCard
          label="Satış Sayısı"
          value={sales.length.toString()}
          icon={Package}
        />
      </div>

      {/* Secondary Metrics */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="rounded-xl border border-[#e5e5e5] bg-white px-4 py-3">
          <p className="text-xs text-[#a3a3a3]">Ort. Marj</p>
          <p className={`mt-1 text-lg font-semibold ${avgMargin >= 0 ? "text-[#16a34a]" : "text-[#dc2626]"}`}>
            {avgMargin.toFixed(0)}%
          </p>
        </div>
        <div className="rounded-xl border border-[#e5e5e5] bg-white px-4 py-3">
          <p className="text-xs text-[#a3a3a3]">Ort. Satış Süresi</p>
          <p className="mt-1 text-lg font-semibold text-[#171717]">
            {avgDaysToSell.toFixed(0)} gün
          </p>
        </div>
        <div className="rounded-xl border border-[#e5e5e5] bg-white px-4 py-3">
          <p className="text-xs text-[#a3a3a3]">Toplam Gider</p>
          <p className="mt-1 text-lg font-semibold text-[#dc2626]">
            {totalExpenses.toFixed(0)}€
          </p>
        </div>
        <div className="rounded-xl border border-[#e5e5e5] bg-white px-4 py-3">
          <p className="text-xs text-[#a3a3a3]">Gerçek Kar</p>
          <p className={`mt-1 text-lg font-semibold ${totalProfit - totalExpenses >= 0 ? "text-[#16a34a]" : "text-[#dc2626]"}`}>
            {(totalProfit - totalExpenses).toFixed(0)}€
          </p>
        </div>
      </div>

      {/* Charts Row */}
      {sales.length > 0 && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* Revenue & Profit Trend */}
          <ChartCard title="Gelir & Kar Trendi" subtitle="Son satışlar bazında">
            <div className="h-[240px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={dailyData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="gradRevenue" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.1} />
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="gradProfit" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#16a34a" stopOpacity={0.1} />
                      <stop offset="95%" stopColor="#16a34a" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                  <XAxis
                    dataKey="label"
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
                  <Area
                    type="monotone"
                    dataKey="revenue"
                    name="Gelir"
                    stroke="#6366f1"
                    strokeWidth={2}
                    fill="url(#gradRevenue)"
                    dot={false}
                    activeDot={{ r: 4, fill: "#6366f1" }}
                  />
                  <Area
                    type="monotone"
                    dataKey="profit"
                    name="Kar"
                    stroke="#16a34a"
                    strokeWidth={2}
                    fill="url(#gradProfit)"
                    dot={false}
                    activeDot={{ r: 4, fill: "#16a34a" }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </ChartCard>

          {/* Profit by Category */}
          <ChartCard title="Kategoriye Göre Kar" subtitle="Satış kategorileri">
            <div className="h-[240px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={categoryData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
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
                  <Bar
                    dataKey="profit"
                    name="Kar"
                    fill="#6366f1"
                    radius={[4, 4, 0, 0]}
                    maxBarSize={40}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </ChartCard>
        </div>
      )}

      {/* Recent Activity */}
      {recentSales.length > 0 && (
        <ChartCard title="Son Satışlar" subtitle="En son tamamlanan işlemler">
          <div className="space-y-3">
            {recentSales.map((s) => (
              <div
                key={s.id}
                className="flex items-center justify-between border-b border-[#f5f5f5] pb-3 last:border-0 last:pb-0"
              >
                <div>
                  <p className="text-sm font-medium text-[#171717]">
                    {s.product_name ?? "Ürün"}
                  </p>
                  <p className="text-xs text-[#a3a3a3]">
                    {s.sold_at ? new Date(s.sold_at).toLocaleDateString("de-DE") : "—"}
                    {s.days_to_sell ? ` · ${s.days_to_sell} gün` : ""}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium text-[#171717]">
                    {Number(s.sell_price).toFixed(0)}€
                  </p>
                  <p
                    className={`text-xs font-medium ${
                      Number(s.net_profit) >= 0
                        ? "text-[#16a34a]"
                        : "text-[#dc2626]"
                    }`}
                  >
                    {Number(s.net_profit) >= 0 ? "+" : ""}
                    {Number(s.net_profit).toFixed(0)}€ kar
                  </p>
                </div>
              </div>
            ))}
          </div>
        </ChartCard>
      )}

      {/* Empty state */}
      {sales.length === 0 && purchases.length === 0 && (
        <div className="rounded-xl border border-dashed border-[#d4d4d4] bg-[#fafafa] p-10 text-center">
          <Package size={36} className="mx-auto mb-3 text-[#d4d4d4]" />
          <p className="text-sm font-medium text-[#525252]">
            Henüz veri yok
          </p>
          <p className="mt-1 text-xs text-[#a3a3a3]">
            Alım ve satış kayıtları eklendikçe grafikler burada görünecek.
          </p>
        </div>
      )}
    </div>
  );
}

function buildDailyData(sales: Sale[], expenses: Expense[]): DailyData[] {
  const dayMap = new Map<string, DailyData>();

  for (const s of sales) {
    const date = s.sold_at ? s.sold_at.split("T")[0] : null;
    if (!date) continue;
    const existing = dayMap.get(date) ?? { date, label: formatDateLabel(date), revenue: 0, profit: 0, expenses: 0 };
    existing.revenue += Number(s.sell_price);
    existing.profit += Number(s.net_profit);
    dayMap.set(date, existing);
  }

  for (const e of expenses) {
    const date = e.expense_date;
    if (!date) continue;
    const existing = dayMap.get(date) ?? { date, label: formatDateLabel(date), revenue: 0, profit: 0, expenses: 0 };
    existing.expenses += Number(e.amount);
    dayMap.set(date, existing);
  }

  return Array.from(dayMap.values()).sort((a, b) => a.date.localeCompare(b.date));
}

function buildCategoryData(sales: Sale[]): CategoryData[] {
  const catLabels: Record<string, string> = {
    telefon: "Telefon",
    bilgisayar: "PC",
    tablet: "Tablet",
    kulaklik: "Kulaklık",
    konsol: "Konsol",
    aksesuar: "Aksesuar",
    kamera: "Kamera",
    dijital: "Dijital",
    diger: "Diğer",
  };

  const catMap = new Map<string, CategoryData>();
  for (const s of sales) {
    const cat = s.category ?? "diger";
    const existing = catMap.get(cat) ?? { name: catLabels[cat] ?? cat, profit: 0, count: 0 };
    existing.profit += Number(s.net_profit);
    existing.count += 1;
    catMap.set(cat, existing);
  }

  return Array.from(catMap.values()).sort((a, b) => b.profit - a.profit);
}

function formatDateLabel(date: string): string {
  const d = new Date(date);
  const day = d.getDate();
  const months = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"];
  return `${day} ${months[d.getMonth()]}`;
}
