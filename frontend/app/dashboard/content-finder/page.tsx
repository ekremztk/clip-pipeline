'use client';

import { useState, useEffect, useMemo, useRef } from "react";
import { Search, ChevronDown, X } from "lucide-react";
import { supabase } from "@/lib/supabase";
import { useChannel } from "@/app/dashboard/layout";

// ─── Types ────────────────────────────────────────────────────────────────────

type RawVideo = {
    id: string;
    video_id: string;
    title: string;
    source_channel: string;
    source_handle: string;
    view_count: number;
    duration_seconds: number;
    upload_date: string | null;
    thumbnail_url: string | null;
    clipped: boolean;
    guest_id: string | null;
};

type Guest = {
    id: string;
    guest_name: string;
    score: number;
    category: string | null;
};

type Video = RawVideo & {
    guest_name: string | null;
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtViews(n: number): string {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${Math.round(n / 1_000)}K`;
    return String(n);
}

function fmtDur(s: number): string {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
    return `${m}:${String(sec).padStart(2, '0')}`;
}

function timeAgo(d: string | null): string {
    if (!d) return '';
    const diff = Date.now() - new Date(d).getTime();
    const days = Math.floor(diff / 86400000);
    if (days === 0) return 'Today';
    if (days < 7) return `${days}d ago`;
    if (days < 30) return `${Math.floor(days / 7)}w ago`;
    if (days < 365) return `${Math.floor(days / 30)}mo ago`;
    return `${Math.floor(days / 365)}y ago`;
}

// Homepage algorithm: views weighted by freshness, clipped videos pushed to end
function homeScore(v: Video): number {
    const ageMs = v.upload_date ? Date.now() - new Date(v.upload_date).getTime() : Infinity;
    const freshness = Math.max(0.3, 1 - ageMs / (730 * 86400000));
    return v.view_count * freshness * (v.clipped ? 0.01 : 1);
}

// ─── Filter Dropdown ──────────────────────────────────────────────────────────

function FilterDropdown({
    label,
    value,
    options,
    onChange,
}: {
    label: string;
    value: string;
    options: { label: string; value: string }[];
    onChange: (v: string) => void;
}) {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);
    const selected = options.find(o => o.value === value);
    const isDefault = value === options[0]?.value;

    useEffect(() => {
        function outside(e: MouseEvent) {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        }
        document.addEventListener('mousedown', outside);
        return () => document.removeEventListener('mousedown', outside);
    }, []);

    return (
        <div className="relative" ref={ref}>
            <button
                onClick={() => setOpen(v => !v)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
                style={{
                    background: open || !isDefault ? 'rgba(250,249,245,0.1)' : 'rgba(250,249,245,0.04)',
                    color: isDefault ? '#ababab' : '#faf9f5',
                    border: `1px solid ${open || !isDefault ? 'rgba(250,249,245,0.15)' : 'rgba(250,249,245,0.07)'}`,
                }}
            >
                <span>{isDefault ? label : (selected?.label ?? label)}</span>
                <ChevronDown
                    size={12}
                    strokeWidth={2.5}
                    style={{
                        transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
                        transition: 'transform 0.15s',
                    }}
                />
            </button>
            {open && (
                <div
                    className="absolute top-9 left-0 z-50 w-48 rounded-xl overflow-hidden py-1"
                    style={{
                        background: '#1c1c1b',
                        border: '1px solid rgba(250,249,245,0.08)',
                        boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
                    }}
                >
                    {options.map(o => (
                        <button
                            key={o.value}
                            onClick={() => { onChange(o.value); setOpen(false); }}
                            className="flex items-center w-full px-4 py-2 text-xs font-medium transition-colors hover:bg-white/5 text-left"
                            style={{ color: value === o.value ? '#faf9f5' : '#ababab' }}
                        >
                            {o.label}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

// ─── Video Card ───────────────────────────────────────────────────────────────

function VideoCard({ video }: { video: Video }) {
    const [imgErr, setImgErr] = useState(false);

    return (
        <a
            href={`https://www.youtube.com/watch?v=${video.video_id}`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col group cursor-pointer"
            style={{ opacity: video.clipped ? 0.38 : 1 }}
        >
            {/* Thumbnail */}
            <div
                className="relative w-full rounded-xl overflow-hidden"
                style={{ paddingBottom: '56.25%', background: '#1c1c1b' }}
            >
                {video.thumbnail_url && !imgErr ? (
                    <img
                        src={video.thumbnail_url}
                        alt={video.title}
                        className="absolute inset-0 w-full h-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
                        onError={() => setImgErr(true)}
                    />
                ) : (
                    <div
                        className="absolute inset-0 flex items-center justify-center"
                        style={{ background: '#1c1c1b' }}
                    >
                        <span style={{ color: 'rgba(250,249,245,0.1)', fontSize: 28 }}>▶</span>
                    </div>
                )}

                {/* Duration badge */}
                <span
                    className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded font-bold"
                    style={{
                        background: 'rgba(0,0,0,0.85)',
                        color: '#faf9f5',
                        fontSize: '11px',
                        lineHeight: '16px',
                    }}
                >
                    {fmtDur(video.duration_seconds)}
                </span>

                {/* Clipped badge */}
                {video.clipped && (
                    <span
                        className="absolute top-2 left-2 px-2 py-0.5 rounded font-semibold"
                        style={{
                            background: 'rgba(0,0,0,0.75)',
                            color: '#ababab',
                            fontSize: '10px',
                            lineHeight: '16px',
                            border: '1px solid rgba(250,249,245,0.12)',
                        }}
                    >
                        Clipped
                    </span>
                )}
            </div>

            {/* Info */}
            <div className="pt-2.5 px-0.5 pb-1">
                <p
                    className="text-sm font-medium leading-snug mb-1.5 group-hover:text-white transition-colors line-clamp-2"
                    style={{ color: '#faf9f5' }}
                >
                    {video.title}
                </p>
                <div className="flex items-center gap-1.5 flex-wrap">
                    <span
                        className="text-xs font-medium px-2 py-0.5 rounded-md"
                        style={{ background: 'rgba(250,249,245,0.06)', color: '#ababab', whiteSpace: 'nowrap', flexShrink: 0 }}
                    >
                        {video.source_channel}
                    </span>
                    <span style={{ color: '#525252', fontSize: 11 }}>·</span>
                    <span className="text-xs" style={{ color: '#737373' }}>{fmtViews(video.view_count)} views</span>
                    {video.upload_date && (
                        <>
                            <span style={{ color: '#525252', fontSize: 11 }}>·</span>
                            <span className="text-xs" style={{ color: '#737373' }}>{timeAgo(video.upload_date)}</span>
                        </>
                    )}
                </div>
            </div>
        </a>
    );
}

