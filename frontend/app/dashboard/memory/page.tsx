"use client";

import { Brain } from "lucide-react";

export default function MemoryPage() {
    return (
        <div className="flex flex-col items-center justify-center h-full text-center py-20">
            <div className="w-16 h-16 mb-4 rounded-full bg-[#0a0a0a] flex items-center justify-center border border-[#1a1a1a]">
                <Brain className="w-6 h-6 text-[#525252]" />
            </div>
            <h2 className="text-xl font-semibold mb-2 text-white">Channel Memory</h2>
            <p className="text-[#737373] text-sm max-w-sm">
                Channel Memory — Coming Soon
            </p>
        </div>
    );
}
