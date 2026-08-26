"use client";

import React, { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Play, FileVideo } from "lucide-react";
import { authFetch } from "@/lib/api";

interface Clip {
    id: string;
    hook_text: string | null;
    suggested_title: string | null;
    duration_s: number | null;
    standalone_score: number | null;
    file_url: string | null;
    video_captioned_path?: string | null;
    video_reframed_path?: string | null;
}

const bestUrl = (c: Clip) => c.video_captioned_path || c.video_reframed_path || c.file_url || null;

export default function BatchJobClipsPage() {
    const params = useParams();
    const router = useRouter();
    const batchId = params?.batchId as string;
    const jobId = params?.jobId as string;

    const [clips, setClips] = useState<Clip[]>([]);
    const [title, setTitle] = useState("");
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!jobId) return;
        (async () => {
            try {
                // This endpoint already returns the job with its clips and checks
                // ownership, so the page needs one request rather than two.
                const res = await authFetch(`/jobs/${jobId}`);
                if (res.ok) {
                    const body = await res.json();
                    setTitle(body.job?.video_title || "");
                    setClips(body.clips || []);
                }
            } finally {
                setLoading(false);
            }
        })();
    }, [jobId]);

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
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
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
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                    {clips.map(clip => {
                        const url = bestUrl(clip);
                        return (
                            <div key={clip.id} className="rounded-2xl overflow-hidden flex flex-col transition-all hover:-translate-y-1 duration-300"
                                style={{ background: "#181817" }}>
                                <div className="relative aspect-[9/16] flex items-center justify-center" style={{ background: "#1c1c1b" }}>
                                    {url ? (
                                        <video src={url} className="w-full h-full object-cover" preload="metadata" muted />
                                    ) : (
                                        <FileVideo className="w-8 h-8" style={{ color: "rgba(250,249,245,0.15)" }} />
                                    )}
                                    {url && (
                                        <a href={url} target="_blank" rel="noreferrer"
                                            className="absolute inset-0 flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity"
                                            style={{ background: "rgba(0,0,0,0.4)" }}>
                                            <Play className="w-8 h-8" style={{ color: "#faf9f5" }} />
                                        </a>
                                    )}
                                    {clip.standalone_score != null && (
                                        <span className="absolute top-2 right-2 text-[10px] px-1.5 py-0.5 rounded"
                                            style={{ background: "rgba(0,0,0,0.6)", color: "#faf9f5" }}>
                                            {clip.standalone_score}
                                        </span>
                                    )}
                                </div>
                                <div className="p-3">
                                    <p className="text-xs line-clamp-2" style={{ color: "#faf9f5" }}>
                                        {clip.suggested_title || clip.hook_text || "Untitled"}
                                    </p>
                                    {clip.duration_s != null && (
                                        <p className="text-[10px] mt-1" style={{ color: "#6f6f6b" }}>
                                            {Math.round(clip.duration_s)}s
                                        </p>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
