"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Play } from "lucide-react";
import { toast } from "sonner";
import { authFetch } from "@/lib/api";
import { useChannel } from "../../layout";
import {
    ClipModal, type Clip, getScoreColor, formatDuration,
} from "../../projects/ClipModal";
import {
    ReviewBadge, ReviewMarkPicker, type ReviewMark,
} from "../../projects/ReviewMark";

type Published = "all" | "unpublished" | "published";
type Mark = "all" | "unreviewed" | "maybe" | "rejected" | "posted";
type Sort = "newest" | "oldest" | "score";

const PUBLISHED_OPTS: { v: Published; label: string }[] = [
    { v: "all", label: "All" },
    { v: "unpublished", label: "Unpublished" },
    { v: "published", label: "Published" },
];
const MARK_OPTS: { v: Mark; label: string }[] = [
    { v: "all", label: "Any mark" },
    { v: "unreviewed", label: "Unmarked" },
    { v: "posted", label: "Green" },
    { v: "rejected", label: "Red" },
    { v: "maybe", label: "Blue" },
];
const SORT_OPTS: { v: Sort; label: string }[] = [
    { v: "newest", label: "Newest" },
    { v: "oldest", label: "Oldest" },
    { v: "score", label: "Top score" },
];

function Select<T extends string>({ value, onChange, options }: {
    value: T; onChange: (v: T) => void; options: { v: T; label: string }[];
}) {
    return (
        <select
            value={value}
            onChange={e => onChange(e.target.value as T)}
            className="px-3 py-2 rounded-xl text-sm outline-none cursor-pointer"
            style={{ background: "#181817", color: "#faf9f5", border: "1px solid #262626" }}
        >
            {options.map(o => <option key={o.v} value={o.v}>{o.label}</option>)}
        </select>
    );
}

