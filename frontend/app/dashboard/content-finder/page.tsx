'use client';

import { Search } from "lucide-react";

export default function ContentFinderPage() {
    return (
        <div className="min-h-screen bg-black p-8">
            <div className="max-w-5xl mx-auto">
                <h1 className="text-2xl font-semibold text-white mb-2">Content Finder</h1>
                <p className="text-sm text-[#737373]">Discover viral moments in your long-form content</p>

                <div className="mt-16 flex flex-col items-center justify-center h-64 gap-4">
                    <div className="w-12 h-12 bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg flex items-center justify-center">
                        <Search className="w-6 h-6 text-[#525252]" />
                    </div>
                    <p className="text-sm text-[#525252]">Content Finder — coming soon</p>
                </div>
            </div>
        </div>
    );
}
