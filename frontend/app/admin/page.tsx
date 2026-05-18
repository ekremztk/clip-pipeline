"use client";

import { useEffect, useMemo, useState } from "react";
import { Clock3, CircleDollarSign, Eye, KeyRound, Tv, WalletCards } from "lucide-react";

import { authFetch } from "@/lib/api";
import { Button, MetricCard, PageHeader, ProgressBar, SectionCard, SectionHeader, SimpleTable } from "./_components/admin-ui";

type OverviewData = {
    range?: RevenueRange;
    period_start?: string;
    period_end?: string;
    finance: {
        total_revenue: number;
        total_expenses: number;
        api_revenue: number;
        channel_revenue: number;
        net_revenue: number;
        daily: Array<{ date: string; revenue: number; expenses: number; net: number }>;
        sources: Array<{ source: string; type: string; revenue: number; cost: number; net: number; status: string }>;
        expense_breakdown: Array<{ label: string; value: number; pct: number; color: string }>;
    };
    youtube: {
        channel_count: number;
        subscriber_count: number;
        view_count: number;
        video_count: number;
    };
    recent_activity: Array<{ title: string; detail: string; time: string }>;
};

type RevenueRange = "7d" | "30d" | "90d" | "all";

type YouTubeChannel = {
    subscriber_count: number | null;
    view_count: number | null;
    video_count: number | null;
    status: string;
};

type RealtimeData = {
    hours: number;
    total_views: number;
    hourly: Array<{ bucket: string | null; views: number }>;
    top_videos: Array<{
        channel_title: string;
        youtube_video_id: string;
        title: string | null;
        thumbnail_url: string | null;
        current_views: number;
        views_delta: number;
    }>;
};

const emptyOverview: OverviewData = {
    range: "30d",
    period_start: undefined,
    period_end: undefined,
    finance: {
        total_revenue: 0,
        total_expenses: 0,
        api_revenue: 0,
        channel_revenue: 0,
        net_revenue: 0,
        daily: [],
        sources: [],
        expense_breakdown: [],
    },
    youtube: {
        channel_count: 0,
        subscriber_count: 0,
        view_count: 0,
        video_count: 0,
    },
    recent_activity: [],
};

const revenueRangeOptions: Array<{ key: RevenueRange; label: string; description: string; fallbackDays: number | "all" }> = [
    { key: "7d", label: "7d", description: "Last 7 days", fallbackDays: 7 },
    { key: "30d", label: "30d", description: "Last 30 days", fallbackDays: 30 },
    { key: "90d", label: "90d", description: "Last 90 days", fallbackDays: 90 },
    { key: "all", label: "All", description: "All time", fallbackDays: "all" },
];

const allTimeStart = new Date(2025, 0, 14);

const emptyRealtime: RealtimeData = {
    hours: 48,
    total_views: 0,
    hourly: [],
    top_videos: [],
};

function money(value: number) {
    return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 2,
    }).format(value || 0);
}

function compact(value: number) {
    return new Intl.NumberFormat("en-US", {
        notation: "compact",
        maximumFractionDigits: 1,
    }).format(value || 0);
}

function integer(value: number) {
    return new Intl.NumberFormat("en-US").format(Math.round(value || 0));
}

function spark(values: number[]) {
    if (!values.length) return Array(12).fill(0);
    const padded = [...values];
    while (padded.length < 12) padded.unshift(values[0] ?? 0);
    return padded.slice(-12);
}

function startOfHour(date: Date) {
    const next = new Date(date);
    next.setMinutes(0, 0, 0);
    return next;
}

function bucketKey(date: Date) {
    return startOfHour(date).getTime();
}

function buildHourlyBars(hourly: RealtimeData["hourly"], hours: number) {
    const count = Math.max(Math.min(hours, 168), 1);
    const end = startOfHour(new Date());
    const values = new Map<number, number>();
    for (const row of hourly) {
        if (!row.bucket) continue;
        values.set(bucketKey(new Date(row.bucket)), row.views || 0);
    }
    return Array.from({ length: count }, (_, index) => {
        const start = new Date(end);
        start.setHours(end.getHours() - (count - 1 - index));
        return {
            start,
            views: values.get(bucketKey(start)) || 0,
        };
    });
}