export default function CastPersonPage() {
    const params = useParams();
    const router = useRouter();
    const personKey = decodeURIComponent(String(params?.person ?? ""));
    const { activeChannelId, isLoading: channelLoading } = useChannel();

    const [clips, setClips] = useState<Clip[]>([]);
    const [displayName, setDisplayName] = useState(personKey);
    const [loading, setLoading] = useState(true);
    const [selectedClip, setSelectedClip] = useState<Clip | null>(null);

    const [published, setPublished] = useState<Published>("all");
    const [mark, setMark] = useState<Mark>("all");
    const [sort, setSort] = useState<Sort>("newest");

    // Filters are query params, not client-side array work: the server returns
    // only the matching rows, so a person with thirty clips ships thirty.
    const query = useMemo(
        () => `channel_id=${activeChannelId}&published=${published}&mark=${mark}&sort=${sort}`,
        [activeChannelId, published, mark, sort],
    );

    useEffect(() => {
        if (channelLoading || !activeChannelId || !personKey) return;
        let cancelled = false;
        setLoading(true);
        authFetch(`/cast/${encodeURIComponent(personKey)}?${query}`)
            .then(r => (r.ok ? r.json() : { person: personKey, clips: [] }))
            .then(data => {
                if (cancelled) return;
                setClips(Array.isArray(data?.clips) ? data.clips : []);
                if (data?.person) setDisplayName(data.person);
            })
            .catch(() => { if (!cancelled) setClips([]); })
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, [personKey, query, activeChannelId, channelLoading]);

    const handleMark = useCallback(async (clipId: string, next: ReviewMark) => {
        const before = clips.find(c => c.id === clipId)?.stock_review_status ?? "unreviewed";
        // Flip locally first — the badge should answer the click, not the network.
        setClips(prev => prev.map(c => (c.id === clipId ? { ...c, stock_review_status: next } : c)));
        try {
            const res = await authFetch(`/clips/${clipId}/stock-review`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ status: next }),
            });
            if (!res.ok) throw new Error();
            const updated = await res.json();
            setClips(prev => prev.map(c => (c.id === clipId
                ? { ...c, stock_review_status: updated.stock_review_status, is_published: updated.is_published }
                : c)));
        } catch {
            setClips(prev => prev.map(c => (c.id === clipId ? { ...c, stock_review_status: before } : c)));
            toast.error("Could not save that mark.");
        }
    }, [clips]);

    return (
        <div className="p-8 max-w-[1600px] mx-auto">
            <div className="flex items-start justify-between mb-8 gap-4 flex-wrap">
                <div className="flex items-center gap-3">
                    <Link
                        href="/dashboard/cast"
                        className="w-9 h-9 rounded-xl flex items-center justify-center transition-colors hover:bg-[rgba(250,249,245,0.08)]"
                        style={{ background: "#181817", color: "#ababab" }}
                    >
                        <ArrowLeft size={16} />
                    </Link>
                    <div>
                        <h1 className="text-2xl font-semibold" style={{ color: "#faf9f5" }}>{displayName}</h1>
                        <p className="text-sm mt-0.5" style={{ color: "#ababab" }}>
                            {loading ? "Loading…" : `${clips.length} clip${clips.length === 1 ? "" : "s"}`}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Select value={published} onChange={setPublished} options={PUBLISHED_OPTS} />
                    <Select value={mark} onChange={setMark} options={MARK_OPTS} />
                    <Select value={sort} onChange={setSort} options={SORT_OPTS} />
                </div>
            </div>

            {loading ? (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                    {Array.from({ length: 10 }).map((_, i) => (
                        <div key={i} className="rounded-2xl animate-pulse" style={{ background: "#181817" }}>
                            <div className="aspect-[9/16]" style={{ background: "#1c1c1b" }} />
                        </div>
                    ))}
                </div>
            ) : clips.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-24 gap-2">
                    <p className="text-sm" style={{ color: "#ababab" }}>No clips match these filters.</p>
                </div>
            ) : (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                    {clips.map(clip => {
                        const score = clip.standalone_score ?? 0;
                        const cmark = (clip.stock_review_status ?? "unreviewed") as ReviewMark;
                        return (
                            <div
                                key={clip.id}
                                className="group rounded-2xl overflow-hidden cursor-pointer transition-all flex flex-col hover:-translate-y-1 duration-300"
                                style={{ background: "#181817" }}
                                onClick={() => setSelectedClip(clip)}
                            >
                                <div className="relative aspect-[9/16] overflow-hidden flex items-center justify-center" style={{ background: "#1c1c1b" }}>
                                    {clip.thumbnail_path ? (
                                        <img
                                            src={clip.thumbnail_path}
                                            alt=""
                                            loading="lazy"
                                            decoding="async"
                                            className="w-full h-full object-cover"
                                        />
                                    ) : (
                                        <Play size={20} style={{ color: "rgba(250,249,245,0.15)" }} />
                                    )}
                                    <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors" />

                                    <div
                                        className={`absolute top-2 left-2 rounded-lg px-1.5 py-0.5 text-[10px] font-bold ${getScoreColor(score)}`}
                                        style={{ background: "rgba(0,0,0,0.75)" }}
                                    >
                                        {score}
                                    </div>
                                    <div
                                        className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded text-[10px]"
                                        style={{ background: "rgba(0,0,0,0.75)", color: "#faf9f5" }}
                                    >
                                        {formatDuration(clip.duration_s)}
                                    </div>

                                    {/* The mark stays visible without hover — it is what you scan for. */}
                                    {cmark !== "unreviewed" && (
                                        <div className="absolute bottom-2 left-2 group-hover:opacity-0 transition-opacity" style={{ zIndex: 10 }}>
                                            <ReviewBadge mark={cmark} size={18} />
                                        </div>
                                    )}
                                    <ReviewMarkPicker mark={cmark} onPick={next => handleMark(clip.id, next)} />
                                </div>
                                <div className="p-3">
                                    <p className="text-[11px] line-clamp-2 leading-relaxed" style={{ color: "#ababab" }}>
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
                    targetGuest={displayName}
                    onClose={() => setSelectedClip(null)}
                    onApprove={async () => {}}
                    onReject={async () => {}}
                    onPublish={async () => {}}
                    onDownload={() => {
                        const url = selectedClip.video_captioned_path || selectedClip.file_url;
                        if (url) window.open(url, "_blank");
                    }}
                    onStockReview={async (id, status) => { await handleMark(id, status as ReviewMark); }}
                />
            )}
        </div>
    );
}
