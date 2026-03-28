'use client';

import { useState } from 'react';
import { Plus } from 'lucide-react';
import { useChannel } from '../layout';
import { authFetch } from '@/lib/api';

export default function SettingsPage() {
    const { channels, isLoading: channelLoading } = useChannel();
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [newChannel, setNewChannel] = useState({ name: '', niche: '', description: '' });
    const [creating, setCreating] = useState(false);

    const handleCreateChannel = async () => {
        if (!newChannel.name.trim()) return;
        setCreating(true);
        try {
            const res = await authFetch('/channels', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    channel_id: newChannel.name.toLowerCase().replace(/\s+/g, '_'),
                    display_name: newChannel.name,
                    niche: newChannel.niche,
                    channel_vision: newChannel.description,
                }),
            });
            if (res.ok) {
                setShowCreateModal(false);
                setNewChannel({ name: '', niche: '', description: '' });
                window.location.reload();
            }
        } catch (e) {
            console.error(e);
        } finally {
            setCreating(false);
        }
    };

    return (
        <div className="min-h-screen bg-black p-8">
            <div className="max-w-2xl mx-auto">
                <h1 className="text-2xl font-semibold text-white mb-2">Settings</h1>
                <p className="text-sm text-[#737373] mb-8">Manage your account and preferences</p>

                {/* Channels Section */}
                <div className="mb-8">
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-sm font-medium text-white">Channels</h2>
                        <button
                            onClick={() => setShowCreateModal(true)}
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-white text-black rounded-lg text-xs font-medium hover:bg-[#e5e5e5] transition-colors"
                        >
                            <Plus className="w-3.5 h-3.5" />
                            New Channel
                        </button>
                    </div>

                    <div className="space-y-2">
                        {channelLoading ? (
                            <div className="space-y-2">
                                {[...Array(2)].map((_, i) => (
                                    <div key={i} className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg p-4 flex items-center justify-between">
                                        <div className="space-y-1.5">
                                            <div className="h-3 w-32 bg-[#1a1a1a] rounded animate-pulse" />
                                            <div className="h-2 w-20 bg-[#1a1a1a] rounded animate-pulse" />
                                        </div>
                                        <div className="h-5 w-24 bg-[#1a1a1a] rounded animate-pulse" />
                                    </div>
                                ))}
                            </div>
                        ) : channels.length === 0 ? (
                            <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg p-8 text-center">
                                <p className="text-sm text-[#525252]">No channels yet. Create your first channel.</p>
                            </div>
                        ) : (
                            channels.map((ch: any) => (
                                <div key={ch.id} className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg p-4 flex items-center justify-between">
                                    <div>
                                        <p className="text-sm font-medium text-white">{ch.display_name || ch.name || ch.id}</p>
                                        {ch.niche && <p className="text-xs text-[#737373] mt-0.5">{ch.niche}</p>}
                                    </div>
                                    <span className="text-xs text-[#525252] bg-[#1a1a1a] px-2 py-1 rounded">
                                        {ch.id}
                                    </span>
                                </div>
                            ))
                        )}
                    </div>
                </div>

                {/* Create Channel Modal */}
                {showCreateModal && (
                    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50" onClick={() => setShowCreateModal(false)}>
                        <div className="bg-[#0a0a0a] border border-[#262626] rounded-xl p-6 w-full max-w-md mx-4" onClick={e => e.stopPropagation()}>
                            <h3 className="text-base font-medium text-white mb-5">Create New Channel</h3>

                            <div className="space-y-4">
                                <div>
                                    <label className="block text-xs text-[#737373] mb-1.5">Channel Name *</label>
                                    <input
                                        type="text"
                                        value={newChannel.name}
                                        onChange={e => setNewChannel({ ...newChannel, name: e.target.value })}
                                        placeholder="My Channel"
                                        className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2.5 text-sm text-white placeholder-[#525252] focus:outline-none focus:border-[#404040] transition-colors"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs text-[#737373] mb-1.5">Niche</label>
                                    <input
                                        type="text"
                                        value={newChannel.niche}
                                        onChange={e => setNewChannel({ ...newChannel, niche: e.target.value })}
                                        placeholder="e.g. Tech, Comedy, Finance"
                                        className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2.5 text-sm text-white placeholder-[#525252] focus:outline-none focus:border-[#404040] transition-colors"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs text-[#737373] mb-1.5">Description</label>
                                    <textarea
                                        value={newChannel.description}
                                        onChange={e => setNewChannel({ ...newChannel, description: e.target.value })}
                                        placeholder="What is this channel about?"
                                        rows={3}
                                        className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2.5 text-sm text-white placeholder-[#525252] focus:outline-none focus:border-[#404040] transition-colors resize-none"
                                    />
                                </div>
                            </div>

                            <div className="flex gap-3 mt-5">
                                <button
                                    onClick={() => setShowCreateModal(false)}
                                    className="flex-1 py-2.5 border border-[#262626] text-[#a3a3a3] rounded-lg text-sm font-medium hover:bg-[#1a1a1a] transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handleCreateChannel}
                                    disabled={!newChannel.name.trim() || creating}
                                    className="flex-1 py-2.5 bg-white text-black rounded-lg text-sm font-medium hover:bg-[#e5e5e5] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    {creating ? 'Creating...' : 'Create Channel'}
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
