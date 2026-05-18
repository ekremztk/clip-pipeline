import { Database, HardDrive, RefreshCw, Trash2 } from "lucide-react";

import { storageRows } from "../_components/admin-data";
import { Button, PageHeader, SectionCard, SectionHeader, SimpleTable, StatusBadge } from "../_components/admin-ui";

function tone(status: string) {
    if (status === "keep") return "success" as const;
    if (status === "clean") return "info" as const;
    return "warning" as const;
}

export default function StoragePage() {
    return (
        <>
            <PageHeader
                title="Storage"
                description="R2 buckets, generated clip objects, cleanup state, and retained stock assets."
                action={
                    <>
                        <Button variant="secondary">
                            <RefreshCw size={16} />
                            Scan R2
                        </Button>
                        <Button>
                            <Trash2 size={16} />
                            Cleanup stale
                        </Button>
                    </>
                }
            />

            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <SectionCard className="p-4">
                    <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-[#737373]">Stored Objects</p>
                        <Database size={18} />
                    </div>
                    <p className="mt-4 text-2xl font-bold tracking-tight text-[#171717]">0</p>
                    <p className="mt-1 text-sm text-[#737373]">No storage scan synced</p>
                </SectionCard>
                <SectionCard className="p-4">
                    <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-[#737373]">Current Size</p>
                        <HardDrive size={18} />
                    </div>
                    <p className="mt-4 text-2xl font-bold tracking-tight text-[#171717]">0 GB</p>
                    <p className="mt-1 text-sm text-[#737373]">No storage scan synced</p>
                </SectionCard>
                <SectionCard className="p-4">
                    <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-[#737373]">Cleanup State</p>
                        <Trash2 size={18} />
                    </div>
                    <p className="mt-4 text-2xl font-bold tracking-tight text-[#171717]">-</p>
                    <p className="mt-1 text-sm text-[#737373]">No cleanup scan synced</p>
                </SectionCard>
            </div>

            <SectionCard className="mt-6 overflow-hidden">
                <SectionHeader title="R2 Object Groups" description="Storage groups that the admin cleanup workflow tracks" />
                {storageRows.length === 0 ? (
                    <div className="p-6 text-sm text-[#737373]">No R2 scan records synced yet.</div>
                ) : (
                    <SimpleTable
                        columns={["Prefix", "Objects", "Size", "Policy", "Status"]}
                        rows={storageRows.map((row) => [
                            <span className="font-mono text-sm font-medium text-[#171717]" key="bucket">{row.bucket}</span>,
                            row.objects,
                            row.size,
                            row.status === "keep" ? "Retain for stock and publishing" : "Safe to keep empty",
                            <StatusBadge key="status" tone={tone(row.status)}>{row.status}</StatusBadge>,
                        ])}
                    />
                )}
            </SectionCard>
        </>
    );
}
