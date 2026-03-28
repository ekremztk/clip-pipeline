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

const MultiTagInput = ({ value, onChange, placeholder, colorClass }: {
    value: string[],
    onChange: (v: string[]) => void,
    placeholder?: string,
    colorClass?: string
}) => {
    const [input, setInput] = useState('');
    const safeValue = Array.isArray(value) ? value : [];

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
                        <span key={i} className={`flex items-center gap-1 text-xs px-2.5 py-1 border rounded-lg ${colorClass || 'bg-[#1a1a1a] text-[#a3a3a3] border-[#262626]'}`}>
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
                className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2 text-sm text-white placeholder-[#525252] focus:outline-none focus:border-[#404040] transition-colors"
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
    const { channels } = useChannel();
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
            avg_successful_duration: parsed.avg_successful_duration || 30
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

    const renderTag = (text: string, colorClass?: string) => (
        <span className={`text-xs px-2.5 py-1 border rounded-lg ${colorClass || 'bg-[#1a1a1a] text-[#a3a3a3] border-[#262626]'}`}>
            {formatText(String(text))}
        </span>
    );

    return (
        <div className="flex h-screen overflow-hidden bg-black">
            {/* Left Panel - Channel List */}
            <div className="w-72 flex-shrink-0 border-r border-[#1a1a1a] flex flex-col">
                <div className="p-5 border-b border-[#1a1a1a]">
                    <div className="flex items-center gap-2 mb-1">
                        <Dna className="w-4 h-4 text-white" />
                        <h1 className="text-base font-semibold text-white">Channel DNA</h1>
                    </div>
                    <p className="text-xs text-[#737373]">Manage your channel's AI profile</p>
                </div>

                <div className="flex-1 overflow-y-auto p-3 space-y-1">
                    {channels.map((ch: any) => {
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
                                className={`w-full text-left p-3 rounded-lg border transition-all ${
                                    isSelected
                                        ? 'bg-[#1a1a1a] border-[#262626] text-white'
                                        : 'border-transparent text-[#a3a3a3] hover:bg-[#0a0a0a] hover:text-white hover:border-[#1a1a1a]'
                                }`}
                            >
                                <div className="flex items-center justify-between">
                                    <p className="text-sm font-medium truncate">{ch.display_name || ch.name || ch.id}</p>
                                    <span className={`text-[10px] px-1.5 py-0.5 rounded flex-shrink-0 ml-2 ${
                                        hasDna
                                            ? 'text-green-400 bg-green-400/10'
                                            : 'text-[#525252] bg-[#1a1a1a]'
                                    }`}>
                                        {hasDna ? 'Ready' : 'Setup'}
                                    </span>
                                </div>
                                {ch.niche && <p className="text-xs text-[#525252] mt-0.5 truncate">{ch.niche}</p>}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Right Panel - DNA Editor */}
            {selectedChannel ? (
                <div className="flex-1 overflow-y-auto p-8">
                    {/* Header */}
                    <div className="flex items-start justify-between mb-8">
                        {editingHeader ? (
                            <div className="flex gap-3 items-start flex-1 max-w-lg">
                                <div className="flex-1 space-y-2">
                                    <input
                                        type="text"
                                        value={headerForm.display_name}
                                        onChange={e => setHeaderForm({ ...headerForm, display_name: e.target.value })}
                                        className="w-full bg-[#0a0a0a] border border-[#262626] rounded-lg px-3 py-2 text-xl font-semibold text-white focus:outline-none focus:border-[#404040]"
                                        placeholder="Channel Name"
                                    />
                                    <input
                                        type="text"
                                        value={headerForm.niche}
                                        onChange={e => setHeaderForm({ ...headerForm, niche: e.target.value })}
                                        className="w-full bg-[#0a0a0a] border border-[#262626] rounded-lg px-3 py-2 text-sm text-[#a3a3a3] focus:outline-none focus:border-[#404040]"
                                        placeholder="Niche"
                                    />
                                </div>
                                <div className="flex gap-2 pt-1">
                                    <button onClick={handleSaveHeader} className="px-3 py-1.5 bg-white text-black text-xs font-medium rounded-lg hover:bg-[#e5e5e5] transition-colors">Save</button>
                                    <button onClick={() => setEditingHeader(false)} className="px-3 py-1.5 border border-[#262626] text-[#a3a3a3] text-xs font-medium rounded-lg hover:bg-[#1a1a1a] transition-colors">Cancel</button>
                                </div>
                            </div>
                        ) : (
                            <div>
                                <div className="flex items-center gap-2">
                                    <h2 className="text-2xl font-semibold text-white">{selectedChannel.display_name || selectedChannel.name || selectedChannel.id}</h2>
                                    <button
                                        onClick={() => {
                                            setHeaderForm({
                                                display_name: selectedChannel.display_name || selectedChannel.name || selectedChannel.id || '',
                                                niche: selectedChannel.niche || ''
                                            });
                                            setEditingHeader(true);
                                        }}
                                        className="text-[#525252] hover:text-white transition-colors"
                                    >
                                        <Pencil className="w-4 h-4" />
                                    </button>
                                </div>
                                {selectedChannel.niche && <p className="text-sm text-[#737373] mt-1">{selectedChannel.niche}</p>}
                            </div>
                        )}

                        {!editingHeader && (
                            <span className={`text-xs px-2.5 py-1 rounded-lg border mt-1 ${
                                dna && Object.keys(dna).length > 0
                                    ? 'text-green-400 bg-green-400/10 border-green-400/20'
                                    : 'text-[#737373] bg-[#0a0a0a] border-[#262626]'
                            }`}>
                                {dna && Object.keys(dna).length > 0 ? 'Ready' : 'Setup Required'}
                            </span>
                        )}
                    </div>

                    {/* DNA Section */}
                    <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl p-6 mb-5">
                        <div className="flex items-center justify-between mb-5">
                            <h3 className="text-sm font-medium text-white flex items-center gap-2">
                                <Dna className="w-4 h-4 text-[#a3a3a3]" />
                                Channel DNA
                            </h3>
                            {!editingDna && (
                                <button
                                    onClick={handleStartEditDna}
                                    className="flex items-center gap-1.5 px-3 py-1.5 border border-[#262626] text-[#a3a3a3] hover:text-white hover:border-[#404040] rounded-lg text-xs transition-all"
                                >
                                    <Pencil className="w-3.5 h-3.5" />
                                    Edit DNA
                                </button>
                            )}
                        </div>

                        {editingDna ? (
                            <div className="space-y-6">
                                <div className="grid grid-cols-2 gap-5">
                                    {/* Tone */}
                                    <div>
                                        <label className="block text-[10px] text-[#737373] mb-1.5 uppercase tracking-widest">Tone</label>
                                        <MultiTagInput value={dnaForm.tone} onChange={v => setDnaForm((p: any) => ({ ...p, tone: v }))} placeholder="e.g. Energetic" />
                                    </div>

                                    {/* Hook Style */}
                                    <div>
                                        <label className="block text-[10px] text-[#737373] mb-1.5 uppercase tracking-widest">Hook Style</label>
                                        <select
                                            value={dnaForm.hook_style}
                                            onChange={e => setDnaForm((p: any) => ({ ...p, hook_style: e.target.value }))}
                                            className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#404040] appearance-none"
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
                                    <div className="col-span-2 bg-black border border-[#1a1a1a] rounded-lg p-4 space-y-4">
                                        <h4 className="text-xs font-medium text-[#a3a3a3]">Humor Profile</h4>
                                        <div className="grid grid-cols-2 gap-4">
                                            <div>
                                                <label className="block text-[10px] text-[#737373] mb-1.5 uppercase tracking-widest">Style</label>
                                                <select value={dnaForm.humor_profile.style} onChange={e => setDnaForm((p: any) => ({ ...p, humor_profile: { ...p.humor_profile, style: e.target.value } }))} className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#404040] appearance-none">
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
                                                <label className="block text-[10px] text-[#737373] mb-1.5 uppercase tracking-widest">Frequency</label>
                                                <select value={dnaForm.humor_profile.frequency} onChange={e => setDnaForm((p: any) => ({ ...p, humor_profile: { ...p.humor_profile, frequency: e.target.value } }))} className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#404040] appearance-none">
                                                    <option value="">Select...</option>
                                                    <option value="very_frequent">Very Frequent</option>
                                                    <option value="frequent">Frequent</option>
                                                    <option value="occasional">Occasional</option>
                                                    <option value="rare">Rare</option>
                                                </select>
                                            </div>
                                            <div className="col-span-2">
                                                <label className="block text-[10px] text-[#737373] mb-1.5 uppercase tracking-widest">Triggers</label>
                                                <MultiTagInput value={dnaForm.humor_profile.triggers} onChange={v => setDnaForm((p: any) => ({ ...p, humor_profile: { ...p.humor_profile, triggers: v } }))} placeholder="e.g. Awkward Silence" />
                                            </div>
                                        </div>
                                    </div>

                                    {/* Do List */}
                                    <div>
                                        <label className="block text-[10px] text-[#737373] mb-1.5 uppercase tracking-widest">Do List</label>
                                        <MultiTagInput value={dnaForm.do_list} onChange={v => setDnaForm((p: any) => ({ ...p, do_list: v }))} placeholder="e.g. Start with shocking statement" />
                                    </div>

                                    {/* Don't List */}
                                    <div>
                                        <label className="block text-[10px] text-[#737373] mb-1.5 uppercase tracking-widest">Don't List</label>
                                        <MultiTagInput value={dnaForm.dont_list} onChange={v => setDnaForm((p: any) => ({ ...p, dont_list: v }))} placeholder="e.g. No slow intros" />
                                    </div>

                                    {/* No Go Zones */}
                                    <div>
                                        <label className="block text-[10px] text-red-500 mb-1.5 uppercase tracking-widest">No Go Zones</label>
                                        <MultiTagInput value={dnaForm.no_go_zones} onChange={v => setDnaForm((p: any) => ({ ...p, no_go_zones: v }))} placeholder="e.g. Explicit Content" colorClass="bg-red-500/10 text-red-400 border-red-500/20" />
                                    </div>

                                    {/* Sacred Topics */}
                                    <div>
                                        <label className="block text-[10px] text-green-500 mb-1.5 uppercase tracking-widest">Sacred Topics</label>
                                        <MultiTagInput value={dnaForm.sacred_topics} onChange={v => setDnaForm((p: any) => ({ ...p, sacred_topics: v }))} placeholder="e.g. Tech Startups" colorClass="bg-green-500/10 text-green-400 border-green-500/20" />
                                    </div>

                                    {/* Best Content Types */}
                                    <div className="col-span-2">
                                        <label className="block text-[10px] text-[#737373] mb-1.5 uppercase tracking-widest">Best Content Types</label>
                                        <div className="flex flex-wrap gap-2">
                                            {contentTypesOptions.map(type => {
                                                const isSelected = dnaForm.best_content_types.includes(type);
                                                return (
                                                    <button key={type} onClick={() => setDnaForm((p: any) => ({ ...p, best_content_types: isSelected ? p.best_content_types.filter((t: string) => t !== type) : [...p.best_content_types, type] }))}
                                                        className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${isSelected ? 'bg-white text-black border-white' : 'bg-transparent text-[#a3a3a3] border-[#262626] hover:border-[#404040] hover:text-white'}`}>
                                                        {formatText(type)}
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    </div>

                                    {/* Content Format */}
                                    <div className="col-span-2">
                                        <label className="block text-[10px] text-[#737373] mb-1.5 uppercase tracking-widest">Content Format</label>
                                        <div className="flex flex-wrap gap-2">
                                            {['podcast', 'interview', 'talk_show', 'comedy', 'debate', 'documentary', 'reaction', 'commentary'].map(format => {
                                                const isSelected = (dnaForm.content_format || []).includes(format);
                                                return (
                                                    <button key={format} onClick={() => setDnaForm((p: any) => ({ ...p, content_format: isSelected ? p.content_format.filter((f: string) => f !== format) : [...(p.content_format || []), format] }))}
                                                        className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${isSelected ? 'bg-white text-black border-white' : 'bg-transparent text-[#a3a3a3] border-[#262626] hover:border-[#404040] hover:text-white'}`}>
                                                        {formatText(format)}
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    </div>

                                    {/* Target Platforms */}
                                    <div className="col-span-2">
                                        <label className="block text-[10px] text-[#737373] mb-1.5 uppercase tracking-widest">Target Platforms</label>
                                        <div className="flex flex-wrap gap-2">
                                            {['youtube_shorts', 'tiktok', 'instagram_reels', 'all'].map(platform => {
                                                const isSelected = (dnaForm.target_platforms || []).includes(platform);
                                                return (
                                                    <button key={platform} onClick={() => setDnaForm((p: any) => ({ ...p, target_platforms: isSelected ? p.target_platforms.filter((pl: string) => pl !== platform) : [...(p.target_platforms || []), platform] }))}
                                                        className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${isSelected ? 'bg-white text-black border-white' : 'bg-transparent text-[#a3a3a3] border-[#262626] hover:border-[#404040] hover:text-white'}`}>
                                                        {formatText(platform)}
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    </div>

                                    {/* Audience Identity */}
                                    <div className="col-span-2">
                                        <label className="block text-[10px] text-[#737373] mb-1.5 uppercase tracking-widest">Audience Identity</label>
                                        <textarea
                                            value={dnaForm.audience_identity}
                                            onChange={e => setDnaForm((p: any) => ({ ...p, audience_identity: e.target.value }))}
                                            rows={3}
                                            className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2 text-sm text-white placeholder-[#525252] focus:outline-none focus:border-[#404040] resize-none"
                                            placeholder="Describe the target audience..."
                                        />
                                    </div>

                                    {/* Speaker Pref & Duration */}
                                    <div>
                                        <label className="block text-[10px] text-[#737373] mb-1.5 uppercase tracking-widest">Speaker Preference</label>
                                        <select value={dnaForm.speaker_preference} onChange={e => setDnaForm((p: any) => ({ ...p, speaker_preference: e.target.value }))} className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#404040] appearance-none">
                                            <option value="">Select...</option>
                                            <option value="guest_dominant">Guest Dominant</option>
                                            <option value="balanced">Balanced</option>
                                            <option value="host_driven">Host Driven</option>
                                        </select>
                                    </div>

                                    <div>
                                        <label className="block text-[10px] text-[#737373] mb-1.5 uppercase tracking-widest">Avg Successful Duration (seconds)</label>
                                        <input
                                            type="number"
                                            value={dnaForm.avg_successful_duration}
                                            onChange={e => setDnaForm((p: any) => ({ ...p, avg_successful_duration: parseInt(e.target.value) || 0 }))}
                                            className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#404040]"
                                        />
                                    </div>
                                </div>

                                <div className="flex items-center gap-3 pt-4 border-t border-[#1a1a1a]">
                                    <button onClick={() => setEditingDna(false)} className="px-4 py-2 border border-[#262626] text-[#a3a3a3] hover:text-white hover:border-[#404040] rounded-lg text-sm font-medium transition-colors">
                                        Cancel
                                    </button>
                                    <button
                                        onClick={handleSaveDna}
                                        disabled={savingDna}
                                        className="px-6 py-2 bg-white text-black rounded-lg text-sm font-medium hover:bg-[#e5e5e5] transition-colors disabled:opacity-50 flex items-center gap-2"
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
                                        <div className="bg-black border border-[#1a1a1a] rounded-lg p-4">
                                            <p className="text-[10px] text-[#525252] uppercase tracking-widest mb-2.5">Tone</p>
                                            <div className="flex flex-wrap gap-1.5">
                                                {(Array.isArray(dna.tone) ? dna.tone : [dna.tone]).map((t: string, i: number) => renderTag(t))}
                                            </div>
                                        </div>
                                    )}
                                    {dna.hook_style && (
                                        <div className="bg-black border border-[#1a1a1a] rounded-lg p-4">
                                            <p className="text-[10px] text-[#525252] uppercase tracking-widest mb-2.5">Hook Style</p>
                                            {renderTag(dna.hook_style)}
                                        </div>
                                    )}
                                    {dna.do_list && dna.do_list.length > 0 && (
                                        <div className="bg-black border border-[#1a1a1a] rounded-lg p-4">
                                            <p className="text-[10px] text-[#525252] uppercase tracking-widest mb-2.5">Do List</p>
                                            <div className="flex flex-wrap gap-1.5">
                                                {dna.do_list.map((t: string, i: number) => renderTag(t, 'bg-green-500/10 text-green-400 border-green-500/20'))}
                                            </div>
                                        </div>
                                    )}
                                    {dna.dont_list && dna.dont_list.length > 0 && (
                                        <div className="bg-black border border-[#1a1a1a] rounded-lg p-4">
                                            <p className="text-[10px] text-[#525252] uppercase tracking-widest mb-2.5">Don't List</p>
                                            <div className="flex flex-wrap gap-1.5">
                                                {dna.dont_list.map((t: string, i: number) => renderTag(t, 'bg-red-500/10 text-red-400 border-red-500/20'))}
                                            </div>
                                        </div>
                                    )}
                                    {dna.no_go_zones && dna.no_go_zones.length > 0 && (
                                        <div className="bg-black border border-[#1a1a1a] rounded-lg p-4">
                                            <p className="text-[10px] text-red-500 uppercase tracking-widest mb-2.5">No Go Zones</p>
                                            <div className="flex flex-wrap gap-1.5">
                                                {dna.no_go_zones.map((t: string, i: number) => renderTag(t, 'bg-red-500/10 text-red-400 border-red-500/20'))}
                                            </div>
                                        </div>
                                    )}
                                    {dna.sacred_topics && dna.sacred_topics.length > 0 && (
                                        <div className="bg-black border border-[#1a1a1a] rounded-lg p-4">
                                            <p className="text-[10px] text-green-500 uppercase tracking-widest mb-2.5">Sacred Topics</p>
                                            <div className="flex flex-wrap gap-1.5">
                                                {dna.sacred_topics.map((t: string, i: number) => renderTag(t, 'bg-green-500/10 text-green-400 border-green-500/20'))}
                                            </div>
                                        </div>
                                    )}
                                    {dna.best_content_types && dna.best_content_types.length > 0 && (
                                        <div className="col-span-2 bg-black border border-[#1a1a1a] rounded-lg p-4">
                                            <p className="text-[10px] text-[#525252] uppercase tracking-widest mb-2.5">Best Content Types</p>
                                            <div className="flex flex-wrap gap-1.5">
                                                {dna.best_content_types.map((t: string, i: number) => renderTag(t))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ) : (
                                <div className="text-center py-8">
                                    <p className="text-sm text-[#525252] mb-3">No DNA configured yet</p>
                                    <button onClick={handleStartEditDna} className="px-4 py-2 bg-white text-black rounded-lg text-sm font-medium hover:bg-[#e5e5e5] transition-colors">
                                        Set Up DNA
                                    </button>
                                </div>
                            )
                        )}
                    </div>

                    {/* Reference Clips */}
                    <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl p-6">
                        <div className="flex items-center justify-between mb-5">
                            <h3 className="text-sm font-medium text-white">Reference Clips</h3>
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
                                    className="flex items-center gap-1.5 px-3 py-1.5 bg-white text-black rounded-lg text-xs font-medium hover:bg-[#e5e5e5] transition-colors disabled:opacity-50"
                                >
                                    <Upload className="w-3.5 h-3.5" />
                                    {uploading ? 'Uploading...' : 'Upload Clip'}
                                </button>
                            </div>
                        </div>

                        {referenceClips.length === 0 ? (
                            <p className="text-sm text-[#525252] text-center py-6">No reference clips uploaded yet</p>
                        ) : (
                            <div className="space-y-2">
                                {referenceClips.map(clip => (
                                    <div key={clip.id} className="flex items-center justify-between bg-black border border-[#1a1a1a] rounded-lg p-3">
                                        <div>
                                            <p className="text-sm text-white font-medium">{clip.title}</p>
                                            {clip.source && <p className="text-xs text-[#525252]">{clip.source}</p>}
                                        </div>
                                        <button className="p-1.5 text-[#525252] hover:text-red-400 hover:bg-red-400/10 rounded transition-colors">
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
                    <p className="text-sm text-[#525252]">Select a channel to manage its DNA</p>
                </div>
            )}
        </div>
    );
}
