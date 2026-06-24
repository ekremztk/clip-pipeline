import {
    Activity,
    BarChart3,
    Bot,
    CalendarDays,
    CreditCard,
    Database,
    FileText,
    KeyRound,
    LayoutDashboard,
    MessageSquare,
    Package,
    Settings,
    Shield,
    SlidersHorizontal,
    Tv,
    Users,
    WalletCards,
    type LucideIcon,
} from "lucide-react";

export type AdminUser = {
    is_admin: boolean;
    user_id: string;
    email: string | null;
    role: string;
};

export type NavItem = {
    label: string;
    href: string;
    icon: LucideIcon;
    badge?: string;
};

export type NavGroup = {
    label: string;
    items: NavItem[];
};

export const navGroups: NavGroup[] = [
    {
        label: "Dashboards",
        items: [
            { label: "Overview", href: "/admin", icon: LayoutDashboard },
            { label: "Revenue", href: "/admin/revenue", icon: BarChart3 },
            { label: "Costs", href: "/admin/costs", icon: WalletCards },
        ],
    },
    {
        label: "Business",
        items: [
            { label: "Channels", href: "/admin/channels", icon: Tv },
            { label: "Customers", href: "/admin/customers", icon: Users },
            { label: "Credits", href: "/admin/credits", icon: WalletCards },
            { label: "Billing", href: "/admin/billing", icon: CreditCard },
            { label: "Calendar", href: "/admin/calendar", icon: CalendarDays },
        ],
    },
    {
        label: "Platform",
        items: [
            { label: "API", href: "/admin/api", icon: KeyRound },
            { label: "Pipeline", href: "/admin/pipeline", icon: Activity },
            { label: "Stock", href: "/admin/stock", icon: Package },
            { label: "Storage", href: "/admin/storage", icon: Database },
        ],
    },
    {
        label: "Workspace",
        items: [
            { label: "Chat", href: "/admin/chat", icon: MessageSquare },
            { label: "Users", href: "/admin/users", icon: Shield },
            { label: "Settings", href: "/admin/settings", icon: Settings },
        ],
    },
];

export const revenueRows: Array<{ source: string; type: string; revenue: string; cost: string; net: string; status: string }> = [];

export const expenseBreakdown: Array<{ label: string; value: string; pct: number; color: string }> = [];

export const channels: Array<{ name: string; handle: string; subs: string; revenue: string; stock: number; posted: number; status: string; nextUpload: string }> = [];

export const customers: Array<{ name: string; contact: string; plan: string; revenue: string; clips: number; status: string }> = [];

export const apiClients: Array<{ name: string; key: string; usage: string; spend: string; revenue: string; status: string }> = [];

export const modelCosts: Array<{ vendor: string; model: string; unit: string; input: string; output: string; status: string }> = [];

export const invoices: Array<{ number: string; customer: string; amount: string; due: string; status: string }> = [];

export const calendarEvents: Array<{ time: string; title: string; owner: string; type: string }> = [];

export const chatMessages: Array<{ role: string; text: string }> = [];

export const adminUsers: Array<{ name: string; email: string; role: string; status: string }> = [];

export const pipelineRows: Array<{ name: string; scope: string; health: string; lastRun: string; cost: string }> = [];

export const stockRows: Array<{ channel: string; ready: number; review: number; rejected: number; days: number; status: string }> = [];

export const storageRows: Array<{ bucket: string; objects: number; size: string; status: string }> = [];

export const recentActivity: Array<{ title: string; detail: string; time: string; icon: LucideIcon }> = [];

export const settingGroups = [
    { title: "Cost formulas", desc: "Token, minute, GPU, and storage pricing", icon: SlidersHorizontal },
    { title: "AI assistant memory", desc: "Admin RAG scope and retained context", icon: Bot },
    { title: "Exports", desc: "Finance CSV, customer reports, and channel summaries", icon: FileText },
];
