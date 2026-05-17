"use client";

import { CheckCircle2, Clock3, Loader2, XCircle } from "lucide-react";

export type ProvisionJob = {
    id: string;
    name: string;
    status: string;
    current_step?: string | null;
    current_step_number?: number | null;
    progress_pct?: number | null;
    variant_modes?: string[];
    item_count?: number | null;
    completed_item_count?: number | null;
    selected_variant_count?: number | null;
    created_at?: string | null;
    updated_at?: string | null;
    completed_at?: string | null;
    error_message?: string | null;
};

export type ProvisionItem = {
    id: string;
    input_title: string | null;
    input_description?: string | null;
    input_video_url: string;
    main_person: string | null;
    status: string;
    current_step?: string | null;
    progress_pct?: number | null;
    created_at?: string | null;
    updated_at?: string | null;
    completed_at?: string | null;
    error_message?: string | null;
};

export type ProvisionVariant = {
    id: string;
    provision_item_id: string;
    provision_job_id: string;
    variant_mode: string;
    status: string;
    current_step?: string | null;
    progress_pct?: number | null;
    review_status: string;
    output_video_url: string | null;
    feedback_note?: string | null;
    score?: number | null;
    duration_s?: number | null;
    edit_plan?: Record<string, any> | null;
    validation_report?: Record<string, any> | null;
    error_message?: string | null;
    created_at?: string | null;
    updated_at?: string | null;
    completed_at?: string | null;
};

export type ProvisionJobDetail = ProvisionJob & {
    items: ProvisionItem[];
    variants: ProvisionVariant[];
};

export function formatDate(value?: string | null) {
    if (!value) return "Just now";
    const time = new Date(value).getTime();
    if (Number.isNaN(time)) return value;
    const diff = Date.now() - time;
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return "Just now";
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days}d ago`;
    return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function formatDuration(seconds?: number | null) {
    if (!seconds || seconds <= 0) return "0:00";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export function readableStatus(value?: string | null) {
    return (value || "unknown").replace(/_/g, " ");
}

export function statusColors(status?: string | null) {
    const value = status || "unknown";
    if (value === "completed") {
        return { color: "#86efac", background: "rgba(34,197,94,0.12)", border: "rgba(34,197,94,0.22)" };
    }
    if (value === "failed" || value === "cancelled" || value === "rejected") {
        return { color: "#fca5a5", background: "rgba(239,68,68,0.10)", border: "rgba(239,68,68,0.22)" };
    }
    if (value === "processing" || value === "planning" || value === "rendering") {
        return { color: "#faf9f5", background: "rgba(250,249,245,0.08)", border: "rgba(250,249,245,0.14)" };
    }
    return { color: "#ababab", background: "rgba(250,249,245,0.05)", border: "rgba(250,249,245,0.08)" };
}

export function StatusPill({ status }: { status?: string | null }) {
    const colors = statusColors(status);
    return (
        <span
            className="inline-flex items-center rounded-lg border px-2 py-1 text-xs font-semibold capitalize"
            style={{ color: colors.color, background: colors.background, borderColor: colors.border }}
        >
            {readableStatus(status)}
        </span>
    );
}

export function ProgressBar({ value }: { value?: number | null }) {
    const progress = Math.max(0, Math.min(100, value ?? 0));
    return (
        <div className="h-1.5 overflow-hidden rounded-full" style={{ background: "rgba(250,249,245,0.06)" }}>
            <div className="h-full rounded-full" style={{ width: `${progress}%`, background: "#faf9f5" }} />
        </div>
    );
}

export function StateIcon({ status }: { status?: string | null }) {
    if (status === "completed") return <CheckCircle2 size={16} style={{ color: "#86efac" }} />;
    if (status === "failed" || status === "cancelled") return <XCircle size={16} style={{ color: "#fca5a5" }} />;
    if (status === "processing" || status === "planning" || status === "rendering") {
        return <Loader2 size={16} className="animate-spin" style={{ color: "#faf9f5" }} />;
    }
    return <Clock3 size={16} style={{ color: "#737373" }} />;
}

export function shortId(value?: string | null) {
    return value ? value.slice(0, 8) : "unknown";
}

