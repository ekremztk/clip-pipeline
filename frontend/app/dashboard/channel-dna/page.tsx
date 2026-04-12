'use client';

import { useState, useEffect, useRef } from 'react';
import { Plus, Trash2, Upload, X, Loader2, Dna, Pencil } from 'lucide-react';
import { useChannel } from '../layout';
import { authFetch } from '@/lib/api';

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

const MultiTagInput = ({ value, onChange, placeholder, variant }: {
    value: string[],
    onChange: (v: string[]) => void,
    placeholder?: string,
    variant?: 'do' | 'dont' | 'default'
}) => {
    const [input, setInput] = useState('');
    const safeValue = Array.isArray(value) ? value : [];

    const tagStyle = variant === 'do'
        ? { background: 'rgba(34,197,94,0.1)', color: '#4ade80', border: '1px solid rgba(34,197,94,0.2)' }
        : variant === 'dont'
        ? { background: 'rgba(239,68,68,0.1)', color: '#f87171', border: '1px solid rgba(239,68,68,0.2)' }
        : { background: 'rgba(250,249,245,0.06)', color: '#ababab', border: '1px solid rgba(250,249,245,0.1)' };

    const commitTag = (val: string) => {
        const trimmed = val.trim();
        if (trimmed && !safeValue.includes(trimmed)) onChange([...safeValue, trimmed]);
        setInput('');
    };

    return (
        <div className="space-y-2">
            {safeValue.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                    {safeValue.map((tag, i) => (
                        <span key={i} style={tagStyle} className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg">
                            {tag}
                            <button type="button" onClick={() => onChange(safeValue.filter((_, idx) => idx !== i))} className="ml-1 opacity-70 hover:opacity-100 transition-opacity">
                                <X className="w-3 h-3" />
                            </button>
                        </span>
                    ))}
                </div>
            )}
            <input
                type="text"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); commitTag(input); } }}
                onBlur={() => { if (input.trim()) commitTag(input); }}
                placeholder={placeholder}
                style={{ background: '#111110', border: '1px solid rgba(250,249,245,0.1)', color: '#faf9f5' }}
                className="w-full rounded-xl px-3 py-2 text-sm placeholder:text-[rgba(250,249,245,0.25)] focus:outline-none transition-colors"
            />
        </div>
    );
};

const formatText = (text: string) => {
    if (!text) return '';
    return text.replace(/_/g, ' ').split(' ').map(word => {
        if (word.toLowerCase() === 'youtube') return 'YouTube';
        return word.charAt(0).toUpperCase() + word.slice(1);
    }).join(' ');
};