function relativeDayLabel(date: Date) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const day = new Date(date);
    day.setHours(0, 0, 0, 0);
    const diffDays = Math.round((day.getTime() - today.getTime()) / 86_400_000);
    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Tomorrow";
    if (diffDays === -1) return "Yesterday";
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(date);
}

function formatClock(date: Date) {
    return new Intl.DateTimeFormat("en-US", {
        hour: "numeric",
        minute: "2-digit",
    }).format(date);
}

function formatHourRange(start: Date) {
    const end = new Date(start);
    end.setHours(start.getHours() + 1);
    return `${relativeDayLabel(start)}, ${formatClock(start)} – ${relativeDayLabel(end)}, ${formatClock(end)}`;
}

function parseLocalDate(value: string) {
    const [year, month, day] = value.slice(0, 10).split("-").map(Number);
    if (year && month && day) return new Date(year, month - 1, day);
    return new Date(value);
}

function formatAxisDate(date: Date, includeYear = false) {
    return new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        ...(includeYear ? { year: "numeric" } : {}),
    }).format(date);
}

function formatTooltipDate(date: Date) {
    return new Intl.DateTimeFormat("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
        year: "numeric",
    }).format(date);
}

function formatMoneyTick(value: number) {
    const abs = Math.abs(value);
    if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
    if (abs >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
    return `$${Math.round(value)}`;
}

function niceCeil(value: number) {
    if (value <= 0) return 1;
    const magnitude = 10 ** Math.floor(Math.log10(value));
    const normalized = value / magnitude;
    const nice = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
    return nice * magnitude;
}

function buildDailyRevenueSeries(daily: OverviewData["finance"]["daily"], range: RevenueRange) {
    const rows = [...daily]
        .filter((row) => row.date)
        .sort((a, b) => parseLocalDate(a.date).getTime() - parseLocalDate(b.date).getTime())
        .map((row) => ({
            date: parseLocalDate(row.date),
            value: row.net || 0,
        }));

    if (rows.length) return rows;

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const option = revenueRangeOptions.find((item) => item.key === range) || revenueRangeOptions[1];
    const fallbackLength =
        option.fallbackDays === "all"
            ? Math.max(Math.round((today.getTime() - allTimeStart.getTime()) / 86_400_000) + 1, 1)
            : option.fallbackDays;
    return Array.from({ length: fallbackLength }, (_, index) => {
        const date = new Date(today);
        if (option.fallbackDays === "all") {
            date.setTime(allTimeStart.getTime());
            date.setDate(allTimeStart.getDate() + index);
        } else {
            date.setDate(today.getDate() - (fallbackLength - 1 - index));
        }
        return { date, value: 0 };
    });
}

function buildRevenueChart(series: Array<{ date: Date; value: number }>) {
    const width = 920;
    const height = 320;
    const padding = { top: 24, right: 82, bottom: 58, left: 18 };
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;
    const maxValue = Math.max(...series.map((point) => point.value), 0);
    const minValue = Math.min(...series.map((point) => point.value), 0);
    const yMax = niceCeil(maxValue);
    const yMin = minValue < 0 ? -niceCeil(Math.abs(minValue)) : 0;
    const range = Math.max(yMax - yMin, 1);
    const coords = series.map((point, index) => {
        const x = padding.left + (index / Math.max(series.length - 1, 1)) * plotWidth;
        const y = padding.top + (1 - (point.value - yMin) / range) * plotHeight;
        return { ...point, x, y };
    });
    const path = coords.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
    const baselineY = padding.top + (1 - (0 - yMin) / range) * plotHeight;
    const areaPath = `${path} L${padding.left + plotWidth} ${baselineY.toFixed(1)} L${padding.left} ${baselineY.toFixed(1)} Z`;
    const ticks = Array.from({ length: 4 }, (_, index) => yMin + ((yMax - yMin) / 3) * index);
    const labelCount = series.length <= 10 ? series.length : 6;
    const labelIndexes = Array.from(
        new Set(
            Array.from({ length: labelCount }, (_, index) =>
                labelCount <= 1 ? 0 : Math.round((index / (labelCount - 1)) * (series.length - 1)),
            ),
        ),
    );
    return { width, height, padding, plotWidth, plotHeight, yMin, yMax, range, coords, path, areaPath, ticks, labelIndexes };
}

function overviewFromChannels(channels: YouTubeChannel[]): OverviewData {
    const connected = channels.filter((channel) => channel.status === "connected");
    return {
        ...emptyOverview,
        youtube: {
            channel_count: connected.length,
            subscriber_count: connected.reduce((sum, channel) => sum + (channel.subscriber_count || 0), 0),
            view_count: connected.reduce((sum, channel) => sum + (channel.view_count || 0), 0),
            video_count: connected.reduce((sum, channel) => sum + (channel.video_count || 0), 0),
        },
    };
}

export default function AdminOverviewPage() {
    const [data, setData] = useState<OverviewData>(emptyOverview);
    const [realtime, setRealtime] = useState<RealtimeData>(emptyRealtime);
    const [revenueRange, setRevenueRange] = useState<RevenueRange>("30d");
    const [hoveredRevenueIndex, setHoveredRevenueIndex] = useState<number | null>(null);
    const [hoveredRealtimeIndex, setHoveredRealtimeIndex] = useState<number | null>(null);
    const [loading, setLoading] = useState(true);
    const selectedRevenueRange = revenueRangeOptions.find((item) => item.key === revenueRange) || revenueRangeOptions[1];

    useEffect(() => {
        let cancelled = false;
        async function loadRealtime() {
            try {
                const res = await authFetch("/admin/youtube/realtime?hours=48");
                if (!res.ok) throw new Error(await res.text());
                const payload = await res.json();
                if (!cancelled) setRealtime(payload);
            } catch (exc) {
                console.error(exc);
                if (!cancelled) setRealtime(emptyRealtime);
            }
        }
        async function loadOverview() {
            try {
                setLoading(true);
                setHoveredRevenueIndex(null);
                const res = await authFetch(`/admin/overview?range=${revenueRange}`);
                if (!res.ok) throw new Error(await res.text());
                const payload = await res.json();
                if (!cancelled) setData(payload);
            } catch (exc) {
                console.error(exc);
                try {
                    const channelRes = await authFetch("/admin/youtube/channels");
                    if (!channelRes.ok) throw new Error(await channelRes.text());
                    const channelPayload = await channelRes.json();
                    if (!cancelled) setData(overviewFromChannels(channelPayload.channels || []));
                } catch (channelExc) {
                    console.error(channelExc);
                    if (!cancelled) setData(emptyOverview);
                }
            } finally {
                if (!cancelled) setLoading(false);
            }
        }
        loadOverview();
        loadRealtime();
        return () => {
            cancelled = true;
        };
    }, [revenueRange]);

    const metrics = useMemo(() => {
        const daily = data.finance.daily;
        const revenueSpark = spark(daily.map((row) => row.revenue));
        const expenseSpark = spark(daily.map((row) => row.expenses));
        const apiSpark = spark([]);
        const channelSpark = spark(daily.map((row) => row.revenue));

        return [
            {
                label: "Revenue",
                value: money(data.finance.total_revenue),
                delta: daily.length ? `${selectedRevenueRange.description} synced` : "No revenue data synced",
                color: "#16a34a",
                icon: CircleDollarSign,
                spark: revenueSpark,
            },
            {
                label: "Expenses",
                value: money(data.finance.total_expenses),
                delta: "No cost data synced",
                color: "#d97706",
                icon: WalletCards,
                spark: expenseSpark,
            },
            {
                label: "API Revenue",
                value: money(data.finance.api_revenue),
                delta: "No API clients connected",
                color: "#0891b2",
                icon: KeyRound,
                spark: apiSpark,
            },
            {
                label: "Channel Revenue",
                value: money(data.finance.channel_revenue),
                delta: `${data.youtube.channel_count} connected channel${data.youtube.channel_count === 1 ? "" : "s"}`,
                color: "#6366f1",
                icon: Tv,
                spark: channelSpark,
            },
        ];
    }, [data, selectedRevenueRange.description]);

    const revenueSeries = buildDailyRevenueSeries(data.finance.daily, revenueRange);
    const revenueChart = buildRevenueChart(revenueSeries);
    const hoveredRevenue = hoveredRevenueIndex === null ? null : revenueChart.coords[hoveredRevenueIndex];
    const realtimeBars = buildHourlyBars(realtime.hourly, realtime.hours);
    const realtimeMax = Math.max(...realtimeBars.map((bar) => bar.views), 1);
    const hoveredRealtime = hoveredRealtimeIndex === null ? null : realtimeBars[hoveredRealtimeIndex];

    return (
        <>
            <PageHeader
                title="Dashboard"
                description="Revenue, expenses, API customers, and channel business overview."
                action={
                    <>
                        <Button variant="secondary">
                            <Clock3 size={16} />
                            {selectedRevenueRange.description}
                        </Button>
                        <Button>Export report</Button>
                    </>
                }
            />

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                {metrics.map((card) => (
                    <MetricCard key={card.label} {...card} />
                ))}
            </div>

            <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-12">
                <SectionCard className="p-4 xl:col-span-8">
                    <div className="mb-4 flex items-center justify-between">
                        <div>
                            <h2 className="font-semibold text-[#171717]">Net Revenue</h2>
                            <p className="text-sm text-[#737373]">
                                {loading ? "Loading real admin data..." : "Channel and API revenue after tracked infrastructure cost"}
                            </p>
                        </div>
                        <div className="flex gap-1 text-xs">
                            {revenueRangeOptions.map((range) => (
                                <button
                                    key={range.key}
                                    type="button"
                                    onClick={() => setRevenueRange(range.key)}
                                    className={`h-8 rounded-md px-3 transition-colors ${revenueRange === range.key ? "bg-[#171717] text-white" : "bg-[#f5f5f5] text-[#737373] hover:bg-[#eeeeee]"}`}
                                >
                                    {range.label}
                                </button>
                            ))}
                        </div>
                    </div>
                    <div
                        className="relative h-[320px] overflow-hidden rounded-md border border-[#e5e5e5] bg-[#fafafa]"
                        onMouseLeave={() => setHoveredRevenueIndex(null)}
                    >
                        {revenueChart.ticks.map((tick) => {
                            const y = revenueChart.padding.top + (1 - (tick - revenueChart.yMin) / revenueChart.range) * revenueChart.plotHeight;
                            return (
                                <div
                                    key={tick}
                                    className="pointer-events-none absolute right-4 z-10 -translate-y-1/2 text-sm font-medium text-[#737373]"
                                    style={{ top: `${(y / revenueChart.height) * 100}%` }}
                                >
                                    {formatMoneyTick(tick)}
                                </div>
                            );
                        })}
                        {revenueChart.labelIndexes.map((index) => {
                            const point = revenueChart.coords[index];
                            return (
                                <div
                                    key={point.date.toISOString()}
                                    className="pointer-events-none absolute bottom-4 z-10 -translate-x-1/2 whitespace-nowrap text-sm font-medium text-[#737373]"
                                    style={{
                                        left: `${(point.x / revenueChart.width) * 100}%`,
                                        transform:
                                            index === 0
                                                ? "translateX(0)"
                                                : index === revenueChart.coords.length - 1
                                                  ? "translateX(-100%)"
                                                  : "translateX(-50%)",
                                    }}
                                >
                                        {formatAxisDate(point.date, revenueRange === "all")}
                                    </div>
                                );
                            })}
                        {hoveredRevenue ? (
                            <div
                                className="pointer-events-none absolute z-20 min-w-[220px] rounded-xl border border-[#d4d4d4] bg-white px-4 py-3 shadow-xl"
                                style={{
                                    left: `${Math.min(Math.max((hoveredRevenue.x / revenueChart.width) * 100, 17), 76)}%`,
                                    top: `${Math.max(14, hoveredRevenue.y - 104)}px`,
                                    transform: "translateX(-50%)",
                                }}
                            >
                                <p className="text-sm font-semibold text-[#171717]">{formatTooltipDate(hoveredRevenue.date)}</p>
                                <p className="mt-2 text-3xl font-medium tracking-tight text-[#38bdf8]">{money(hoveredRevenue.value)}</p>
                            </div>
                        ) : null}
                        <svg
                            viewBox={`0 0 ${revenueChart.width} ${revenueChart.height}`}
                            className="absolute inset-0 h-full w-full"
                            preserveAspectRatio="none"
                        >
                            <defs>
                                <linearGradient id="adminRevenueFill" x1="0" x2="0" y1="0" y2="1">
                                    <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.18" />
                                    <stop offset="100%" stopColor="#38bdf8" stopOpacity="0.02" />
                                </linearGradient>
                            </defs>
                            {revenueChart.ticks.map((tick) => {
                                const y = revenueChart.padding.top + (1 - (tick - revenueChart.yMin) / revenueChart.range) * revenueChart.plotHeight;
                                return (
                                    <g key={tick}>
                                        <line
                                            x1={revenueChart.padding.left}
                                            x2={revenueChart.width - revenueChart.padding.right}
                                            y1={y}
                                            y2={y}
                                            stroke="#e5e5e5"
                                            strokeWidth="1"
                                        />
                                    </g>
                                );
                            })}
                            <line
                                x1={revenueChart.padding.left}
                                x2={revenueChart.width - revenueChart.padding.right}
                                y1={revenueChart.height - revenueChart.padding.bottom}
                                y2={revenueChart.height - revenueChart.padding.bottom}
                                stroke="#a3a3a3"
                                strokeWidth="1"
                            />
                            <path d={revenueChart.areaPath} fill="url(#adminRevenueFill)" />
                            <path
                                d={revenueChart.path}
                                fill="none"
                                stroke="#38bdf8"
                                strokeWidth="3"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                            />
                            {hoveredRevenue ? (
                                <g>
                                    <line
                                        x1={hoveredRevenue.x}
                                        x2={hoveredRevenue.x}
                                        y1={revenueChart.padding.top}
                                        y2={revenueChart.height - revenueChart.padding.bottom}
                                        stroke="#a3a3a3"
                                        strokeDasharray="4 6"
                                    />
                                    <circle cx={hoveredRevenue.x} cy={hoveredRevenue.y} r="6" fill="#38bdf8" stroke="#ffffff" strokeWidth="3" />
                                </g>
                            ) : null}
                            {revenueChart.coords.map((point, index) => {
                                const previous = revenueChart.coords[index - 1];
                                const next = revenueChart.coords[index + 1];
                                const left = previous ? (previous.x + point.x) / 2 : revenueChart.padding.left;
                                const right = next ? (next.x + point.x) / 2 : revenueChart.width - revenueChart.padding.right;
                                return (
                                    <rect
                                        key={point.date.toISOString()}
                                        x={left}
                                        y={revenueChart.padding.top}
                                        width={Math.max(right - left, 1)}
                                        height={revenueChart.plotHeight}
                                        fill="transparent"
                                        onMouseEnter={() => setHoveredRevenueIndex(index)}
                                    />
                                );
                            })}
                        </svg>
                    </div>
                </SectionCard>

                <SectionCard className="space-y-6 p-4 xl:col-span-4">
                    <div>
                        <h2 className="mb-1 font-semibold text-[#171717]">Expense Mix</h2>
                        <p className="mb-4 text-sm text-[#737373]">Tracked cost distribution</p>
                        {data.finance.expense_breakdown.length === 0 ? (
                            <div className="rounded-md border border-dashed border-[#d4d4d4] bg-[#fafafa] p-6 text-sm text-[#737373]">
                                No cost data synced yet.
                            </div>
                        ) : (
                            <ul className="space-y-4">
                                {data.finance.expense_breakdown.map((item) => (
                                    <li key={item.label}>
                                        <div className="mb-1 flex items-center justify-between text-sm">
                                            <span>{item.label}</span>
                                            <span className="text-[#737373]">{money(item.value)}</span>
                                        </div>
                                        <ProgressBar value={item.pct} color={item.color} />
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                </SectionCard>
            </div>

            <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-12">
                <SectionCard className="p-4 xl:col-span-5">
                    <div className="mb-4 flex items-center justify-between">
                        <div>
                            <h2 className="font-semibold text-[#171717]">Realtime Views</h2>
                            <p className="text-sm text-[#737373]">Snapshot-based last {realtime.hours} hours</p>
                        </div>
                        <span className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-[#e0f2fe] text-[#075985]">
                            <Eye size={18} />
                        </span>
                    </div>
                    <p className="text-2xl font-semibold tracking-tight text-[#171717]">{integer(realtime.total_views)}</p>
                    <p className="mt-1 text-sm text-[#737373]">Across connected channels with captured snapshots</p>
                    <div
                        className="relative mt-4 h-[210px] rounded-md border border-[#e5e5e5] bg-[#fafafa] px-3 pb-9 pt-5"
                        onMouseLeave={() => setHoveredRealtimeIndex(null)}
                    >
                        {hoveredRealtime ? (
                            <div
                                className="pointer-events-none absolute top-3 z-10 min-w-[220px] rounded-lg border border-[#d4d4d4] bg-white px-4 py-3 shadow-lg"
                                style={{
                                    left: `${Math.min(Math.max((hoveredRealtimeIndex ?? 0) / Math.max(realtimeBars.length - 1, 1) * 100, 8), 72)}%`,
                                    transform: "translateX(-50%)",
                                }}
                            >
                                <p className="text-sm font-semibold text-[#171717]">{formatHourRange(hoveredRealtime.start)}</p>
                                <p className="mt-2 text-3xl font-bold text-[#075985]">{integer(hoveredRealtime.views)}</p>
                            </div>
                        ) : null}
                        <div className="absolute inset-x-3 bottom-9 h-px bg-[#a3a3a3]" />
                        <div className="flex h-full items-end gap-[3px]">
                            {realtimeBars.map((bar, index) => {
                                const height = Math.max((bar.views / realtimeMax) * 132, bar.views > 0 ? 8 : 2);
                                const isHovered = hoveredRealtimeIndex === index;
                                return (
                                    <button
                                        key={bar.start.toISOString()}
                                        type="button"
                                        aria-label={`${formatHourRange(bar.start)}: ${bar.views} views`}
                                        onMouseEnter={() => setHoveredRealtimeIndex(index)}
                                        onFocus={() => setHoveredRealtimeIndex(index)}
                                        className="group flex min-w-0 flex-1 items-end justify-center outline-none"
                                    >
                                        <span
                                            className={`w-full rounded-t-[3px] transition-colors ${isHovered ? "bg-[#075985]" : index === realtimeBars.length - 1 ? "bg-[#7dd3fc]" : "bg-[#38bdf8] group-hover:bg-[#0ea5e9]"}`}
                                            style={{ height }}
                                        />
                                    </button>
                                );
                            })}
                        </div>
                        <div className="absolute bottom-2 left-3 text-xs font-medium text-[#737373]">-48h</div>
                        <div className="absolute bottom-2 right-3 text-xs font-medium text-[#737373]">Now</div>
                    </div>
                </SectionCard>

                <SectionCard className="overflow-hidden xl:col-span-7">
                    <SectionHeader title="Realtime Top Videos" description="Latest captured counter delta over the selected window" />
                    {realtime.top_videos.length === 0 ? (
                        <div className="p-6 text-sm text-[#737373]">No realtime snapshots captured yet.</div>
                    ) : (
                        <SimpleTable
                            columns={["Video", "Channel", "Current views", "Window gain"]}
                            rows={realtime.top_videos.slice(0, 8).map((video) => [
                                <span className="flex items-center gap-3 font-medium text-[#171717]" key="video">
                                    {video.thumbnail_url ? (
                                        <img src={video.thumbnail_url} alt="" className="h-10 w-16 rounded object-cover" />
                                    ) : null}
                                    <span className="line-clamp-2">{video.title || video.youtube_video_id}</span>
                                </span>,
                                video.channel_title,
                                compact(video.current_views),
                                compact(video.views_delta),
                            ])}
                        />
                    )}
                </SectionCard>
            </div>

            <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-12">
                <SectionCard className="overflow-hidden xl:col-span-8">
                    <SectionHeader title="Revenue Sources" description="Connected revenue lines only" />
                    {data.finance.sources.length === 0 ? (
                        <div className="p-6 text-sm text-[#737373]">No revenue source has synced revenue yet.</div>
                    ) : (
                        <SimpleTable
                            columns={["Source", "Type", "Revenue", "Cost", "Net", "Status"]}
                            rows={data.finance.sources.map((row) => [
                                <span className="font-medium text-[#171717]" key="source">{row.source}</span>,
                                row.type,
                                money(row.revenue),
                                money(row.cost),
                                money(row.net),
                                row.status,
                            ])}
                        />
                    )}
                </SectionCard>

                <SectionCard className="p-4 xl:col-span-4">
                    <div className="mb-4">
                        <h2 className="font-semibold text-[#171717]">Recent Activity</h2>
                        <p className="text-sm text-[#737373]">Real admin events only</p>
                    </div>
                    {data.recent_activity.length === 0 ? (
                        <div className="rounded-md border border-dashed border-[#d4d4d4] bg-[#fafafa] p-6 text-sm text-[#737373]">
                            No admin activity recorded yet.
                        </div>
                    ) : null}
                </SectionCard>
            </div>
        </>
    );
}
