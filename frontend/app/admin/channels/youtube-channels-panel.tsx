"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BarChart3, RefreshCw, Youtube, Zap } from "lucide-react";

import { authFetch } from "@/lib/api";
import { SectionCard, SectionHeader, StatusBadge } from "../_components/admin-ui";

type YouTubeChannel = {
    id: string;
    youtube_channel_id: string;
    title: string;
    description: string | null;
    custom_url: string | null;
    thumbnail_url: string | null;
    country: string | null;
    subscriber_count: number | null;
    view_count: number | null;
    video_count: number | null;
    uploads_playlist_id: string | null;
    status: string;
    connected_at: string;
    last_synced_at: string | null;
};

function formatNumber(value: number | null) {
    if (value === null || value === undefined) return "-";
    return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export default function YouTubeChannelsPanel() {
    const [channels, setChannels] = useState<YouTubeChannel[]>([]);
    const [loading, setLoading] = useState(true);
    const [connecting, setConnecting] = useState(false);
    const [syncing, setSyncing] = useState<Record<string, string>>({});
    const [error, setError] = useState<string | null>(null);

    const callbackStatus = useMemo(() => {
        if (typeof window === "undefined") return null;
        const params = new URLSearchParams(window.location.search);
        return params.get("youtube");
    }, []);

    const loadChannels = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await authFetch("/admin/youtube/channels");
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            setChannels(data.channels || []);
        } catch (exc) {
            console.error(exc);
            setError("Could not load YouTube channels");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadChannels();
    }, [loadChannels]);

    async function connectChannel() {
        setConnecting(true);
        setError(null);
        try {
            const res = await authFetch("/admin/youtube/connect");
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            window.location.href = data.auth_url;
        } catch (exc) {
            console.error(exc);
            setError("Could not start YouTube connection");
            setConnecting(false);
        }
    }

    async function syncChannel(channelId: string, type: "realtime" | "analytics") {
        setSyncing((prev) => ({ ...prev, [channelId]: type }));
        setError(null);
        try {
            const endpoint =
                type === "realtime"
                    ? `/admin/youtube/channels/${channelId}/sync/realtime?strategy=smart&max_videos=500&recent_always=30&hot_threshold_per_hour=100&calibration_hours=4`
                    : `/admin/youtube/channels/${channelId}/sync/analytics?days=30&currency=USD`;
            const res = await authFetch(endpoint, { method: "POST" });
            if (!res.ok) throw new Error(await res.text());
            await loadChannels();
        } catch (exc) {
            console.error(exc);
            setError(type === "realtime" ? "Realtime sync failed" : "Analytics sync failed");
        } finally {
            setSyncing((prev) => {
                const next = { ...prev };
                delete next[channelId];
                return next;
            });
        }
    }

    return (
        <SectionCard className="mb-6 overflow-hidden">
            <SectionHeader
                title="YouTube Connection"
                description="Connect Speedy Cast to pull channel stats, revenue, regions, and stock coverage into admin."
                action={
                    <div className="flex items-center gap-2">
                        <button
                            type="button"
                            onClick={loadChannels}
                            disabled={loading}
                            className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-[#e5e5e5] bg-white px-3 text-sm font-medium text-[#171717] hover:bg-[#f5f5f5] disabled:cursor-not-allowed disabled:opacity-60"
                        >
                            <RefreshCw size={16} />
                            Refresh
                        </button>
                        <button
                            type="button"
                            onClick={connectChannel}
                            disabled={connecting}
                            className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-[#171717] px-3 text-sm font-medium text-white hover:bg-[#2a2a2a] disabled:cursor-not-allowed disabled:opacity-60"
                        >
                            <Youtube size={16} />
                            {connecting ? "Connecting..." : "Connect YouTube Channel"}
                        </button>
                    </div>
                }
            />

            {callbackStatus === "connected" ? (
                <div className="border-b border-[#e5e5e5] bg-[#f0fdf4] px-4 py-3 text-sm text-[#166534]">
                    YouTube channel connected successfully.
                </div>
            ) : null}
            {callbackStatus === "error" || error ? (
                <div className="border-b border-[#e5e5e5] bg-[#fef2f2] px-4 py-3 text-sm text-[#991b1b]">
                    {error || "YouTube connection failed. Check backend logs and OAuth redirect settings."}
                </div>
            ) : null}

            <div className="p-4">
                {loading ? (
                    <div className="text-sm text-[#737373]">Loading connected channels...</div>
                ) : channels.length === 0 ? (
                    <div className="rounded-md border border-dashed border-[#d4d4d4] bg-[#fafafa] p-6 text-center">
                        <Youtube className="mx-auto mb-3 text-[#737373]" size={28} />
                        <h3 className="font-semibold text-[#171717]">No YouTube channel connected</h3>
                        <p className="mx-auto mt-1 max-w-xl text-sm text-[#737373]">
                            Connect the Speedy Cast Google account first. After connection, metadata appears here and analytics sync will be added next.
                        </p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                        {channels.map((channel) => (
                            <div key={channel.id} className="rounded-lg border border-[#e5e5e5] bg-[#fafafa] p-4">
                                <div className="flex items-start gap-4">
                                    {channel.thumbnail_url ? (
                                        <img src={channel.thumbnail_url} alt="" className="h-14 w-14 rounded-full object-cover" />
                                    ) : (
                                        <span className="flex h-14 w-14 items-center justify-center rounded-full bg-[#171717] text-white">
                                            <Youtube size={24} />
                                        </span>
                                    )}
                                    <div className="min-w-0 flex-1">
                                        <div className="flex items-center gap-2">
                                            <h3 className="truncate font-semibold text-[#171717]">{channel.title}</h3>
                                            <StatusBadge tone={channel.status === "connected" ? "success" : "warning"}>{channel.status}</StatusBadge>
                                        </div>
                                        <p className="mt-1 truncate text-sm text-[#737373]">{channel.custom_url || channel.youtube_channel_id}</p>
                                    </div>
                                </div>
                                <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
                                    <div className="rounded-md bg-white p-3">
                                        <p className="text-[#737373]">Subscribers</p>
                                        <p className="mt-1 font-semibold text-[#171717]">{formatNumber(channel.subscriber_count)}</p>
                                    </div>
                                    <div className="rounded-md bg-white p-3">
                                        <p className="text-[#737373]">Views</p>
                                        <p className="mt-1 font-semibold text-[#171717]">{formatNumber(channel.view_count)}</p>
                                    </div>
                                    <div className="rounded-md bg-white p-3">
                                        <p className="text-[#737373]">Videos</p>
                                        <p className="mt-1 font-semibold text-[#171717]">{formatNumber(channel.video_count)}</p>
                                    </div>
                                </div>
                                <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-[#e5e5e5] pt-4">
                                    <p className="text-xs text-[#737373]">
                                        Last synced: {channel.last_synced_at ? new Date(channel.last_synced_at).toLocaleString() : "-"}
                                    </p>
                                    <div className="flex flex-wrap gap-2">
                                        <button
                                            type="button"
                                            onClick={() => syncChannel(channel.id, "realtime")}
                                            disabled={Boolean(syncing[channel.id])}
                                            className="inline-flex h-8 items-center justify-center gap-2 rounded-md border border-[#e5e5e5] bg-white px-3 text-xs font-medium text-[#171717] hover:bg-[#f5f5f5] disabled:cursor-not-allowed disabled:opacity-60"
                                        >
                                            <Zap size={14} />
                                            {syncing[channel.id] === "realtime" ? "Syncing..." : "Sync realtime"}
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => syncChannel(channel.id, "analytics")}
                                            disabled={Boolean(syncing[channel.id])}
                                            className="inline-flex h-8 items-center justify-center gap-2 rounded-md bg-[#171717] px-3 text-xs font-medium text-white hover:bg-[#2a2a2a] disabled:cursor-not-allowed disabled:opacity-60"
                                        >
                                            <BarChart3 size={14} />
                                            {syncing[channel.id] === "analytics" ? "Syncing..." : "Sync analytics"}
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </SectionCard>
    );
}