export default function ChannelDNAPage() {
    const { channels, isLoading: channelLoading } = useChannel();
    const [selectedChannel, setSelectedChannel] = useState<Channel | null>(null);
    const [referenceClips, setReferenceClips] = useState<ReferenceClip[]>([]);
    const [uploading, setUploading] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const [editingHeader, setEditingHeader] = useState(false);
    const [headerForm, setHeaderForm] = useState({ display_name: '', niche: '' });

    const [editingDna, setEditingDna] = useState(false);
    const [savingDna, setSavingDna] = useState(false);
    const [dnaForm, setDnaForm] = useState<any>({});

    useEffect(() => {
        if (channels.length > 0 && !selectedChannel) {
            setSelectedChannel(channels[0] as Channel);
        }
    }, [channels]);

    useEffect(() => {
        if (selectedChannel) {
            fetchReferenceClips(selectedChannel.id);
        }
    }, [selectedChannel]);

    const fetchReferenceClips = async (channelId: string) => {
        try {
            const res = await authFetch(`/channels/${channelId}/references`);
            if (res.ok) setReferenceClips((await res.json()) || []);
        } catch (e) { console.error(e); }
    };

    const handleUploadReference = async (file: File) => {
        if (!selectedChannel) return;
        setUploading(true);
        try {
            const formData = new FormData();
            formData.append('file', file);
            await authFetch(`/channels/${selectedChannel.id}/references`, { method: 'POST', body: formData });
            fetchReferenceClips(selectedChannel.id);
        } catch (e) { console.error(e); }
        finally { setUploading(false); }
    };

    const handleSaveHeader = async () => {
        if (!selectedChannel) return;
        try {
            const res = await authFetch(`/channels/${selectedChannel.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ display_name: headerForm.display_name, niche: headerForm.niche })
            });
            if (res.ok) {
                setSelectedChannel({ ...selectedChannel, display_name: headerForm.display_name, niche: headerForm.niche });
                setEditingHeader(false);
            }
        } catch (e) { console.error(e); }
    };

    const handleStartEditDna = () => {
        let parsed: any = {};
        const raw = selectedChannel?.channel_dna;
        if (typeof raw === 'string') { try { parsed = JSON.parse(raw); } catch { parsed = {}; } }
        else if (typeof raw === 'object' && raw !== null) { parsed = raw; }

        setDnaForm({
            tone: parsed.tone || [],
            humor_profile: {
                style: parsed.humor_profile?.style || '',
                triggers: parsed.humor_profile?.triggers || [],
                frequency: parsed.humor_profile?.frequency || ''
            },
            do_list: parsed.do_list || [],
            dont_list: parsed.dont_list || [],
            hook_style: parsed.hook_style || '',
            no_go_zones: parsed.no_go_zones || [],
            sacred_topics: parsed.sacred_topics || [],
            best_content_types: parsed.best_content_types || [],
            content_format: parsed.content_format || [],
            target_platforms: parsed.target_platforms || [],
            audience_identity: parsed.audience_identity || parsed.target_audience || '',
            speaker_preference: parsed.speaker_preference || '',
            avg_successful_duration: parsed.avg_successful_duration || 30,

        });
        setEditingDna(true);
    };

    const handleSaveDna = async () => {
        if (!selectedChannel) return;
        setSavingDna(true);
        try {
            const res = await authFetch(`/channels/${selectedChannel.id}`, {
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

    const dna = (() => {
        const raw = selectedChannel?.channel_dna;
        if (!raw) return null;
        if (typeof raw === 'string') { try { return JSON.parse(raw); } catch { return null; } }
        return raw;
    })();

    const contentTypesOptions = ['revelation', 'debate', 'humor', 'insight', 'emotional', 'controversial', 'storytelling', 'celebrity_conflict', 'hot_take', 'funny_reaction', 'unexpected_answer', 'relatable_moment', 'educational_insight'];

    const renderTag = (text: string, variant?: 'do' | 'dont' | 'zone' | 'sacred' | 'default') => {
        const styles: Record<string, React.CSSProperties> = {
            do: { background: 'rgba(34,197,94,0.1)', color: '#4ade80', border: '1px solid rgba(34,197,94,0.2)' },
            dont: { background: 'rgba(239,68,68,0.1)', color: '#f87171', border: '1px solid rgba(239,68,68,0.2)' },
            zone: { background: 'rgba(239,68,68,0.08)', color: '#f87171', border: '1px solid rgba(239,68,68,0.15)' },
            sacred: { background: 'rgba(34,197,94,0.08)', color: '#4ade80', border: '1px solid rgba(34,197,94,0.15)' },
            default: { background: 'rgba(250,249,245,0.06)', color: '#ababab', border: '1px solid rgba(250,249,245,0.1)' },
        };
        const s = styles[variant || 'default'];
        return (
            <span style={s} className="text-xs px-2.5 py-1 rounded-lg">
                {formatText(String(text))}
            </span>
        );
    };

    const inputStyle: React.CSSProperties = {
        background: '#111110',
        border: '1px solid rgba(250,249,245,0.1)',
        color: '#faf9f5',
    };

    const selectStyle: React.CSSProperties = {
        background: '#111110',
        border: '1px solid rgba(250,249,245,0.1)',
        color: '#faf9f5',
    };

    return (
        <div style={{ background: '#141413' }} className="flex h-screen overflow-hidden">
            {/* Left Panel - Channel List */}
            <div style={{ background: '#111110', borderRight: '1px solid rgba(250,249,245,0.06)', width: '200px' }} className="shrink-0 flex flex-col py-5 px-3">
                <div className="px-2 mb-3">
                    <div className="flex items-center gap-2 mb-0.5">
                        <Dna style={{ color: '#faf9f5' }} className="w-4 h-4" />
                        <p style={{ color: '#faf9f5' }} className="text-sm font-semibold">Channel DNA</p>
                    </div>
                    <p style={{ color: '#ababab' }} className="text-[11px]">Manage your channel's AI profile</p>
                </div>

                <div className="space-y-1">
                    {channelLoading ? (
                        [...Array(2)].map((_, i) => (
                            <div key={i} className="p-3 rounded-xl">
                                <div style={{ background: 'rgba(250,249,245,0.06)' }} className="h-3 w-28 rounded animate-pulse mb-1.5" />
                                <div style={{ background: 'rgba(250,249,245,0.04)' }} className="h-2 w-16 rounded animate-pulse" />
                            </div>
                        ))
                    ) : channels.map((ch: any) => {
                        const isSelected = selectedChannel?.id === ch.id;
                        const hasDna = (() => {
                            const raw = ch.channel_dna;
                            if (!raw) return false;
                            const parsed = typeof raw === 'string' ? JSON.parse(raw || '{}') : raw;
                            return parsed && Object.keys(parsed).length > 0;
                        })();

                        return (
                            <button
                                key={ch.id}
                                onClick={() => setSelectedChannel(ch)}
                                style={{
                                    background: isSelected ? 'rgba(250,249,245,0.08)' : 'transparent',
                                    border: isSelected ? '1px solid rgba(250,249,245,0.1)' : '1px solid transparent',
                                }}
                                className="w-full px-3 py-2.5 rounded-xl text-left transition-all"
                            >
                                <div className="flex items-center justify-between">
                                    <span style={{ color: '#faf9f5' }} className="text-xs font-medium truncate">{ch.display_name || ch.name || ch.id}</span>
                                    <span style={hasDna
                                        ? { color: '#4ade80', background: 'rgba(34,197,94,0.1)' }
                                        : { color: '#ababab', background: 'rgba(250,249,245,0.06)' }
                                    } className="text-[10px] px-1.5 py-0.5 rounded-md flex-shrink-0 ml-2">
                                        {hasDna ? 'Ready' : 'Setup'}
                                    </span>
                                </div>
                                {ch.niche && <p style={{ color: '#ababab' }} className="text-[11px] mt-0.5 truncate">{ch.niche}</p>}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Right Panel - DNA Editor */}
            {selectedChannel ? (
                <div className="flex-1 overflow-y-auto px-7 py-6">
                    {/* Header */}
                    <div className="flex items-start justify-between mb-6">
                        {editingHeader ? (
                            <div className="flex gap-3 items-start flex-1 max-w-lg">
                                <div className="flex-1 space-y-2">
                                    <input
                                        type="text"
                                        value={headerForm.display_name}
                                        onChange={e => setHeaderForm({ ...headerForm, display_name: e.target.value })}
                                        style={inputStyle}
                                        className="w-full rounded-xl px-3 py-2 text-lg font-semibold focus:outline-none transition-colors"
                                        placeholder="Channel Name"
                                    />
                                    <input
                                        type="text"
                                        value={headerForm.niche}
                                        onChange={e => setHeaderForm({ ...headerForm, niche: e.target.value })}
                                        style={inputStyle}
                                        className="w-full rounded-xl px-3 py-2 text-sm focus:outline-none transition-colors"
                                        placeholder="Niche"
                                    />
                                </div>
                                <div className="flex gap-2 pt-1">
                                    <button onClick={handleSaveHeader} className="px-3 py-1.5 bg-white text-black text-xs font-medium rounded-xl hover:bg-[#e5e5e5] transition-colors">Save</button>
                                    <button onClick={() => setEditingHeader(false)} style={{ border: '1px solid rgba(250,249,245,0.1)', color: '#ababab' }} className="px-3 py-1.5 text-xs font-medium rounded-xl hover:text-[#faf9f5] transition-colors">Cancel</button>
                                </div>
                            </div>
                        ) : (
                            <div>
                                <div className="flex items-center gap-2 mb-0.5">
                                    <h2 style={{ color: '#faf9f5' }} className="text-lg font-semibold">{selectedChannel.display_name || selectedChannel.name || selectedChannel.id}</h2>
                                    <button
                                        onClick={() => {
                                            setHeaderForm({
                                                display_name: selectedChannel.display_name || selectedChannel.name || selectedChannel.id || '',
                                                niche: selectedChannel.niche || ''
                                            });
                                            setEditingHeader(true);
                                        }}
                                        style={{ color: '#ababab' }}
                                        className="hover:text-[#faf9f5] transition-colors"
                                    >
                                        <Pencil className="w-3.5 h-3.5" />
                                    </button>
                                    <span style={dna && Object.keys(dna).length > 0
                                        ? { color: '#4ade80', background: 'rgba(34,197,94,0.1)' }
                                        : { color: '#ababab', background: 'rgba(250,249,245,0.06)' }
                                    } className="text-[10px] px-2 py-0.5 rounded-lg">
                                        {dna && Object.keys(dna).length > 0 ? 'Ready' : 'Setup Required'}
                                    </span>
                                </div>
                                {selectedChannel.niche && <p style={{ color: '#ababab' }} className="text-sm">{selectedChannel.niche}</p>}
                            </div>
                        )}
                    </div>

                    {/* DNA Card */}
                    <div style={{ background: '#1c1c1b', border: '1px solid rgba(250,249,245,0.07)' }} className="rounded-2xl overflow-hidden mb-5">
                        {/* Card Header */}
                        <div style={{ borderBottom: '1px solid rgba(250,249,245,0.06)' }} className="flex items-center justify-between px-5 py-4">
                            <div className="flex items-center gap-2">
                                <div style={{ background: 'rgba(250,249,245,0.07)' }} className="w-6 h-6 rounded-lg flex items-center justify-center">
                                    <span style={{ color: '#ababab' }} className="text-xs">⚡</span>
                                </div>
                                <span style={{ color: '#faf9f5' }} className="text-sm font-medium">Channel DNA</span>
                            </div>
                            {!editingDna && (
                                <button
                                    onClick={handleStartEditDna}
                                    style={{ background: 'rgba(250,249,245,0.07)', border: '1px solid rgba(250,249,245,0.1)', color: '#ababab' }}
                                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs hover:text-[#faf9f5] transition-colors"
                                >
                                    <Pencil className="w-3 h-3" />
                                    Edit DNA
                                </button>
                            )}
                        </div>

                        <div className="p-5">
                            {editingDna ? (
                                <div className="space-y-6">
                                    <div className="grid grid-cols-2 gap-5">
                                        {/* Tone */}
                                        <div>
                                            <label style={{ color: '#ababab' }} className="block text-[10px] mb-1.5 uppercase tracking-widest">Tone</label>
                                            <MultiTagInput value={dnaForm.tone} onChange={v => setDnaForm((p: any) => ({ ...p, tone: v }))} placeholder="e.g. Energetic" />
                                        </div>

                                        {/* Hook Style */}
                                        <div>
                                            <label style={{ color: '#ababab' }} className="block text-[10px] mb-1.5 uppercase tracking-widest">Hook Style</label>
                                            <select
                                                value={dnaForm.hook_style}
                                                onChange={e => setDnaForm((p: any) => ({ ...p, hook_style: e.target.value }))}
                                                style={selectStyle}
                                                className="w-full rounded-xl px-3 py-2 text-sm focus:outline-none appearance-none"
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

                                        {/* Humor Profile */}
                                        <div style={{ background: '#141413', border: '1px solid rgba(250,249,245,0.06)' }} className="col-span-2 rounded-xl p-4 space-y-4">
                                            <h4 style={{ color: '#ababab' }} className="text-xs font-medium">Humor Profile</h4>
                                            <div className="grid grid-cols-2 gap-4">
                                                <div>
                                                    <label style={{ color: '#ababab' }} className="block text-[10px] mb-1.5 uppercase tracking-widest">Style</label>
                                                    <select value={dnaForm.humor_profile.style} onChange={e => setDnaForm((p: any) => ({ ...p, humor_profile: { ...p.humor_profile, style: e.target.value } }))} style={selectStyle} className="w-full rounded-xl px-3 py-2 text-sm focus:outline-none appearance-none">
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
                                                    <label style={{ color: '#ababab' }} className="block text-[10px] mb-1.5 uppercase tracking-widest">Frequency</label>
                                                    <select value={dnaForm.humor_profile.frequency} onChange={e => setDnaForm((p: any) => ({ ...p, humor_profile: { ...p.humor_profile, frequency: e.target.value } }))} style={selectStyle} className="w-full rounded-xl px-3 py-2 text-sm focus:outline-none appearance-none">
                                                        <option value="">Select...</option>
                                                        <option value="very_frequent">Very Frequent</option>
                                                        <option value="frequent">Frequent</option>
                                                        <option value="occasional">Occasional</option>
                                                        <option value="rare">Rare</option>
                                                    </select>
                                                </div>
                                                <div className="col-span-2">
                                                    <label style={{ color: '#ababab' }} className="block text-[10px] mb-1.5 uppercase tracking-widest">Triggers</label>
                                                    <MultiTagInput value={dnaForm.humor_profile.triggers} onChange={v => setDnaForm((p: any) => ({ ...p, humor_profile: { ...p.humor_profile, triggers: v } }))} placeholder="e.g. Awkward Silence" />
                                                </div>
                                            </div>
                                        </div>

                                        {/* Do List */}
                                        <div>
                                            <label style={{ color: '#ababab' }} className="block text-[10px] mb-1.5 uppercase tracking-widest">Do List</label>
                                            <MultiTagInput value={dnaForm.do_list} onChange={v => setDnaForm((p: any) => ({ ...p, do_list: v }))} placeholder="e.g. Start with shocking statement" variant="do" />
                                        </div>

                                        {/* Don't List */}
                                        <div>
                                            <label style={{ color: '#ababab' }} className="block text-[10px] mb-1.5 uppercase tracking-widest">Don't List</label>
                                            <MultiTagInput value={dnaForm.dont_list} onChange={v => setDnaForm((p: any) => ({ ...p, dont_list: v }))} placeholder="e.g. No slow intros" variant="dont" />
                                        </div>

                                        {/* No Go Zones */}
                                        <div>
                                            <label style={{ color: '#f87171' }} className="block text-[10px] mb-1.5 uppercase tracking-widest">No Go Zones</label>
                                            <MultiTagInput value={dnaForm.no_go_zones} onChange={v => setDnaForm((p: any) => ({ ...p, no_go_zones: v }))} placeholder="e.g. Explicit Content" variant="dont" />
                                        </div>

                                        {/* Sacred Topics */}
                                        <div>
                                            <label style={{ color: '#4ade80' }} className="block text-[10px] mb-1.5 uppercase tracking-widest">Sacred Topics</label>
                                            <MultiTagInput value={dnaForm.sacred_topics} onChange={v => setDnaForm((p: any) => ({ ...p, sacred_topics: v }))} placeholder="e.g. Tech Startups" variant="do" />
                                        </div>

                                        {/* Best Content Types */}
                                        <div className="col-span-2">
                                            <label style={{ color: '#ababab' }} className="block text-[10px] mb-1.5 uppercase tracking-widest">Best Content Types</label>
                                            <div className="flex flex-wrap gap-2">
                                                {contentTypesOptions.map(type => {
                                                    const isSelected = dnaForm.best_content_types.includes(type);
                                                    return (
                                                        <button key={type} onClick={() => setDnaForm((p: any) => ({ ...p, best_content_types: isSelected ? p.best_content_types.filter((t: string) => t !== type) : [...p.best_content_types, type] }))}
                                                            style={isSelected
                                                                ? { background: '#faf9f5', color: '#141413', border: '1px solid #faf9f5' }
                                                                : { background: 'transparent', color: '#ababab', border: '1px solid rgba(250,249,245,0.1)' }
                                                            }
                                                            className="text-xs px-3 py-1.5 rounded-xl transition-all hover:text-[#faf9f5]">
                                                            {formatText(type)}
                                                        </button>
                                                    );
                                                })}
                                            </div>
                                        </div>

                                        {/* Content Format */}
                                        <div className="col-span-2">
                                            <label style={{ color: '#ababab' }} className="block text-[10px] mb-1.5 uppercase tracking-widest">Content Format</label>
                                            <div className="flex flex-wrap gap-2">
                                                {['podcast', 'interview', 'talk_show', 'comedy', 'debate', 'documentary', 'reaction', 'commentary'].map(format => {
                                                    const isSelected = (dnaForm.content_format || []).includes(format);
                                                    return (
                                                        <button key={format} onClick={() => setDnaForm((p: any) => ({ ...p, content_format: isSelected ? p.content_format.filter((f: string) => f !== format) : [...(p.content_format || []), format] }))}
                                                            style={isSelected
                                                                ? { background: '#faf9f5', color: '#141413', border: '1px solid #faf9f5' }
                                                                : { background: 'transparent', color: '#ababab', border: '1px solid rgba(250,249,245,0.1)' }
                                                            }
                                                            className="text-xs px-3 py-1.5 rounded-xl transition-all hover:text-[#faf9f5]">
                                                            {formatText(format)}
                                                        </button>
                                                    );
                                                })}
                                            </div>
                                        </div>

                                        {/* Target Platforms */}
                                        <div className="col-span-2">
                                            <label style={{ color: '#ababab' }} className="block text-[10px] mb-1.5 uppercase tracking-widest">Target Platforms</label>
                                            <div className="flex flex-wrap gap-2">
                                                {['youtube_shorts', 'tiktok', 'instagram_reels', 'all'].map(platform => {
                                                    const isSelected = (dnaForm.target_platforms || []).includes(platform);
                                                    return (
                                                        <button key={platform} onClick={() => setDnaForm((p: any) => ({ ...p, target_platforms: isSelected ? p.target_platforms.filter((pl: string) => pl !== platform) : [...(p.target_platforms || []), platform] }))}
                                                            style={isSelected
                                                                ? { background: '#faf9f5', color: '#141413', border: '1px solid #faf9f5' }
                                                                : { background: 'transparent', color: '#ababab', border: '1px solid rgba(250,249,245,0.1)' }
                                                            }
                                                            className="text-xs px-3 py-1.5 rounded-xl transition-all hover:text-[#faf9f5]">
                                                            {formatText(platform)}
                                                        </button>
                                                    );
                                                })}
                                            </div>
                                        </div>

                                        {/* Audience Identity */}
                                        <div className="col-span-2">
                                            <label style={{ color: '#ababab' }} className="block text-[10px] mb-1.5 uppercase tracking-widest">Audience Identity</label>
                                            <textarea
                                                value={dnaForm.audience_identity}
                                                onChange={e => setDnaForm((p: any) => ({ ...p, audience_identity: e.target.value }))}
                                                rows={3}
                                                style={inputStyle}
                                                className="w-full rounded-xl px-3 py-2 text-sm placeholder:text-[rgba(250,249,245,0.25)] focus:outline-none resize-none"
                                                placeholder="Describe the target audience..."
                                            />
                                        </div>

                                        {/* Speaker Pref & Duration */}
                                        <div>
                                            <label style={{ color: '#ababab' }} className="block text-[10px] mb-1.5 uppercase tracking-widest">Speaker Preference</label>
                                            <select value={dnaForm.speaker_preference} onChange={e => setDnaForm((p: any) => ({ ...p, speaker_preference: e.target.value }))} style={selectStyle} className="w-full rounded-xl px-3 py-2 text-sm focus:outline-none appearance-none">
                                                <option value="">Select...</option>
                                                <option value="guest_dominant">Guest Dominant</option>
                                                <option value="balanced">Balanced</option>
                                                <option value="host_driven">Host Driven</option>
                                            </select>
                                        </div>

                                        <div>
                                            <label style={{ color: '#ababab' }} className="block text-[10px] mb-1.5 uppercase tracking-widest">Avg Successful Duration (seconds)</label>
                                            <input
                                                type="number"
                                                value={dnaForm.avg_successful_duration}
                                                onChange={e => setDnaForm((p: any) => ({ ...p, avg_successful_duration: parseInt(e.target.value) || 0 }))}
                                                style={inputStyle}
                                                className="w-full rounded-xl px-3 py-2 text-sm focus:outline-none"
                                            />
                                        </div>

                                    </div>

                                    <div style={{ borderTop: '1px solid rgba(250,249,245,0.06)' }} className="flex items-center gap-3 pt-4">
                                        <button onClick={() => setEditingDna(false)} style={{ border: '1px solid rgba(250,249,245,0.1)', color: '#ababab' }} className="px-4 py-2 rounded-xl text-sm font-medium hover:text-[#faf9f5] transition-colors">
                                            Cancel
                                        </button>
                                        <button
                                            onClick={handleSaveDna}
                                            disabled={savingDna}
                                            className="px-6 py-2 bg-white text-black rounded-xl text-sm font-medium hover:bg-[#e5e5e5] transition-colors disabled:opacity-50 flex items-center gap-2"
                                        >
                                            {savingDna && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                                            Save Changes
                                        </button>
                                    </div>
                                </div>
                            ) : (
                                dna && Object.keys(dna).length > 0 ? (
                                    <div className="grid grid-cols-2 gap-3">
                                        {dna.tone && (
                                            <div style={{ background: '#141413', border: '1px solid rgba(250,249,245,0.06)' }} className="rounded-xl p-4">
                                                <p style={{ color: '#ababab' }} className="text-[10px] uppercase tracking-wider font-semibold mb-2.5">Tone</p>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {(Array.isArray(dna.tone) ? dna.tone : [dna.tone]).map((t: string, i: number) => <span key={i}>{renderTag(t)}</span>)}
                                                </div>
                                            </div>
                                        )}
                                        {dna.hook_style && (
                                            <div style={{ background: '#141413', border: '1px solid rgba(250,249,245,0.06)' }} className="rounded-xl p-4">
                                                <p style={{ color: '#ababab' }} className="text-[10px] uppercase tracking-wider font-semibold mb-2.5">Hook Style</p>
                                                {renderTag(dna.hook_style)}
                                            </div>
                                        )}
                                        {dna.do_list && dna.do_list.length > 0 && (
                                            <div style={{ background: '#141413', border: '1px solid rgba(250,249,245,0.06)' }} className="rounded-xl p-4">
                                                <p style={{ color: '#ababab' }} className="text-[10px] uppercase tracking-wider font-semibold mb-2.5">Do List</p>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {dna.do_list.map((t: string, i: number) => <span key={i}>{renderTag(t, 'do')}</span>)}
                                                </div>
                                            </div>
                                        )}
                                        {dna.dont_list && dna.dont_list.length > 0 && (
                                            <div style={{ background: '#141413', border: '1px solid rgba(250,249,245,0.06)' }} className="rounded-xl p-4">
                                                <p style={{ color: '#ababab' }} className="text-[10px] uppercase tracking-wider font-semibold mb-2.5">Don't List</p>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {dna.dont_list.map((t: string, i: number) => <span key={i}>{renderTag(t, 'dont')}</span>)}
                                                </div>
                                            </div>
                                        )}
                                        {dna.no_go_zones && dna.no_go_zones.length > 0 && (
                                            <div style={{ background: '#141413', border: '1px solid rgba(250,249,245,0.06)' }} className="rounded-xl p-4">
                                                <p style={{ color: '#f87171' }} className="text-[10px] uppercase tracking-wider font-semibold mb-2.5">No Go Zones</p>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {dna.no_go_zones.map((t: string, i: number) => <span key={i}>{renderTag(t, 'zone')}</span>)}
                                                </div>
                                            </div>
                                        )}
                                        {dna.sacred_topics && dna.sacred_topics.length > 0 && (
                                            <div style={{ background: '#141413', border: '1px solid rgba(250,249,245,0.06)' }} className="rounded-xl p-4">
                                                <p style={{ color: '#4ade80' }} className="text-[10px] uppercase tracking-wider font-semibold mb-2.5">Sacred Topics</p>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {dna.sacred_topics.map((t: string, i: number) => <span key={i}>{renderTag(t, 'sacred')}</span>)}
                                                </div>
                                            </div>
                                        )}
                                        {dna.best_content_types && dna.best_content_types.length > 0 && (
                                            <div style={{ background: '#141413', border: '1px solid rgba(250,249,245,0.06)' }} className="col-span-2 rounded-xl p-4">
                                                <p style={{ color: '#ababab' }} className="text-[10px] uppercase tracking-wider font-semibold mb-2.5">Best Content Types</p>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {dna.best_content_types.map((t: string, i: number) => <span key={i}>{renderTag(t)}</span>)}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <div className="text-center py-8">
                                        <p style={{ color: '#ababab' }} className="text-sm mb-3">No DNA configured yet</p>
                                        <button onClick={handleStartEditDna} className="px-4 py-2 bg-white text-black rounded-xl text-sm font-medium hover:bg-[#e5e5e5] transition-colors">
                                            Set Up DNA
                                        </button>
                                    </div>
                                )
                            )}
                        </div>
                    </div>

                    {/* Reference Clips */}
                    <div style={{ background: '#1c1c1b', border: '1px solid rgba(250,249,245,0.07)' }} className="rounded-2xl overflow-hidden">
                        <div style={{ borderBottom: '1px solid rgba(250,249,245,0.06)' }} className="flex items-center justify-between px-5 py-4">
                            <span style={{ color: '#faf9f5' }} className="text-sm font-medium">Reference Clips</span>
                            <div>
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    accept="video/*"
                                    className="hidden"
                                    onChange={e => e.target.files?.[0] && handleUploadReference(e.target.files[0])}
                                />
                                <button
                                    onClick={() => fileInputRef.current?.click()}
                                    disabled={uploading}
                                    style={{ background: 'rgba(250,249,245,0.07)', border: '1px solid rgba(250,249,245,0.1)', color: '#ababab' }}
                                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs hover:text-[#faf9f5] transition-colors disabled:opacity-50"
                                >
                                    <Upload className="w-3.5 h-3.5" />
                                    {uploading ? 'Uploading...' : 'Upload Clip'}
                                </button>
                            </div>
                        </div>

                        {referenceClips.length === 0 ? (
                            <div className="px-5 py-10 text-center">
                                <p style={{ color: '#ababab' }} className="text-sm">No reference clips uploaded yet</p>
                                <p style={{ color: 'rgba(250,249,245,0.15)' }} className="text-xs mt-1">Upload clips to help AI understand your style</p>
                            </div>
                        ) : (
                            <div className="p-5 space-y-2">
                                {referenceClips.map(clip => (
                                    <div key={clip.id} style={{ background: '#141413', border: '1px solid rgba(250,249,245,0.06)' }} className="flex items-center justify-between rounded-xl p-3">
                                        <div>
                                            <p style={{ color: '#faf9f5' }} className="text-sm font-medium">{clip.title}</p>
                                            {clip.source && <p style={{ color: '#ababab' }} className="text-xs mt-0.5">{clip.source}</p>}
                                        </div>
                                        <button style={{ color: '#ababab' }} className="p-1.5 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-colors">
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            ) : (
                <div className="flex-1 flex items-center justify-center">
                    <p style={{ color: '#ababab' }} className="text-sm">Select a channel to manage its DNA</p>
                </div>
            )}
        </div>
    );
}
