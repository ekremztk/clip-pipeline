import { Archive, CheckCircle2, Clock3, Trash2 } from "lucide-react";

import { stockRows } from "../_components/admin-data";
import { Button, PageHeader, ProgressBar, SectionCard, SectionHeader, SimpleTable, StatusBadge } from "../_components/admin-ui";

function tone(status: string) {
    if (status === "usable") return "success" as const;
    if (status === "empty") return "warning" as const;
    return "neutral" as const;
}

export default function StockPage() {
    const totals = stockRows.reduce(
        (acc, row) => ({
            ready: acc.ready + row.ready,
            review: acc.review + row.review,
            rejected: acc.rejected + row.rejected,
            days: Math.max(acc.days, row.days),
        }),
        { ready: 0, review: 0, rejected: 0, days: 0 },
    );

    return (
        <>
            <PageHeader
                title="Stock"
                description="Ready clips, review queue, rejected candidates, and publishing coverage by channel."
                action={
                    <>
                        <Button variant="secondary">
                            <Archive size={16} />
                            Import batch
                        </Button>
                        <Button>Open stock board</Button>
                    </>
                }
            />

            <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
                {[
                    { label: "Ready", value: totals.ready, icon: CheckCircle2, color: "#16a34a" },
                    { label: "Review", value: totals.review, icon: Clock3, color: "#d97706" },
                    { label: "Rejected", value: totals.rejected, icon: Trash2, color: "#dc2626" },
                    { label: "Coverage", value: `${totals.days} days`, icon: Archive, color: "#171717" },
                ].map((item) => {
                    const Icon = item.icon;
                    return (
                        <SectionCard key={item.label} className="p-4">
                            <div className="flex items-center justify-between">
                                <p className="text-sm font-medium text-[#737373]">{item.label}</p>
                                <span className="inline-flex h-9 w-9 items-center justify-center rounded-md" style={{ backgroundColor: `${item.color}1a`, color: item.color }}>
                                    <Icon size={18} />
                                </span>
                            </div>
                            <p className="mt-4 text-2xl font-bold tracking-tight text-[#171717]">{item.value}</p>
                        </SectionCard>
                    );
                })}
            </div>

            <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-12">
                <SectionCard className="overflow-hidden xl:col-span-8">
                    <SectionHeader title="Stock Coverage" description="Channel-level stock status for posting cadence" />
                    {stockRows.length === 0 ? (
                        <div className="p-6 text-sm text-[#737373]">No stock data synced yet.</div>
                    ) : (
                        <SimpleTable
                            columns={["Channel", "Ready", "Review", "Rejected", "Coverage", "Status"]}
                            rows={stockRows.map((row) => [
                                <span className="font-medium text-[#171717]" key="channel">{row.channel}</span>,
                                row.ready,
                                row.review,
                                row.rejected,
                                `${row.days} days`,
                                <StatusBadge key="status" tone={tone(row.status)}>{row.status}</StatusBadge>,
                            ])}
                        />
                    )}
                </SectionCard>

                <SectionCard className="p-4 xl:col-span-4">
                    <h2 className="font-semibold text-[#171717]">Coverage Targets</h2>
                    <p className="mb-5 text-sm text-[#737373]">Minimum healthy target is 30 ready days per channel.</p>
                    {stockRows.length === 0 ? (
                        <div className="rounded-md border border-dashed border-[#d4d4d4] bg-[#fafafa] p-6 text-sm text-[#737373]">No channel stock targets synced yet.</div>
                    ) : (
                        <div className="space-y-5">
                            {stockRows.map((row) => (
                                <div key={row.channel}>
                                    <div className="mb-1 flex items-center justify-between text-sm">
                                        <span className="font-medium text-[#171717]">{row.channel}</span>
                                        <span className="text-[#737373]">{row.days}/30</span>
                                    </div>
                                    <ProgressBar value={Math.min((row.days / 30) * 100, 100)} color={row.days >= 30 ? "#16a34a" : row.days > 0 ? "#d97706" : "#737373"} />
                                </div>
                            ))}
                        </div>
                    )}
                </SectionCard>
            </div>
        </>
    );
}
