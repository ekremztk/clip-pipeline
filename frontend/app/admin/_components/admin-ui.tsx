import type { ReactNode } from "react";
import { ArrowUpRight, ChevronRight, Search, type LucideIcon } from "lucide-react";

export function PageHeader({
    title,
    description,
    action,
}: {
    title: string;
    description: string;
    action?: ReactNode;
}) {
    return (
        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
                <h1 className="text-2xl font-bold tracking-tight text-[#171717]">{title}</h1>
                <p className="mt-1 text-sm text-[#737373]">{description}</p>
            </div>
            {action ? <div className="flex items-center gap-2">{action}</div> : null}
        </div>
    );
}

export function Button({
    children,
    variant = "primary",
}: {
    children: ReactNode;
    variant?: "primary" | "secondary";
}) {
    return (
        <button
            type="button"
            className={
                variant === "primary"
                    ? "inline-flex h-9 items-center justify-center gap-2 rounded-md bg-[#171717] px-3 text-sm font-medium text-white hover:bg-[#2a2a2a]"
                    : "inline-flex h-9 items-center justify-center gap-2 rounded-md border border-[#e5e5e5] bg-white px-3 text-sm font-medium text-[#171717] hover:bg-[#f5f5f5]"
            }
        >
            {children}
        </button>
    );
}

export function SectionCard({ children, className = "" }: { children: ReactNode; className?: string }) {
    return <div className={`rounded-lg border border-[#e5e5e5] bg-white ${className}`}>{children}</div>;
}

export function SectionHeader({
    title,
    description,
    action,
}: {
    title: string;
    description?: string;
    action?: ReactNode;
}) {
    return (
        <div className="flex items-center justify-between border-b border-[#e5e5e5] p-4">
            <div>
                <h2 className="font-semibold text-[#171717]">{title}</h2>
                {description ? <p className="text-sm text-[#737373]">{description}</p> : null}
            </div>
            {action}
        </div>
    );
}

function linePath(values: number[]) {
    const width = 132;
    const height = 42;
    const max = Math.max(...values);
    const min = Math.min(...values);
    const range = Math.max(max - min, 1);
    return values
        .map((value, index) => {
            const x = (index / (values.length - 1)) * width;
            const y = height - 5 - ((value - min) / range) * 32;
            return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
        })
        .join(" ");
}

export function MetricCard({
    label,
    value,
    delta,
    color,
    icon: Icon,
    spark,
}: {
    label: string;
    value: string;
    delta: string;
    color: string;
    icon: LucideIcon;
    spark: number[];
}) {
    const path = linePath(spark);
    return (
        <div className="flex min-h-[168px] flex-col gap-3 rounded-lg border border-[#e5e5e5] bg-white p-4">
            <div className="flex items-start justify-between">
                <p className="text-sm font-medium text-[#737373]">{label}</p>
                <span className="inline-flex h-9 w-9 items-center justify-center rounded-md" style={{ backgroundColor: `${color}1a`, color }}>
                    <Icon size={18} />
                </span>
            </div>
            <div>
                <p className="text-2xl font-bold tracking-tight text-[#171717]">{value}</p>
                <p className="mt-1 flex items-center gap-1 text-xs" style={{ color }}>
                    <ArrowUpRight size={12} />
                    <span>{delta}</span>
                </p>
            </div>
            <svg viewBox="0 0 132 42" preserveAspectRatio="none" className="mt-auto h-11 w-full overflow-visible" aria-hidden="true">
                <path d={`${path} L132 42 L0 42 Z`} fill={color} opacity="0.08" />
                <path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
        </div>
    );
}

export function StatusBadge({ children, tone = "neutral" }: { children: ReactNode; tone?: "success" | "warning" | "danger" | "info" | "neutral" }) {
    const styles = {
        success: "bg-[#dcfce7] text-[#166534]",
        warning: "bg-[#fef3c7] text-[#92400e]",
        danger: "bg-[#fee2e2] text-[#991b1b]",
        info: "bg-[#e0f2fe] text-[#075985]",
        neutral: "bg-[#f5f5f5] text-[#404040]",
    };
    return <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[tone]}`}>{children}</span>;
}

export function ProgressBar({ value, color = "#171717" }: { value: number; color?: string }) {
    return (
        <div className="h-2 overflow-hidden rounded-full bg-[#f0f0f0]">
            <div className="h-full rounded-full" style={{ width: `${value}%`, backgroundColor: color }} />
        </div>
    );
}

export function SearchToolbar({ placeholder = "Search..." }: { placeholder?: string }) {
    return (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <label className="relative block w-full max-w-md">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#737373]" />
                <input
                    className="h-9 w-full rounded-md border border-[#e5e5e5] bg-white pl-9 pr-3 text-sm text-[#171717] placeholder:text-[#a3a3a3] focus:border-[#a3a3a3]"
                    placeholder={placeholder}
                />
            </label>
            <div className="flex items-center gap-2">
                <Button variant="secondary">Export</Button>
                <Button>New</Button>
            </div>
        </div>
    );
}

export function SimpleTable({
    columns,
    rows,
}: {
    columns: string[];
    rows: Array<Array<ReactNode>>;
}) {
    return (
        <div className="overflow-x-auto">
            <table className="w-full text-sm">
                <thead className="bg-[#f5f5f5]">
                    <tr className="text-left">
                        {columns.map((column, index) => (
                            <th key={column} className={`px-4 py-3 font-medium text-[#404040] ${index === columns.length - 1 ? "text-right" : ""}`}>
                                {column}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row, rowIndex) => (
                        <tr key={rowIndex} className="border-t border-[#e5e5e5] hover:bg-[#fafafa]">
                            {row.map((cell, cellIndex) => (
                                <td key={cellIndex} className={`px-4 py-3 ${cellIndex === row.length - 1 ? "text-right" : ""}`}>
                                    {cell}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export function PersonCell({ initials, title, subtitle, color = "#0369a1" }: { initials: string; title: string; subtitle: string; color?: string }) {
    return (
        <div className="flex items-center gap-3">
            <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white" style={{ backgroundColor: color }}>
                {initials}
            </span>
            <div className="min-w-0">
                <div className="truncate font-medium text-[#171717]">{title}</div>
                <div className="truncate text-xs text-[#737373]">{subtitle}</div>
            </div>
        </div>
    );
}

export function LinkCard({
    title,
    description,
    icon: Icon,
}: {
    title: string;
    description: string;
    icon: LucideIcon;
}) {
    return (
        <button type="button" className="flex w-full items-center gap-3 rounded-lg border border-[#e5e5e5] bg-white p-4 text-left hover:bg-[#fafafa]">
            <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-[#f5f5f5] text-[#171717]">
                <Icon size={18} />
            </span>
            <span className="min-w-0 flex-1">
                <span className="block font-medium text-[#171717]">{title}</span>
                <span className="block truncate text-sm text-[#737373]">{description}</span>
            </span>
            <ChevronRight size={16} className="text-[#737373]" />
        </button>
    );
}
