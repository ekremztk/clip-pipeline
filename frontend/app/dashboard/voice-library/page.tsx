'use client';

import { useState, useEffect, useRef } from 'react';
import { Plus, Trash2, X, Loader2, AudioLines, Upload } from 'lucide-react';
import { authFetch } from '@/lib/api';

interface Voice {
    id: string;
    name: string;
    role: 'host' | 'guest';
    sample_duration_sec: number | null;
    audio_path: string | null;
    created_at: string;
    updated_at?: string;
}

const ALLOWED_EXTS = ['.wav', '.mp3', '.m4a', '.flac', '.ogg', '.webm', '.mp4'];
const MAX_SIZE_MB = 25;

function formatDuration(sec: number | null): string {
    if (!sec || sec <= 0) return '—';
    const m = Math.floor(sec / 60);
    const s = Math.round(sec % 60);
    if (m === 0) return `${s}s`;
    return `${m}m ${s.toString().padStart(2, '0')}s`;
}

function formatDate(iso: string): string {
    try {
        const d = new Date(iso);
        return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    } catch {
        return iso;
    }
}

export default function VoiceLibraryPage() {
    const [voices, setVoices] = useState<Voice[]>([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState<string | null>(null);

    const [showAdd, setShowAdd] = useState(false);
    const [name, setName] = useState('');
    const [role, setRole] = useState<'host' | 'guest'>('guest');
    const [file, setFile] = useState<File | null>(null);
    const [submitting, setSubmitting] = useState(false);
    const [formError, setFormError] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const [deletingId, setDeletingId] = useState<string | null>(null);
    const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

    useEffect(() => {
        fetchVoices();
    }, []);

    useEffect(() => {
        if (!toast) return;
        const t = setTimeout(() => setToast(null), 4000);
        return () => clearTimeout(t);
    }, [toast]);

    const fetchVoices = async () => {
        setLoading(true);
        setLoadError(null);
        try {
            const res = await authFetch('/voice-library');
            if (!res.ok) {
                const body = await res.text().catch(() => '');
                throw new Error(body || `HTTP ${res.status}`);
            }
            const data = await res.json();
            setVoices(Array.isArray(data) ? data : []);
        } catch (e: any) {
            setLoadError(e?.message || 'Failed to load voices');
        } finally {
            setLoading(false);
        }
    };

    const resetForm = () => {
        setName('');
        setRole('guest');
        setFile(null);
        setFormError(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    const closeModal = () => {
        if (submitting) return;
        setShowAdd(false);
        resetForm();
    };

    const handleFilePick = (f: File | null) => {
        setFormError(null);
        if (!f) {
            setFile(null);
            return;
        }
        const lower = f.name.toLowerCase();
        const hasValidExt = ALLOWED_EXTS.some(ext => lower.endsWith(ext));
        if (!hasValidExt) {
            setFormError(`Unsupported format. Allowed: ${ALLOWED_EXTS.join(', ')}`);
            setFile(null);
            return;
        }
        if (f.size > MAX_SIZE_MB * 1024 * 1024) {
            setFormError(`File too large (max ${MAX_SIZE_MB} MB)`);
            setFile(null);
            return;
        }
        setFile(f);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError(null);

        const trimmed = name.trim();
        if (!trimmed) {
            setFormError('Name is required');
            return;
        }
        if (!file) {
            setFormError('Please select an audio file');
            return;
        }

        setSubmitting(true);
        try {
            const formData = new FormData();
            formData.append('name', trimmed);
            formData.append('role', role);
            formData.append('file', file);

            const res = await authFetch('/voice-library', {
                method: 'POST',
                body: formData,
            });

            if (!res.ok) {
                const body = await res.text().catch(() => '');
                let detail = body;
                try {
                    const parsed = JSON.parse(body);
                    detail = parsed.detail || body;
                } catch {}
                throw new Error(detail || `HTTP ${res.status}`);
            }

            const created: Voice = await res.json();
            setVoices(prev => [created, ...prev]);
            setToast({ type: 'success', message: `Added "${created.name}"` });
            setShowAdd(false);
            resetForm();
        } catch (e: any) {
            setFormError(e?.message || 'Failed to add voice');
        } finally {
            setSubmitting(false);
        }
    };

    const handleDelete = async (voice: Voice) => {
        if (!confirm(`Delete voice "${voice.name}"? This cannot be undone.`)) return;
        setDeletingId(voice.id);
        try {
            const res = await authFetch(`/voice-library/${voice.id}`, { method: 'DELETE' });
            if (!res.ok) {
                const body = await res.text().catch(() => '');
                throw new Error(body || `HTTP ${res.status}`);
            }
            setVoices(prev => prev.filter(v => v.id !== voice.id));
            setToast({ type: 'success', message: `Deleted "${voice.name}"` });
        } catch (e: any) {
            setToast({ type: 'error', message: e?.message || 'Failed to delete voice' });
        } finally {
            setDeletingId(null);
        }
    };

    return (
        <div className="min-h-full" style={{ background: '#141413', color: '#faf9f5' }}>
            <div className="max-w-5xl mx-auto px-8 py-10">
                {/* Header */}
                <div className="flex items-start justify-between mb-8">
                    <div>
                        <h1 className="text-2xl font-medium tracking-tight mb-2" style={{ color: '#faf9f5' }}>
                            Voice Library
                        </h1>
                        <p className="text-sm" style={{ color: '#ababab', maxWidth: 560 }}>
                            Upload a clean audio sample of a person's voice to register their fingerprint.
                            The pipeline uses these to identify the target guest across episodes.
                        </p>
                    </div>
                    <button
                        onClick={() => setShowAdd(true)}
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors"
                        style={{ background: '#faf9f5', color: '#141413' }}
                    >
                        <Plus className="w-4 h-4" />
                        Add Voice
                    </button>
                </div>

                {/* Content */}
                {loading ? (
                    <div className="flex items-center justify-center py-16" style={{ color: '#ababab' }}>
                        <Loader2 className="w-5 h-5 animate-spin" />
                    </div>
                ) : loadError ? (
                    <div
                        className="rounded-xl p-6 text-sm"
                        style={{
                            background: 'rgba(239,68,68,0.08)',
                            border: '1px solid rgba(239,68,68,0.2)',
                            color: '#f87171',
                        }}
                    >
                        {loadError}
                    </div>
                ) : voices.length === 0 ? (
                    <div
                        className="rounded-xl p-12 text-center"
                        style={{
                            background: 'rgba(250,249,245,0.03)',
                            border: '1px dashed rgba(250,249,245,0.12)',
                        }}
                    >
                        <AudioLines className="w-8 h-8 mx-auto mb-3" style={{ color: '#525252' }} />
                        <div className="text-sm font-medium mb-1" style={{ color: '#faf9f5' }}>
                            No voices yet
                        </div>
                        <div className="text-xs" style={{ color: '#737373' }}>
                            Add your first voice fingerprint to get started.
                        </div>
                    </div>
                ) : (
                    <div
                        className="rounded-xl overflow-hidden"
                        style={{
                            background: 'rgba(250,249,245,0.03)',
                            border: '1px solid rgba(250,249,245,0.08)',
                        }}
                    >
                        <div
                            className="grid grid-cols-12 gap-4 px-5 py-3 text-xs uppercase tracking-wider"
                            style={{
                                background: 'rgba(250,249,245,0.03)',
                                borderBottom: '1px solid rgba(250,249,245,0.08)',
                                color: '#737373',
                            }}
                        >
                            <div className="col-span-5">Name</div>
                            <div className="col-span-2">Role</div>
                            <div className="col-span-2">Duration</div>
                            <div className="col-span-2">Added</div>
                            <div className="col-span-1"></div>
                        </div>
                        {voices.map(v => (
                            <div
                                key={v.id}
                                className="grid grid-cols-12 gap-4 px-5 py-3 items-center text-sm"
                                style={{ borderBottom: '1px solid rgba(250,249,245,0.05)' }}
                            >
                                <div className="col-span-5 flex items-center gap-3">
                                    <div
                                        className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
                                        style={{ background: 'rgba(250,249,245,0.06)' }}
                                    >
                                        <AudioLines className="w-4 h-4" style={{ color: '#ababab' }} />
                                    </div>
                                    <span className="truncate" style={{ color: '#faf9f5' }}>
                                        {v.name}
                                    </span>
                                </div>
                                <div className="col-span-2">
                                    <span
                                        className="px-2 py-0.5 rounded-md text-xs font-medium"
                                        style={{
                                            background: v.role === 'host' ? 'rgba(139,92,246,0.12)' : 'rgba(34,197,94,0.10)',
                                            color: v.role === 'host' ? '#a78bfa' : '#4ade80',
                                            border: v.role === 'host' ? '1px solid rgba(139,92,246,0.25)' : '1px solid rgba(34,197,94,0.2)',
                                        }}
                                    >
                                        {v.role ?? 'guest'}
                                    </span>
                                </div>
                                <div className="col-span-2" style={{ color: '#ababab' }}>
                                    {formatDuration(v.sample_duration_sec)}
                                </div>
                                <div className="col-span-2" style={{ color: '#ababab' }}>
                                    {formatDate(v.created_at)}
                                </div>
                                <div className="col-span-1 flex justify-end">
                                    <button
                                        onClick={() => handleDelete(v)}
                                        disabled={deletingId === v.id}
                                        className="p-2 rounded-lg transition-colors disabled:opacity-40"
                                        style={{ color: '#737373' }}
                                        title="Delete"
                                        onMouseEnter={e => {
                                            e.currentTarget.style.background = 'rgba(239,68,68,0.1)';
                                            e.currentTarget.style.color = '#f87171';
                                        }}
                                        onMouseLeave={e => {
                                            e.currentTarget.style.background = 'transparent';
                                            e.currentTarget.style.color = '#737373';
                                        }}
                                    >
                                        {deletingId === v.id ? (
                                            <Loader2 className="w-4 h-4 animate-spin" />
                                        ) : (
                                            <Trash2 className="w-4 h-4" />
                                        )}
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Add modal */}
            {showAdd && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center p-4"
                    style={{ background: 'rgba(0,0,0,0.6)' }}
                    onClick={closeModal}
                >
                    <div
                        className="w-full max-w-md rounded-2xl overflow-hidden"
                        style={{
                            background: '#1c1c1b',
                            border: '1px solid rgba(250,249,245,0.1)',
                        }}
                        onClick={e => e.stopPropagation()}
                    >
                        <div
                            className="flex items-center justify-between px-6 py-4"
                            style={{ borderBottom: '1px solid rgba(250,249,245,0.08)' }}
                        >
                            <h2 className="text-base font-medium" style={{ color: '#faf9f5' }}>
                                Add Voice
                            </h2>
                            <button
                                onClick={closeModal}
                                disabled={submitting}
                                className="p-1 rounded-lg transition-colors disabled:opacity-40"
                                style={{ color: '#ababab' }}
                            >
                                <X className="w-4 h-4" />
                            </button>
                        </div>

                        <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
                            <div>
                                <label
                                    className="block text-xs uppercase tracking-wider mb-2"
                                    style={{ color: '#737373' }}
                                >
                                    Name
                                </label>
                                <input
                                    type="text"
                                    value={name}
                                    onChange={e => setName(e.target.value)}
                                    placeholder="e.g. Rowan Atkinson"
                                    maxLength={120}
                                    disabled={submitting}
                                    className="w-full rounded-xl px-3 py-2 text-sm focus:outline-none transition-colors"
                                    style={{
                                        background: '#111110',
                                        border: '1px solid rgba(250,249,245,0.1)',
                                        color: '#faf9f5',
                                    }}
                                />
                            </div>

                            <div>
                                <label
                                    className="block text-xs uppercase tracking-wider mb-2"
                                    style={{ color: '#737373' }}
                                >
                                    Role
                                </label>
                                <div className="flex gap-2">
                                    {(['guest', 'host'] as const).map(r => (
                                        <button
                                            key={r}
                                            type="button"
                                            disabled={submitting}
                                            onClick={() => setRole(r)}
                                            className="flex-1 py-2 rounded-xl text-sm font-medium transition-colors capitalize disabled:opacity-40"
                                            style={{
                                                background: role === r
                                                    ? (r === 'host' ? 'rgba(139,92,246,0.15)' : 'rgba(34,197,94,0.12)')
                                                    : 'rgba(250,249,245,0.04)',
                                                border: role === r
                                                    ? (r === 'host' ? '1px solid rgba(139,92,246,0.35)' : '1px solid rgba(34,197,94,0.3)')
                                                    : '1px solid rgba(250,249,245,0.08)',
                                                color: role === r
                                                    ? (r === 'host' ? '#a78bfa' : '#4ade80')
                                                    : '#737373',
                                            }}
                                        >
                                            {r}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div>
                                <label
                                    className="block text-xs uppercase tracking-wider mb-2"
                                    style={{ color: '#737373' }}
                                >
                                    Audio sample
                                </label>
                                <div
                                    className="rounded-xl px-4 py-4 cursor-pointer transition-colors"
                                    style={{
                                        background: '#111110',
                                        border: '1px dashed rgba(250,249,245,0.15)',
                                    }}
                                    onClick={() => !submitting && fileInputRef.current?.click()}
                                >
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        accept={ALLOWED_EXTS.join(',')}
                                        className="hidden"
                                        onChange={e => handleFilePick(e.target.files?.[0] || null)}
                                        disabled={submitting}
                                    />
                                    <div className="flex items-center gap-3">
                                        <div
                                            className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                                            style={{ background: 'rgba(250,249,245,0.06)' }}
                                        >
                                            <Upload className="w-4 h-4" style={{ color: '#ababab' }} />
                                        </div>
                                        <div className="min-w-0 flex-1">
                                            {file ? (
                                                <>
                                                    <div
                                                        className="text-sm truncate"
                                                        style={{ color: '#faf9f5' }}
                                                    >
                                                        {file.name}
                                                    </div>
                                                    <div className="text-xs" style={{ color: '#737373' }}>
                                                        {(file.size / 1024 / 1024).toFixed(2)} MB
                                                    </div>
                                                </>
                                            ) : (
                                                <>
                                                    <div
                                                        className="text-sm"
                                                        style={{ color: '#faf9f5' }}
                                                    >
                                                        Click to select an audio file
                                                    </div>
                                                    <div className="text-xs" style={{ color: '#737373' }}>
                                                        {ALLOWED_EXTS.join(', ')} — max {MAX_SIZE_MB} MB
                                                    </div>
                                                </>
                                            )}
                                        </div>
                                    </div>
                                </div>
                                <p className="mt-2 text-xs" style={{ color: '#737373' }}>
                                    Use a clean sample (3-10s, single speaker, no music).
                                </p>
                            </div>

                            {formError && (
                                <div
                                    className="rounded-xl px-3 py-2 text-sm"
                                    style={{
                                        background: 'rgba(239,68,68,0.08)',
                                        border: '1px solid rgba(239,68,68,0.2)',
                                        color: '#f87171',
                                    }}
                                >
                                    {formError}
                                </div>
                            )}

                            <div className="flex items-center justify-end gap-2 pt-2">
                                <button
                                    type="button"
                                    onClick={closeModal}
                                    disabled={submitting}
                                    className="px-4 py-2 rounded-xl text-sm transition-colors disabled:opacity-40"
                                    style={{ color: '#ababab' }}
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={submitting || !name.trim() || !file}
                                    className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                    style={{ background: '#faf9f5', color: '#141413' }}
                                >
                                    {submitting ? (
                                        <>
                                            <Loader2 className="w-4 h-4 animate-spin" />
                                            Processing…
                                        </>
                                    ) : (
                                        <>
                                            <Plus className="w-4 h-4" />
                                            Add
                                        </>
                                    )}
                                </button>
                            </div>

                            {submitting && (
                                <p className="text-xs text-center" style={{ color: '#737373' }}>
                                    Computing voice fingerprint on GPU — this takes 5-10 seconds.
                                </p>
                            )}
                        </form>
                    </div>
                </div>
            )}

            {/* Toast */}
            {toast && (
                <div
                    className="fixed bottom-6 right-6 z-50 rounded-xl px-4 py-3 text-sm shadow-lg"
                    style={{
                        background: toast.type === 'success' ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)',
                        border: toast.type === 'success'
                            ? '1px solid rgba(34,197,94,0.3)'
                            : '1px solid rgba(239,68,68,0.3)',
                        color: toast.type === 'success' ? '#4ade80' : '#f87171',
                    }}
                >
                    {toast.message}
                </div>
            )}
        </div>
    );
}
