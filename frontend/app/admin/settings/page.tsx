import { Bot, FileText, SlidersHorizontal } from "lucide-react";

import { settingGroups } from "../_components/admin-data";
import { Button, LinkCard, PageHeader, SectionCard, SectionHeader, SimpleTable, StatusBadge } from "../_components/admin-ui";

const pricingRows: string[][] = [];

export default function SettingsPage() {
    return (
        <>
            <PageHeader title="Settings" description="Cost formulas, admin assistant scope, export rules, and platform configuration." action={<Button>Save changes</Button>} />

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                {settingGroups.map((group) => (
                    <LinkCard key={group.title} title={group.title} description={group.desc} icon={group.icon} />
                ))}
            </div>

            <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-12">
                <SectionCard className="overflow-hidden xl:col-span-8">
                    <SectionHeader title="Pricing Formulas" description="Manual unit pricing that will drive spend and margin calculations" />
                    {pricingRows.length === 0 ? (
                        <div className="p-6 text-sm text-[#737373]">No pricing formulas configured yet.</div>
                    ) : (
                        <SimpleTable
                            columns={["Service", "Unit", "Input", "Output", "Status"]}
                            rows={pricingRows.map((row) => [
                                <span className="font-medium text-[#171717]" key="service">{row[0]}</span>,
                                row[1],
                                row[2],
                                row[3],
                                <StatusBadge key="status" tone={row[4] === "credit" ? "info" : "success"}>{row[4]}</StatusBadge>,
                            ])}
                        />
                    )}
                </SectionCard>

                <SectionCard className="p-4 xl:col-span-4">
                    <h2 className="font-semibold text-[#171717]">Admin Modules</h2>
                    <p className="mb-4 text-sm text-[#737373]">Configuration areas planned for the internal console.</p>
                    <div className="space-y-3">
                        {[
                            { title: "Cost control", desc: "Token, audio, GPU, and storage rates", icon: SlidersHorizontal },
                            { title: "Assistant RAG", desc: "Chat access to admin data and reports", icon: Bot },
                            { title: "Reports", desc: "Customer, channel, and finance exports", icon: FileText },
                        ].map((item) => {
                            const Icon = item.icon;
                            return (
                                <div key={item.title} className="flex gap-3 rounded-md border border-[#e5e5e5] p-3">
                                    <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-[#f5f5f5] text-[#171717]">
                                        <Icon size={17} />
                                    </span>
                                    <div>
                                        <p className="text-sm font-medium text-[#171717]">{item.title}</p>
                                        <p className="text-xs text-[#737373]">{item.desc}</p>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </SectionCard>
            </div>
        </>
    );
}
