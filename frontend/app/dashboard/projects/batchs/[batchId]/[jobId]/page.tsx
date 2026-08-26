"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, FileVideo, Play } from "lucide-react";
import { authFetch } from "@/lib/api";
import { toast } from "@/lib/toast";
import { ClipModal, getBestUrl, getScoreHex, formatDuration } from "../../../ClipModal";
import type { Clip } from "../../../ClipModal";

export default function BatchJobClipsPage() {
    const params = useParams();
    const router = useRouter();
    const batchId = params?.batchId as string;
    const jobId = params?.jobId as string;

    const [clips, setClips] = useState<Clip[]>([]);
    const [title, setTitle] = useState("");
    const [targetGuest, setTargetGuest] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [selectedClip, setSelectedClip] = useState<Clip | null>(null);

    const load = useCallback(async () => {
        if (!jobId) return;
        try {
            // Returns the job with its clips and enforces ownership, so this is
            // one request rather than two.
            const res = await authFetch(`/jobs/${jobId}`);
            if (res.ok) {
                const body = await res.json();
                setTitle(body.job?.video_title || "");
                setTargetGuest(body.job?.target_guest ?? null);
                setClips(body.clips || []);
            }
        } finally {
            setLoading(false);
        }
    }, [jobId]);

    useEffect(() => { load(); }, [load]);

    /** Keep the open modal pointing at the same clip after a list refresh. */
    const syncSelected = (updated: Clip[]) => {
        setClips(updated);
        setSelectedClip(prev => (prev ? updated.find(c => c.id === prev.id) ?? prev : prev));
    };

    const patchClip = async (id: string, body: Record<string, unknown>, okMsg: string) => {
        const res = await authFetch(`/clips/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        if (res.ok) {
            syncSelected(clips.map(c => (c.id === id ? { ...c, ...body } as Clip : c)));
            toast.success(okMsg);
        } else {
            toast.error("Could not update clip.");
        }
    };

    const handleApprove = (id: string) => {
        const clip = clips.find(c => c.id === id);
        patchClip(id, { is_successful: clip?.is_successful === true ? null : true }, "Clip approved.");
    };
    const handleReject = (id: string) => {
        const clip = clips.find(c => c.id === id);
        patchClip(id, { is_successful: clip?.is_successful === false ? null : false }, "Clip rejected.");
    };
    const handlePublish = (id: string) => {
        const clip = clips.find(c => c.id === id);
        patchClip(id, { is_published: !clip?.is_published }, "Marked as published.");
    };
    const handleDownload = (id: string) => {
        const clip = clips.find(c => c.id === id);
        const url = clip ? getBestUrl(clip) : null;
        if (url) window.open(url, "_blank");
    };
    const handleStockReview = async (
        id: string,
        status: "unreviewed" | "selected" | "rejected" | "posted",
        note: string,
    ) => {
        const res = await authFetch(`/clips/${id}/stock-review`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ stock_review_status: status, stock_review_note: note }),
        });
        if (res.ok) {
            syncSelected(clips.map(c => (c.id === id ? { ...c, stock_review_status: status, stock_review_note: note } : c)));
        } else {
            toast.error("Could not save review.");
        }
    };

    return (
        <div className="min-h-screen p-6 pb-24" style={{ background: "#141413", color: "#faf9f5" }}>
            <button onClick={() => router.push(`/dashboard/projects/batchs/${batchId}`)}
                className="inline-flex items-center gap-1.5 text-xs mb-3 transition-colors hover:!text-[#faf9f5]"
                style={{ color: "#ababab" }}>
                <ArrowLeft className="w-3.5 h-3.5" /> Batch
            </button>

            <h1 className="text-2xl font-semibold mb-1">{title || "Project Clips"}</h1>
            <p className="text-xs mb-8" style={{ color: "#ababab" }}>{clips.length} clips</p>

            {loading ? (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                    {[...Array(5)].map((_, i) => (
                        <div key={i} className="rounded-2xl overflow-hidden" style={{ background: "#181817" }}>
                            <div className="aspect-[9/16] shimmer-load" style={{ background: "rgba(250,249,245,0.06)" }} />
                        </div>
                    ))}
                </div>
            ) : clips.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 rounded-2xl" style={{ background: "#181817" }}>
                    <FileVideo className="w-12 h-12 mb-3" style={{ color: "rgba(250,249,245,0.1)" }} />
                    <p className="text-sm" style={{ color: "#ababab" }}>No clips for this source.</p>
                </div>
            ) : (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                    {clips.map(clip => {
                        const url = getBestUrl(clip);
                        const score = clip.standalone_score ?? 0;
                        return (
                            <div
                                key={clip.id}
                                onClick={() => setSelectedClip(clip)}
                                className="rounded-2xl overflow-hidden cursor-pointer transition-all group flex flex-col hover:-translate-y-1 duration-300"
                                style={{ background: "#181817" }}
                            >
                                <div className="relative aspect-[9/16] flex items-center justify-center" style={{ background: "#1c1c1b" }}>
                                    {url ? (
                                        <video src={url} className="w-full h-full object-cover" preload="metadata" muted />
                                    ) : (
                                        <FileVideo className="w-8 h-8" style={{ color: "rgba(250,249,245,0.15)" }} />
                                    )}
                                    <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                                        style={{ background: "rgba(0,0,0,0.35)" }}>
                                        <Play className="w-8 h-8" style={{ color: "#faf9f5" }} />
                                    </div>
                                    {/* Colour is what makes a score readable at a glance —
                                        a plain number has to be read before it means anything. */}
                                    <span className="absolute top-2 right-2 text-[10px] font-semibold px-1.5 py-0.5 rounded"
                                        style={{ background: "rgba(0,0,0,0.65)", color: getScoreHex(score) }}>
                                        {score}
                                    </span>
                                    {clip.duration_s != null && (
                                        <span className="absolute bottom-2 left-2 text-[10px] px-1.5 py-0.5 rounded"
                                            style={{ background: "rgba(0,0,0,0.65)", color: "#faf9f5" }}>
                                            {formatDuration(clip.duration_s)}
                                        </span>
                                    )}
                                </div>
                                <div className="p-3">
                                    <p className="text-xs line-clamp-2" style={{ color: "#faf9f5" }}>
                                        {clip.suggested_title || clip.hook_text || "Untitled"}
                                    </p>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {selectedClip && (
                <ClipModal
                    clip={selectedClip}
                    targetGuest={targetGuest}
                    onClose={() => setSelectedClip(null)}
                    onApprove={handleApprove}
                    onReject={handleReject}
                    onPublish={handlePublish}
                    onDownload={handleDownload}
                    onStockReview={handleStockReview}
                />
            )}
        </div>
    );
}
