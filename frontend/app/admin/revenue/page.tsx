import { Download } from "lucide-react";

import { revenueRows } from "../_components/admin-data";
import { Button, MetricCard, PageHeader, SectionCard, SectionHeader, SimpleTable, StatusBadge } from "../_components/admin-ui";
import { CircleDollarSign, TrendingUp, Tv, KeyRound } from "lucide-react";

const revenueStats = [
    { label: "Gross Revenue", value: "$0.00", delta: "No revenue data synced", color: "#16a34a", icon: CircleDollarSign, spark: Array(10).fill(0) },
    { label: "Net Profit", value: "$0.00", delta: "No cost data synced", color: "#111827", icon: TrendingUp, spark: Array(10).fill(0) },
    { label: "Channel Income", value: "$0.00", delta: "Waiting for YouTube Analytics sync", color: "#6366f1", icon: Tv, spark: Array(10).fill(0) },
    { label: "API Income", value: "$0.00", delta: "No API clients connected", color: "#0891b2", icon: KeyRound, spark: Array(10).fill(0) },
];

export default function RevenuePage() {
    return (
        <>
            <PageHeader title="Revenue" description="YouTube channel income, API revenue, service income, and monthly net tracking." action={<Button><Download size={16} />Export</Button>} />
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                {revenueStats.map((stat) => <MetricCard key={stat.label} {...stat} />)}
            </div>
            <SectionCard className="mt-6 overflow-hidden">
                <SectionHeader title="Revenue Ledger" description="Business lines that will later connect to YouTube API, Stripe, and internal usage billing" />
                {revenueRows.length === 0 ? (
                    <div className="p-6 text-sm text-[#737373]">No revenue records synced yet.</div>
                ) : (
                    <SimpleTable
                        columns={["Source", "Type", "Revenue", "Cost", "Net", "Status"]}
                        rows={revenueRows.map((row) => [
                            <span className="font-medium text-[#171717]" key="source">{row.source}</span>,
                            row.type,
                            row.revenue,
                            row.cost,
                            row.net,
                            <StatusBadge key="status" tone={row.status === "healthy" ? "success" : row.status === "watch" ? "warning" : "info"}>{row.status}</StatusBadge>,
                        ])}
                    />
                )}
            </SectionCard>
        </>
    );
}
