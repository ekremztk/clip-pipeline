'use client';

import { useState, useEffect, useRef, createContext, useContext } from "react";
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
    Scissors,
    Plus,
    CreditCard,
    Globe,
    LogOut,
    User,
    HelpCircle,
    BookOpen,
    Zap,
    Check,
    ChevronsLeft,
    ChevronsRight,
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
    isLoading: boolean;
    refreshChannels: () => Promise<void>;
}>({
    channels: [],
    activeChannelId: "",
    setActiveChannelId: () => {},
    isLoading: true,
    refreshChannels: async () => {},
});

export const useChannel = () => useContext(ChannelContext);

function Skeleton({ className }: { className?: string }) {
    return (
        <div className={`bg-[#1a1a1a] rounded animate-pulse ${className ?? ""}`} />
    );
}

function ProBadge() {
    return (
        <span className="ml-auto text-[9px] font-semibold border border-[#2a2a2a] text-[#525252] px-1.5 py-0.5 rounded-md leading-none tracking-wide flex-shrink-0">
            PRO
        </span>
    );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();

    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [profileOpen, setProfileOpen] = useState(false);
    const [channels, setChannels] = useState<Channel[]>([]);
    const [selectedChannel, setSelectedChannel] = useState<Channel | null>(null);
    const [user, setUser] = useState<any>(null);
    const [isLoading, setIsLoading] = useState(true);

    const profileRef = useRef<HTMLDivElement>(null);

    // Auto-close sidebar on route change
    useEffect(() => {
        setSidebarOpen(false);
    }, [pathname]);

    // Close profile dropdown on outside click
    useEffect(() => {
        function handleClickOutside(e: MouseEvent) {
            if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
                setProfileOpen(false);
            }
        }
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    useEffect(() => {
        const init = async () => {
            const { data: sessionData } = await supabase.auth.getSession();
            const sessionUser = sessionData.session?.user ?? null;

            if (sessionUser) {
                const storageKey = `selectedChannelId_${sessionUser.id}`;
                const cacheKey = `channelList_${sessionUser.id}`;
                const cached = typeof window !== 'undefined' ? localStorage.getItem(cacheKey) : null;

                if (cached) {
                    try {
                        const list = JSON.parse(cached) as Channel[];
                        if (list.length > 0) {
                            const saved = localStorage.getItem(storageKey);
                            const active = (saved ? list.find(c => c.id === saved) : null) ?? list[0];
                            setChannels(list);
                            setSelectedChannel(active);
                            setUser(sessionUser);
                            setIsLoading(false);
                        }
                    } catch { }
                }
            }

            const { data } = await supabase.auth.getUser();
            const currentUser = data.user;
            setUser(currentUser);

            if (!currentUser) {
                setIsLoading(false);
                return;
            }

            const storageKey = `selectedChannelId_${currentUser.id}`;
            const cacheKey = `channelList_${currentUser.id}`;

            try {
                const res = await authFetch('/channels');
                const json = await res.json();
                const list: Channel[] = Array.isArray(json) ? json : json.channels ?? [];

                if (typeof window !== 'undefined') {
                    localStorage.setItem(cacheKey, JSON.stringify(list));
                }

                setChannels(list);

                if (list.length === 0) {
                    setSelectedChannel(null);
                    setIsLoading(false);
                    return;
                }

                const saved = localStorage.getItem(storageKey);
                const active = (saved ? list.find(c => c.id === saved) : null) ?? list[0];
                setSelectedChannel(active);
                localStorage.setItem(storageKey, active.id);
            } catch (err) {
                console.error('Failed to fetch channels', err);
            } finally {
                setIsLoading(false);
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

    const refreshChannels = async () => {
        if (!user) return;
        try {
            const res = await authFetch('/channels');
            const json = await res.json();
            const list: Channel[] = Array.isArray(json) ? json : json.channels ?? [];
            const cacheKey = `channelList_${user.id}`;
            const storageKey = `selectedChannelId_${user.id}`;
            if (typeof window !== 'undefined') {
                localStorage.setItem(cacheKey, JSON.stringify(list));
            }
            setChannels(list);
            if (list.length > 0) {
                const saved = localStorage.getItem(storageKey);
                const active = (saved ? list.find(c => c.id === saved) : null) ?? list[0];
                setSelectedChannel(active);
                localStorage.setItem(storageKey, active.id);
            }
        } catch (err) {
            console.error('Failed to refresh channels', err);
        }
    };

    const isAdmin = user?.app_metadata?.role === 'admin';

    const userInitials = user?.user_metadata?.full_name
        ? user.user_metadata.full_name.split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2)
        : user?.email?.slice(0, 2).toUpperCase() ?? '??';

    const userName = user?.user_metadata?.full_name ?? user?.email?.split('@')[0] ?? '';
    const userEmail = user?.email ?? '';
    const truncatedEmail = userEmail.length > 22 ? userEmail.slice(0, 14) + '\u2026' : userEmail;

    function isActive(href: string, exact: boolean) {
        if (!href || href === '#' || href.startsWith('http')) return false;
        return exact
            ? pathname === href
            : pathname === href || (href !== '/dashboard' && pathname.startsWith(href));
    }

    const modulesItems = [
        { href: "/dashboard",                label: "Dashboard",      icon: Home,        exact: true,  pro: false },
        { href: "/dashboard/content-finder", label: "Content Finder", icon: Search,      exact: false, pro: false },
        { href: "https://edit.prognot.com",  label: "Editor",         icon: Scissors,    exact: false, pro: true,  external: true },
        ...(isAdmin ? [{ href: "/director",  label: "AI Director",    icon: Clapperboard, exact: false, pro: false }] : []),
    ];

    const creativeItems = [
        { href: "/dashboard/clips",       label: "Projects",    icon: FolderOpen, exact: false },
        { href: "/dashboard/performance", label: "Analytics",   icon: BarChart3,  exact: false },
        { href: "/dashboard/channel-dna", label: "Channel DNA", icon: Dna,        exact: false },
    ];

    const bottomItems = [
        { href: "/dashboard/settings", label: "Settings",    icon: Settings,   exact: false },
        { href: "#",                   label: "Subscription", icon: Zap,        exact: false },
        { href: "#",                   label: "Learn",        icon: BookOpen,   exact: false },
        { href: "#",                   label: "Help Center",  icon: HelpCircle, exact: false },
    ];

    const renderNavItem = (item: {
        href: string;
        label: string;
        icon: React.ElementType;
        exact?: boolean;
        pro?: boolean;
        external?: boolean;
    }) => {
        const Icon = item.icon;
        const active = isActive(item.href, item.exact ?? false);
        const cls = `flex items-center rounded-lg text-sm font-medium transition-all ${
            sidebarOpen ? 'gap-3 px-3 py-2' : 'justify-center py-2.5'
        } ${
            active
                ? "bg-[#1a1a1a] text-white" + (sidebarOpen ? " border-l-2 border-white -ml-[2px] pl-[14px]" : "")
                : "text-white hover:bg-[#1a1a1a]"
        }`;

        const inner = (
            <>
                <Icon className="w-4 h-4 flex-shrink-0" />
                {sidebarOpen && <span>{item.label}</span>}
                {sidebarOpen && item.pro && <ProBadge />}
            </>
        );

        if (item.external) {
            return (
                <a key={item.href} href={item.href} target="_blank" rel="noopener noreferrer" className={cls}>
                    {inner}
                </a>
            );
        }

        return (
            <Link key={item.href + item.label} href={item.href} className={cls}>
                {inner}
            </Link>
        );
    };

    return (
        <ChannelContext.Provider value={{
            channels,
            activeChannelId: selectedChannel?.id ?? "",
            setActiveChannelId: handleChannelChange,
            isLoading,
            refreshChannels,
        }}>
            <div className="flex h-screen w-screen bg-black text-white overflow-hidden">

                {/* ── Sidebar ── */}
                <aside className={`flex-shrink-0 transition-[width] duration-200 overflow-hidden bg-black border-r border-[#1a1a1a] flex flex-col ${sidebarOpen ? 'w-56' : 'w-14'}`}>

                    {/* Header: logo + toggle */}
                    {sidebarOpen ? (
                        <div className="h-14 flex items-center px-4 flex-shrink-0">
                            <Sparkles className="w-5 h-5 text-white flex-shrink-0" />
                            <span className="ml-2 text-base font-semibold text-white">PrognoT</span>
                            <button
                                onClick={() => setSidebarOpen(false)}
                                className="ml-auto p-1.5 rounded-lg text-[#525252] hover:text-white hover:bg-[#1a1a1a] transition-colors"
                                aria-label="Close sidebar"
                            >
                                <ChevronsLeft className="w-4 h-4" />
                            </button>
                        </div>
                    ) : (
                        <div className="h-14 flex items-center justify-center flex-shrink-0">
                            <button
                                onClick={() => setSidebarOpen(true)}
                                className="p-1.5 rounded-lg text-[#525252] hover:text-white hover:bg-[#1a1a1a] transition-colors"
                                aria-label="Open sidebar"
                            >
                                <ChevronsRight className="w-4 h-4" />
                            </button>
                        </div>
                    )}

                    {/* Nav */}
                    <nav className={`flex-1 py-3 overflow-y-auto flex flex-col ${sidebarOpen ? 'px-3' : 'px-2'}`}>

                        {/* Modules */}
                        <div className="space-y-0.5">
                            {sidebarOpen && (
                                <p className="text-[10px] font-semibold text-[#525252] px-3 mb-1.5 uppercase tracking-widest">
                                    Modules
                                </p>
                            )}
                            <div className={sidebarOpen ? 'pl-2 space-y-0.5' : 'space-y-0.5'}>
                                {modulesItems.map(renderNavItem)}
                            </div>
                        </div>

                        {/* Creative */}
                        <div className={`space-y-0.5 ${sidebarOpen ? 'mt-5' : 'mt-3'}`}>
                            {sidebarOpen && (
                                <p className="text-[10px] font-semibold text-[#525252] px-3 mb-1.5 uppercase tracking-widest">
                                    Creative
                                </p>
                            )}
                            <div className={sidebarOpen ? 'pl-2 space-y-0.5' : 'space-y-0.5'}>
                                {creativeItems.map(renderNavItem)}
                            </div>
                        </div>

                        {/* Bottom items — pushed to bottom */}
                        <div className={`mt-auto space-y-0.5 ${sidebarOpen ? 'pt-3' : 'pt-3'}`}>
                            {bottomItems.map(renderNavItem)}
                        </div>
                    </nav>
                </aside>

                {/* ── Main Area ── */}
                <div className="flex-1 flex flex-col overflow-hidden min-w-0">

                    {/* Top Bar — no border */}
                    <div className="h-14 flex items-center justify-end px-5 flex-shrink-0">

                        {/* Profile widget */}
                        <div className="relative" ref={profileRef}>
                            <button
                                onClick={() => setProfileOpen((v) => !v)}
                                className="flex items-center gap-3 px-3.5 py-2.5 border border-[#262626] hover:bg-[#1a1a1a] rounded-lg transition-colors"
                            >
                                {isLoading ? (
                                    <>
                                        <Skeleton className="w-9 h-9 rounded-full flex-shrink-0" />
                                        <div className="space-y-1.5">
                                            <Skeleton className="h-2.5 w-24" />
                                            <Skeleton className="h-2 w-16" />
                                        </div>
                                    </>
                                ) : (
                                    <>
                                        <div className="w-9 h-9 bg-[#262626] rounded-full flex items-center justify-center flex-shrink-0">
                                            <span className="text-sm font-medium text-white leading-none">{userInitials}</span>
                                        </div>
                                        <div className="flex flex-col items-start">
                                            <span className="text-sm text-white leading-tight">{truncatedEmail || '\u2026'}</span>
                                            <span className="text-xs text-white mt-0.5">
                                                {channels.length} channel{channels.length !== 1 ? 's' : ''}
                                            </span>
                                        </div>
                                    </>
                                )}
                            </button>

                            {/* Dropdown */}
                            {profileOpen && (
                                <div className="absolute right-0 top-full mt-2 w-60 bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl shadow-2xl z-50 py-2">

                                    {/* Profile header */}
                                    <div className="px-4 pb-3">
                                        <p className="text-[10px] font-semibold text-[#525252] uppercase tracking-widest mb-2">
                                            Profile
                                        </p>
                                        <div className="flex items-center gap-2.5">
                                            <div className="w-8 h-8 bg-[#262626] rounded-full flex items-center justify-center flex-shrink-0">
                                                <span className="text-xs font-medium text-white">{userInitials}</span>
                                            </div>
                                            <div className="flex flex-col min-w-0">
                                                <span className="text-sm font-medium text-white truncate">{userName || userEmail}</span>
                                                <span className="text-xs text-[#525252] truncate">{userEmail}</span>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Channel chips */}
                                    {channels.length > 0 && (
                                        <div className="px-4 pb-3">
                                            <p className="text-[10px] font-semibold text-[#525252] uppercase tracking-widest mb-2">
                                                Channels
                                            </p>
                                            <div className="flex flex-wrap gap-1.5">
                                                {channels.map((ch) => (
                                                    <button
                                                        key={ch.id}
                                                        onClick={() => { handleChannelChange(ch.id); setProfileOpen(false); }}
                                                        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                                                            selectedChannel?.id === ch.id
                                                                ? 'bg-white text-black'
                                                                : 'bg-[#1a1a1a] text-white hover:bg-[#262626]'
                                                        }`}
                                                    >
                                                        {selectedChannel?.id === ch.id && <Check className="w-3 h-3 flex-shrink-0" />}
                                                        <span>{ch.display_name || ch.name || ch.id}</span>
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {/* Divider */}
                                    <div className="mx-4 border-t border-[#1a1a1a] mb-1" />

                                    {/* Actions */}
                                    <div className="py-1">
                                        <Link
                                            href="/dashboard/settings"
                                            onClick={() => setProfileOpen(false)}
                                            className="flex items-center gap-3 px-4 py-2 text-sm text-white hover:bg-[#1a1a1a] transition-colors"
                                        >
                                            <Plus className="w-4 h-4 flex-shrink-0 text-[#525252]" />
                                            Add channel
                                        </Link>
                                        <button className="w-full flex items-center gap-3 px-4 py-2 text-sm text-white hover:bg-[#1a1a1a] transition-colors text-left">
                                            <CreditCard className="w-4 h-4 flex-shrink-0 text-[#525252]" />
                                            Credit usage
                                        </button>
                                        <Link
                                            href="/dashboard/settings"
                                            onClick={() => setProfileOpen(false)}
                                            className="flex items-center gap-3 px-4 py-2 text-sm text-white hover:bg-[#1a1a1a] transition-colors"
                                        >
                                            <Settings className="w-4 h-4 flex-shrink-0 text-[#525252]" />
                                            Settings
                                        </Link>
                                        <button className="w-full flex items-center gap-3 px-4 py-2 text-sm text-white hover:bg-[#1a1a1a] transition-colors text-left">
                                            <Globe className="w-4 h-4 flex-shrink-0 text-[#525252]" />
                                            Language
                                            <span className="ml-auto text-sm text-[#525252]">EN</span>
                                        </button>
                                    </div>

                                    <div className="mx-4 border-t border-[#1a1a1a] mt-1 mb-1" />

                                    <div className="py-1">
                                        <button
                                            onClick={handleSignOut}
                                            className="w-full flex items-center gap-3 px-4 py-2 text-sm text-white hover:bg-[#1a1a1a] transition-colors text-left"
                                        >
                                            <LogOut className="w-4 h-4 flex-shrink-0 text-[#525252]" />
                                            Log out
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Content */}
                    <main className="flex-1 overflow-y-auto bg-black">
                        {children}
                    </main>
                </div>

            </div>
        </ChannelContext.Provider>
    );
}
