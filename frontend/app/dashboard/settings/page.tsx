'use client';

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Settings, Trash2, Upload, X, ChevronRight, Check, AlertCircle, Loader2, Dna, Film, Sparkles, Pencil } from 'lucide-react';
import { useChannel } from '../layout';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Channel {
    id: string;
    display_name?: string;
    name?: string;
    niche?: string;
    channel_dna?: any;
    onboarding_status?: string;
    successful_clips_count?: number;
}

interface ReferenceClip {
    id: string;
    title: string;
    source?: string;
    created_at?: string;
}

const MultiTagInput = ({ value, onChange, placeholder, colorClass }: { value: string[], onChange: (v: string[]) => void, placeholder?: string, colorClass?: string }) => {
    const [input, setInput] = useState('');

    const safeValue = Array.isArray(value) ? value : [];

    const commitTag = (valToCommit: string) => {
        const val = valToCommit.trim();
        if (val && !safeValue.includes(val)) {
            onChange([...safeValue, val]);
        }
        setInput('');
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            commitTag(input);
        }
    };

    const handleBlur = () => {
        if (input.trim()) {
            commitTag(input);
        }
    };

    return (
        <div className="space-y-2">
            {safeValue.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                    {safeValue.map((tag, i) => (
                        <span key={i} className={`flex items-center gap-1 text-xs px-2.5 py-1 border rounded-lg ${colorClass || 'bg-white/[0.06] text-zinc-300 border-white/[0.1]'}`}>
                            {tag}
                            <button type="button" onClick={() => onChange(safeValue.filter((_, idx) => idx !== i))} className="ml-1 opacity-70 hover:opacity-100 transition-opacity"><X className="w-3 h-3" /></button>
                        </span>
                    ))}
                </div>
            )}
            <input
                type="text"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                onBlur={handleBlur}
                placeholder={placeholder}
                className="w-full bg-zinc-900 border border-white/[0.08] rounded-xl px-3 py-2 text-sm text-white placeholder-zinc-600 focus:border-violet-500/50 outline-none transition-all"
            />
        </div>
    );
};

