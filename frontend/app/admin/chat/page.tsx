import { Send } from "lucide-react";

import { chatMessages } from "../_components/admin-data";
import { Button, PageHeader, SectionCard } from "../_components/admin-ui";

const conversations: Array<{ title: string; subtitle: string }> = [];

export default function ChatPage() {
    return (
        <>
            <PageHeader title="Chat" description="Admin assistant for finance, channel stock, customer status, and platform questions." />
            <SectionCard className="grid min-h-[680px] grid-cols-1 overflow-hidden lg:grid-cols-[280px_1fr]">
                <aside className="border-b border-[#e5e5e5] bg-[#fafafa] p-4 lg:border-b-0 lg:border-r">
                    <h2 className="font-semibold text-[#171717]">Conversations</h2>
                    <div className="mt-4 space-y-2">
                        {conversations.length === 0 ? (
                            <div className="rounded-md border border-dashed border-[#d4d4d4] bg-white p-4 text-sm text-[#737373]">No assistant threads yet.</div>
                        ) : (
                            conversations.map((item, index) => (
                                <button key={item.title} type="button" className={`w-full rounded-md px-3 py-2 text-left text-sm ${index === 0 ? "bg-white shadow-sm" : "hover:bg-white"}`}>
                                    <span className="block font-medium text-[#171717]">{item.title}</span>
                                    <span className="block truncate text-xs text-[#737373]">{item.subtitle}</span>
                                </button>
                            ))
                        )}
                    </div>
                </aside>
                <div className="flex min-h-[680px] flex-col">
                    <div className="border-b border-[#e5e5e5] p-4">
                        <h2 className="font-semibold text-[#171717]">Business overview</h2>
                        <p className="text-sm text-[#737373]">RAG scope: admin metrics, costs, customers, channels, stock, jobs</p>
                    </div>
                    <div className="flex-1 space-y-4 overflow-y-auto p-5">
                        {chatMessages.length === 0 ? (
                            <div className="rounded-md border border-dashed border-[#d4d4d4] bg-[#fafafa] p-6 text-sm text-[#737373]">No admin assistant messages yet.</div>
                        ) : (
                            chatMessages.map((message, index) => (
                                <div key={index} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                                    <div className={`max-w-[720px] rounded-lg px-4 py-3 text-sm ${message.role === "user" ? "bg-[#171717] text-white" : "border border-[#e5e5e5] bg-white text-[#171717]"}`}>
                                        {message.text}
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                    <div className="border-t border-[#e5e5e5] p-4">
                        <div className="flex gap-2">
                            <input className="h-10 flex-1 rounded-md border border-[#e5e5e5] px-3 text-sm" placeholder="Ask about costs, channels, stock, or customers..." />
                            <Button><Send size={16} />Send</Button>
                        </div>
                    </div>
                </div>
            </SectionCard>
        </>
    );
}
