'use client';

import { useState, useEffect, useRef, createContext, useContext, Suspense } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
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
    Scissors,
    Plus,
    CreditCard,
    LogOut,
    HelpCircle,
    BookOpen,
    Zap,
    Check,
    ChevronLeft,
    ChevronRight,
    Bell,
    User,
    LayoutGrid,
    Download,
    Palette,
    Shield,
    Key,
    ArrowLeft,
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

const SETTINGS_SECTIONS = [
    { id: 'account',       icon: User,        label: 'Account' },
    { id: 'channels',      icon: LayoutGrid,  label: 'Channels' },
    { id: 'notifications', icon: Bell,        label: 'Notifications' },
    { id: 'api-keys',      icon: Key,         label: 'API Keys' },
    { id: 'clip-settings', icon: Scissors,    label: 'Clip Settings' },
    { id: 'export',        icon: Download,    label: 'Export' },
    { id: 'appearance',    icon: Palette,     label: 'Appearance' },
    { id: 'privacy',       icon: Shield,      label: 'Privacy & Data' },
];

function SettingsSidebarNav() {
    const searchParams = useSearchParams();
    const active = searchParams.get('section') ?? 'account';
    return (
        <nav className="flex flex-col gap-1 flex-1">
            {SETTINGS_SECTIONS.map((s) => {
                const Icon = s.icon;
                const on = active === s.id;
                return (
                    <Link
                        key={s.id}
                        href={`/dashboard/settings?section=${s.id}`}
                        className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all hover:bg-[rgba(250,249,245,0.08)]"
                        style={{
                            background: on ? "rgba(250,249,245,0.08)" : undefined,
                            color: "#faf9f5",
                        }}
                    >
                        <Icon size={16} strokeWidth={on ? 2.2 : 1.7} />
                        {s.label}
                    </Link>
                );
            })}
        </nav>
    );
}

function Skeleton({ className }: { className?: string }) {
    return (
        <div
            className={`rounded animate-pulse ${className ?? ""}`}
            style={{ background: "rgba(250,249,245,0.06)" }}
        />
    );
}

