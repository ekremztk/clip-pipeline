'use client';

import { BarChart3 } from "lucide-react";

export default function AnalyticsPage() {
    return (
        <div className="min-h-screen bg-black p-8">
            <div className="max-w-5xl mx-auto">
                <h1 className="text-2xl font-semibold text-white mb-2">Analytics</h1>
                <p className="text-sm text-[#737373]">Track your video performance and insights</p>

                <div className="mt-16 flex flex-col items-center justify-center h-64 gap-4">
                    <div className="w-12 h-12 bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg flex items-center justify-center">
                        <BarChart3 className="w-6 h-6 text-[#525252]" />
                    </div>
                    <p className="text-sm text-[#525252]">Analytics dashboard — coming soon</p>
                </div>
            </div>
        </div>
    );
}
