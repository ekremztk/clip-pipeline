import { pipelineRows } from "../_components/admin-data";
import { PageHeader, SectionCard, SectionHeader, SimpleTable, StatusBadge } from "../_components/admin-ui";

function tone(health: string) {
    if (health === "stable") return "success" as const;
    if (health === "testing") return "info" as const;
    if (health === "paused") return "warning" as const;
    return "neutral" as const;
}

export default function PipelinePage() {
    return (
        <>
            <PageHeader title="Pipeline" description="High-level pipeline health only. Detailed execution control stays in AI Director." />
            <SectionCard className="overflow-hidden">
                <SectionHeader title="Pipeline Systems" description="Operational status and recent cost by subsystem" />
                {pipelineRows.length === 0 ? (
                    <div className="p-6 text-sm text-[#737373]">No pipeline health data synced yet.</div>
                ) : (
                    <SimpleTable
                        columns={["System", "Scope", "Health", "Last run", "Cost"]}
                        rows={pipelineRows.map((row) => [
                            <span className="font-medium text-[#171717]" key="name">{row.name}</span>,
                            row.scope,
                            <StatusBadge key="health" tone={tone(row.health)}>{row.health}</StatusBadge>,
                            row.lastRun,
                            row.cost,
                        ])}
                    />
                )}
            </SectionCard>
        </>
    );
}
