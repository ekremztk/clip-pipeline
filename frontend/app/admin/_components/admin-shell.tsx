"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Bell, ChevronDown, Loader2, LogOut, Menu, Rocket, Search, X } from "lucide-react";

import { authFetch } from "@/lib/api";
import { AdminUser, navGroups } from "./admin-data";

function initials(email: string | null) {
    if (!email) return "AD";
    const [name] = email.split("@");
    const parts = name.split(/[._-]/).filter(Boolean);
    return (parts[0]?.[0] ?? "A").concat(parts[1]?.[0] ?? "D").toUpperCase();
}

function Sidebar({ adminUser, open, onClose }: { adminUser: AdminUser; open: boolean; onClose: () => void }) {
    const pathname = usePathname();

    return (
        <>
            <aside
                className={`fixed left-0 top-0 z-40 flex h-screen w-[260px] flex-col border-r border-[#e5e5e5] bg-[#fafafa] text-[#171717] transition-transform duration-200 ease-out lg:translate-x-0 ${
                    open ? "translate-x-0" : "-translate-x-full"
                }`}
            >
                <div className="flex h-16 shrink-0 items-center justify-between border-b border-[#e5e5e5] px-6">
                    <Link href="/admin" className="flex items-center gap-2.5 font-semibold">
                        <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-[#171717] text-white">
                            <Rocket size={18} />
                        </span>
                        <span className="text-base tracking-tight">Prognot</span>
                    </Link>
                    <button type="button" onClick={onClose} className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-[#f0f0f0] lg:hidden" aria-label="Close menu">
                        <X size={18} />
                    </button>
                </div>

                <nav aria-label="Admin navigation" className="admin-scrollbar flex-1 space-y-6 overflow-y-auto overscroll-contain p-4">
                    {navGroups.map((group) => (
                        <div key={group.label}>
                            <p className="px-2 pb-2 text-xs uppercase tracking-wider text-[#5f5f5f]">{group.label}</p>
                            <ul className="space-y-1">
                                {group.items.map((item) => {
                                    const Icon = item.icon;
                                    const active = item.href === "/admin" ? pathname === "/admin" : pathname.startsWith(item.href);
                                    return (
                                        <li key={item.href}>
                                            <Link
                                                href={item.href}
                                                onClick={onClose}
                                                className={`flex items-center gap-3 rounded-md px-2 py-2 text-sm transition-colors ${
                                                    active ? "bg-[#f0f0f0] text-[#171717]" : "text-[#171717] hover:bg-[#f0f0f0] hover:text-[#171717]"
                                                }`}
                                            >
                                                <Icon size={18} />
                                                <span>{item.label}</span>
                                                {item.badge ? <span className="ml-auto rounded-full bg-[#171717] px-2 py-0.5 text-[10px] font-semibold text-white">{item.badge}</span> : null}
                                            </Link>
                                        </li>
                                    );
                                })}
                            </ul>
                        </div>
                    ))}
                </nav>

                <div className="shrink-0 border-t border-[#e5e5e5] p-3">
                    <div className="flex items-center gap-3 rounded-md px-2 py-2">
                        <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#0369a1] text-xs font-semibold text-white">{initials(adminUser.email)}</span>
                        <div className="min-w-0 flex-1">
                            <div className="truncate text-sm font-medium">{adminUser.email ?? "Admin user"}</div>
                            <div className="truncate text-xs capitalize text-[#737373]">{adminUser.role}</div>
                        </div>
                        <Link href="/dashboard" aria-label="Back to dashboard" className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-[#f0f0f0]">
                            <LogOut size={16} />
                        </Link>
                    </div>
                </div>
            </aside>
            {open ? <button type="button" aria-label="Close menu overlay" onClick={onClose} className="fixed inset-0 z-30 bg-black/50 lg:hidden" /> : null}
        </>
    );
}

function Header({ adminUser, onOpenMenu }: { adminUser: AdminUser; onOpenMenu: () => void }) {
    return (
        <header className="z-20 flex h-16 shrink-0 items-center justify-between gap-2 border-b border-[#e5e5e5] bg-white/90 px-4 backdrop-blur lg:px-6">
            <div className="flex min-w-0 flex-1 items-center gap-2">
                <button type="button" onClick={onOpenMenu} className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-[#e5e5e5] hover:bg-[#f5f5f5] lg:hidden" aria-label="Open menu">
                    <Menu size={18} />
                </button>
                <button type="button" className="group flex h-9 max-w-md flex-1 items-center gap-2 rounded-md border border-[#e5e5e5] bg-white px-3 text-sm text-[#737373] transition-colors hover:text-[#171717]">
                    <Search size={16} />
                    <span className="flex-1 text-left">Search...</span>
                    <kbd className="hidden h-5 items-center rounded border border-[#e5e5e5] bg-[#f5f5f5] px-1.5 font-mono text-[10px] text-[#737373] sm:inline-flex">⌘K</kbd>
                </button>
            </div>

            <div className="flex items-center gap-2">
                <div className="hidden h-9 items-center gap-1.5 rounded-md border border-[#e5e5e5] px-2.5 text-xs text-[#737373] md:inline-flex">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-[#16a34a]" />
                    <span>3 online</span>
                </div>
                <button type="button" className="relative inline-flex h-9 w-9 items-center justify-center rounded-md border border-[#e5e5e5] hover:bg-[#f5f5f5]" aria-label="Notifications">
                    <Bell size={18} />
                    <span className="absolute -right-1 -top-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[#dc2626] px-1 text-[10px] font-semibold text-white ring-2 ring-white">4</span>
                </button>
                <button type="button" className="hidden h-9 items-center gap-2 rounded-md px-2 hover:bg-[#f5f5f5] sm:flex">
                    <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-[#0369a1] text-xs font-semibold text-white">{initials(adminUser.email)}</span>
                    <span className="max-w-[140px] truncate text-sm font-medium">{adminUser.email?.split("@")[0] ?? "admin"}</span>
                    <ChevronDown size={14} className="text-[#737373]" />
                </button>
            </div>
        </header>
    );
}

export default function AdminShell({ children }: { children: ReactNode }) {
    const router = useRouter();
    const [adminUser, setAdminUser] = useState<AdminUser | null>(null);
    const [loading, setLoading] = useState(true);
    const [sidebarOpen, setSidebarOpen] = useState(false);

    useEffect(() => {
        let cancelled = false;

        async function checkAdmin() {
            try {
                const res = await authFetch("/admin/me");
                if (cancelled) return;

                if (!res.ok) {
                    router.replace("/dashboard");
                    return;
                }

                setAdminUser(await res.json());
            } catch {
                if (!cancelled) router.replace("/dashboard");
            } finally {
                if (!cancelled) setLoading(false);
            }
        }

        checkAdmin();
        return () => {
            cancelled = true;
        };
    }, [router]);

    const visibleUser = useMemo(() => adminUser, [adminUser]);

    if (loading) {
        return (
            <main className="flex min-h-screen items-center justify-center bg-white text-[#171717]">
                <div className="flex items-center gap-3 text-sm text-[#737373]">
                    <Loader2 size={18} className="animate-spin" />
                    Checking admin access
                </div>
            </main>
        );
    }

    if (!visibleUser) return null;

    return (
        <div className="h-screen overflow-hidden bg-white text-[#171717]">
            <Sidebar adminUser={visibleUser} open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
            <div className="flex h-screen min-w-0 flex-col lg:ml-[260px]">
                <Header adminUser={visibleUser} onOpenMenu={() => setSidebarOpen(true)} />
                <main id="main-content" tabIndex={-1} className="admin-scrollbar flex-1 overflow-y-auto overflow-x-hidden overscroll-contain p-6">
                    {children}
                </main>
            </div>
        </div>
    );
}
