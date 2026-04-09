"use client";

import { Brain } from "lucide-react";

export default function MemoryPage() {
    return (
        <div style={{ background: '#141413' }} className="flex flex-col items-center justify-center h-full text-center py-20">
            <div style={{ background: '#1c1c1b', border: '1px solid rgba(250,249,245,0.07)' }} className="w-14 h-14 mb-4 rounded-2xl flex items-center justify-center">
                <Brain style={{ color: 'rgba(250,249,245,0.25)' }} className="w-6 h-6" />
            </div>
            <h2 style={{ color: '#faf9f5' }} className="text-xl font-semibold mb-2">Channel Memory</h2>
            <p style={{ color: 'rgba(250,249,245,0.4)' }} className="text-sm max-w-sm">
                Channel Memory — Coming Soon
            </p>
        </div>
    );
}
