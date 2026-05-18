import { Copy, Plus, RotateCcw } from "lucide-react";

import { apiClients } from "../_components/admin-data";
import { Button, MetricCard, PageHeader, SectionCard, SectionHeader, SimpleTable, StatusBadge } from "../_components/admin-ui";
import { KeyRound, Timer, WalletCards, Zap } from "lucide-react";

const apiStats = [
    { label: "API Revenue", value: "$0.00", delta: "No API clients connected", color: "#0891b2", icon: KeyRound, spark: Array(8).fill(0) },
    { label: "Processing Time", value: "0s", delta: "No API usage synced", color: "#6366f1", icon: Timer, spark: Array(8).fill(0) },
    { label: "API Cost", value: "$0.00", delta: "No API usage synced", color: "#d97706", icon: WalletCards, spark: Array(8).fill(0) },
    { label: "Success Rate", value: "-", delta: "No API usage synced", color: "#16a34a", icon: Zap, spark: Array(8).fill(0) },
];

export default function ApiPage() {
    return (
        <>
            <PageHeader title="API" description="External API clients, keys, usage, and usage-based billing." action={<Button><Plus size={16} />Create API key</Button>} />
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                {apiStats.map((stat) => <MetricCard key={stat.label} {...stat} />)}
            </div>
            <SectionCard className="mt-6 overflow-hidden">
                <SectionHeader title="API Clients" description="Usage, cost, and revenue per API key" action={<Button variant="secondary"><RotateCcw size={16} />Rotate keys</Button>} />
                {apiClients.length === 0 ? (
                    <div className="p-6 text-sm text-[#737373]">No API clients created yet.</div>
                ) : (
                    <SimpleTable
                        columns={["Client", "Key", "Usage", "Cost", "Revenue", "Status"]}
                        rows={apiClients.map((client) => [
                            <span className="font-medium text-[#171717]" key="client">{client.name}</span>,
                            <span key="key" className="inline-flex items-center gap-2 rounded-md bg-[#f5f5f5] px-2 py-1 font-mono text-xs"><Copy size={12} />{client.key}</span>,
                            client.usage,
                            client.spend,
                            client.revenue,
                            <StatusBadge key="status" tone={client.status === "active" ? "success" : client.status === "internal" ? "neutral" : "warning"}>{client.status}</StatusBadge>,
                        ])}
                    />
                )}
            </SectionCard>
        </>
    );
}
