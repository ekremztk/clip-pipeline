'use client';

import { useEffect, useState } from 'react';
import {
    CheckCircle2,
    Clock3,
    FileVideo,
    Gauge,
    ListChecks,
    Loader2,
    Plus,
    RefreshCw,
    Scissors,
    Sparkles,
    Upload,
} from 'lucide-react';
import { authFetch } from '@/lib/api';
import { useChannel } from '@/app/dashboard/layout';

type EditMode = 'conservative' | 'tight' | 'aggressive' | 'loop';

type ProvisionJob = {
    id: string;
    name: string;
    status: string;
    current_step?: string;
    current_step_number?: number;
    progress_pct?: number;
    variant_modes: string[];
    item_count: number;
    completed_item_count: number;
    selected_variant_count: number;
    created_at: string;
};

type ProvisionItem = {
    id: string;
    input_title: string | null;
    input_video_url: string;
    main_person: string | null;
    status: string;
    current_step?: string;
    progress_pct?: number;
    created_at: string;
};

type ProvisionVariant = {
    id: string;
    provision_item_id: string;
    variant_mode: string;
    status: string;
    current_step?: string;
    progress_pct?: number;
    review_status: string;
    output_video_url: string | null;
    feedback_note?: string | null;
    score?: number | null;
};

type ProvisionJobDetail = ProvisionJob & {
    items: ProvisionItem[];
    variants: ProvisionVariant[];
};

const EDIT_MODES: Array<{
    key: EditMode;
    label: string;
    description: string;
}> = [
    {
        key: 'conservative',
        label: 'Conservative',
        description: 'Start/end cleanup with minimal internal cuts.',
    },
    {
        key: 'tight',
        label: 'Tight',
        description: 'Sharper pacing while keeping the full story intact.',
    },
    {
        key: 'aggressive',
        label: 'Aggressive',
        description: 'Shorts-first compression with stronger dead-air removal.',
    },
    {
        key: 'loop',
        label: 'Loop',
        description: 'Ending biased toward punchline and replayability.',
    },
];

const STAGE_ITEMS = [
    { icon: FileVideo, label: 'Input', value: 'S10 captioned MP4' },
    { icon: Clock3, label: 'Timing', value: 'Nova-3 + FFmpeg gaps' },
    { icon: Sparkles, label: 'Decision', value: 'Gemini edit plan' },
    { icon: Scissors, label: 'Output', value: 'Polished variants' },
];

function SettingRow({
    label,
    value,
}: {
    label: string;
    value: string;
}) {
    return (
        <div
            className="flex items-center justify-between gap-4 rounded-xl px-4 py-3"
            style={{ background: 'rgba(250,249,245,0.035)', border: '1px solid rgba(250,249,245,0.06)' }}
        >
            <span className="text-sm" style={{ color: '#ababab' }}>{label}</span>
            <span className="text-sm font-medium text-right" style={{ color: '#faf9f5' }}>{value}</span>
        </div>
    );
}

