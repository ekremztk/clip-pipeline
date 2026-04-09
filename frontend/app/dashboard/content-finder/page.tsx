'use client';

import { Search } from "lucide-react";

export default function ContentFinderPage() {
    return (
        <div style={{ background: '#141413', minHeight: '100vh' }} className="p-8">
            <div className="max-w-5xl mx-auto">
                <h1 style={{ color: '#faf9f5' }} className="text-2xl font-semibold mb-1">Content Finder</h1>
                <p style={{ color: 'rgba(250,249,245,0.4)' }} className="text-sm">Discover viral moments in your long-form content</p>

                <div className="mt-16 flex flex-col items-center justify-center h-64 gap-4">
                    <div style={{ background: '#1c1c1b', border: '1px solid rgba(250,249,245,0.07)' }} className="w-12 h-12 rounded-2xl flex items-center justify-center">
                        <Search style={{ color: 'rgba(250,249,245,0.25)' }} className="w-5 h-5" />
                    </div>
                    <p style={{ color: 'rgba(250,249,245,0.25)' }} className="text-sm">Content Finder — coming soon</p>
                </div>
            </div>
        </div>
    );
}
