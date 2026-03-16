'use client';

import { useState, useEffect, createContext, useContext } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import {
    LayoutDashboard,
    Plus,
    Film,
    BarChart2,
    Brain,
    Settings,
    Bell,
    PanelLeftClose,
    PanelLeftOpen,
    ChevronDown
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Channel = {
    id: string;
    name: string;
};

export const ChannelContext = createContext<{
    channels: Channel[];
    activeChannelId: string;
    setActiveChannelId: (id: string) => void;
}>({
    channels: [],
    activeChannelId: "speedy_cast",
    setActiveChannelId: () => { },
});

export const useChannel = () => useContext(ChannelContext);

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const [sidebarOpen, setSidebarOpen] = useState(true);

    const [channels, setChannels] = useState<Channel[]>([]);
    const [activeChannelId, setActiveChannelId] = useState<string>("speedy_cast");

    useEffect(() => {
        const fetchChannels = async () => {
            try {
                const res = await fetch(`${API}/channels`);
                if (res.ok) {
                    const data = await res.json();
                    setChannels(data);
                    if (data.length > 0 && !data.find((c: Channel) => c.id === activeChannelId)) {
                        setActiveChannelId(data[0].id);
                    }
                }
            } catch (err) {
                console.error("Failed to fetch channels", err);
            }
        };
        fetchChannels();
    }, []);

    const navItems = [
        { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
        { href: "/dashboard/new-job", label: "New Clip Job", icon: Plus },
        { href: "/dashboard/clips", label: "Clip Library", icon: Film },
        { href: "/dashboard/performance", label: "Performance", icon: BarChart2 },
        { href: "/dashboard/memory", label: "Channel Memory", icon: Brain },
        { href: "/dashboard/settings", label: "Channel Settings", icon: Settings },
    ] as const;

    return (
        <ChannelContext.Provider value={{ channels, activeChannelId, setActiveChannelId }}>
            <div className="min-h-screen bg-[#000000] text-[#e5e5e5] font-sans flex">
                {/* ─── SIDEBAR ──────────────────────────────────────────────────────── */}
                <aside
                    className={`fixed left-0 top-0 bottom-0 bg-[#0d0d0d] border-r border-white/[0.06] transition-all duration-300 z-50 flex flex-col ${sidebarOpen ? "w-[240px]" : "w-[60px]"
                        }`}
                >
                    {/* Logo Area */}
                    <div className="h-16 flex items-center px-4 border-b border-white/[0.06] overflow-hidden whitespace-nowrap">
                        {sidebarOpen ? (
                            <div className="flex items-center gap-1.5 font-bold tracking-tight">
                                <span className="text-white text-lg">PROGNOT</span>
                                <span className="text-[#7c3aed] text-lg">STUDIO</span>
                            </div>
                        ) : (
                            <div className="w-full flex justify-center text-[#7c3aed] font-bold text-xl">
                                P
                            </div>
                        )}
                    </div>

                    {/* Nav Items */}
                    <div className="flex-1 py-6 flex flex-col gap-1 overflow-y-auto">
                        {navItems.map((item) => {
                            const Icon = item.icon;
                            const isActive = pathname === item.href;
                            return (
                                <Link key={item.href} href={item.href} passHref legacyBehavior>
                                    <motion.a
                                        whileHover={{ x: 2 }}
                                        transition={{ duration: 0.15 }}
                                        className={`relative flex items-center h-10 transition-colors group ${sidebarOpen ? "px-4" : "justify-center"
                                            } ${isActive
                                                ? "bg-[#0d0d0d] text-white"
                                                : "text-[#6b7280] hover:bg-white/[0.03] hover:text-[#e5e5e5]"
                                            }`}
                                        title={!sidebarOpen ? item.label : undefined}
                                    >
                                        {isActive && (
                                            <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-[#7c3aed]" />
                                        )}
                                        <Icon
                                            className={`w-5 h-5 flex-shrink-0 ${isActive ? "text-[#7c3aed]" : ""
                                                }`}
                                        />
                                        {sidebarOpen && (
                                            <span
                                                className={`ml-3 text-sm font-medium ${isActive ? "text-white" : ""
                                                    }`}
                                            >
                                                {item.label}
                                            </span>
                                        )}
                                    </motion.a>
                                </Link>
                            );
                        })}
                    </div>

                    {/* Collapse Button */}
                    <div className="p-2 border-t border-white/[0.06]">
                        <button
                            onClick={() => setSidebarOpen(!sidebarOpen)}
                            className="w-full flex items-center justify-center h-10 text-[#6b7280] hover:bg-white/[0.03] hover:text-[#e5e5e5] rounded-md transition-colors"
                        >
                            {sidebarOpen ? (
                                <PanelLeftClose className="w-5 h-5" />
                            ) : (
                                <PanelLeftOpen className="w-5 h-5" />
                            )}
                        </button>
                    </div>
                </aside>

                {/* ─── MAIN CONTENT AREA ────────────────────────────────────────────── */}
                <div
                    className={`flex-1 flex flex-col transition-all duration-300 ${sidebarOpen ? "ml-[240px]" : "ml-[60px]"
                        }`}
                >
                    {/* TOP BAR */}
                    <header className="h-16 bg-[#000000] border-b border-white/[0.06] flex items-center justify-between px-6 sticky top-0 z-40">
                        <div className="flex items-center">
                            {/* Channel Selector Pill */}
                            <div className="relative">
                                <select
                                    value={activeChannelId}
                                    onChange={(e) => setActiveChannelId(e.target.value)}
                                    className="appearance-none flex items-center gap-2 pl-4 pr-10 py-1.5 rounded-full border border-[#7c3aed] bg-transparent text-sm font-medium hover:bg-[#7c3aed]/10 transition-colors text-[#e5e5e5] cursor-pointer focus:outline-none"
                                >
                                    {channels.length > 0 ? (
                                        channels.map((c) => (
                                            <option key={c.id} value={c.id} className="bg-[#0d0d0d]">
                                                {c.name}
                                            </option>
                                        ))
                                    ) : (
                                        <option value="speedy_cast" className="bg-[#0d0d0d]">
                                            Speedy Cast
                                        </option>
                                    )}
                                </select>
                                <ChevronDown className="w-4 h-4 text-[#6b7280] absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                            </div>
                        </div>
                        <div className="flex items-center gap-4">
                            <button className="text-[#6b7280] hover:text-white transition-colors relative">
                                <Bell className="w-5 h-5" />
                                <span className="absolute top-0 right-0 w-2 h-2 bg-[#7c3aed] rounded-full border-2 border-black" />
                            </button>
                            <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-[#7c3aed] to-[#06b6d4] flex items-center justify-center cursor-pointer border border-white/10">
                                <span className="text-xs font-bold text-white">SC</span>
                            </div>
                        </div>
                    </header>

                    {/* PAGE CONTENT */}
                    <main className="flex-1 p-6 overflow-y-auto">
                        {children}
                    </main>
                </div>
            </div>
        </ChannelContext.Provider>
    );
}