// ─── Channel Switcher ─────────────────────────────────────────────────────────

function ChannelSwitcher() {
    const { channels, activeChannelId, setActiveChannelId } = useChannel();
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);
    const active = channels.find(c => c.id === activeChannelId);

    useEffect(() => {
        function outside(e: MouseEvent) {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        }
        document.addEventListener('mousedown', outside);
        return () => document.removeEventListener('mousedown', outside);
    }, []);

    return (
        <div className="relative" ref={ref}>
            <button
                onClick={() => setOpen(v => !v)}
                className="flex items-center justify-between w-full px-3 py-2.5 rounded-xl text-sm font-medium transition-all"
                style={{
                    background: open ? 'rgba(250,249,245,0.07)' : 'rgba(250,249,245,0.04)',
                    border: '1px solid rgba(250,249,245,0.08)',
                    color: '#faf9f5',
                }}
            >
                <span className="truncate text-sm">{active?.display_name ?? 'Select channel'}</span>
                <ChevronDown
                    size={14}
                    strokeWidth={2}
                    style={{
                        flexShrink: 0,
                        marginLeft: 8,
                        transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
                        transition: 'transform 0.15s',
                    }}
                />
            </button>
            {open && channels.length > 0 && (
                <div
                    className="absolute top-12 left-0 right-0 z-50 rounded-xl overflow-hidden py-1"
                    style={{
                        background: '#1c1c1b',
                        border: '1px solid rgba(250,249,245,0.08)',
                        boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
                    }}
                >
                    {channels.map(ch => (
                        <button
                            key={ch.id}
                            onClick={() => { setActiveChannelId(ch.id); setOpen(false); }}
                            className="flex items-center gap-2 w-full px-4 py-2.5 text-sm font-medium transition-colors hover:bg-white/5 text-left"
                            style={{ color: ch.id === activeChannelId ? '#faf9f5' : '#ababab' }}
                        >
                            {ch.display_name ?? ch.name ?? ch.id}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

// ─── Constants ────────────────────────────────────────────────────────────────

const SORT_OPTIONS = [
    { label: 'Most viewed', value: 'views_desc' },
    { label: 'Least viewed', value: 'views_asc' },
    { label: 'Newest first', value: 'date_desc' },
    { label: 'Oldest first', value: 'date_asc' },
    { label: 'Shortest first', value: 'dur_asc' },
    { label: 'Longest first', value: 'dur_desc' },
];

const DURATION_OPTIONS = [
    { label: 'All durations', value: 'all' },
    { label: '< 10 minutes', value: 'lt10' },
    { label: '10 – 30 minutes', value: '10_30' },
    { label: '30 – 60 minutes', value: '30_60' },
    { label: '1 – 2 hours', value: '60_120' },
    { label: '2+ hours', value: 'gt120' },
];

const DATE_OPTIONS = [
    { label: 'All time', value: 'all' },
    { label: 'Last week', value: 'week' },
    { label: 'Last month', value: 'month' },
    { label: 'Last 3 months', value: '3months' },
    { label: 'Last year', value: 'year' },
];

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ContentFinderPage() {
    const { activeChannelId } = useChannel();
    const [poolPrefix, setPoolPrefix] = useState<string | null>(null);
    const [prefixLoaded, setPrefixLoaded] = useState(false);
    const [videos, setVideos] = useState<Video[]>([]);
    const [guests, setGuests] = useState<Guest[]>([]);
    const [loading, setLoading] = useState(true);

    const [search, setSearch] = useState('');
    const [sort, setSort] = useState('views_desc');
    const [durFilter, setDurFilter] = useState('all');
    const [dateFilter, setDateFilter] = useState('all');
    const [channelFilter, setChannelFilter] = useState('all');

    const searchRef = useRef<HTMLInputElement>(null);

    // Fetch pool_prefix for active channel
    useEffect(() => {
        if (!activeChannelId) return;
        setPrefixLoaded(false);
        supabase
            .from('channels')
            .select('pool_prefix')
            .eq('id', activeChannelId)
            .single()
            .then(({ data }) => {
                setPoolPrefix(data?.pool_prefix ?? null);
                setPrefixLoaded(true);
            });
    }, [activeChannelId]);

    // Fetch videos + guests when poolPrefix resolves
    useEffect(() => {
        if (!prefixLoaded) return;
        if (!poolPrefix) { setLoading(false); return; }

        setLoading(true);
        const videosTable = `${poolPrefix}_source_videos`;
        const guestsTable = `${poolPrefix}_guests`;

        Promise.all([
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            supabase.from(videosTable as any).select('*').then(r => (r.data ?? []) as RawVideo[]),
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            supabase.from(guestsTable as any)
                .select('id, guest_name, score, category')
                .eq('active', true)
                .order('score', { ascending: false })
                .then(r => (r.data ?? []) as Guest[]),
        ]).then(([rawVideos, rawGuests]) => {
            const guestMap: Record<string, Guest> = {};
            rawGuests.forEach(g => { guestMap[g.id] = g; });

            const enriched: Video[] = rawVideos.map(v => ({
                ...v,
                guest_name: v.guest_id ? (guestMap[v.guest_id]?.guest_name ?? null) : null,
            }));

            setVideos(enriched);
            setGuests(rawGuests);
            setLoading(false);
        });
    }, [poolPrefix, prefixLoaded]);

    // Source channel options for filter
    const sourceChannelOptions = useMemo(() => {
        const set = new Set<string>();
        videos.forEach(v => set.add(v.source_channel));
        const sorted = Array.from(set).sort();
        return [{ label: 'All channels', value: 'all' }, ...sorted.map(c => ({ label: c, value: c }))];
    }, [videos]);

    // Filtered + sorted videos
    const filtered = useMemo(() => {
        let list = [...videos];
        const q = search.toLowerCase().trim();

        if (q) {
            list = list.filter(v =>
                v.title.toLowerCase().includes(q) ||
                (v.guest_name ?? '').toLowerCase().includes(q)
            );
        }

        if (durFilter !== 'all') {
            list = list.filter(v => {
                const m = v.duration_seconds / 60;
                if (durFilter === 'lt10') return m < 10;
                if (durFilter === '10_30') return m >= 10 && m < 30;
                if (durFilter === '30_60') return m >= 30 && m < 60;
                if (durFilter === '60_120') return m >= 60 && m < 120;
                if (durFilter === 'gt120') return m >= 120;
                return true;
            });
        }

        if (dateFilter !== 'all') {
            const now = Date.now();
            const cutoffs: Record<string, number> = {
                week: now - 7 * 86400000,
                month: now - 30 * 86400000,
                '3months': now - 90 * 86400000,
                year: now - 365 * 86400000,
            };
            const c = cutoffs[dateFilter];
            if (c) list = list.filter(v => v.upload_date ? new Date(v.upload_date).getTime() >= c : false);
        }

        if (channelFilter !== 'all') {
            list = list.filter(v => v.source_channel === channelFilter);
        }

        const sorter = (a: Video, b: Video): number => {
            // Homepage mode: no search + default sort → freshness-weighted score
            if (!q && sort === 'views_desc') return homeScore(b) - homeScore(a);
            if (sort === 'views_desc') return b.view_count - a.view_count;
            if (sort === 'views_asc') return a.view_count - b.view_count;
            if (sort === 'date_desc') return new Date(b.upload_date ?? 0).getTime() - new Date(a.upload_date ?? 0).getTime();
            if (sort === 'date_asc') return new Date(a.upload_date ?? 0).getTime() - new Date(b.upload_date ?? 0).getTime();
            if (sort === 'dur_asc') return a.duration_seconds - b.duration_seconds;
            if (sort === 'dur_desc') return b.duration_seconds - a.duration_seconds;
            return 0;
        };

        // Clipped videos always sorted last
        const unclipped = list.filter(v => !v.clipped).sort(sorter);
        const clipped = list.filter(v => v.clipped).sort(sorter);
        return [...unclipped, ...clipped];
    }, [videos, search, sort, durFilter, dateFilter, channelFilter]);

    const hasActiveFilters = sort !== 'views_desc' || durFilter !== 'all' || dateFilter !== 'all' || channelFilter !== 'all';

    const handleGuestClick = (name: string) => {
        setSearch(name);
        searchRef.current?.focus();
    };

    // No pool_prefix configured
    if (prefixLoaded && !poolPrefix) {
        return (
            <div className="flex flex-col items-center justify-center h-full gap-3">
                <Search size={32} style={{ color: 'rgba(250,249,245,0.1)' }} />
                <p className="text-sm font-medium" style={{ color: '#ababab' }}>
                    This channel has no guest pool configured.
                </p>
                <p className="text-xs" style={{ color: '#525252' }}>
                    Set a <code className="px-1 py-0.5 rounded" style={{ background: 'rgba(250,249,245,0.06)' }}>pool_prefix</code> on this channel to enable Content Finder.
                </p>
            </div>
        );
    }

    return (
        <div className="flex h-full overflow-hidden" style={{ background: '#141413' }}>

            {/* ── Main area ── */}
            <div className="flex-1 flex flex-col overflow-hidden min-w-0 px-6 pt-6">

                {/* Header */}
                <div className="flex items-baseline gap-3 mb-4 flex-shrink-0">
                    <h1 className="text-xl font-semibold" style={{ color: '#faf9f5' }}>Content Finder</h1>
                    {!loading && (
                        <span className="text-sm" style={{ color: '#525252' }}>
                            {filtered.length} videos
                            {videos.filter(v => v.clipped).length > 0 && ` · ${videos.filter(v => v.clipped).length} clipped`}
                        </span>
                    )}
                </div>

                {/* Search bar */}
                <div className="relative mb-3 flex-shrink-0">
                    <Search
                        size={15}
                        className="absolute left-4 top-1/2 -translate-y-1/2 pointer-events-none"
                        style={{ color: '#ababab' }}
                    />
                    <input
                        ref={searchRef}
                        type="text"
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        placeholder="Search by title or guest name…"
                        className="w-full pl-11 pr-10 py-3 rounded-xl text-sm font-medium outline-none transition-all"
                        style={{
                            background: 'rgba(250,249,245,0.04)',
                            border: '1px solid rgba(250,249,245,0.08)',
                            color: '#faf9f5',
                        }}
                        onFocus={e => {
                            e.currentTarget.style.borderColor = 'rgba(250,249,245,0.2)';
                            e.currentTarget.style.background = 'rgba(250,249,245,0.06)';
                        }}
                        onBlur={e => {
                            e.currentTarget.style.borderColor = 'rgba(250,249,245,0.08)';
                            e.currentTarget.style.background = 'rgba(250,249,245,0.04)';
                        }}
                    />
                    {search && (
                        <button
                            onClick={() => setSearch('')}
                            className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded-full transition-colors hover:bg-white/10"
                            style={{ color: '#ababab' }}
                        >
                            <X size={14} />
                        </button>
                    )}
                </div>

                {/* Filter row */}
                <div className="flex items-center gap-2 flex-wrap mb-4 flex-shrink-0">
                    <FilterDropdown label="Sort" value={sort} options={SORT_OPTIONS} onChange={setSort} />
                    <FilterDropdown label="Duration" value={durFilter} options={DURATION_OPTIONS} onChange={setDurFilter} />
                    <FilterDropdown label="Date" value={dateFilter} options={DATE_OPTIONS} onChange={setDateFilter} />
                    <FilterDropdown label="Channel" value={channelFilter} options={sourceChannelOptions} onChange={setChannelFilter} />
                    {hasActiveFilters && (
                        <button
                            onClick={() => { setSort('views_desc'); setDurFilter('all'); setDateFilter('all'); setChannelFilter('all'); }}
                            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors hover:bg-white/5"
                            style={{ color: '#525252' }}
                        >
                            <X size={11} strokeWidth={2.5} />
                            Clear
                        </button>
                    )}
                </div>

                {/* Video grid */}
                <div className="flex-1 overflow-y-auto pb-6">
                    {loading ? (
                        <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
                            {Array.from({ length: 12 }).map((_, i) => (
                                <div key={i} className="flex flex-col gap-2.5">
                                    <div
                                        className="w-full rounded-xl animate-pulse"
                                        style={{ paddingBottom: '56.25%', background: 'rgba(250,249,245,0.06)' }}
                                    />
                                    <div className="h-3 rounded-md animate-pulse w-4/5" style={{ background: 'rgba(250,249,245,0.05)' }} />
                                    <div className="h-3 rounded-md animate-pulse w-3/5" style={{ background: 'rgba(250,249,245,0.03)' }} />
                                </div>
                            ))}
                        </div>
                    ) : filtered.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-56 gap-3">
                            <Search size={28} style={{ color: 'rgba(250,249,245,0.1)' }} />
                            <p className="text-sm" style={{ color: '#737373' }}>No videos found</p>
                            {(search || hasActiveFilters) && (
                                <button
                                    onClick={() => { setSearch(''); setSort('views_desc'); setDurFilter('all'); setDateFilter('all'); setChannelFilter('all'); }}
                                    className="text-xs transition-colors hover:text-white"
                                    style={{ color: '#525252' }}
                                >
                                    Clear all filters
                                </button>
                            )}
                        </div>
                    ) : (
                        <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
                            {filtered.map(v => <VideoCard key={v.id} video={v} />)}
                        </div>
                    )}
                </div>
            </div>

            {/* ── Right panel ── */}
            <aside
                className="flex-shrink-0 flex flex-col"
                style={{
                    width: 256,
                    borderLeft: '1px solid rgba(250,249,245,0.05)',
                    background: '#141413',
                }}
            >
                {/* Channel switcher */}
                <div className="p-4 flex-shrink-0" style={{ borderBottom: '1px solid rgba(250,249,245,0.05)' }}>
                    <p className="text-[10px] font-bold uppercase tracking-widest mb-3" style={{ color: '#525252' }}>
                        Channel
                    </p>
                    <ChannelSwitcher />
                </div>

                {/* Guest list */}
                <div className="flex-1 overflow-y-auto p-4">
                    <p className="text-[10px] font-bold uppercase tracking-widest mb-3" style={{ color: '#525252' }}>
                        Guests {guests.length > 0 && `· ${guests.length}`}
                    </p>

                    {loading ? (
                        <div className="flex flex-col gap-1">
                            {Array.from({ length: 8 }).map((_, i) => (
                                <div key={i} className="h-8 rounded-lg animate-pulse" style={{ background: 'rgba(250,249,245,0.04)' }} />
                            ))}
                        </div>
                    ) : guests.length === 0 ? (
                        <p className="text-xs" style={{ color: '#525252' }}>No guests found</p>
                    ) : (
                        <div className="flex flex-col gap-0.5">
                            {guests.map(g => (
                                <button
                                    key={g.id}
                                    onClick={() => handleGuestClick(g.guest_name)}
                                    className="flex items-center gap-2.5 w-full px-2.5 py-2 rounded-lg text-left transition-colors hover:bg-white/5 group"
                                >
                                    <div
                                        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                                        style={{
                                            background: g.category === 'evergreen'
                                                ? '#4ade80'
                                                : g.category === 'trending'
                                                    ? '#fb923c'
                                                    : 'rgba(250,249,245,0.15)',
                                        }}
                                    />
                                    <span
                                        className="flex-1 text-xs font-medium truncate transition-colors group-hover:text-white"
                                        style={{ color: '#ababab' }}
                                    >
                                        {g.guest_name}
                                    </span>
                                    <span
                                        className="text-[10px] font-bold px-1.5 py-0.5 rounded-md flex-shrink-0"
                                        style={{ background: 'rgba(250,249,245,0.06)', color: '#737373' }}
                                    >
                                        {g.score}
                                    </span>
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            </aside>

        </div>
    );
}
