"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Download, ExternalLink, Loader2, Play, RefreshCw, Sparkles } from "lucide-react";
import { authFetch } from "@/lib/api";
import { downloadProvisionVariant } from "../../download";
import {
    formatDate,
    formatDuration,
    ProgressBar,
    ProvisionJobDetail,
    ProvisionVariant,
    readableStatus,
    StateIcon,
    StatusPill,
} from "../_shared";

type ReviewStatus = "selected" | "manual_fix" | "rejected";

export default function ProvisionJobDetailPage() {
    const params = useParams<{ jobId: string }>();
    const jobId = params.jobId;
    const [job, setJob] = useState<ProvisionJobDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [starting, setStarting] = useState(false);
    const [reviewingVariantId, setReviewingVariantId] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    const variantsByItem = useMemo(() => {
        const grouped: Record<string, ProvisionVariant[]> = {};
        for (const variant of job?.variants || []) {
            grouped[variant.provision_item_id] = grouped[variant.provision_item_id] || [];
            grouped[variant.provision_item_id].push(variant);
        }
        return grouped;
    }, [job?.variants]);

    const loadJob = async () => {
        if (!jobId) return;
        setLoading(true);
        setError(null);
        try {
            const res = await authFetch(`/provision/jobs/${jobId}`);
            if (!res.ok) {
                const body = await res.text().catch(() => "");
                throw new Error(body || `HTTP ${res.status}`);
            }
            setJob(await res.json());
        } catch (err: any) {
            setError(err?.message || "Failed to load provision job");
        } finally {
            setLoading(false);
        }
    };

    const startNextItem = async () => {
        if (!jobId || starting) return;
        setStarting(true);
        setError(null);
        try {
            const res = await authFetch(`/provision/jobs/${jobId}/start`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ limit: 1 }),
            });
            if (!res.ok) {
                const body = await res.text().catch(() => "");
                throw new Error(body || `HTTP ${res.status}`);
            }
            await loadJob();
        } catch (err: any) {
            setError(err?.message || "Failed to start provision job");
        } finally {
            setStarting(false);
        }
    };

    const reviewVariant = async (variantId: string, reviewStatus: ReviewStatus) => {
        if (reviewingVariantId) return;
        setReviewingVariantId(variantId);
        setError(null);
        try {
            const res = await authFetch(`/provision/variants/${variantId}/review`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ review_status: reviewStatus }),
            });
            if (!res.ok) {
                const body = await res.text().catch(() => "");
                throw new Error(body || `HTTP ${res.status}`);
            }
            await loadJob();
        } catch (err: any) {
            setError(err?.message || "Failed to update variant review");
        } finally {
            setReviewingVariantId(null);
        }
    };

    const handleDownloadVariant = async (variantId: string) => {
        setError(null);
        try {
            await downloadProvisionVariant(variantId);
        } catch (err: any) {
            setError(err?.message || "Failed to download variant");
        }
    };

    useEffect(() => {
        loadJob();
    }, [jobId]);

    const active = !!job && ["queued", "processing"].includes(job.status);

    return (
        <main className="min-h-screen px-6 py-8" style={{ background: "#141413" }}>
            <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
                <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                    <div className="min-w-0">
                        <Link
                            href="/dashboard/provision/jobs"
                            className="mb-4 inline-flex items-center gap-2 text-sm font-medium hover:underline"
                            style={{ color: "#ababab" }}
                        >
                            <ArrowLeft size={15} />
                            Provision Jobs
                        </Link>
                        <div className="flex items-center gap-2">
                            <span
                                className="flex h-8 w-8 items-center justify-center rounded-xl"
                                style={{ background: "rgba(250,249,245,0.08)", color: "#faf9f5" }}
                            >
                                <Sparkles size={16} />
                            </span>
                            <StatusPill status={job?.status || "loading"} />
                        </div>
                        <h1 className="mt-3 truncate text-3xl font-semibold tracking-tight" style={{ color: "#faf9f5" }}>
                            {job?.name || "Provision Job"}
                        </h1>
                        <p className="mt-2 text-sm" style={{ color: "#737373" }}>
                            Updated {formatDate(job?.updated_at || job?.created_at)}
                        </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                        <button
                            type="button"
                            onClick={loadJob}
                            disabled={loading}
                            className="inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-colors hover:bg-white/5 disabled:opacity-60"
                            style={{ color: "#faf9f5", border: "1px solid rgba(250,249,245,0.08)", background: "rgba(250,249,245,0.03)" }}
                        >
                            {loading ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
                            Refresh
                        </button>
                        <button
                            type="button"
                            onClick={startNextItem}
                            disabled={starting || active || !job || job.items.length === 0}
                            className="inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-colors hover:bg-white/90 disabled:opacity-60"
                            style={{ background: "#faf9f5", color: "#141413" }}
                        >
                            {starting || active ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
                            Plan next item
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

                {loading && !job ? (
                    <div className="flex min-h-[420px] items-center justify-center">
                        <Loader2 className="animate-spin" size={24} style={{ color: "#faf9f5" }} />
                    </div>
                ) : !job ? (
                    <div
                        className="rounded-2xl p-8 text-center text-sm"
                        style={{ color: "#737373", background: "#1c1c1b", border: "1px solid rgba(250,249,245,0.06)" }}
                    >
                        Provision job not found.
                    </div>
                ) : (
                    <>
                        <div className="grid gap-3 md:grid-cols-4">
                            {[
                                ["Items", job.item_count || job.items.length],
                                ["Completed", job.completed_item_count || 0],
                                ["Variants", job.variants.length],
                                ["Selected", job.selected_variant_count || 0],
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

                        <div className="space-y-5">
                            {job.items.map(item => {
                                const variants = variantsByItem[item.id] || [];
                                return (
                                    <section
                                        key={item.id}
                                        className="rounded-2xl p-5"
                                        style={{ background: "#1c1c1b", border: "1px solid rgba(250,249,245,0.06)" }}
                                    >
                                        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                                            <div className="min-w-0">
                                                <div className="flex items-center gap-2">
                                                    <StateIcon status={item.status} />
                                                    <h2 className="truncate text-lg font-semibold" style={{ color: "#faf9f5" }}>
                                                        {item.input_title || "Provision item"}
                                                    </h2>
                                                </div>
                                                <p className="mt-1 text-sm" style={{ color: "#737373" }}>
                                                    {item.main_person || "No main person"} · {readableStatus(item.current_step || item.status)}
                                                </p>
                                            </div>
                                            <StatusPill status={item.status} />
                                        </div>

                                        <div className="mt-4 grid gap-4 lg:grid-cols-[260px_1fr]">
                                            <div
                                                className="overflow-hidden rounded-2xl"
                                                style={{ background: "#111110", border: "1px solid rgba(250,249,245,0.06)" }}
                                            >
                                                <video src={item.input_video_url} controls playsInline className="aspect-[9/16] w-full object-contain" />
                                                <div className="p-3">
                                                    <a
                                                        href={item.input_video_url}
                                                        target="_blank"
                                                        rel="noreferrer"
                                                        className="inline-flex items-center gap-1 text-xs font-semibold hover:underline"
                                                        style={{ color: "#ababab" }}
                                                    >
                                                        Source MP4
                                                        <ExternalLink size={12} />
                                                    </a>
                                                </div>
                                            </div>

                                            <div className="grid gap-3 xl:grid-cols-3">
                                                {variants.map(variant => (
                                                    <div
                                                        key={variant.id}
                                                        className="rounded-2xl p-3"
                                                        style={{ background: "rgba(250,249,245,0.03)", border: "1px solid rgba(250,249,245,0.06)" }}
                                                    >
                                                        <div className="flex items-center justify-between gap-2">
                                                            <div className="flex items-center gap-2">
                                                                <StateIcon status={variant.status} />
                                                                <p className="text-sm font-semibold capitalize" style={{ color: "#faf9f5" }}>
                                                                    {variant.variant_mode}
                                                                </p>
                                                            </div>
                                                            <StatusPill status={variant.status} />
                                                        </div>

                                                        <div className="mt-3 overflow-hidden rounded-xl" style={{ background: "#111110" }}>
                                                            {variant.output_video_url ? (
                                                                <video src={variant.output_video_url} controls playsInline className="aspect-[9/16] w-full object-contain" />
                                                            ) : (
                                                                <div className="flex aspect-[9/16] items-center justify-center">
                                                                    <Loader2 size={18} className={variant.status === "rendering" || variant.status === "planning" ? "animate-spin" : ""} style={{ color: "#737373" }} />
                                                                </div>
                                                            )}
                                                        </div>

                                                        <div className="mt-3 space-y-2">
                                                            <div className="flex items-center justify-between text-xs">
                                                                <span className="capitalize" style={{ color: "#737373" }}>{readableStatus(variant.current_step || variant.status)}</span>
                                                                <span style={{ color: "#737373" }}>{variant.progress_pct ?? 0}%</span>
                                                            </div>
                                                            <ProgressBar value={variant.progress_pct} />
                                                            <div className="flex items-center justify-between gap-3 text-xs">
                                                                <span className="capitalize" style={{ color: "#ababab" }}>
                                                                    {readableStatus(variant.review_status)}
                                                                    {typeof variant.score === "number" ? ` · ${variant.score}` : ""}
                                                                </span>
                                                                <div className="flex shrink-0 items-center gap-3">
                                                                    {variant.output_video_url && (
                                                                        <button
                                                                            type="button"
                                                                            onClick={() => handleDownloadVariant(variant.id)}
                                                                            className="inline-flex items-center gap-1 font-semibold hover:underline"
                                                                            style={{ color: "#faf9f5" }}
                                                                        >
                                                                            <Download size={12} />
                                                                            Download
                                                                        </button>
                                                                    )}
                                                                    <Link
                                                                        href={`/dashboard/provision/jobs/${job.id}/${variant.id}`}
                                                                        className="font-semibold hover:underline"
                                                                        style={{ color: "#faf9f5" }}
                                                                    >
                                                                        Details
                                                                    </Link>
                                                                </div>
                                                            </div>
                                                            <div className="grid grid-cols-3 gap-1.5">
                                                                {(["selected", "manual_fix", "rejected"] as const).map(status => (
                                                                    <button
                                                                        key={status}
                                                                        type="button"
                                                                        onClick={() => reviewVariant(variant.id, status)}
                                                                        disabled={reviewingVariantId === variant.id}
                                                                        className="rounded-lg px-2 py-1 text-[10px] font-semibold capitalize transition-colors hover:bg-white/10 disabled:opacity-60"
                                                                        style={{
                                                                            color: variant.review_status === status ? "#141413" : "#ababab",
                                                                            background: variant.review_status === status ? "#faf9f5" : "rgba(250,249,245,0.05)",
                                                                        }}
                                                                    >
                                                                        {status.replace(/_/g, " ")}
                                                                    </button>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    </section>
                                );
                            })}
                        </div>
                    </>
                )}
            </div>
        </main>
    );
}
