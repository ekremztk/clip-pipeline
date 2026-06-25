"use client";

import type { ReactNode } from "react";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Box,
  LayoutDashboard,
  Menu,
  Package,
  Receipt,
  ShoppingCart,
  Tag,
  TrendingUp,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

type NavItem = { label: string; href: string; icon: LucideIcon };

const navItems: NavItem[] = [
  { label: "Overview", href: "/dashboard", icon: LayoutDashboard },
  { label: "Fırsat Ürünler", href: "/dashboard/deals", icon: Tag },
  { label: "Ürünler", href: "/dashboard/products", icon: Box },
  { label: "Alımlar", href: "/dashboard/purchases", icon: ShoppingCart },
  { label: "Satışlar", href: "/dashboard/sales", icon: Package },
  { label: "Giderler", href: "/dashboard/expenses", icon: Receipt },
  { label: "Kazanç", href: "/dashboard/earnings", icon: TrendingUp },
];

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();

  return (
    <>
      <aside
        className={`fixed left-0 top-0 z-40 flex h-screen w-[260px] flex-col border-r border-[#e5e5e5] bg-[#fafafa] text-[#171717] transition-transform duration-200 ease-out lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-[#e5e5e5] px-6">
          <Link href="/dashboard" className="flex items-center gap-2.5 font-semibold">
            <img src="/favicon.png" alt="Prognot" className="h-8 w-8 object-contain invert" />
            <span className="text-base tracking-tight">ProgSell</span>
          </Link>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-[#f0f0f0] lg:hidden"
            aria-label="Close menu"
          >
            <X size={18} />
          </button>
        </div>

        <nav className="sell-scrollbar flex-1 space-y-1 overflow-y-auto overscroll-contain p-4">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onClose}
                className={`flex items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors ${
                  active
                    ? "bg-[#f0f0f0] font-medium text-[#171717]"
                    : "text-[#525252] hover:bg-[#f0f0f0] hover:text-[#171717]"
                }`}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </aside>
      {open ? (
        <button
          type="button"
          aria-label="Close menu overlay"
          onClick={onClose}
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
        />
      ) : null}
    </>
  );
}

function MobileMenuButton({ onOpenMenu }: { onOpenMenu: () => void }) {
  return (
    <div className="flex h-12 items-center px-4 lg:hidden">
      <button
        type="button"
        onClick={onOpenMenu}
        className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-[#e5e5e5] hover:bg-[#f5f5f5]"
        aria-label="Open menu"
      >
        <Menu size={18} />
      </button>
    </div>
  );
}

export default function SellShell({ children }: { children: ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="h-screen overflow-hidden bg-white text-[#171717]">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex h-screen min-w-0 flex-col lg:ml-[260px]">
        <MobileMenuButton onOpenMenu={() => setSidebarOpen(true)} />
        <main className="sell-scrollbar flex-1 overflow-y-auto overflow-x-hidden overscroll-contain p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
