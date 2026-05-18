"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Download, ExternalLink, Loader2, RefreshCw } from "lucide-react";
import { authFetch } from "@/lib/api";
import { downloadProvisionVariant } from "../../../download";
import {
    formatDate,
    formatDuration,
    ProvisionJobDetail,
    ProvisionVariant,
    readableStatus,
    StatusPill,
} from "../../_shared";

type ReviewStatus = "selected" | "manual_fix" | "rejected" | "posted" | "unreviewed";

function PlanSection({ label, value }: { label: string; value: unknown }) {
    if (value === undefined || value === null || value === "") return null;
    return (
        <div className="rounded-xl p-3" style={{ background: "#111110", border: "1px solid rgba(250,249,245,0.06)" }}>
            <p className="mb-1 text-[10px] uppercase tracking-[0.18em]" style={{ color: "#737373" }}>{label}</p>
            <p className="text-sm leading-6" style={{ color: "#ababab" }}>
                {Array.isArray(value) ? value.join(", ") : String(value)}
            </p>
        </div>
    );
}

export default function ProvisionVariantPage() {
    const params = useParams<{ jobId: string; variantId: string }>();
    const [job, setJob] = useState<ProvisionJobDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const variant = useMemo<ProvisionVariant | null>(
        () => job?.variants.find(item => item.id === params.variantId) || null,
        [job?.variants, params.variantId],
    );
    const sourceItem = useMemo(
        () => job?.items.find(item => item.id === variant?.provision_item_id) || null,
        [job?.items, variant?.provision_item_id],
    );
    const editPlan = variant?.edit_plan || {};

    const loadJob = async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await authFetch(`/provision/jobs/${params.jobId}`);
            if (!res.ok) {
                const body = await res.text().catch(() => "");
                throw new Error(body || `HTTP ${res.status}`);
            }
            setJob(await res.json());
        } catch (err: any) {
            setError(err?.message || "Failed to load provision variant");
        } finally {
            setLoading(false);
        }
    };

    const reviewVariant = async (reviewStatus: ReviewStatus) => {
        if (!variant || saving) return;
        setSaving(true);
        setError(null);
        try {
            const res = await authFetch(`/provision/variants/${variant.id}/review`, {
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
            setError(err?.message || "Failed to update review");
        } finally {
            setSaving(false);
        }
    };

    const handleDownloadVariant = async () => {
        if (!variant) return;
        setError(null);
        try {
            await downloadProvisionVariant(variant.id);
        } catch (err: any) {
            setError(err?.message || "Failed to download variant");
        }
    };

    useEffect(() => {
        loadJob();
    }, [params.jobId]);

    return (
        <main className="min-h-screen px-6 py-8" style={{ background: "#141413" }}>
            <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
                <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                    <div>
                        <Link
                            href={`/dashboard/provision/jobs/${params.jobId}`}
                            className="mb-4 inline-flex items-center gap-2 text-sm font-medium hover:underline"
                            style={{ color: "#ababab" }}
                        >
                            <ArrowLeft size={15} />
                            Job variants
                        </Link>
                        <div className="flex items-center gap-2">
                            <StatusPill status={variant?.status || "loading"} />
                            {variant?.review_status && <StatusPill status={variant.review_status} />}
                        </div>
                        <h1 className="mt-3 text-3xl font-semibold capitalize tracking-tight" style={{ color: "#faf9f5" }}>
                            {variant?.variant_mode || "Variant"}
                        </h1>
                        <p className="mt-2 text-sm" style={{ color: "#737373" }}>
                            {sourceItem?.input_title || job?.name || "Provision output"}
                        </p>
                    </div>

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
                ) : !variant ? (
                    <div
                        className="rounded-2xl p-8 text-center text-sm"
                        style={{ color: "#737373", background: "#1c1c1b", border: "1px solid rgba(250,249,245,0.06)" }}
                    >
                        Variant not found.
                    </div>
                ) : (
                    <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
                        <section
                            className="rounded-2xl p-4"
                            style={{ background: "#1c1c1b", border: "1px solid rgba(250,249,245,0.06)" }}
                        >
                            <div className="overflow-hidden rounded-2xl" style={{ background: "#111110" }}>
                                {variant.output_video_url ? (
                                    <video src={variant.output_video_url} controls playsInline className="aspect-[9/16] w-full object-contain" />
                                ) : (
                                    <div className="flex aspect-[9/16] items-center justify-center">
                                        <Loader2 className="animate-spin" size={22} style={{ color: "#737373" }} />
                                    </div>
                                )}
                            </div>

                            <div className="mt-4 grid grid-cols-2 gap-2">
                                <div className="rounded-xl p-3" style={{ background: "rgba(250,249,245,0.035)" }}>
                                    <p className="text-[10px] uppercase tracking-[0.18em]" style={{ color: "#737373" }}>Score</p>
                                    <p className="mt-1 text-lg font-semibold" style={{ color: "#faf9f5" }}>
                                        {typeof variant.score === "number" ? variant.score : "—"}
                                    </p>
                                </div>
                                <div className="rounded-xl p-3" style={{ background: "rgba(250,249,245,0.035)" }}>
                                    <p className="text-[10px] uppercase tracking-[0.18em]" style={{ color: "#737373" }}>Duration</p>
                                    <p className="mt-1 text-lg font-semibold" style={{ color: "#faf9f5" }}>
                                        {formatDuration(variant.duration_s)}
                                    </p>
                                </div>
                            </div>

                            <div className="mt-4 grid grid-cols-2 gap-2">
                                {(["selected", "manual_fix", "rejected", "posted"] as const).map(status => (
                                    <button
                                        key={status}
                                        type="button"
                                        onClick={() => reviewVariant(status)}
                                        disabled={saving}
                                        className="rounded-xl px-3 py-2 text-xs font-semibold capitalize transition-colors hover:bg-white/10 disabled:opacity-60"
                                        style={{
                                            color: variant.review_status === status ? "#141413" : "#ababab",
                                            background: variant.review_status === status ? "#faf9f5" : "rgba(250,249,245,0.05)",
                                        }}
                                    >
                                        {status.replace(/_/g, " ")}
                                    </button>
                                ))}
                            </div>

                            {variant.output_video_url && (
                                <div className="mt-4 flex flex-wrap items-center gap-4">
                                    <button
                                        type="button"
                                        onClick={handleDownloadVariant}
                                        className="inline-flex items-center gap-2 text-xs font-semibold hover:underline"
                                        style={{ color: "#faf9f5" }}
                                    >
                                        Download output file
                                        <Download size={12} />
                                    </button>
                                    <a
                                        href={variant.output_video_url}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="inline-flex items-center gap-2 text-xs font-semibold hover:underline"
                                        style={{ color: "#ababab" }}
                                    >
                                        Open output file
                                        <ExternalLink size={12} />
                                    </a>
                                </div>
                            )}
                        </section>

                        <section className="space-y-4">
                            <div
                                className="rounded-2xl p-5"
                                style={{ background: "#1c1c1b", border: "1px solid rgba(250,249,245,0.06)" }}
                            >
                                <h2 className="text-lg font-semibold" style={{ color: "#faf9f5" }}>Edit Plan</h2>
                                <p className="mt-1 text-sm" style={{ color: "#737373" }}>
                                    Generated {formatDate(variant.updated_at || variant.created_at)} · {readableStatus(variant.status)}
                                </p>
                                <div className="mt-4 grid gap-3 md:grid-cols-2">
                                    <PlanSection label="Decision summary" value={editPlan.decision_summary} />
                                    <PlanSection label="Opening assessment" value={editPlan.opening_assessment} />
                                    <PlanSection label="Ending assessment" value={editPlan.ending_assessment} />
                                    <PlanSection label="Pacing assessment" value={editPlan.pacing_assessment} />
                                    <PlanSection label="Standalone assessment" value={editPlan.standalone_assessment} />
                                    <PlanSection label="Editor note" value={editPlan.editor_note} />
                                    <PlanSection label="Keep moments" value={editPlan.keep_moments} />
                                    <PlanSection label="Remove moments" value={editPlan.remove_moments} />
                                </div>
                            </div>

                            <div
                                className="rounded-2xl p-5"
                                style={{ background: "#1c1c1b", border: "1px solid rgba(250,249,245,0.06)" }}
                            >
                                <h2 className="text-lg font-semibold" style={{ color: "#faf9f5" }}>Raw Plan</h2>
                                <pre
                                    className="mt-4 max-h-[420px] overflow-auto rounded-xl p-4 text-xs leading-5"
                                    style={{ color: "#ababab", background: "#111110", border: "1px solid rgba(250,249,245,0.06)" }}
                                >
                                    {JSON.stringify(variant.edit_plan || {}, null, 2)}
                                </pre>
                            </div>
                        </section>
                    </div>
                )}
            </div>
        </main>
    );
}