function ProBadge() {
    return (
        <span
            className="ml-auto text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md leading-none flex-shrink-0"
            style={{ background: "rgba(250,249,245,0.1)", color: "#faf9f5" }}
        >
            PRO
        </span>
    );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();

    const [sidebarOpen, setSidebarOpen] = useState(() => {
        if (typeof window !== 'undefined') {
            const saved = localStorage.getItem('sidebarOpen');
            return saved !== null ? saved === 'true' : true;
        }
        return true;
    });
    const [profileOpen, setProfileOpen] = useState(false);
    const [notifOpen, setNotifOpen] = useState(false);
    const [channels, setChannels] = useState<Channel[]>([]);
    const [selectedChannel, setSelectedChannel] = useState<Channel | null>(null);
    const [user, setUser] = useState<any>(null);
    const [isLoading, setIsLoading] = useState(true);

    const profileRef = useRef<HTMLDivElement>(null);
    const notifRef = useRef<HTMLDivElement>(null);

    // Persist sidebar state
    useEffect(() => {
        if (typeof window !== 'undefined') {
            localStorage.setItem('sidebarOpen', String(sidebarOpen));
        }
    }, [sidebarOpen]);

    // Close dropdowns on outside click
    useEffect(() => {
        function handleClickOutside(e: MouseEvent) {
            if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
                setProfileOpen(false);
            }
            if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
                setNotifOpen(false);
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

    const isSettings = pathname.startsWith('/dashboard/settings');

    const modulesItems = [
        { href: "/dashboard",                label: "Dashboard",      icon: Home,         exact: true,  pro: false },
        { href: "/dashboard/content-finder", label: "Content Finder", icon: Search,       exact: false, pro: false },
        { href: "https://edit.prognot.com",  label: "Editor",         icon: Scissors,     exact: false, pro: true,  external: true },
        ...(isAdmin ? [{ href: "/director",  label: "AI Director",    icon: Clapperboard, exact: false, pro: false }] : []),
    ];

    const creativeItems = [
        { href: "/dashboard/projects",    label: "Projects",    icon: FolderOpen, exact: false },
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

        const cls = `flex items-center rounded-xl text-sm font-medium transition-all ${
            sidebarOpen ? 'gap-3 px-3 py-2.5' : 'justify-center py-2.5'
        }`;

        const activeStyle = {
            background: active ? "rgba(250,249,245,0.08)" : undefined,
            color: "#faf9f5",
        };

        const hoverCls = !active ? "hover:bg-[rgba(250,249,245,0.08)]" : "";

        const inner = (
            <>
                <Icon size={18} strokeWidth={active ? 2.5 : 2} className="flex-shrink-0" />
                {sidebarOpen && <span className="flex-1 text-left">{item.label}</span>}
                {sidebarOpen && item.pro && <ProBadge />}
            </>
        );

        if (item.external) {
            return (
                <a
                    key={item.href}
                    href={item.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`${cls} ${hoverCls}`}
                    style={activeStyle}
                >
                    {inner}
                </a>
            );
        }

        return (
            <Link
                key={item.href + item.label}
                href={item.href}
                className={`${cls} ${hoverCls}`}
                style={activeStyle}
            >
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
            <div
                className="flex h-screen w-screen overflow-hidden"
                style={{ background: "#141413", color: "#faf9f5", fontFamily: "Inter, sans-serif" }}
            >

                {/* ── Sidebar ── */}
                <aside
                    className={`flex-shrink-0 flex flex-col h-screen transition-all duration-300 relative ${isSettings ? 'w-[220px]' : sidebarOpen ? 'w-[240px]' : 'w-[72px]'}`}
                    style={{ background: "#141413", borderRight: "1px solid rgba(250,249,245,0.05)" }}
                >
                    {isSettings ? (
                        /* ── Settings sidebar ── */
                        <div className="flex flex-col h-full px-4 py-6">
                            {/* Back button */}
                            <Link
                                href="/dashboard"
                                className="flex items-center gap-2.5 px-3 py-2 rounded-xl mb-6 text-sm font-medium transition-all hover:bg-white/5 w-fit"
                                style={{ color: "#ababab" }}
                            >
                                <ArrowLeft size={15} strokeWidth={2} />
                                <span>Dashboard</span>
                            </Link>

                            <p className="text-[11px] font-bold uppercase tracking-widest px-3 mb-3" style={{ color: "#ababab" }}>
                                Settings
                            </p>

                            <Suspense>
                                <SettingsSidebarNav />
                            </Suspense>
                        </div>
                    ) : (
                        /* ── Dashboard sidebar ── */
                        <>
                            {/* Logo */}
                            <div className={`flex items-center h-20 flex-shrink-0 mt-2 ${sidebarOpen ? 'px-6 gap-3' : 'justify-center'}`}>
                                <img
                                    src="/favicon.png"
                                    alt="Prognot"
                                    className="w-8 h-8 flex-shrink-0"
                                    style={{ objectFit: 'contain' }}
                                />
                                {sidebarOpen && (
                                    <span className="text-lg font-bold tracking-tight" style={{ color: "#faf9f5" }}>
                                        PrognoT
                                    </span>
                                )}
                            </div>

                            {/* Floating toggle button */}
                            <button
                                onClick={() => setSidebarOpen(!sidebarOpen)}
                                className="absolute z-10 w-6 h-6 rounded-full flex items-center justify-center transition-all hover:!text-[#faf9f5]"
                                style={{
                                    background: "#1c1c1b",
                                    color: "#ababab",
                                    top: "84px",
                                    right: "-12px",
                                    boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
                                    border: "1px solid rgba(250,249,245,0.05)",
                                }}
                                aria-label={sidebarOpen ? "Close sidebar" : "Open sidebar"}
                            >
                                {sidebarOpen
                                    ? <ChevronLeft size={12} strokeWidth={3} />
                                    : <ChevronRight size={12} strokeWidth={3} />
                                }
                            </button>

                            {/* Nav */}
                            <nav className={`flex-1 flex flex-col overflow-y-auto gap-1 py-6 ${sidebarOpen ? 'px-4' : 'px-3'}`}>
                                <div className="space-y-0.5">
                                    {sidebarOpen && (
                                        <p className="text-[11px] font-bold uppercase tracking-widest px-3 pb-2 mt-2" style={{ color: "#ababab" }}>
                                            Workspace
                                        </p>
                                    )}
                                    {modulesItems.map(renderNavItem)}
                                </div>
                                <div className={`space-y-0.5 ${sidebarOpen ? 'mt-8' : 'mt-4'}`}>
                                    {sidebarOpen && (
                                        <p className="text-[11px] font-bold uppercase tracking-widest px-3 pb-2" style={{ color: "#ababab" }}>
                                            Library
                                        </p>
                                    )}
                                    {creativeItems.map(renderNavItem)}
                                </div>
                                <div className="mt-auto pt-4 space-y-0.5">
                                    {bottomItems.map(renderNavItem)}
                                </div>
                            </nav>
                        </>
                    )}
                </aside>

                {/* ── Main Area ── */}
                <div className="flex-1 flex flex-col overflow-hidden min-w-0">

                    {/* Top Bar */}
                    <div
                        className="h-16 flex items-center justify-end px-6 flex-shrink-0 gap-4"
                        style={{ background: "#141413" }}
                    >
                        {/* Notification Bell */}
                        <div className="relative" ref={notifRef}>
                            <button
                                onClick={() => setNotifOpen(!notifOpen)}
                                className="w-9 h-9 rounded-full flex items-center justify-center transition-all hover:!text-[#faf9f5]"
                                style={{ color: "#ababab", background: "rgba(250,249,245,0.03)" }}
                            >
                                <Bell size={16} />
                            </button>

                            {notifOpen && (
                                <div
                                    className="absolute right-0 top-12 w-80 rounded-2xl z-50 overflow-hidden"
                                    style={{
                                        background: "#1c1c1b",
                                        border: "1px solid rgba(250,249,245,0.05)",
                                        boxShadow: "0 10px 40px -10px rgba(0,0,0,0.5)",
                                    }}
                                >
                                    <div
                                        className="px-5 py-4 flex items-center justify-between"
                                        style={{ borderBottom: "1px solid rgba(250,249,245,0.05)" }}
                                    >
                                        <span className="text-sm font-semibold" style={{ color: "#faf9f5" }}>Notifications</span>
                                        <button
                                            className="text-xs font-medium transition-colors hover:!text-[#faf9f5]"
                                            style={{ color: "#ababab" }}
                                        >
                                            Mark all read
                                        </button>
                                    </div>
                                    <div className="px-5 py-8 text-center">
                                        <Bell size={24} className="mx-auto mb-3" style={{ color: "rgba(250,249,245,0.15)" }} />
                                        <p className="text-sm font-medium" style={{ color: "#ababab" }}>No new notifications</p>
                                        <p className="text-xs mt-1" style={{ color: "#ababab" }}>You're all caught up</p>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Profile Widget */}
                        <div className="relative" ref={profileRef}>
                            <button
                                onClick={() => setProfileOpen((v) => !v)}
                                className="flex items-center gap-3 pl-2 pr-3 py-1.5 rounded-full transition-all hover:bg-white/5"
                                style={{
                                    background: profileOpen ? "rgba(250,249,245,0.05)" : "transparent",
                                    color: "#faf9f5",
                                }}
                            >
                                {isLoading ? (
                                    <>
                                        <Skeleton className="w-8 h-8 rounded-full flex-shrink-0" />
                                        <div className="space-y-1.5">
                                            <Skeleton className="h-2.5 w-20" />
                                            <Skeleton className="h-2 w-14" />
                                        </div>
                                    </>
                                ) : (
                                    <>
                                        <div
                                            className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm"
                                            style={{ background: "#faf9f5" }}
                                        >
                                            <span className="text-sm font-bold" style={{ color: "#141413" }}>
                                                {userInitials}
                                            </span>
                                        </div>
                                        <div className="text-left hidden sm:block">
                                            <div className="text-sm font-medium leading-tight" style={{ color: "#faf9f5" }}>
                                                {userName || truncatedEmail || '…'}
                                            </div>
                                            <div className="text-xs leading-tight mt-0.5" style={{ color: "#ababab" }}>
                                                {selectedChannel?.display_name ?? selectedChannel?.name ?? (channels.length > 0 ? channels[0].display_name : 'No channel')}
                                            </div>
                                        </div>
                                    </>
                                )}
                            </button>

                            {/* Profile Dropdown */}
                            {profileOpen && (
                                <div
                                    className="absolute right-0 top-14 w-64 rounded-2xl z-50 overflow-hidden"
                                    style={{
                                        background: "#1c1c1b",
                                        border: "1px solid rgba(250,249,245,0.05)",
                                        boxShadow: "0 10px 40px -10px rgba(0,0,0,0.5)",
                                    }}
                                >
                                    {/* Profile info */}
                                    <div className="p-5" style={{ borderBottom: "1px solid rgba(250,249,245,0.05)" }}>
                                        <div className="flex items-center gap-3">
                                            <div
                                                className="w-10 h-10 rounded-full flex items-center justify-center"
                                                style={{ background: "rgba(250,249,245,0.1)" }}
                                            >
                                                <span className="text-base font-bold" style={{ color: "#faf9f5" }}>{userInitials}</span>
                                            </div>
                                            <div className="min-w-0">
                                                <div className="text-sm font-semibold truncate" style={{ color: "#faf9f5" }}>
                                                    {userName || userEmail}
                                                </div>
                                                <div className="text-xs mt-0.5 truncate" style={{ color: "#ababab" }}>
                                                    {userEmail}
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Channels list */}
                                    <div className="p-2" style={{ borderBottom: "1px solid rgba(250,249,245,0.05)" }}>
                                        <div
                                            className="text-[10px] font-semibold uppercase tracking-wider px-3 py-2"
                                            style={{ color: "#ababab" }}
                                        >
                                            Your Channels
                                        </div>
                                        {channels.map((ch) => (
                                            <button
                                                key={ch.id}
                                                onClick={() => { handleChannelChange(ch.id); setProfileOpen(false); }}
                                                className="flex items-center gap-2.5 w-full px-3 py-2.5 rounded-xl transition-colors text-left hover:bg-white/5"
                                                style={{ color: selectedChannel?.id === ch.id ? "#faf9f5" : "rgba(250,249,245,0.5)" }}
                                            >
                                                <div className="w-4 flex items-center justify-center flex-shrink-0">
                                                    {selectedChannel?.id === ch.id && <Check size={14} style={{ color: "#faf9f5" }} />}
                                                </div>
                                                <span className="text-sm font-medium">{ch.display_name || ch.name || ch.id}</span>
                                            </button>
                                        ))}
                                        <Link
                                            href="/dashboard/settings"
                                            onClick={() => setProfileOpen(false)}
                                            className="flex items-center gap-2 w-full px-3 py-2.5 mt-1 rounded-xl transition-colors text-sm font-medium hover:bg-white/5"
                                            style={{ color: "#ababab" }}
                                        >
                                            <div className="w-4 flex items-center justify-center"><Plus size={14} /></div>
                                            Add new channel
                                        </Link>
                                    </div>

                                    {/* Actions */}
                                    <div className="p-2">
                                        <button
                                            className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl transition-colors text-sm font-medium hover:bg-white/5 hover:!text-[#faf9f5] text-left"
                                            style={{ color: "#ababab" }}
                                        >
                                            <CreditCard size={16} />
                                            <span className="flex-1 text-left">Billing & Credits</span>
                                        </button>
                                        <Link
                                            href="/dashboard/settings"
                                            onClick={() => setProfileOpen(false)}
                                            className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl transition-colors text-sm font-medium hover:bg-white/5 hover:!text-[#faf9f5]"
                                            style={{ color: "#ababab" }}
                                        >
                                            <Settings size={16} />
                                            <span className="flex-1">Account Settings</span>
                                        </Link>
                                        <div className="my-1" style={{ borderTop: "1px solid rgba(250,249,245,0.05)" }} />
                                        <button
                                            onClick={handleSignOut}
                                            className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl transition-colors text-sm font-medium hover:bg-red-500/10 text-left"
                                            style={{ color: "rgba(239,68,68,0.8)" }}
                                        >
                                            <LogOut size={16} />
                                            Log out
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Content */}
                    <main className="flex-1 overflow-y-auto" style={{ background: "#141413" }}>
                        {children}
                    </main>
                </div>

            </div>
        </ChannelContext.Provider>
    );
}