export default function ChannelSettingsPage() {
    const { channels, setActiveChannelId } = useChannel();
    const [selectedChannel, setSelectedChannel] = useState<Channel | null>(null);
    const [referenceClips, setReferenceClips] = useState<ReferenceClip[]>([]);
    const [showAddModal, setShowAddModal] = useState(false);
    const [showDeleteModal, setShowDeleteModal] = useState(false);
    const [uploading, setUploading] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [newChannel, setNewChannel] = useState({ name: '', niche: '', description: '' });
    const [creating, setCreating] = useState(false);

    // Stats
    const [totalClips, setTotalClips] = useState<number>(0);

    // Header Editing
    const [editingHeader, setEditingHeader] = useState(false);
    const [headerForm, setHeaderForm] = useState({ display_name: '', niche: '' });

    // DNA Editor
    const [editingDna, setEditingDna] = useState(false);
    const [savingDna, setSavingDna] = useState(false);
    const [dnaForm, setDnaForm] = useState<any>({});

    const formatText = (text: string) => {
        if (!text) return '';
        return text.replace(/_/g, ' ').split(' ').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
    };

    const renderTags = (data: any, colorClass: string = "bg-violet-500/10 text-violet-300 border-violet-500/20") => {
        if (!data) return null;

        if (typeof data === 'string') {
            return <span className={`text-xs px-2.5 py-1 border rounded-lg ${colorClass}`}>{formatText(data)}</span>;
        }

        if (Array.isArray(data)) {
            return data.map((item, i) => (
                <span key={i} className={`text-xs px-2.5 py-1 border rounded-lg ${colorClass}`}>
                    {typeof item === 'string' ? formatText(item) : formatText(JSON.stringify(item))}
                </span>
            ));
        }

        if (typeof data === 'object') {
            return Object.entries(data).map(([key, value], i) => {
                if (Array.isArray(value)) {
                    return value.map((v, j) => (
                        <span key={`${i}-${j}`} className={`text-xs px-2.5 py-1 border rounded-lg ${colorClass}`}>
                            <span className="opacity-50 mr-1">{formatText(key)}:</span>
                            {typeof v === 'string' ? formatText(v) : formatText(JSON.stringify(v))}
                        </span>
                    ));
                }
                if (typeof value === 'object' && value !== null) {
                    return <span key={i} className={`text-xs px-2.5 py-1 border rounded-lg ${colorClass}`}>
                        <span className="opacity-50 mr-1">{formatText(key)}:</span>
                        {formatText(JSON.stringify(value))}
                    </span>;
                }
                return (
                    <span key={i} className={`text-xs px-2.5 py-1 border rounded-lg ${colorClass}`}>
                        <span className="opacity-50 mr-1">{formatText(key)}:</span>
                        {typeof value === 'string' ? formatText(value) : String(value)}
                    </span>
                );
            });
        }

        return <span className={`text-xs px-2.5 py-1 border rounded-lg ${colorClass}`}>{String(data)}</span>;
    };

    useEffect(() => {
        if (selectedChannel) {
            fetchReferenceClips(selectedChannel.id);
            fetchTotalClips(selectedChannel.id);
            setEditingHeader(false);
            setEditingDna(false);
        }
    }, [selectedChannel]);

    const fetchTotalClips = async (channelId: string) => {
        try {
            const res = await fetch(`${API}/clips?channel_id=${channelId}&limit=200`);
            if (res.ok) {
                const data = await res.json();
                setTotalClips(data.length);
            } else {
                setTotalClips(selectedChannel?.successful_clips_count || 0);
            }
        } catch (e) {
            console.error(e);
            setTotalClips(selectedChannel?.successful_clips_count || 0);
        }
    };

    const fetchReferenceClips = async (channelId: string) => {
        try {
            const res = await fetch(`${API}/channels/${channelId}/references`);
            if (res.ok) setReferenceClips((await res.json()) || []);
        } catch (e) { console.error(e); }
    };

    const handleCreateChannel = async () => {
        if (!newChannel.name.trim()) return;
        setCreating(true);
        try {
            const res = await fetch(`${API}/channels`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    channel_id: newChannel.name.toLowerCase().replace(/\s+/g, '_'),
                    display_name: newChannel.name,
                    niche: newChannel.niche,
                    channel_vision: newChannel.description,
                }),
            });
            if (res.ok) { setShowAddModal(false); setNewChannel({ name: '', niche: '', description: '' }); window.location.reload(); }
        } catch (e) { console.error(e); }
        finally { setCreating(false); }
    };

    const handleUploadReference = async (file: File) => {
        if (!selectedChannel) return;
        setUploading(true);
        try {
            const formData = new FormData();
            formData.append('file', file);
            await fetch(`${API}/channels/${selectedChannel.id}/references`, { method: 'POST', body: formData });
            fetchReferenceClips(selectedChannel.id);
        } catch (e) { console.error(e); }
        finally { setUploading(false); }
    };

    const handleSaveHeader = async () => {
        if (!selectedChannel) return;
        try {
            const res = await fetch(`${API}/channels/${selectedChannel.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ display_name: headerForm.display_name, niche: headerForm.niche })
            });
            if (res.ok) {
                setSelectedChannel({ ...selectedChannel, display_name: headerForm.display_name, niche: headerForm.niche });
                setEditingHeader(false);
                // Trigger an update if needed globally
            }
        } catch (e) { console.error(e); }
    };

    const handleStartEditHeader = () => {
        setHeaderForm({
            display_name: selectedChannel?.display_name || selectedChannel?.name || selectedChannel?.id || '',
            niche: selectedChannel?.niche || ''
        });
        setEditingHeader(true);
    };

    const handleStartEditDna = () => {
        let parsed = {};
        const raw = selectedChannel?.channel_dna;
        if (typeof raw === 'string') {
            try { parsed = JSON.parse(raw); } catch { parsed = {}; }
        } else if (typeof raw === 'object' && raw !== null) {
            parsed = raw;
        }

        const p = parsed as any;
        setDnaForm({
            tone: p.tone || [],
            humor_profile: {
                style: p.humor_profile?.style || '',
                triggers: p.humor_profile?.triggers || [],
                frequency: p.humor_profile?.frequency || ''
            },
            do_list: p.do_list || [],
            dont_list: p.dont_list || [],
            hook_style: p.hook_style || '',
            no_go_zones: p.no_go_zones || [],
            sacred_topics: p.sacred_topics || [],
            best_content_types: p.best_content_types || [],
            audience_identity: p.audience_identity || p.target_audience || '',
            speaker_preference: p.speaker_preference || '',
            avg_successful_duration: p.avg_successful_duration || 30
        });
        setEditingDna(true);
    };

    const handleSaveDna = async () => {
        if (!selectedChannel) return;
        setSavingDna(true);
        try {
            const res = await fetch(`${API}/channels/${selectedChannel.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ channel_dna: dnaForm })
            });
            if (res.ok) {
                setSelectedChannel({ ...selectedChannel, channel_dna: dnaForm });
                setEditingDna(false);
            }
        } catch (e) { console.error(e); }
        finally { setSavingDna(false); }
    };

    const getStatusConfig = (ch: Channel | null) => {
        if (!ch) return { label: 'Setup Required', dot: 'bg-zinc-500', text: 'text-zinc-400', bg: 'bg-zinc-800/50 border-zinc-700/50' };

        let parsedDna = ch.channel_dna;
        if (typeof parsedDna === 'string') {
            try { parsedDna = JSON.parse(parsedDna); } catch { parsedDna = null; }
        }
        const hasDna = parsedDna && typeof parsedDna === 'object' && Object.keys(parsedDna).length > 0;

        if (hasDna) {
            return { label: 'Ready', dot: 'bg-emerald-400', text: 'text-emerald-400', bg: 'bg-emerald-400/10 border-emerald-400/20' };
        }

        const hasRefClips = (ch.id === selectedChannel?.id) ? referenceClips.length > 0 : ch.onboarding_status === 'processing';

        if (hasRefClips || ch.onboarding_status === 'processing') {
            return { label: 'Training', dot: 'bg-yellow-400 animate-pulse', text: 'text-yellow-400', bg: 'bg-yellow-400/10 border-yellow-400/20' };
        }

        return { label: 'Setup Required', dot: 'bg-zinc-500', text: 'text-zinc-400', bg: 'bg-zinc-800/50 border-zinc-700/50' };
    };

    const dna = (() => {
        const raw = selectedChannel?.channel_dna;
        if (!raw) return null;
        if (typeof raw === 'string') {
            try { return JSON.parse(raw); } catch { return null; }
        }
        return raw;
    })();

    const contentTypesOptions = ['revelation', 'debate', 'humor', 'insight', 'emotional', 'controversial', 'storytelling', 'celebrity_conflict', 'hot_take', 'funny_reaction', 'unexpected_answer', 'relatable_moment', 'educational_insight'];

    try {
        return (
            <div className="flex h-[calc(100vh-64px)] overflow-hidden bg-[#09090b]">

                {/* ── LEFT PANEL ── */}
                <div className="w-[360px] flex-shrink-0 border-r border-white/[0.06] flex flex-col">
                    <div className="p-5 border-b border-white/[0.06]">
                        <div className="flex items-center justify-between mb-0.5">
                            <h1 className="text-lg font-semibold text-white tracking-tight">Channels</h1>
                            <motion.button
                                whileHover={{ scale: 1.03 }}
                                whileTap={{ scale: 0.97 }}
                                onClick={() => setShowAddModal(true)}
                                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-white
                bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500
                shadow-[0_0_16px_rgba(124,58,237,0.3)] hover:shadow-[0_0_24px_rgba(124,58,237,0.5)]
                transition-all duration-200"
                            >
                                <Plus className="w-3.5 h-3.5" />
                                New Channel
                            </motion.button>
                        </div>
                        <p className="text-xs text-zinc-500">Manage your channels and AI DNA</p>
                    </div>

                    <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
                        {channels.map((ch: Channel, i: number) => {
                            const status = getStatusConfig(ch);
                            const isSelected = selectedChannel?.id === ch.id;
                            return (
                                <motion.button
                                    key={ch.id}
                                    initial={{ opacity: 0, y: 8 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: i * 0.04, duration: 0.2 }}
                                    whileHover={{ y: -1 }}
                                    onClick={() => setSelectedChannel(ch)}
                                    className={`w-full text-left p-3.5 rounded-xl border transition-all duration-200 group ${isSelected
                                        ? 'bg-white/[0.04] border-violet-500/40 shadow-[0_0_0_1px_rgba(124,58,237,0.2),0_0_20px_rgba(124,58,237,0.08)]'
                                        : 'bg-white/[0.02] border-white/[0.06] hover:border-white/[0.12] hover:bg-white/[0.03]'
                                        }`}
                                >
                                    <div className="flex items-center gap-3">
                                        <div className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 text-sm font-bold text-white
                    bg-gradient-to-br ${isSelected ? 'from-violet-500 to-purple-700' : 'from-zinc-700 to-zinc-800 group-hover:from-violet-600/50 group-hover:to-purple-700/50'}
                    transition-all duration-200`}>
                                            {(ch.display_name || ch.name || ch.id).charAt(0).toUpperCase()}
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center justify-between gap-2 mb-0.5">
                                                <p className="font-medium text-white text-sm truncate">{ch.display_name || ch.name || ch.id}</p>
                                                <span className={`flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border font-medium flex-shrink-0 ${status.bg} ${status.text}`}>
                                                    <span className={`w-1.5 h-1.5 rounded-full ${status.dot}`} />
                                                    {status.label}
                                                </span>
                                            </div>
                                            {ch.niche && <p className="text-xs text-zinc-500 truncate">{ch.niche}</p>}
                                        </div>
                                        <ChevronRight className={`w-3.5 h-3.5 flex-shrink-0 transition-all duration-200 ${isSelected ? 'text-violet-400 rotate-90' : 'text-zinc-600'}`} />
                                    </div>
                                </motion.button>
                            );
                        })}

                        {channels.length === 0 && (
                            <div className="text-center py-16 text-zinc-600">
                                <Settings className="w-8 h-8 mx-auto mb-3 opacity-30" />
                                <p className="text-sm">No channels yet</p>
                                <p className="text-xs mt-1 text-zinc-700">Create your first channel to get started</p>
                            </div>
                        )}
                    </div>
                </div>

                {/* ── RIGHT PANEL ── */}
                <AnimatePresence mode="wait">
                    {selectedChannel ? (
                        <motion.div
                            key={selectedChannel.id}
                            initial={{ opacity: 0, x: 16 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: 16 }}
                            transition={{ duration: 0.2, ease: 'easeOut' }}
                            className="flex-1 overflow-y-auto p-8"
                        >
                            {/* Header */}
                            <div className="flex items-start justify-between mb-8">
                                <div className="flex items-center gap-3 w-full max-w-xl">
                                    {editingHeader ? (
                                        <div className="flex-1 flex gap-3 items-start">
                                            <div className="flex-1 space-y-2">
                                                <input
                                                    type="text"
                                                    value={headerForm.display_name}
                                                    onChange={e => setHeaderForm({ ...headerForm, display_name: e.target.value })}
                                                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-1.5 text-xl font-bold text-white focus:border-violet-500/50 outline-none"
                                                    placeholder="Channel Name"
                                                />
                                                <input
                                                    type="text"
                                                    value={headerForm.niche}
                                                    onChange={e => setHeaderForm({ ...headerForm, niche: e.target.value })}
                                                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3 py-1.5 text-sm text-zinc-300 focus:border-violet-500/50 outline-none"
                                                    placeholder="Niche"
                                                />
                                            </div>
                                            <div className="flex gap-2 pt-1">
                                                <button onClick={handleSaveHeader} className="px-3 py-1.5 bg-violet-600 hover:bg-violet-500 text-white text-xs font-medium rounded-lg transition-colors">Save</button>
                                                <button onClick={() => setEditingHeader(false)} className="px-3 py-1.5 bg-white/[0.05] hover:bg-white/[0.1] text-white text-xs font-medium rounded-lg transition-colors">Cancel</button>
                                            </div>
                                        </div>
                                    ) : (
                                        <div>
                                            <div className="flex items-center gap-2">
                                                <h2 className="text-2xl font-bold text-white tracking-tight">{selectedChannel.display_name || selectedChannel.name || selectedChannel.id}</h2>
                                                <button onClick={handleStartEditHeader} className="text-zinc-500 hover:text-white transition-colors">
                                                    <Pencil className="w-4 h-4" />
                                                </button>
                                            </div>
                                            {selectedChannel.niche && <p className="text-sm text-zinc-400 mt-1">{selectedChannel.niche}</p>}
                                        </div>
                                    )}
                                </div>
                                {!editingHeader && (
                                    <span className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border font-medium mt-1 ${getStatusConfig(selectedChannel).bg} ${getStatusConfig(selectedChannel).text}`}>
                                        <span className={`w-1.5 h-1.5 rounded-full ${getStatusConfig(selectedChannel).dot}`} />
                                        {getStatusConfig(selectedChannel).label}
                                    </span>
                                )}
                            </div>

                            {/* Stats Row */}
                            <div className="grid grid-cols-3 gap-4 mb-8">
                                <div className="bg-zinc-800/50 rounded-xl p-4 border border-white/[0.04]">
                                    <p className="text-xs text-zinc-500 mb-1 font-medium">Total Clips</p>
                                    <p className="text-xl font-bold text-white">{totalClips}</p>
                                </div>
                                <div className="bg-zinc-800/50 rounded-xl p-4 border border-white/[0.04]">
                                    <p className="text-xs text-zinc-500 mb-1 font-medium">DNA Status</p>
                                    <p className="text-xl font-bold text-white">{dna && Object.keys(dna).length > 0 ? 'Ready' : 'Not Generated'}</p>
                                </div>
                                <div className="bg-zinc-800/50 rounded-xl p-4 border border-white/[0.04]">
                                    <p className="text-xs text-zinc-500 mb-1 font-medium">Reference Clips</p>
                                    <p className="text-xl font-bold text-white">{referenceClips.length}</p>
                                </div>
                            </div>

                            {/* Channel DNA */}
                            <motion.div
                                initial={{ opacity: 0, y: 12 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: 0.05 }}
                                className={`rounded-2xl border bg-white/[0.02] backdrop-blur-sm p-6 mb-5 transition-colors duration-300 ${editingDna ? 'border-violet-500/30 shadow-[0_0_30px_rgba(124,58,237,0.05)]' : 'border-white/[0.06]'}`}
                            >
                                <div className="flex items-center gap-2 mb-5">
                                    <Dna className="w-4 h-4 text-violet-400" />
                                    <h3 className="font-semibold text-white text-sm">
                                        {editingDna ? (
                                            <span className="flex items-center gap-2">
                                                Editing DNA <span className="w-2 h-2 rounded-full bg-violet-500 animate-pulse" />
                                            </span>
                                        ) : 'Channel DNA'}
                                    </h3>
                                    {!editingDna && (
                                        <button onClick={handleStartEditDna} className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/[0.08] hover:border-violet-500/40 text-xs text-zinc-400 hover:text-white transition-all duration-200">
                                            <Pencil className="w-3.5 h-3.5" />
                                            Edit DNA
                                        </button>
                                    )}
                                </div>

                                {editingDna ? (
                                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="space-y-6">
                                        <div className="grid grid-cols-2 gap-6">
                                            {/* TONE */}
                                            <div className="col-span-2 md:col-span-1">
                                                <label className="block text-[10px] text-zinc-500 mb-1.5 uppercase tracking-widest">Tone</label>
                                                <MultiTagInput value={dnaForm.tone} onChange={(v) => setDnaForm((prev: any) => ({ ...prev, tone: v }))} placeholder="e.g. Energetic" />
                                            </div>

                                            {/* HOOK STYLE */}
                                            <div className="col-span-2 md:col-span-1">
                                                <label className="block text-[10px] text-zinc-500 mb-1.5 uppercase tracking-widest">Hook Style</label>
                                                <select
                                                    value={dnaForm.hook_style}
                                                    onChange={(e) => setDnaForm((prev: any) => ({ ...prev, hook_style: e.target.value }))}
                                                    className="w-full bg-zinc-900 border border-white/[0.08] rounded-xl px-3 py-2 text-sm text-white focus:border-violet-500/50 outline-none appearance-none"
                                                >
                                                    <option value="">Select style...</option>
                                                    <option value="provocative_question">Provocative Question</option>
                                                    <option value="shocking_statement">Shocking Statement</option>
                                                    <option value="emotional_hook">Emotional Hook</option>
                                                    <option value="funny_opener">Funny Opener</option>
                                                    <option value="controversial_take">Controversial Take</option>
                                                    <option value="story_tease">Story Tease</option>
                                                </select>
                                            </div>

                                            {/* HUMOR PROFILE */}
                                            <div className="col-span-2 bg-white/[0.02] border border-white/[0.04] p-4 rounded-xl space-y-4">
                                                <h4 className="text-xs font-semibold text-zinc-300">Humor Profile</h4>
                                                <div className="grid grid-cols-2 gap-4">
                                                    <div>
                                                        <label className="block text-[10px] text-zinc-500 mb-1.5 uppercase tracking-widest">Style</label>
                                                        <select
                                                            value={dnaForm.humor_profile.style}
                                                            onChange={(e) => setDnaForm((prev: any) => ({ ...prev, humor_profile: { ...prev.humor_profile, style: e.target.value } }))}
                                                            className="w-full bg-zinc-900 border border-white/[0.08] rounded-xl px-3 py-2 text-sm text-white focus:border-violet-500/50 outline-none appearance-none"
                                                        >
                                                            <option value="">Select...</option>
                                                            <option value="dry_wit">Dry Wit</option>
                                                            <option value="deadpan">Deadpan</option>
                                                            <option value="sarcastic">Sarcastic</option>
                                                            <option value="observational">Observational</option>
                                                            <option value="dark">Dark</option>
                                                            <option value="absurdist">Absurdist</option>
                                                            <option value="self_deprecating">Self Deprecating</option>
                                                        </select>
                                                    </div>
                                                    <div>
                                                        <label className="block text-[10px] text-zinc-500 mb-1.5 uppercase tracking-widest">Frequency</label>
                                                        <select
                                                            value={dnaForm.humor_profile.frequency}
                                                            onChange={(e) => setDnaForm((prev: any) => ({ ...prev, humor_profile: { ...prev.humor_profile, frequency: e.target.value } }))}
                                                            className="w-full bg-zinc-900 border border-white/[0.08] rounded-xl px-3 py-2 text-sm text-white focus:border-violet-500/50 outline-none appearance-none"
                                                        >
                                                            <option value="">Select...</option>
                                                            <option value="very_frequent">Very Frequent</option>
                                                            <option value="frequent">Frequent</option>
                                                            <option value="occasional">Occasional</option>
                                                            <option value="rare">Rare</option>
                                                        </select>
                                                    </div>
                                                    <div className="col-span-2">
                                                        <label className="block text-[10px] text-zinc-500 mb-1.5 uppercase tracking-widest">Triggers</label>
                                                        <MultiTagInput value={dnaForm.humor_profile.triggers} onChange={(v) => setDnaForm((prev: any) => ({ ...prev, humor_profile: { ...prev.humor_profile, triggers: v } }))} placeholder="e.g. Awkward Silence" />
                                                    </div>
                                                </div>
                                            </div>

                                            {/* DO LIST */}
                                            <div className="col-span-2 md:col-span-1">
                                                <label className="block text-[10px] text-zinc-500 mb-1.5 uppercase tracking-widest">Do List</label>
                                                <MultiTagInput value={dnaForm.do_list} onChange={(v) => setDnaForm((prev: any) => ({ ...prev, do_list: v }))} placeholder="e.g. Start with shocking statement" />
                                            </div>

                                            {/* DONT LIST */}
                                            <div className="col-span-2 md:col-span-1">
                                                <label className="block text-[10px] text-zinc-500 mb-1.5 uppercase tracking-widest">Don't List</label>
                                                <MultiTagInput value={dnaForm.dont_list} onChange={(v) => setDnaForm((prev: any) => ({ ...prev, dont_list: v }))} placeholder="e.g. No slow intros" />
                                            </div>

                                            {/* NO GO ZONES */}
                                            <div className="col-span-2 md:col-span-1">
                                                <label className="block text-[10px] text-red-500 mb-1.5 uppercase tracking-widest">No Go Zones</label>
                                                <MultiTagInput value={dnaForm.no_go_zones} onChange={(v) => setDnaForm((prev: any) => ({ ...prev, no_go_zones: v }))} placeholder="e.g. Explicit Content" colorClass="bg-red-500/10 text-red-400 border-red-500/20" />
                                            </div>

                                            {/* SACRED TOPICS */}
                                            <div className="col-span-2 md:col-span-1">
                                                <label className="block text-[10px] text-emerald-500 mb-1.5 uppercase tracking-widest">Sacred Topics</label>
                                                <MultiTagInput value={dnaForm.sacred_topics} onChange={(v) => setDnaForm((prev: any) => ({ ...prev, sacred_topics: v }))} placeholder="e.g. Tech Startups" colorClass="bg-emerald-500/10 text-emerald-400 border-emerald-500/20" />
                                            </div>

                                            {/* BEST CONTENT TYPES */}
                                            <div className="col-span-2">
                                                <label className="block text-[10px] text-zinc-500 mb-1.5 uppercase tracking-widest">Best Content Types</label>
                                                <div className="flex flex-wrap gap-2">
                                                    {contentTypesOptions.map((type) => {
                                                        const isSelected = dnaForm.best_content_types.includes(type);
                                                        return (
                                                            <button
                                                                key={type}
                                                                onClick={() => {
                                                                    setDnaForm((prev: any) => {
                                                                        const selected = prev.best_content_types || [];
                                                                        if (selected.includes(type)) {
                                                                            return { ...prev, best_content_types: selected.filter((t: string) => t !== type) };
                                                                        }
                                                                        return { ...prev, best_content_types: [...selected, type] };
                                                                    });
                                                                }}
                                                                className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${isSelected ? 'bg-violet-600/20 text-violet-300 border-violet-500/40' : 'bg-white/[0.02] text-zinc-400 border-white/[0.08] hover:bg-white/[0.06]'}`}
                                                            >
                                                                {formatText(type)}
                                                            </button>
                                                        );
                                                    })}
                                                </div>
                                            </div>

                                            {/* AUDIENCE IDENTITY */}
                                            <div className="col-span-2">
                                                <label className="block text-[10px] text-zinc-500 mb-1.5 uppercase tracking-widest">Audience Identity</label>
                                                <textarea
                                                    value={dnaForm.audience_identity}
                                                    onChange={(e) => setDnaForm((prev: any) => ({ ...prev, audience_identity: e.target.value }))}
                                                    rows={3}
                                                    className="w-full bg-zinc-900 border border-white/[0.08] rounded-xl px-3 py-2 text-sm text-white focus:border-violet-500/50 outline-none resize-none"
                                                    placeholder="Describe the target audience..."
                                                />
                                            </div>

                                            {/* SPEAKER PREF & AVG DURATION */}
                                            <div className="col-span-2 grid grid-cols-2 gap-6">
                                                <div>
                                                    <label className="block text-[10px] text-zinc-500 mb-1.5 uppercase tracking-widest">Speaker Preference</label>
                                                    <select
                                                        value={dnaForm.speaker_preference}
                                                        onChange={(e) => setDnaForm((prev: any) => ({ ...prev, speaker_preference: e.target.value }))}
                                                        className="w-full bg-zinc-900 border border-white/[0.08] rounded-xl px-3 py-2 text-sm text-white focus:border-violet-500/50 outline-none appearance-none"
                                                    >
                                                        <option value="">Select...</option>
                                                        <option value="guest_dominant">Guest Dominant</option>
                                                        <option value="balanced">Balanced</option>
                                                        <option value="host_driven">Host Driven</option>
                                                    </select>
                                                </div>
                                                <div>
                                                    <label className="block text-[10px] text-zinc-500 mb-1.5 uppercase tracking-widest">Avg Successful Duration</label>
                                                    <div className="relative">
                                                        <input
                                                            type="number"
                                                            value={dnaForm.avg_successful_duration}
                                                            onChange={(e) => setDnaForm((prev: any) => ({ ...prev, avg_successful_duration: parseInt(e.target.value) || 0 }))}
                                                            className="w-full bg-zinc-900 border border-white/[0.08] rounded-xl px-3 py-2 text-sm text-white focus:border-violet-500/50 outline-none"
                                                        />
                                                        <span className="absolute right-3 top-2.5 text-xs text-zinc-500 pointer-events-none">seconds</span>
                                                    </div>
                                                </div>
                                            </div>

                                        </div>

                                        <div className="flex items-center gap-3 pt-4 border-t border-white/[0.06] mt-6">
                                            <button
                                                onClick={() => setEditingDna(false)}
                                                className="px-4 py-2 border border-white/[0.08] text-zinc-400 hover:text-white hover:bg-white/[0.04] rounded-xl text-sm font-medium transition-colors"
                                            >
                                                Cancel
                                            </button>
                                            <motion.button
                                                whileHover={{ scale: 1.02 }}
                                                whileTap={{ scale: 0.98 }}
                                                onClick={handleSaveDna}
                                                disabled={savingDna}
                                                className="px-6 py-2 bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500
                                                text-white rounded-xl text-sm font-medium transition-all flex items-center gap-2
                                                shadow-[0_0_16px_rgba(124,58,237,0.3)] hover:shadow-[0_0_24px_rgba(124,58,237,0.4)] disabled:opacity-50"
                                            >
                                                {savingDna && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                                                Save Changes
                                            </motion.button>
                                        </div>
                                    </motion.div>
                                ) : (
                                    dna ? (
                                        <div className="grid grid-cols-2 gap-3">
                                            {dna?.tone && (
                                                <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
                                                    <p className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2.5">Tone</p>
                                                    <div className="flex flex-wrap gap-1.5">
                                                        {renderTags(dna.tone, "bg-violet-500/10 text-violet-300 border-violet-500/20")}
                                                    </div>
                                                </div>
                                            )}
                                            {dna?.humor_profile && (
                                                <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
                                                    <p className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2.5">Humor Profile</p>
                                                    <div className="flex flex-col gap-3">
                                                        {typeof dna.humor_profile === 'object' && !Array.isArray(dna.humor_profile) ? (
                                                            <>
                                                                {dna.humor_profile.style && (
                                                                    <div>
                                                                        <span className="text-[10px] text-zinc-500 mr-2">STYLE</span>
                                                                        <span className="text-xs px-2.5 py-1 bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 rounded-lg">{formatText(dna.humor_profile.style)}</span>
                                                                    </div>
                                                                )}
                                                                {dna.humor_profile.triggers && Array.isArray(dna.humor_profile.triggers) && (
                                                                    <div className="flex items-center gap-1.5 flex-wrap">
                                                                        <span className="text-[10px] text-zinc-500 mr-1">TRIGGERS</span>
                                                                        {dna.humor_profile.triggers.map((t: string, i: number) => (
                                                                            <span key={i} className="text-xs px-2.5 py-1 bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 rounded-lg">{formatText(t)}</span>
                                                                        ))}
                                                                    </div>
                                                                )}
                                                                {dna.humor_profile.frequency && (
                                                                    <div>
                                                                        <span className="text-[10px] text-zinc-500 mr-2">FREQUENCY</span>
                                                                        <span className="text-xs px-2 py-0.5 bg-zinc-800 text-zinc-300 border border-zinc-700 rounded text-[10px] uppercase tracking-wider">{dna.humor_profile.frequency}</span>
                                                                    </div>
                                                                )}
                                                            </>
                                                        ) : (
                                                            <div className="flex flex-wrap gap-1.5">
                                                                {renderTags(dna.humor_profile, "bg-cyan-500/10 text-cyan-400 border-cyan-500/20")}
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            )}
                                            {dna?.do_list && (
                                                <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
                                                    <p className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2.5">Do List</p>
                                                    <div className="flex flex-wrap gap-1.5">
                                                        {renderTags(dna.do_list, "bg-emerald-500/10 text-emerald-400 border-emerald-500/20")}
                                                    </div>
                                                </div>
                                            )}
                                            {dna?.dont_list && (
                                                <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
                                                    <p className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2.5">Don't List</p>
                                                    <div className="flex flex-wrap gap-1.5">
                                                        {renderTags(dna.dont_list, "bg-orange-500/10 text-orange-400 border-orange-500/20")}
                                                    </div>
                                                </div>
                                            )}
                                            {dna?.hook_style && (
                                                <div className="col-span-2 bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
                                                    <p className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2.5">Hook Style</p>
                                                    <div className="flex flex-wrap gap-1.5">
                                                        {renderTags(dna.hook_style, "bg-violet-500/10 text-violet-300 border-violet-500/20")}
                                                    </div>
                                                </div>
                                            )}
                                            {dna?.no_go_zones && (
                                                <div className="col-span-2 bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
                                                    <p className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2.5">No Go Zones</p>
                                                    <div className="flex flex-wrap gap-1.5">
                                                        {renderTags(dna.no_go_zones, "bg-red-500/10 text-red-400 border-red-500/20")}
                                                    </div>
                                                </div>
                                            )}
                                            {dna?.sacred_topics && (
                                                <div className="col-span-2 bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
                                                    <p className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2.5">Sacred Topics</p>
                                                    <div className="flex flex-wrap gap-1.5">
                                                        {renderTags(dna.sacred_topics, "bg-emerald-500/10 text-emerald-400 border-emerald-500/20")}
                                                    </div>
                                                </div>
                                            )}
                                            {dna?.best_content_types && (
                                                <div className="col-span-2 bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
                                                    <p className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2.5">Best Content Types</p>
                                                    <div className="flex flex-wrap gap-1.5">
                                                        {renderTags(dna.best_content_types, "bg-blue-500/10 text-blue-400 border-blue-500/20")}
                                                    </div>
                                                </div>
                                            )}
                                            {(dna?.audience_identity || dna?.target_audience) && (
                                                <div className="col-span-2 bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
                                                    <p className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2.5">Audience Identity</p>
                                                    <div className="flex flex-wrap gap-1.5">
                                                        {typeof (dna.audience_identity || dna.target_audience) === 'string' ? (
                                                            <p className="text-sm text-zinc-300 leading-relaxed">{dna.audience_identity || dna.target_audience}</p>
                                                        ) : (
                                                            renderTags(dna.audience_identity || dna.target_audience, "bg-zinc-800 text-zinc-300 border-zinc-700")
                                                        )}
                                                    </div>
                                                </div>
                                            )}
                                            {dna?.speaker_preference && (
                                                <div className="col-span-2 bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
                                                    <p className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2.5">Speaker Preference</p>
                                                    <div className="flex flex-wrap gap-1.5">
                                                        {renderTags(dna.speaker_preference, "bg-zinc-800 text-zinc-300 border-zinc-700")}
                                                    </div>
                                                </div>
                                            )}
                                            {dna?.avg_successful_duration && (
                                                <div className="col-span-2 bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
                                                    <p className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2.5">Avg Successful Duration</p>
                                                    <div className="flex flex-wrap gap-1.5">
                                                        {renderTags(`${dna.avg_successful_duration} seconds`, "bg-zinc-800 text-zinc-300 border-zinc-700")}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        <div className="text-center py-10 text-zinc-600">
                                            <Sparkles className="w-8 h-8 mx-auto mb-3 opacity-30" />
                                            <p className="text-sm">No DNA generated yet</p>
                                            <p className="text-xs mt-1 text-zinc-700">Upload reference clips or edit DNA manually</p>
                                        </div>
                                    )
                                )}
                            </motion.div>

                            {/* Reference Clips */}
                            <motion.div
                                initial={{ opacity: 0, y: 12 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: 0.1 }}
                                className="rounded-2xl border border-white/[0.06] bg-white/[0.02] backdrop-blur-sm p-6 mb-5"
                            >
                                <div className="flex items-center gap-2 mb-5">
                                    <Film className="w-4 h-4 text-violet-400" />
                                    <h3 className="font-semibold text-white text-sm">Reference Clips</h3>
                                    <motion.button
                                        whileHover={{ scale: 1.02 }}
                                        whileTap={{ scale: 0.98 }}
                                        onClick={() => fileInputRef.current?.click()}
                                        disabled={uploading}
                                        className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/[0.08] hover:border-violet-500/40 text-xs text-zinc-400 hover:text-white transition-all duration-200 disabled:opacity-50"
                                    >
                                        {uploading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                                        Upload
                                    </motion.button>
                                    <input ref={fileInputRef} type="file" accept="video/*" className="hidden"
                                        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUploadReference(f); }} />
                                </div>

                                {referenceClips.length > 0 ? (
                                    <div className="space-y-2">
                                        {referenceClips.map((clip) => (
                                            <div key={clip.id} className="flex items-center gap-3 p-3 bg-white/[0.03] border border-white/[0.04] rounded-xl">
                                                <div className="w-7 h-7 bg-violet-500/10 border border-violet-500/20 rounded-lg flex items-center justify-center flex-shrink-0">
                                                    <Check className="w-3.5 h-3.5 text-violet-400" />
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <p className="text-sm text-zinc-200 truncate">{clip.title || 'Reference Clip'}</p>
                                                    {clip.source && <p className="text-xs text-zinc-600">{clip.source}</p>}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <motion.div
                                        whileHover={{ borderColor: 'rgba(124,58,237,0.3)' }}
                                        onClick={() => fileInputRef.current?.click()}
                                        className="border-2 border-dashed border-white/[0.06] rounded-xl p-8 text-center cursor-pointer transition-colors"
                                    >
                                        <Upload className="w-7 h-7 mx-auto mb-2 text-zinc-600" />
                                        <p className="text-sm text-zinc-500">Drop clips here or click to upload</p>
                                        <p className="text-xs text-zinc-700 mt-1">MP4, MOV files accepted</p>
                                    </motion.div>
                                )}
                            </motion.div>

                            {/* Danger Zone */}
                            <motion.div
                                initial={{ opacity: 0, y: 12 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: 0.15 }}
                                className="rounded-2xl border border-red-500/10 bg-red-500/[0.03] p-6"
                            >
                                <h3 className="font-semibold text-white text-sm mb-1">Danger Zone</h3>
                                <p className="text-xs text-zinc-500 mb-4">Permanently delete this channel and all associated data.</p>
                                <button
                                    onClick={() => setShowDeleteModal(true)}
                                    className="flex items-center gap-2 px-4 py-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 rounded-xl text-xs font-medium transition-colors"
                                >
                                    <Trash2 className="w-3.5 h-3.5" />
                                    Delete Channel
                                </button>
                            </motion.div>
                        </motion.div>
                    ) : (
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="flex-1 flex items-center justify-center"
                        >
                            <div className="text-center">
                                <div className="w-16 h-16 rounded-2xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center mx-auto mb-4">
                                    <Settings className="w-7 h-7 text-zinc-600" />
                                </div>
                                <p className="text-sm text-zinc-500">Select a channel to view settings</p>
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* ── DELETE CHANNEL MODAL ── */}
                <AnimatePresence>
                    {showDeleteModal && selectedChannel && (
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            className="fixed inset-0 bg-black/70 backdrop-blur-xl flex items-center justify-center z-50 p-4"
                            onClick={(e) => { if (e.target === e.currentTarget) setShowDeleteModal(false); }}
                        >
                            <motion.div
                                initial={{ opacity: 0, scale: 0.95, y: 8 }}
                                animate={{ opacity: 1, scale: 1, y: 0 }}
                                exit={{ opacity: 0, scale: 0.95, y: 8 }}
                                transition={{ duration: 0.18, ease: 'easeOut' }}
                                className="bg-zinc-900/90 backdrop-blur-xl border border-red-500/20 rounded-2xl p-6 w-full max-w-md shadow-2xl"
                            >
                                <div className="flex items-center gap-3 mb-4">
                                    <div className="w-10 h-10 rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center flex-shrink-0">
                                        <AlertCircle className="w-5 h-5 text-red-400" />
                                    </div>
                                    <h3 className="text-lg font-bold text-white tracking-tight">Delete Channel?</h3>
                                </div>

                                <p className="text-sm text-zinc-400 mb-6 leading-relaxed">
                                    This will permanently delete <strong className="text-white">{selectedChannel.display_name || selectedChannel.name || selectedChannel.id}</strong> and all its clips, jobs, and DNA data. This action cannot be undone.
                                </p>

                                <div className="flex gap-3">
                                    <button
                                        onClick={() => setShowDeleteModal(false)}
                                        className="flex-1 py-2.5 border border-white/[0.08] text-zinc-400 hover:text-white hover:bg-white/[0.04] rounded-xl text-sm font-medium transition-colors"
                                    >
                                        Cancel
                                    </button>
                                    <motion.button
                                        whileHover={{ scale: 1.01 }}
                                        whileTap={{ scale: 0.99 }}
                                        onClick={() => setShowDeleteModal(false)}
                                        className="flex-1 py-2.5 bg-gradient-to-r from-red-600 to-red-500 hover:from-red-500 hover:to-red-400
                                        text-white rounded-xl text-sm font-medium transition-all shadow-[0_0_16px_rgba(239,68,68,0.3)] hover:shadow-[0_0_24px_rgba(239,68,68,0.4)]"
                                    >
                                        Delete Forever
                                    </motion.button>
                                </div>
                            </motion.div>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* ── ADD CHANNEL MODAL ── */}
                <AnimatePresence>
                    {showAddModal && (
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            className="fixed inset-0 bg-black/70 backdrop-blur-xl flex items-center justify-center z-50 p-4"
                            onClick={(e) => { if (e.target === e.currentTarget) setShowAddModal(false); }}
                        >
                            <motion.div
                                initial={{ opacity: 0, scale: 0.95, y: 8 }}
                                animate={{ opacity: 1, scale: 1, y: 0 }}
                                exit={{ opacity: 0, scale: 0.95, y: 8 }}
                                transition={{ duration: 0.18, ease: 'easeOut' }}
                                className="bg-zinc-900/90 backdrop-blur-xl border border-white/[0.08] rounded-2xl p-6 w-full max-w-md shadow-2xl"
                            >
                                <div className="flex items-center justify-between mb-6">
                                    <div>
                                        <h3 className="text-base font-bold text-white">New Channel</h3>
                                        <p className="text-xs text-zinc-500 mt-0.5">Add a new channel to your workspace</p>
                                    </div>
                                    <button onClick={() => setShowAddModal(false)}
                                        className="w-8 h-8 rounded-lg flex items-center justify-center text-zinc-500 hover:text-white hover:bg-white/[0.06] transition-colors">
                                        <X className="w-4 h-4" />
                                    </button>
                                </div>

                                <div className="space-y-4">
                                    {[
                                        { label: 'Channel Name', key: 'name', placeholder: 'e.g. Speedy Cast Clip', type: 'input' },
                                        { label: 'Niche / Topic', key: 'niche', placeholder: 'e.g. Tech Podcasts, Comedy Interviews', type: 'input' },
                                        { label: 'Target Audience', key: 'description', placeholder: 'Describe your target audience...', type: 'textarea' },
                                    ].map(({ label, key, placeholder, type }) => (
                                        <div key={key}>
                                            <label className="block text-[10px] text-zinc-500 mb-1.5 uppercase tracking-widest">{label}</label>
                                            {type === 'textarea' ? (
                                                <textarea
                                                    value={(newChannel as any)[key]}
                                                    onChange={(e) => setNewChannel({ ...newChannel, [key]: e.target.value })}
                                                    placeholder={placeholder}
                                                    rows={3}
                                                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-3 text-sm text-white placeholder-zinc-600 focus:border-violet-500/50 focus:bg-white/[0.06] transition-all resize-none"
                                                />
                                            ) : (
                                                <input
                                                    type="text"
                                                    value={(newChannel as any)[key]}
                                                    onChange={(e) => setNewChannel({ ...newChannel, [key]: e.target.value })}
                                                    placeholder={placeholder}
                                                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-3 text-sm text-white placeholder-zinc-600 focus:border-violet-500/50 focus:bg-white/[0.06] transition-all"
                                                />
                                            )}
                                        </div>
                                    ))}
                                </div>

                                <div className="flex gap-2.5 mt-6">
                                    <button onClick={() => setShowAddModal(false)}
                                        className="flex-1 py-2.5 border border-white/[0.08] text-zinc-400 hover:text-white rounded-xl text-sm font-medium transition-colors">
                                        Cancel
                                    </button>
                                    <motion.button
                                        whileHover={{ scale: 1.01 }}
                                        whileTap={{ scale: 0.99 }}
                                        onClick={handleCreateChannel}
                                        disabled={creating || !newChannel.name.trim()}
                                        className="flex-1 py-2.5 bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500
                    text-white rounded-xl text-sm font-medium transition-all disabled:opacity-50
                    shadow-[0_0_16px_rgba(124,58,237,0.3)] hover:shadow-[0_0_24px_rgba(124,58,237,0.4)]
                    flex items-center justify-center gap-2"
                                    >
                                        {creating && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                                        Create Channel
                                    </motion.button>
                                </div>
                            </motion.div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        );
    } catch (err) {
        console.error("Render error in ChannelSettingsPage:", err);
        return (
            <div className="p-8 flex flex-col items-center justify-center h-full text-zinc-400">
                <AlertCircle className="w-12 h-12 text-red-500 mb-4" />
                <h2 className="text-lg font-semibold text-white mb-2">Something went wrong</h2>
                <p className="text-sm mb-6">We couldn't load the channel settings. The data might be corrupted.</p>
                <button
                    onClick={() => window.location.reload()}
                    className="px-4 py-2 bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] rounded-xl text-sm font-medium transition-colors"
                >
                    Reload Page
                </button>
            </div>
        );
    }
}
