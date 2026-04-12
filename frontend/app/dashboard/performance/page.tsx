'use client';

import { BarChart3 } from "lucide-react";

export default function AnalyticsPage() {
    return (
        <div style={{ background: '#141413', minHeight: '100vh' }} className="p-8">
            <div className="max-w-5xl mx-auto">
                <h1 style={{ color: '#faf9f5' }} className="text-2xl font-semibold mb-1">Analytics</h1>
                <p style={{ color: '#ababab' }} className="text-sm">Track your video performance and insights</p>

                <div className="mt-16 flex flex-col items-center justify-center h-64 gap-4">
                    <div style={{ background: '#1c1c1b', border: '1px solid rgba(250,249,245,0.07)' }} className="w-12 h-12 rounded-2xl flex items-center justify-center">
                        <BarChart3 style={{ color: '#ababab' }} className="w-5 h-5" />
                    </div>
                    <p style={{ color: '#ababab' }} className="text-sm">Analytics dashboard — coming soon</p>
                </div>
            </div>
        </div>
    );
}
