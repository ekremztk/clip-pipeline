'use client';

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Settings, Trash2, Upload, X, ChevronRight, Check, AlertCircle, Loader2, Dna, Film, Sparkles } from 'lucide-react';
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

export default function ChannelSettingsPage() {
    const { channels, setActiveChannelId } = useChannel();
    const [selectedChannel, setSelectedChannel] = useState<Channel | null>(null);
    const [referenceClips, setReferenceClips] = useState<ReferenceClip[]>([]);
    const [showAddModal, setShowAddModal] = useState(false);
    const [uploading, setUploading] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [newChannel, setNewChannel] = useState({ name: '', niche: '', description: '' });
    const [creating, setCreating] = useState(false);

    useEffect(() => {
        if (selectedChannel) fetchReferenceClips(selectedChannel.id);
    }, [selectedChannel]);

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

    const getStatusConfig = (status?: string) => {
        if (status === 'completed') return { label: 'Ready', dot: 'bg-emerald-400', text: 'text-emerald-400', bg: 'bg-emerald-400/10 border-emerald-400/20' };
        if (status === 'processing') return { label: 'Training', dot: 'bg-yellow-400 animate-pulse', text: 'text-yellow-400', bg: 'bg-yellow-400/10 border-yellow-400/20' };
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
                            const status = getStatusConfig(ch.onboarding_status);
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
                                <div>
                                    <h2 className="text-2xl font-bold text-white tracking-tight">{selectedChannel.display_name || selectedChannel.name || selectedChannel.id}</h2>
                                    {selectedChannel.niche && <p className="text-sm text-zinc-400 mt-1">{selectedChannel.niche}</p>}
                                </div>
                                <span className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border font-medium mt-1 ${getStatusConfig(selectedChannel.onboarding_status).bg} ${getStatusConfig(selectedChannel.onboarding_status).text}`}>
                                    <span className={`w-1.5 h-1.5 rounded-full ${getStatusConfig(selectedChannel.onboarding_status).dot}`} />
                                    {getStatusConfig(selectedChannel.onboarding_status).label}
                                </span>
                            </div>

                            {/* Channel DNA */}
                            <motion.div
                                initial={{ opacity: 0, y: 12 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: 0.05 }}
                                className="rounded-2xl border border-white/[0.06] bg-white/[0.02] backdrop-blur-sm p-6 mb-5"
                            >
                                <div className="flex items-center gap-2 mb-5">
                                    <Dna className="w-4 h-4 text-violet-400" />
                                    <h3 className="font-semibold text-white text-sm">Channel DNA</h3>
                                    <span className="ml-auto text-xs text-zinc-600">Auto-generated from content</span>
                                </div>

                                {dna ? (
                                    <div className="grid grid-cols-2 gap-3">
                                        {dna?.tone && (
                                            <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
                                                <p className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2.5">Tone</p>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {Array.isArray(dna.tone) ? dna.tone.map((t: any, i: number) => (
                                                        <span key={i} className="text-xs px-2.5 py-1 bg-violet-500/10 text-violet-300 border border-violet-500/20 rounded-lg">{typeof t === 'string' ? t : JSON.stringify(t)}</span>
                                                    )) : (
                                                        <span className="text-xs px-2.5 py-1 bg-violet-500/10 text-violet-300 border border-violet-500/20 rounded-lg">{typeof dna.tone === 'string' ? dna.tone : JSON.stringify(dna.tone)}</span>
                                                    )}
                                                </div>
                                            </div>
                                        )}
                                        {dna?.humor_profile && (
                                            <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
                                                <p className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2.5">Humor Style</p>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {Array.isArray(dna.humor_profile) ? dna.humor_profile.map((h: any, i: number) => (
                                                        <span key={i} className="text-xs px-2.5 py-1 bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 rounded-lg">{typeof h === 'string' ? h : JSON.stringify(h)}</span>
                                                    )) : (
                                                        <span className="text-xs px-2.5 py-1 bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 rounded-lg">{typeof dna.humor_profile === 'string' ? dna.humor_profile : JSON.stringify(dna.humor_profile)}</span>
                                                    )}
                                                </div>
                                            </div>
                                        )}
                                        {dna?.target_audience && (
                                            <div className="col-span-2 bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
                                                <p className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2.5">Target Audience</p>
                                                <p className="text-sm text-zinc-300 leading-relaxed">{typeof dna.target_audience === 'string' ? dna.target_audience : JSON.stringify(dna.target_audience)}</p>
                                            </div>
                                        )}
                                        {dna?.content_pillars && (
                                            <div className="col-span-2 bg-white/[0.03] border border-white/[0.06] rounded-xl p-4">
                                                <p className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2.5">Content Pillars</p>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {Array.isArray(dna.content_pillars) ? dna.content_pillars.map((p: any, i: number) => (
                                                        <span key={i} className="text-xs px-2.5 py-1 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-lg">{typeof p === 'string' ? p : JSON.stringify(p)}</span>
                                                    )) : (
                                                        <span className="text-xs px-2.5 py-1 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-lg">{typeof dna.content_pillars === 'string' ? dna.content_pillars : JSON.stringify(dna.content_pillars)}</span>
                                                    )}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <div className="text-center py-10 text-zinc-600">
                                        <Sparkles className="w-8 h-8 mx-auto mb-3 opacity-30" />
                                        <p className="text-sm">No DNA generated yet</p>
                                        <p className="text-xs mt-1 text-zinc-700">Upload reference clips to generate channel DNA</p>
                                    </div>
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
                                <button className="flex items-center gap-2 px-4 py-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 rounded-xl text-xs font-medium transition-colors">
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
