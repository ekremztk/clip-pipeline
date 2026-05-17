"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, FileVideo, Loader2, Plus, RefreshCw, Sparkles } from "lucide-react";
import { authFetch } from "@/lib/api";
import { useChannel } from "@/app/dashboard/layout";
import { formatDate, ProgressBar, ProvisionJob, StateIcon, StatusPill } from "./_shared";

export default function ProvisionJobsPage() {
    const { activeChannelId, isLoading: channelLoading } = useChannel();
    const [jobs, setJobs] = useState<ProvisionJob[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const activeCount = useMemo(
        () => jobs.filter(job => ["queued", "processing"].includes(job.status)).length,
        [jobs],
    );

    const loadJobs = async () => {
        if (!activeChannelId) return;
        setLoading(true);
        setError(null);
        try {
            const res = await authFetch(`/provision/jobs?channel_id=${encodeURIComponent(activeChannelId)}&limit=200`);
            if (!res.ok) {
                const body = await res.text().catch(() => "");
                throw new Error(body || `HTTP ${res.status}`);
            }
            const data = await res.json();
            setJobs(Array.isArray(data) ? data : []);
        } catch (err: any) {
            setError(err?.message || "Failed to load provision jobs");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (!activeChannelId || channelLoading) return;
        loadJobs();
    }, [activeChannelId, channelLoading]);

    return (
        <main className="min-h-screen px-6 py-8" style={{ background: "#141413" }}>
            <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
                <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                    <div>
                        <Link
                            href="/dashboard/provision"
                            className="mb-4 inline-flex items-center gap-2 text-sm font-medium hover:underline"
                            style={{ color: "#ababab" }}
                        >
                            <ArrowLeft size={15} />
                            Provision
                        </Link>
                        <div className="mb-3 flex items-center gap-2">
                            <span
                                className="flex h-8 w-8 items-center justify-center rounded-xl"
                                style={{ background: "rgba(250,249,245,0.08)", color: "#faf9f5" }}
                            >
                                <Sparkles size={16} />
                            </span>
                            <span className="text-xs font-semibold uppercase tracking-[0.22em]" style={{ color: "#ababab" }}>
                                Last Editor
                            </span>
                        </div>
                        <h1 className="text-3xl font-semibold tracking-tight" style={{ color: "#faf9f5" }}>
                            Provision Jobs
                        </h1>
                        <p className="mt-2 text-sm" style={{ color: "#737373" }}>
                            Review every final-edit run and open each job to compare generated variants.
                        </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                        <Link
                            href="/dashboard/provision"
                            className="inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-colors hover:bg-white/90"
                            style={{ background: "#faf9f5", color: "#141413" }}
                        >
                            <Plus size={15} />
                            New run
                        </Link>
                        <button
                            type="button"
                            onClick={loadJobs}
                            disabled={loading}
                            className="inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-colors hover:bg-white/5 disabled:opacity-60"
                            style={{ color: "#faf9f5", border: "1px solid rgba(250,249,245,0.08)", background: "rgba(250,249,245,0.03)" }}
                        >
                            {loading ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
                            Refresh
                        </button>
                    </div>
                </div>

                {error && (
                    <div
                        className="rounded-xl px-4 py-3 text-sm"
                        style={{ color: "#fca5a5", background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.18)" }}
                    >
                        {error}
                    </div>
                )}

                <div className="grid gap-3 md:grid-cols-4">
                    {[
                        ["Total jobs", jobs.length],
                        ["Active", activeCount],
                        ["Completed", jobs.filter(job => job.status === "completed").length],
                        ["Selected variants", jobs.reduce((sum, job) => sum + (job.selected_variant_count || 0), 0)],
                    ].map(([label, value]) => (
                        <div
                            key={label}
                            className="rounded-2xl p-4"
                            style={{ background: "#1c1c1b", border: "1px solid rgba(250,249,245,0.06)" }}
                        >
                            <p className="text-xs uppercase tracking-[0.18em]" style={{ color: "#737373" }}>{label}</p>
                            <p className="mt-2 text-2xl font-semibold" style={{ color: "#faf9f5" }}>{value}</p>
                        </div>
                    ))}
                </div>

                {loading && jobs.length === 0 ? (
                    <div className="flex min-h-[360px] items-center justify-center">
                        <Loader2 size={24} className="animate-spin" style={{ color: "#faf9f5" }} />
                    </div>
                ) : jobs.length === 0 ? (
                    <div
                        className="flex min-h-[360px] flex-col items-center justify-center rounded-2xl border border-dashed px-6 text-center"
                        style={{ borderColor: "rgba(250,249,245,0.12)", background: "rgba(250,249,245,0.02)" }}
                    >
                        <FileVideo size={34} style={{ color: "rgba(250,249,245,0.32)" }} />
                        <p className="mt-4 text-sm font-semibold" style={{ color: "#faf9f5" }}>No provision jobs</p>
                        <p className="mt-1 text-sm" style={{ color: "#737373" }}>Create a run from the Provision page.</p>
                    </div>
                ) : (
                    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                        {jobs.map(job => (
                            <Link
                                key={job.id}
                                href={`/dashboard/provision/jobs/${job.id}`}
                                className="rounded-2xl p-4 transition-transform duration-200 hover:-translate-y-0.5"
                                style={{ background: "#1c1c1b", border: "1px solid rgba(250,249,245,0.06)" }}
                            >
                                <div className="flex items-start justify-between gap-4">
                                    <div className="min-w-0">
                                        <div className="flex items-center gap-2">
                                            <StateIcon status={job.status} />
                                            <p className="truncate text-sm font-semibold" style={{ color: "#faf9f5" }}>
                                                {job.name}
                                            </p>
                                        </div>
                                        <p className="mt-2 text-xs" style={{ color: "#737373" }}>
                                            Updated {formatDate(job.updated_at || job.created_at)}
                                        </p>
                                    </div>
                                    <StatusPill status={job.status} />
                                </div>

                                <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                                    {[
                                        ["Items", job.item_count || 0],
                                        ["Done", job.completed_item_count || 0],
                                        ["Selected", job.selected_variant_count || 0],
                                    ].map(([label, value]) => (
                                        <div key={label} className="rounded-lg px-3 py-2" style={{ background: "rgba(250,249,245,0.035)" }}>
                                            <p className="text-xs" style={{ color: "#737373" }}>{label}</p>
                                            <p className="mt-1 text-sm font-semibold" style={{ color: "#faf9f5" }}>{value}</p>
                                        </div>
                                    ))}
                                </div>

                                <div className="mt-4">
                                    <div className="mb-1 flex items-center justify-between text-xs">
                                        <span className="capitalize" style={{ color: "#737373" }}>{job.current_step || "draft"}</span>
                                        <span style={{ color: "#737373" }}>{job.progress_pct ?? 0}%</span>
                                    </div>
                                    <ProgressBar value={job.progress_pct} />
                                </div>
                            </Link>
                        ))}
                    </div>
                )}
            </div>
        </main>
    );
}

