import { Plus } from "lucide-react";

import { calendarEvents } from "../_components/admin-data";
import { Button, PageHeader, SectionCard, StatusBadge } from "../_components/admin-ui";

function eventTone(type: string) {
    if (type === "publish") return "success" as const;
    if (type === "pipeline") return "info" as const;
    if (type === "growth") return "warning" as const;
    return "neutral" as const;
}

export default function CalendarPage() {
    const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    return (
        <>
            <PageHeader title="Calendar" description="Publishing plan, customer work, content stock deadlines, and growth tasks." action={<Button><Plus size={16} />New event</Button>} />
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
                <SectionCard className="p-4 xl:col-span-8">
                    <div className="mb-4 flex items-center justify-between">
                        <h2 className="font-semibold text-[#171717]">May 2026</h2>
                        <div className="flex gap-1 text-xs">
                            {["Month", "Week", "Day"].map((tab, index) => (
                                <button key={tab} type="button" className={`h-8 rounded-md px-3 ${index === 1 ? "bg-[#171717] text-white" : "bg-[#f5f5f5] text-[#737373]"}`}>{tab}</button>
                            ))}
                        </div>
                    </div>
                    <div className="grid grid-cols-7 overflow-hidden rounded-lg border border-[#e5e5e5] text-sm">
                        {days.map((day) => <div key={day} className="border-b border-[#e5e5e5] bg-[#f5f5f5] px-3 py-2 font-medium">{day}</div>)}
                        {Array.from({ length: 35 }, (_, index) => (
                            <div key={index} className="min-h-28 border-r border-t border-[#e5e5e5] p-2 last:border-r-0">
                                <span className="text-xs text-[#737373]">{index + 1}</span>
                            </div>
                        ))}
                    </div>
                </SectionCard>
                <SectionCard className="p-4 xl:col-span-4">
                    <h2 className="mb-1 font-semibold text-[#171717]">Today</h2>
                    <p className="mb-4 text-sm text-[#737373]">Scheduled operations</p>
                    {calendarEvents.length === 0 ? (
                        <div className="rounded-md border border-dashed border-[#d4d4d4] bg-[#fafafa] p-6 text-sm text-[#737373]">No calendar events synced yet.</div>
                    ) : (
                        <ul className="space-y-3">
                            {calendarEvents.map((event) => (
                                <li key={event.title} className="rounded-lg border border-[#e5e5e5] p-3">
                                    <div className="flex items-center justify-between gap-3">
                                        <span className="text-sm font-medium text-[#171717]">{event.time}</span>
                                        <StatusBadge tone={eventTone(event.type)}>{event.type}</StatusBadge>
                                    </div>
                                    <p className="mt-2 text-sm text-[#171717]">{event.title}</p>
                                    <p className="mt-1 text-xs text-[#737373]">{event.owner}</p>
                                </li>
                            ))}
                        </ul>
                    )}
                </SectionCard>
            </div>
        </>
    );
}
