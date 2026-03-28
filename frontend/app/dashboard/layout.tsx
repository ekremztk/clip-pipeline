'use client';

import { useState, useEffect, createContext, useContext } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { authFetch } from "@/lib/api";
import {
    Home,
    FolderOpen,
    Dna,
    Clapperboard,
    Search,
    BarChart3,
    Settings,
    Sparkles,
    ChevronDown,
} from "lucide-react";

type Channel = {
    id: string;
    display_name: string;
    [key: string]: any;
};

export const ChannelContext = createContext<{
    channels: Channel[];
    activeChannelId: string;
    setActiveChannelId: (id: string) => void;
}>({
    channels: [],
    activeChannelId: "speedy_cast",
    setActiveChannelId: () => {},
});

export const useChannel = () => useContext(ChannelContext);

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();
    const [channels, setChannels] = useState<Channel[]>([]);
    const [selectedChannel, setSelectedChannel] = useState<any>(null);
    const [user, setUser] = useState<any>(null);

    useEffect(() => {
        const init = async () => {
            const { data } = await supabase.auth.getUser();
            const currentUser = data.user;
            setUser(currentUser);
            if (!currentUser) return;

            // User-scoped localStorage key — different users never share channel selection
            const storageKey = `selectedChannelId_${currentUser.id}`;

            try {
                const res = await authFetch('/channels');
                const json = await res.json();
                const list: Channel[] = Array.isArray(json) ? json : json.channels || [];
                setChannels(list);

                if (list.length === 0) return;

                const saved = localStorage.getItem(storageKey);
                const match = saved ? list.find((c) => c.id === saved) : null;
                const active = match || list[0];
                setSelectedChannel(active);
                localStorage.setItem(storageKey, active.id);
            } catch (err) {
                console.error('Failed to fetch channels', err);
            }
        };
        init();
    }, []);

    const handleChannelChange = (channelId: string) => {
        const ch = channels.find((c) => c.id === channelId);
        if (ch && user) {
            setSelectedChannel(ch);
            localStorage.setItem(`selectedChannelId_${user.id}`, ch.id);
        }
    };

    const handleSignOut = async () => {
        await supabase.auth.signOut();
        router.push('/login');
    };

    const navItems = [
        { href: "/dashboard", label: "Dashboard", icon: Home, exact: true },
        { href: "/dashboard/clips", label: "My Projects", icon: FolderOpen, exact: false },
        { href: "/dashboard/channel-dna", label: "Channel DNA", icon: Dna, exact: false },
        { href: "/director", label: "AI Director", icon: Clapperboard, exact: false },
        { href: "/dashboard/content-finder", label: "Content Finder", icon: Search, exact: false },
        { href: "/dashboard/performance", label: "Analytics", icon: BarChart3, exact: false },
        { href: "/dashboard/settings", label: "Settings", icon: Settings, exact: false },
    ];

    const userInitials = user?.user_metadata?.full_name
        ? user.user_metadata.full_name.split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2)
        : user?.email?.slice(0, 2).toUpperCase() || 'U';

    const userName = user?.user_metadata?.full_name || user?.email?.split('@')[0] || 'User';
    const userEmail = user?.email || '';

    return (
        <ChannelContext.Provider value={{
            channels,
            activeChannelId: selectedChannel?.id || "",
            setActiveChannelId: handleChannelChange
        }}>
            <div className="flex h-screen w-screen bg-black text-white overflow-hidden">
                {/* Sidebar */}
                <aside className="w-64 bg-black border-r border-[#1a1a1a] flex flex-col flex-shrink-0">
                    {/* Logo */}
                    <div className="h-16 flex items-center px-6 border-b border-[#1a1a1a]">
                        <div className="flex items-center gap-2">
                            <Sparkles className="w-5 h-5 text-white" />
                            <span className="text-lg font-semibold tracking-tight">PrognoT</span>
                        </div>
                    </div>

                    {/* Channel Selector */}
                    {channels.length > 0 ? (
                        <div className="px-3 pt-4 pb-1">
                            <div className="relative">
                                <select
                                    value={selectedChannel?.id || ''}
                                    onChange={(e) => handleChannelChange(e.target.value)}
                                    className="w-full appearance-none bg-[#0a0a0a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#a3a3a3] focus:outline-none focus:border-[#404040] transition-colors cursor-pointer pr-7"
                                >
                                    {channels.map((ch: any) => (
                                        <option key={ch.id} value={ch.id} className="bg-[#0a0a0a]">
                                            {ch.display_name || ch.name || ch.id}
                                        </option>
                                    ))}
                                </select>
                                <ChevronDown className="w-3 h-3 text-[#525252] absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                            </div>
                        </div>
                    ) : (
                        <div className="px-3 pt-4 pb-1">
                            <Link
                                href="/dashboard/settings"
                                className="flex items-center justify-center gap-1.5 w-full bg-[#0a0a0a] border border-dashed border-[#262626] hover:border-[#404040] rounded-lg px-3 py-2 text-xs text-[#525252] hover:text-[#a3a3a3] transition-colors"
                            >
                                <span className="text-base leading-none">+</span>
                                Add Channel
                            </Link>
                        </div>
                    )}

                    {/* Navigation */}
                    <nav className="flex-1 px-3 py-3 space-y-0.5 overflow-y-auto">
                        {navItems.map((item) => {
                            const Icon = item.icon;
                            const isActive = item.exact
                                ? pathname === item.href
                                : pathname === item.href || (item.href !== '/dashboard' && pathname.startsWith(item.href));

                            return (
                                <Link
                                    key={item.href}
                                    href={item.href}
                                    className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                                        isActive
                                            ? "bg-[#1a1a1a] text-white border-l-2 border-white -ml-[2px] pl-[14px]"
                                            : "text-[#a3a3a3] hover:bg-[#1a1a1a] hover:text-white"
                                    }`}
                                >
                                    <Icon className="w-4 h-4 flex-shrink-0" />
                                    <span>{item.label}</span>
                                </Link>
                            );
                        })}
                    </nav>

                    {/* Bottom: Credits + Profile */}
                    <div className="p-4 space-y-3 border-t border-[#1a1a1a]">
                        {/* Credits Card */}
                        <div className="bg-[#0a0a0a] border border-[#262626] rounded-lg p-3">
                            <div className="flex items-center justify-between mb-2">
                                <span className="text-xs text-[#737373]">Credits</span>
                                <span className="text-xs font-medium text-white">Pro</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <div className="flex-1 h-1.5 bg-[#1a1a1a] rounded-full overflow-hidden">
                                    <div className="h-full w-3/4 bg-white rounded-full" />
                                </div>
                                <span className="text-xs text-[#a3a3a3]">75%</span>
                            </div>
                        </div>

                        {/* Profile (click to sign out) */}
                        <button
                            onClick={handleSignOut}
                            title="Sign out"
                            className="w-full flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-[#1a1a1a] cursor-pointer transition-colors text-left"
                        >
                            <div className="w-9 h-9 bg-[#262626] rounded-full flex items-center justify-center flex-shrink-0">
                                <span className="text-sm font-medium text-white">{userInitials}</span>
                            </div>
                            <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-white truncate">{userName}</p>
                                <p className="text-xs text-[#737373] truncate">{userEmail}</p>
                            </div>
                        </button>
                    </div>
                </aside>

                {/* Main content */}
                <main className="flex-1 overflow-y-auto bg-black">
                    {children}
                </main>
            </div>
        </ChannelContext.Provider>
    );
}
