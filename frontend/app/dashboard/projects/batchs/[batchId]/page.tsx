"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Layers, Loader2, Check, X as XIcon, Clock, FileVideo } from "lucide-react";
import { authFetch } from "@/lib/api";
import { toast } from "@/lib/toast";

interface Job {
    id: string;
    video_title: string | null;
    status: string;
    current_step: string | null;
    progress_pct: number | null;
    clip_count: number | null;
    batch_position: number | null;
    error_message: string | null;
    created_at: string;
    thumb_url?: string | null;
}

interface Batch {
    id: string;
    name: string | null;
    status: string;
    max_parallel: number;
    created_at: string;
}

const ACTIVE = ["processing", "analyzing", "cutting", "queued"];

// A queued source's file lives under upload_sources/, which the R2 TTL sweeper
// clears after 24 hours. A batch that sits in the queue that long loses its
// inputs, so warn well before it happens rather than after.
const STALE_QUEUE_HOURS = 18;

const StatusIcon = ({ status }: { status: string }) => {
    if (status === "completed") return <Check className="w-3.5 h-3.5" style={{ color: "#8fd4a0" }} />;
    if (status === "failed") return <XIcon className="w-3.5 h-3.5" style={{ color: "#e07a5f" }} />;
    if (status === "queued") return <Clock className="w-3.5 h-3.5" style={{ color: "#ababab" }} />;
    return <Loader2 className="w-3.5 h-3.5 animate-spin" style={{ color: "#faf9f5" }} />;
};