function formatDate(value: string) {
    try {
        return new Date(value).toLocaleString(undefined, {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch {
        return value;
    }
}

function StatusPill({ label }: { label: string }) {
    const normalized = (label || 'unknown').replace(/_/g, ' ');
    return (
        <span
            className="rounded-lg px-2 py-1 text-xs font-semibold capitalize"
            style={{ color: '#ababab', background: 'rgba(250,249,245,0.06)' }}
        >
            {normalized}
        </span>
    );
}

function shortId(value: string) {
    return value ? value.slice(0, 8) : 'unknown';
}

export default function ProvisionPage() {
    const { activeChannelId, isLoading: channelLoading } = useChannel();
    const [selectedModes, setSelectedModes] = useState<EditMode[]>(['conservative', 'tight', 'loop']);
    const [jobs, setJobs] = useState<ProvisionJob[]>([]);
    const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
    const [jobDetail, setJobDetail] = useState<ProvisionJobDetail | null>(null);
    const [loadingJobs, setLoadingJobs] = useState(false);
    const [loadingDetail, setLoadingDetail] = useState(false);
    const [creatingJob, setCreatingJob] = useState(false);
    const [addingItem, setAddingItem] = useState(false);
    const [startingJob, setStartingJob] = useState(false);
    const [itemClipId, setItemClipId] = useState('');
    const [itemVideoUrl, setItemVideoUrl] = useState('');
    const [itemTitle, setItemTitle] = useState('');
    const [itemPerson, setItemPerson] = useState('');
    const [reviewingVariantId, setReviewingVariantId] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!activeChannelId || channelLoading) return;
        fetchJobs();
    }, [activeChannelId, channelLoading]);

    const fetchJobs = async () => {
        if (!activeChannelId) return;
        setLoadingJobs(true);
        setError(null);
        try {
            const res = await authFetch(`/provision/jobs?channel_id=${encodeURIComponent(activeChannelId)}&limit=50`);
            if (!res.ok) {
                const body = await res.text().catch(() => '');
                throw new Error(body || `HTTP ${res.status}`);
            }
            const data = await res.json();
            setJobs(Array.isArray(data) ? data : []);
            if (!selectedJobId && Array.isArray(data) && data.length > 0) {
                setSelectedJobId(data[0].id);
                fetchJobDetail(data[0].id);
            }
        } catch (err: any) {
            setError(err?.message || 'Failed to load provision jobs');
        } finally {
            setLoadingJobs(false);
        }
    };

    const fetchJobDetail = async (jobId: string) => {
        setLoadingDetail(true);
        setError(null);
        try {
            const res = await authFetch(`/provision/jobs/${jobId}`);
            if (!res.ok) {
                const body = await res.text().catch(() => '');
                throw new Error(body || `HTTP ${res.status}`);
            }
            const data = await res.json();
            setJobDetail(data);
            setSelectedJobId(jobId);
        } catch (err: any) {
            setError(err?.message || 'Failed to load provision job');
        } finally {
            setLoadingDetail(false);
        }
    };

    const createJob = async () => {
        if (!activeChannelId || creatingJob) return;
        setCreatingJob(true);
        setError(null);
        try {
            const res = await authFetch('/provision/jobs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    channel_id: activeChannelId,
                    variant_modes: selectedModes,
                    settings: {
                        max_internal_cuts: 2,
                        max_duration_reduction_pct: 35,
                        minimum_final_duration_s: 12,
                    },
                }),
            });
            if (!res.ok) {
                const body = await res.text().catch(() => '');
                throw new Error(body || `HTTP ${res.status}`);
            }
            const created = await res.json();
            setJobs(prev => [created, ...prev]);
            setSelectedJobId(created.id);
            setJobDetail({ ...created, items: [], variants: [] });
        } catch (err: any) {
            setError(err?.message || 'Failed to create provision job');
        } finally {
            setCreatingJob(false);
        }
    };

    const addItem = async () => {
        if (!selectedJobId || addingItem) return;
        const clipId = itemClipId.trim();
        const videoUrl = itemVideoUrl.trim();
        if (!clipId && !videoUrl) {
            setError('Clip ID or video URL is required');
            return;
        }

        setAddingItem(true);
        setError(null);
        try {
            const payload = clipId
                ? [{ clip_id: clipId }]
                : [{
                    input_video_url: videoUrl,
                    input_title: itemTitle.trim() || null,
                    main_person: itemPerson.trim() || null,
                }];
            const res = await authFetch(`/provision/jobs/${selectedJobId}/items`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!res.ok) {
                const body = await res.text().catch(() => '');
                throw new Error(body || `HTTP ${res.status}`);
            }
            setItemClipId('');
            setItemVideoUrl('');
            setItemTitle('');
            setItemPerson('');
            await fetchJobDetail(selectedJobId);
            await fetchJobs();
        } catch (err: any) {
            setError(err?.message || 'Failed to add item');
        } finally {
            setAddingItem(false);
        }
    };

    const startProvisionJob = async () => {
        if (!selectedJobId || startingJob) return;
        setStartingJob(true);
        setError(null);
        try {
            const res = await authFetch(`/provision/jobs/${selectedJobId}/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ limit: 1 }),
            });
            if (!res.ok) {
                const body = await res.text().catch(() => '');
                throw new Error(body || `HTTP ${res.status}`);
            }
            await fetchJobDetail(selectedJobId);
            await fetchJobs();
        } catch (err: any) {
            setError(err?.message || 'Failed to start provision job');
        } finally {
            setStartingJob(false);
        }
    };

    const reviewVariant = async (variantId: string, reviewStatus: 'selected' | 'rejected' | 'manual_fix') => {
        if (reviewingVariantId || !selectedJobId) return;
        setReviewingVariantId(variantId);
        setError(null);
        try {
            const res = await authFetch(`/provision/variants/${variantId}/review`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ review_status: reviewStatus }),
            });
            if (!res.ok) {
                const body = await res.text().catch(() => '');
                throw new Error(body || `HTTP ${res.status}`);
            }
            await fetchJobDetail(selectedJobId);
            await fetchJobs();
        } catch (err: any) {
            setError(err?.message || 'Failed to update review');
        } finally {
            setReviewingVariantId(null);
        }
    };

    const toggleMode = (mode: EditMode) => {
        setSelectedModes(prev => {
            if (!prev.includes(mode)) {
                return [...prev, mode];
            }
            return prev.length > 1 ? prev.filter(item => item !== mode) : prev;
        });
    };

    const variantsByItem = (jobDetail?.variants ?? []).reduce<Record<string, ProvisionVariant[]>>((acc, variant) => {
        acc[variant.provision_item_id] = acc[variant.provision_item_id] ?? [];
        acc[variant.provision_item_id].push(variant);
        return acc;
    }, {});

    return (
        <main className="h-full overflow-y-auto px-6 pb-12 pt-4" style={{ background: '#141413' }}>
            <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
                <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                    <div>
                        <div className="mb-3 flex items-center gap-2">
                            <span
                                className="flex h-8 w-8 items-center justify-center rounded-xl"
                                style={{ background: 'rgba(250,249,245,0.08)', color: '#faf9f5' }}
                            >
                                <Sparkles size={16} />
                            </span>
                            <span className="text-xs font-semibold uppercase tracking-[0.22em]" style={{ color: '#ababab' }}>
                                Last Editor
                            </span>
                        </div>
                        <h1 className="text-3xl font-semibold tracking-tight" style={{ color: '#faf9f5' }}>
                            Provision
                        </h1>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                        <button
                            className="inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold opacity-60"
                            style={{ background: '#faf9f5', color: '#141413' }}
                            type="button"
                            disabled
                        >
                            <Upload size={15} />
                            Batch import soon
                        </button>
                        <button
                            className="inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-colors hover:bg-white/5"
                            style={{
                                color: '#faf9f5',
                                border: '1px solid rgba(250,249,245,0.08)',
                                background: 'rgba(250,249,245,0.03)',
                            }}
                            type="button"
                            onClick={createJob}
                            disabled={!activeChannelId || creatingJob}
                        >
                            {creatingJob ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
                            New run
                        </button>
                    </div>
                </div>

                {error && (
                    <div
                        className="rounded-xl px-4 py-3 text-sm"
                        style={{ color: '#fca5a5', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.18)' }}
                    >
                        {error}
                    </div>
                )}

                <div className="grid gap-3 md:grid-cols-4">
                    {STAGE_ITEMS.map(item => {
                        const Icon = item.icon;
                        return (
                            <div
                                key={item.label}
                                className="rounded-2xl p-4"
                                style={{ background: '#1c1c1b', border: '1px solid rgba(250,249,245,0.06)' }}
                            >
                                <div className="mb-4 flex items-center justify-between">
                                    <Icon size={18} style={{ color: '#faf9f5' }} />
                                    <CheckCircle2 size={15} style={{ color: 'rgba(250,249,245,0.35)' }} />
                                </div>
                                <p className="text-xs font-medium uppercase tracking-[0.18em]" style={{ color: '#737373' }}>
                                    {item.label}
                                </p>
                                <p className="mt-1 text-sm font-semibold" style={{ color: '#faf9f5' }}>
                                    {item.value}
                                </p>
                            </div>
                        );
                    })}
                </div>

                <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
                    <section
                        className="rounded-2xl p-5"
                        style={{ background: '#1c1c1b', border: '1px solid rgba(250,249,245,0.06)' }}
                    >
                        <div className="mb-5 flex items-center justify-between gap-4">
                            <div>
                                <h2 className="text-lg font-semibold" style={{ color: '#faf9f5' }}>
                                    Provision Jobs
                                </h2>
                                <p className="mt-1 text-sm" style={{ color: '#737373' }}>
                                    Manual last-editor runs for selected clips.
                                </p>
                            </div>
                            <button
                                type="button"
                                onClick={fetchJobs}
                                className="inline-flex items-center gap-2 rounded-lg px-2.5 py-1 text-xs font-semibold transition-colors hover:bg-white/5"
                                style={{ color: '#ababab', background: 'rgba(250,249,245,0.05)' }}
                            >
                                {loadingJobs ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                                Refresh
                            </button>
                        </div>

                        {jobs.length === 0 ? (
                            <div
                                className="flex min-h-[280px] flex-col items-center justify-center rounded-2xl border border-dashed px-6 text-center"
                                style={{ borderColor: 'rgba(250,249,245,0.12)', background: 'rgba(250,249,245,0.02)' }}
                            >
                                <FileVideo size={32} style={{ color: 'rgba(250,249,245,0.32)' }} />
                                <p className="mt-4 text-sm font-semibold" style={{ color: '#faf9f5' }}>
                                    No provision jobs
                                </p>
                                <p className="mt-1 max-w-md text-sm leading-6" style={{ color: '#737373' }}>
                                    Create a run, then add selected final clips before generating variants.
                                </p>
                            </div>
                        ) : (
                            <div className="space-y-2">
                                {jobs.map(job => (
                                    <button
                                        key={job.id}
                                        type="button"
                                        onClick={() => fetchJobDetail(job.id)}
                                        className="w-full rounded-xl p-4 text-left transition-colors hover:bg-white/5"
                                        style={{
                                            background: selectedJobId === job.id ? 'rgba(250,249,245,0.075)' : 'rgba(250,249,245,0.035)',
                                            border: `1px solid ${selectedJobId === job.id ? 'rgba(250,249,245,0.18)' : 'rgba(250,249,245,0.06)'}`,
                                        }}
                                    >
                                        <div className="flex items-start justify-between gap-4">
                                            <div className="min-w-0">
                                                <p className="truncate text-sm font-semibold" style={{ color: '#faf9f5' }}>
                                                    {job.name}
                                                </p>
                                                <p className="mt-1 text-xs" style={{ color: '#737373' }}>
                                                    {formatDate(job.created_at)}
                                                </p>
                                            </div>
                                            <StatusPill label={job.status} />
                                        </div>
                                        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                                            {[
                                                ['Items', job.item_count ?? 0],
                                                ['Done', job.completed_item_count ?? 0],
                                                ['Selected', job.selected_variant_count ?? 0],
                                            ].map(([label, value]) => (
                                                <div
                                                    key={label}
                                                    className="rounded-lg px-3 py-2"
                                                    style={{ background: 'rgba(250,249,245,0.035)' }}
                                                >
                                                    <div className="text-xs" style={{ color: '#737373' }}>{label}</div>
                                                    <div className="mt-1 text-sm font-semibold" style={{ color: '#faf9f5' }}>{value}</div>
                                                </div>
                                            ))}
                                        </div>
                                        <div className="mt-3">
                                            <div className="mb-1 flex items-center justify-between text-xs">
                                                <span style={{ color: '#737373' }}>{job.current_step || 'draft'}</span>
                                                <span style={{ color: '#737373' }}>{job.progress_pct ?? 0}%</span>
                                            </div>
                                            <div className="h-1.5 overflow-hidden rounded-full" style={{ background: 'rgba(250,249,245,0.06)' }}>
                                                <div
                                                    className="h-full rounded-full"
                                                    style={{
                                                        width: `${Math.max(0, Math.min(100, job.progress_pct ?? 0))}%`,
                                                        background: '#faf9f5',
                                                    }}
                                                />
                                            </div>
                                        </div>
                                    </button>
                                ))}
                            </div>
                        )}
                    </section>

                    <section
                        className="rounded-2xl p-5"
                        style={{ background: '#1c1c1b', border: '1px solid rgba(250,249,245,0.06)' }}
                    >
                        <div className="mb-5">
                            <h2 className="text-lg font-semibold" style={{ color: '#faf9f5' }}>
                                Variant Set
                            </h2>
                            <p className="mt-1 text-sm" style={{ color: '#737373' }}>
                                Generate multiple edits for each clip and keep the chosen one as feedback.
                            </p>
                        </div>

                        <div className="space-y-2">
                            {EDIT_MODES.map(mode => {
                                const selected = selectedModes.includes(mode.key);
                                return (
                                    <button
                                        key={mode.key}
                                        type="button"
                                        onClick={() => toggleMode(mode.key)}
                                        className="flex w-full items-start gap-3 rounded-xl p-4 text-left transition-colors hover:bg-white/5"
                                        style={{
                                            background: selected ? 'rgba(250,249,245,0.08)' : 'rgba(250,249,245,0.025)',
                                            border: `1px solid ${selected ? 'rgba(250,249,245,0.18)' : 'rgba(250,249,245,0.06)'}`,
                                        }}
                                    >
                                        <span
                                            className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full"
                                            style={{
                                                background: selected ? '#faf9f5' : 'transparent',
                                                border: `1px solid ${selected ? '#faf9f5' : 'rgba(250,249,245,0.18)'}`,
                                                color: '#141413',
                                            }}
                                        >
                                            {selected && <CheckCircle2 size={13} />}
                                        </span>
                                        <span className="min-w-0">
                                            <span className="block text-sm font-semibold" style={{ color: '#faf9f5' }}>
                                                {mode.label}
                                            </span>
                                            <span className="mt-1 block text-sm leading-5" style={{ color: '#737373' }}>
                                                {mode.description}
                                            </span>
                                        </span>
                                    </button>
                                );
                            })}
                        </div>
                    </section>
                </div>

                <section
                    className="rounded-2xl p-5"
                    style={{ background: '#1c1c1b', border: '1px solid rgba(250,249,245,0.06)' }}
                >
                    <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                        <div>
                            <h2 className="text-lg font-semibold" style={{ color: '#faf9f5' }}>
                                Selected Run
                            </h2>
                            <p className="mt-1 text-sm" style={{ color: '#737373' }}>
                                Add final captioned clips, then review the generated edit variants.
                            </p>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                            {jobDetail && <StatusPill label={`${jobDetail.items.length} items`} />}
                            {jobDetail && (
                                <button
                                    type="button"
                                    onClick={startProvisionJob}
                                    disabled={startingJob || jobDetail.status === 'processing' || jobDetail.items.length === 0}
                                    className="inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-colors hover:bg-white/90 disabled:opacity-60"
                                    style={{ background: '#faf9f5', color: '#141413' }}
                                >
                                    {startingJob || jobDetail.status === 'processing' ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
                                    Plan next item
                                </button>
                            )}
                        </div>
                    </div>

                    {loadingDetail ? (
                        <div className="flex min-h-[220px] items-center justify-center">
                            <Loader2 className="animate-spin" size={24} style={{ color: '#faf9f5' }} />
                        </div>
                    ) : !jobDetail ? (
                        <div
                            className="flex min-h-[220px] items-center justify-center rounded-2xl border border-dashed px-6 text-center"
                            style={{ borderColor: 'rgba(250,249,245,0.12)', background: 'rgba(250,249,245,0.02)' }}
                        >
                            <p className="text-sm" style={{ color: '#737373' }}>
                                Create or select a provision job to add clips.
                            </p>
                        </div>
                    ) : (
                        <div className="grid gap-5 xl:grid-cols-[0.85fr_1.15fr]">
                            <div
                                className="rounded-2xl p-4"
                                style={{ background: 'rgba(250,249,245,0.025)', border: '1px solid rgba(250,249,245,0.06)' }}
                            >
                                <h3 className="text-sm font-semibold" style={{ color: '#faf9f5' }}>
                                    Add Clip
                                </h3>
                                <p className="mt-1 text-sm leading-6" style={{ color: '#737373' }}>
                                    Use a clip ID from My Projects, or paste a captioned MP4 URL for manual testing.
                                </p>

                                <div className="mt-4 space-y-3">
                                    <input
                                        value={itemClipId}
                                        onChange={(e) => setItemClipId(e.target.value)}
                                        placeholder="Clip ID"
                                        className="w-full rounded-xl px-3 py-2 text-sm outline-none"
                                        style={{ background: '#141413', border: '1px solid rgba(250,249,245,0.12)', color: '#faf9f5' }}
                                    />
                                    <div className="flex items-center gap-3">
                                        <div className="h-px flex-1" style={{ background: 'rgba(250,249,245,0.08)' }} />
                                        <span className="text-xs uppercase tracking-[0.18em]" style={{ color: '#525252' }}>or</span>
                                        <div className="h-px flex-1" style={{ background: 'rgba(250,249,245,0.08)' }} />
                                    </div>
                                    <input
                                        value={itemVideoUrl}
                                        onChange={(e) => setItemVideoUrl(e.target.value)}
                                        placeholder="Captioned MP4 URL"
                                        className="w-full rounded-xl px-3 py-2 text-sm outline-none"
                                        style={{ background: '#141413', border: '1px solid rgba(250,249,245,0.12)', color: '#faf9f5' }}
                                    />
                                    <input
                                        value={itemTitle}
                                        onChange={(e) => setItemTitle(e.target.value)}
                                        placeholder="Title"
                                        className="w-full rounded-xl px-3 py-2 text-sm outline-none"
                                        style={{ background: '#141413', border: '1px solid rgba(250,249,245,0.12)', color: '#faf9f5' }}
                                    />
                                    <input
                                        value={itemPerson}
                                        onChange={(e) => setItemPerson(e.target.value)}
                                        placeholder="Main person"
                                        className="w-full rounded-xl px-3 py-2 text-sm outline-none"
                                        style={{ background: '#141413', border: '1px solid rgba(250,249,245,0.12)', color: '#faf9f5' }}
                                    />
                                    <button
                                        type="button"
                                        onClick={addItem}
                                        disabled={addingItem}
                                        className="inline-flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-colors hover:bg-white/90 disabled:opacity-60"
                                        style={{ background: '#faf9f5', color: '#141413' }}
                                    >
                                        {addingItem ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
                                        Add to run
                                    </button>
                                </div>
                            </div>

                            <div className="space-y-3">
                                {jobDetail.items.length === 0 ? (
                                    <div
                                        className="flex min-h-[260px] items-center justify-center rounded-2xl border border-dashed px-6 text-center"
                                        style={{ borderColor: 'rgba(250,249,245,0.12)', background: 'rgba(250,249,245,0.02)' }}
                                    >
                                        <p className="text-sm" style={{ color: '#737373' }}>
                                            This run has no clips yet.
                                        </p>
                                    </div>
                                ) : (
                                    jobDetail.items.map(item => {
                                        const variants = variantsByItem[item.id] ?? [];
                                        return (
                                            <div
                                                key={item.id}
                                                className="rounded-2xl p-4"
                                                style={{ background: 'rgba(250,249,245,0.025)', border: '1px solid rgba(250,249,245,0.06)' }}
                                            >
                                                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                                                    <div className="min-w-0">
                                                        <p className="truncate text-sm font-semibold" style={{ color: '#faf9f5' }}>
                                                            {item.input_title || `Clip ${shortId(item.id)}`}
                                                        </p>
                                                    <p className="mt-1 text-xs" style={{ color: '#737373' }}>
                                                            {item.main_person || 'No main person'} · {item.current_step || 'queued'} · {formatDate(item.created_at)}
                                                        </p>
                                                    </div>
                                                    <StatusPill label={item.status} />
                                                </div>

                                                <a
                                                    href={item.input_video_url}
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    className="mt-3 block truncate text-xs hover:underline"
                                                    style={{ color: '#ababab' }}
                                                >
                                                    {item.input_video_url}
                                                </a>

                                                <div className="mt-4 grid gap-2 md:grid-cols-2">
                                                    {variants.map(variant => (
                                                        <div
                                                            key={variant.id}
                                                            className="rounded-xl p-3"
                                                            style={{ background: 'rgba(250,249,245,0.035)', border: '1px solid rgba(250,249,245,0.06)' }}
                                                        >
                                                            <div className="flex items-center justify-between gap-2">
                                                                <span className="text-sm font-semibold capitalize" style={{ color: '#faf9f5' }}>
                                                                    {variant.variant_mode}
                                                                </span>
                                                                <StatusPill label={variant.status} />
                                                            </div>
                                                            <div className="mt-2 flex items-center justify-between gap-2">
                                                                <span className="text-xs capitalize" style={{ color: '#737373' }}>
                                                                    {variant.review_status.replace(/_/g, ' ')}
                                                                    {typeof variant.score === 'number' ? ` · score ${variant.score}` : ''}
                                                                </span>
                                                                {variant.output_video_url && (
                                                                    <a
                                                                        href={variant.output_video_url}
                                                                        target="_blank"
                                                                        rel="noreferrer"
                                                                        className="text-xs font-semibold hover:underline"
                                                                        style={{ color: '#faf9f5' }}
                                                                    >
                                                                        Open
                                                                    </a>
                                                                )}
                                                            </div>
                                                            <div className="mt-3 flex flex-wrap gap-2">
                                                                {(['selected', 'manual_fix', 'rejected'] as const).map(status => (
                                                                    <button
                                                                        key={status}
                                                                        type="button"
                                                                        onClick={() => reviewVariant(variant.id, status)}
                                                                        disabled={reviewingVariantId === variant.id}
                                                                        className="rounded-lg px-2 py-1 text-xs font-semibold capitalize transition-colors hover:bg-white/10 disabled:opacity-60"
                                                                        style={{
                                                                            color: variant.review_status === status ? '#141413' : '#ababab',
                                                                            background: variant.review_status === status ? '#faf9f5' : 'rgba(250,249,245,0.05)',
                                                                        }}
                                                                    >
                                                                        {reviewingVariantId === variant.id ? 'Saving' : status.replace(/_/g, ' ')}
                                                                    </button>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        );
                                    })
                                )}
                            </div>
                        </div>
                    )}
                </section>

                <div className="grid gap-6 xl:grid-cols-2">
                    <section
                        className="rounded-2xl p-5"
                        style={{ background: '#1c1c1b', border: '1px solid rgba(250,249,245,0.06)' }}
                    >
                        <div className="mb-5 flex items-center gap-2">
                            <ListChecks size={18} style={{ color: '#faf9f5' }} />
                            <h2 className="text-lg font-semibold" style={{ color: '#faf9f5' }}>
                                Guardrails
                            </h2>
                        </div>
                        <div className="space-y-2">
                            <SettingRow label="Max internal cuts" value="2" />
                            <SettingRow label="Max duration reduction" value="35%" />
                            <SettingRow label="Minimum final duration" value="12s" />
                            <SettingRow label="Boundary snap" value="Word timestamps" />
                        </div>
                    </section>

                    <section
                        className="rounded-2xl p-5"
                        style={{ background: '#1c1c1b', border: '1px solid rgba(250,249,245,0.06)' }}
                    >
                        <div className="mb-5 flex items-center gap-2">
                            <Gauge size={18} style={{ color: '#faf9f5' }} />
                            <h2 className="text-lg font-semibold" style={{ color: '#faf9f5' }}>
                                Review Labels
                            </h2>
                        </div>
                        <div className="grid gap-2 sm:grid-cols-3">
                            {['Selected', 'Manual fix', 'Rejected'].map(label => (
                                <div
                                    key={label}
                                    className="rounded-xl px-4 py-3 text-sm font-semibold"
                                    style={{ color: '#faf9f5', background: 'rgba(250,249,245,0.035)', border: '1px solid rgba(250,249,245,0.06)' }}
                                >
                                    {label}
                                </div>
                            ))}
                        </div>
                    </section>
                </div>
            </div>
        </main>
    );
}
