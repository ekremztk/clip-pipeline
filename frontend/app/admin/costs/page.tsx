import { Plus } from "lucide-react";

import { expenseBreakdown, modelCosts } from "../_components/admin-data";
import { Button, MetricCard, PageHeader, ProgressBar, SectionCard, SectionHeader, SimpleTable, StatusBadge } from "../_components/admin-ui";
import { Bot, CreditCard, Database, WalletCards } from "lucide-react";

const costStats = [
    { label: "Total Expenses", value: "$0.00", delta: "No cost data synced", color: "#d97706", icon: WalletCards, spark: Array(10).fill(0) },
    { label: "AI Model Cost", value: "$0.00", delta: "No token usage synced", color: "#111827", icon: Bot, spark: Array(10).fill(0) },
    { label: "Infrastructure", value: "$0.00", delta: "No infra usage synced", color: "#0891b2", icon: Database, spark: Array(10).fill(0) },
    { label: "Budget Used", value: "0%", delta: "No budget configured", color: "#16a34a", icon: CreditCard, spark: Array(10).fill(0) },
];

export default function CostsPage() {
    return (
        <>
            <PageHeader title="Costs" description="Pricing formulas for Claude, Gemini, Deepgram, Modal, Railway, and R2." action={<Button><Plus size={16} />Add pricing rule</Button>} />
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                {costStats.map((stat) => <MetricCard key={stat.label} {...stat} />)}
            </div>
            <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-12">
                <SectionCard className="overflow-hidden xl:col-span-8">
                    <SectionHeader title="Model Pricing" description="Rates used for token, audio, GPU minute, and storage calculations" />
                    {modelCosts.length === 0 ? (
                        <div className="p-6 text-sm text-[#737373]">No pricing rules configured yet.</div>
                    ) : (
                        <SimpleTable
                            columns={["Vendor", "Model", "Unit", "Input", "Output", "Status"]}
                            rows={modelCosts.map((row) => [
                                <span className="font-medium text-[#171717]" key="vendor">{row.vendor}</span>,
                                row.model,
                                row.unit,
                                row.input,
                                row.output,
                                <StatusBadge key="status" tone={row.status === "credit" ? "info" : "success"}>{row.status}</StatusBadge>,
                            ])}
                        />
                    )}
                </SectionCard>
                <SectionCard className="p-4 xl:col-span-4">
                    <h2 className="mb-1 font-semibold text-[#171717]">Current Spend Mix</h2>
                    <p className="mb-5 text-sm text-[#737373]">Cost split for the current month</p>
                    {expenseBreakdown.length === 0 ? (
                        <div className="rounded-md border border-dashed border-[#d4d4d4] bg-[#fafafa] p-6 text-sm text-[#737373]">No cost records synced yet.</div>
                    ) : (
                        <ul className="space-y-4">
                            {expenseBreakdown.map((item) => (
                                <li key={item.label}>
                                    <div className="mb-1 flex items-center justify-between text-sm">
                                        <span>{item.label}</span>
                                        <span className="text-[#737373]">{item.value}</span>
                                    </div>
                                    <ProgressBar value={item.pct} color={item.color} />
                                </li>
                            ))}
                        </ul>
                    )}
                </SectionCard>
            </div>
        </>
    );
}