export default function BatchDetailPage() {
    const params = useParams();
    const router = useRouter();
    const batchId = params?.batchId as string;

    const [batch, setBatch] = useState<Batch | null>(null);
    const [jobs, setJobs] = useState<Job[]>([]);
    const [loading, setLoading] = useState(true);
    const [notFound, setNotFound] = useState(false);

    const load = useCallback(async () => {
        if (!batchId) return;
        try {
            const res = await authFetch(`/batches/${batchId}`);
            if (res.status === 404) { setNotFound(true); return; }
            if (!res.ok) return;
            const body = await res.json();
            setBatch(body.batch);
            setJobs(body.jobs || []);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    }, [batchId]);

    useEffect(() => { load(); }, [load]);

    useEffect(() => {
        if (!jobs.some(j => ACTIVE.includes(j.status))) return;
        const t = setInterval(load, 4000);
        return () => clearInterval(t);
    }, [jobs, load]);

    const cancel = async () => {
        const res = await authFetch(`/batches/${batchId}`, { method: "DELETE" });
        if (res.ok) {
            const body = await res.json();
            toast.success(`Queue cleared — ${body.cancelled_jobs} pending sources cancelled`);
            load();
        } else {
            toast.error("Could not cancel batch");
        }
    };

    const done = jobs.filter(j => j.status === "completed" || j.status === "failed").length;
    const failed = jobs.filter(j => j.status === "failed").length;
    const pct = jobs.length ? Math.round((done / jobs.length) * 100) : 0;

    const oldestQueued = jobs
        .filter(j => j.status === "queued")
        .map(j => (Date.now() - new Date(j.created_at).getTime()) / 3_600_000)
        .sort((a, b) => b - a)[0];
    const queueIsStale = (oldestQueued ?? 0) > STALE_QUEUE_HOURS;

    if (notFound) {
        return (
            <div className="min-h-screen p-6" style={{ background: "#141413", color: "#faf9f5" }}>
                <button onClick={() => router.push("/dashboard/projects")}
                    className="inline-flex items-center gap-1.5 text-xs mb-6" style={{ color: "#ababab" }}>
                    <ArrowLeft className="w-3.5 h-3.5" /> Projects
                </button>
                <p className="text-sm" style={{ color: "#ababab" }}>Batch not found.</p>
            </div>
        );
    }

    return (
        <div className="min-h-screen p-6 pb-24" style={{ background: "#141413", color: "#faf9f5" }}>
            <button onClick={() => router.push("/dashboard/projects")}
                className="inline-flex items-center gap-1.5 text-xs mb-3 transition-colors hover:!text-[#faf9f5]"
                style={{ color: "#ababab" }}>
                <ArrowLeft className="w-3.5 h-3.5" /> Projects
            </button>

            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
                <div>
                    <div className="flex items-center gap-2">
                        <Layers className="w-5 h-5" style={{ color: "#ababab" }} />
                        <h1 className="text-2xl font-semibold">{batch?.name || "Untitled batch"}</h1>
                    </div>
                    <p className="text-xs mt-1" style={{ color: "#ababab" }}>
                        {jobs.length} sources · {batch?.max_parallel} at a time · {batch?.status}
                    </p>
                </div>
                {batch?.status === "running" && (
                    <button onClick={cancel}
                        className="px-4 py-2 rounded-full text-sm transition-colors"
                        style={{ border: "1px solid #2a2a28", color: "#e07a5f" }}>
                        Cancel queue
                    </button>
                )}
            </div>

            <div className="mb-8">
                <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "#2a2a28" }}>
                    <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: "#faf9f5" }} />
                </div>
                <div className="flex items-center gap-1.5 mt-2 text-xs" style={{ color: "#ababab" }}>
                    <span>{done}/{jobs.length} finished</span>
                    {failed > 0 && <><span>·</span><span style={{ color: "#e07a5f" }}>{failed} failed</span></>}
                </div>
            </div>

            {queueIsStale && (
                <div className="mb-6 px-4 py-3 rounded-xl text-xs" style={{ background: "#2a2418", color: "#e0c05f" }}>
                    A source has been queued for over {STALE_QUEUE_HOURS} hours. Uploaded files are swept after 24 hours,
                    so anything still waiting then will fail with a missing source.
                </div>
            )}

            {loading ? (
                <div className="space-y-2">
                    {[...Array(3)].map((_, i) => (
                        <div key={i} className="h-16 rounded-xl animate-pulse" style={{ background: "#181817" }} />
                    ))}
                </div>
            ) : (
                <div className="space-y-2">
                    {jobs.map(job => {
                        const openable = job.status === "completed";
                        return (
                            <div
                                key={job.id}
                                onClick={() => openable && router.push(`/dashboard/projects/batchs/${batchId}/${job.id}`)}
                                className={`flex items-center gap-4 px-4 py-3 rounded-xl transition-colors ${openable ? "cursor-pointer hover:bg-white/[0.02]" : ""}`}
                                style={{ background: "#181817" }}
                            >
                                <span className="text-xs w-5 text-center flex-shrink-0" style={{ color: "#6f6f6b" }}>
                                    {(job.batch_position ?? 0) + 1}
                                </span>
                                {/* One frame of the source. Seven rows of similar
                                    filenames are indistinguishable without it. */}
                                <div className="w-16 h-9 rounded-md overflow-hidden flex-shrink-0 flex items-center justify-center"
                                    style={{ background: "#1c1c1b" }}>
                                    {/* The server hands back a poster frame when the pipeline made
                                        one and a video URL otherwise, so the tag follows the file. */}
                                    {job.thumb_url ? (
                                        job.thumb_url.endsWith(".jpg") ? (
                                            <img
                                                src={job.thumb_url}
                                                alt=""
                                                loading="lazy"
                                                decoding="async"
                                                className="w-full h-full object-cover"
                                            />
                                        ) : (
                                            <video src={job.thumb_url} className="w-full h-full object-cover" preload="metadata" muted />
                                        )
                                    ) : (
                                        <FileVideo className="w-3.5 h-3.5" style={{ color: "rgba(250,249,245,0.15)" }} />
                                    )}
                                </div>
                                <StatusIcon status={job.status} />
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm truncate" style={{ color: "#faf9f5" }}>{job.video_title || "Untitled"}</p>
                                    <p className="text-[11px] truncate" style={{ color: job.error_message ? "#e07a5f" : "#6f6f6b" }}>
                                        {job.error_message || job.current_step || job.status}
                                    </p>
                                </div>
                                {job.status === "completed" && (
                                    <span className="text-xs whitespace-nowrap" style={{ color: "#ababab" }}>
                                        {job.clip_count ?? 0} clips
                                    </span>
                                )}
                                {ACTIVE.includes(job.status) && job.status !== "queued" && (
                                    <span className="text-xs whitespace-nowrap" style={{ color: "#ababab" }}>
                                        {job.progress_pct ?? 0}%
                                    </span>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
