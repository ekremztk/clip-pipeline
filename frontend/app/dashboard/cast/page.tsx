"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Users } from "lucide-react";
import { authFetch } from "@/lib/api";
import { useChannel } from "../layout";

type CastPerson = {
    person_key: string;
    display_name: string;
    clip_count: number;
    published_count: number;
    unmarked_count: number;
    last_cut_at: string;
    cover_url: string | null;
};

export default function CastLibraryPage() {
    const { activeChannelId, isLoading: channelLoading } = useChannel();
    const [cast, setCast] = useState<CastPerson[]>([]);
    const [loading, setLoading] = useState(true);
    const [query, setQuery] = useState("");

    useEffect(() => {
        if (channelLoading || !activeChannelId) return;
        let cancelled = false;
        setLoading(true);
        authFetch(`/cast?channel_id=${activeChannelId}`)
            .then(r => (r.ok ? r.json() : []))
            .then(data => { if (!cancelled) setCast(Array.isArray(data) ? data : []); })
            .catch(() => { if (!cancelled) setCast([]); })
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, [activeChannelId, channelLoading]);

    const shown = query.trim()
        ? cast.filter(p => p.display_name.toLowerCase().includes(query.trim().toLowerCase()))
        : cast;

    const totalClips = cast.reduce((n, p) => n + p.clip_count, 0);

    return (
        <div className="p-8 max-w-[1600px] mx-auto">
            <div className="flex items-start justify-between mb-8">
                <div>
                    <h1 className="text-2xl font-semibold" style={{ color: "#faf9f5" }}>Cast Library</h1>
                    <p className="text-sm mt-0.5" style={{ color: "#ababab" }}>
                        {loading ? "Loading…" : `${cast.length} people · ${totalClips} clips`}
                    </p>
                </div>
                <input
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    placeholder="Search a name…"
                    className="px-3 py-2 rounded-xl text-sm outline-none w-64"
                    style={{ background: "#181817", color: "#faf9f5", border: "1px solid #262626" }}
                />
            </div>

            {loading ? (
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                    {Array.from({ length: 12 }).map((_, i) => (
                        <div key={i} className="rounded-2xl animate-pulse" style={{ background: "#181817" }}>
                            <div className="aspect-video rounded-t-2xl" style={{ background: "#1c1c1b" }} />
                            <div className="p-3 h-12" />
                        </div>
                    ))}
                </div>
            ) : shown.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-24 gap-3">
                    <Users size={28} style={{ color: "rgba(250,249,245,0.2)" }} />
                    <p className="text-sm" style={{ color: "#ababab" }}>
                        {cast.length === 0 ? "No clips with a person attached yet." : "No match."}
                    </p>
                </div>
            ) : (
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                    {shown.map(p => (
                        <Link
                            key={p.person_key}
                            href={`/dashboard/cast/${encodeURIComponent(p.person_key)}`}
                            className="group rounded-2xl overflow-hidden hover:-translate-y-1 transition-all duration-300"
                            style={{ background: "#181817" }}
                        >
                            <div className="relative aspect-video overflow-hidden flex items-center justify-center" style={{ background: "#1c1c1b" }}>
                                {p.cover_url ? (
                                    /* Clips cut before thumbnails existed only have a 9:16 frame,
                                       and their 16:9 source is long gone from R2 — object-cover
                                       crops to the middle band, which is where the face is. */
                                    <img
                                        src={p.cover_url}
                                        alt=""
                                        loading="lazy"
                                        decoding="async"
                                        className="w-full h-full object-cover"
                                    />
                                ) : (
                                    <Users size={18} style={{ color: "rgba(250,249,245,0.15)" }} />
                                )}
                                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors" />
                                {p.unmarked_count > 0 && (
                                    <div
                                        className="absolute top-2 right-2 px-1.5 py-0.5 rounded-md text-[10px] font-semibold"
                                        style={{ background: "rgba(0,0,0,0.75)", color: "#faf9f5" }}
                                        title={`${p.unmarked_count} not looked at yet`}
                                    >
                                        {p.unmarked_count}
                                    </div>
                                )}
                            </div>
                            <div className="p-3">
                                <p className="text-sm font-medium truncate" style={{ color: "#faf9f5" }}>{p.display_name}</p>
                                <p className="text-[11px] mt-0.5" style={{ color: "#ababab" }}>
                                    {p.clip_count} clip{p.clip_count === 1 ? "" : "s"}
                                    {p.published_count > 0 && ` · ${p.published_count} published`}
                                </p>
                            </div>
                        </Link>
                    ))}
                </div>
            )}
        </div>
    );
}
