'use client';

import { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { Eye, EyeOff, Plus, Trash2 } from 'lucide-react';
import { useChannel } from '../layout';
import { authFetch } from '@/lib/api';
import { supabase } from '@/lib/supabase';

type Section =
    | 'account'
    | 'channels'
    | 'notifications'
    | 'api-keys'
    | 'clip-settings'
    | 'export'
    | 'appearance'
    | 'privacy';

const SECTION_LABELS: Record<Section, string> = {
    account:       'Account',
    channels:      'Channels',
    notifications: 'Notifications',
    'api-keys':    'API Keys',
    'clip-settings': 'Clip Settings',
    export:        'Export',
    appearance:    'Appearance',
    privacy:       'Privacy & Data',
};

const COMING_SOON: Section[] = [
    'notifications', 'api-keys', 'clip-settings', 'export', 'appearance', 'privacy',
];

function SettingsContent() {
    const searchParams = useSearchParams();
    const active = (searchParams.get('section') as Section) ?? 'account';

    const { channels, isLoading: channelLoading, refreshChannels } = useChannel();

    // User
    const [user, setUser]               = useState<any>(null);
    const [displayName, setDisplayName] = useState('');
    const [savingProfile, setSavingProfile] = useState(false);
    const [profileMsg, setProfileMsg]   = useState('');

    // Password
    const [showPasswords, setShowPasswords]       = useState(false);
    const [newPassword, setNewPassword]           = useState('');
    const [confirmPassword, setConfirmPassword]   = useState('');
    const [passwordError, setPasswordError]       = useState('');
    const [passwordSuccess, setPasswordSuccess]   = useState(false);
    const [savingPassword, setSavingPassword]     = useState(false);

    // Channel modal
    const [showCreateModal, setShowCreateModal]   = useState(false);
    const [newChannel, setNewChannel]             = useState({ name: '', niche: '', description: '' });
    const [creating, setCreating]                 = useState(false);

    useEffect(() => {
        supabase.auth.getUser().then(({ data }) => {
            if (data.user) {
                setUser(data.user);
                setDisplayName(data.user.user_metadata?.full_name ?? '');
            }
        });
    }, []);

    // Reset messages when switching section
    useEffect(() => {
        setProfileMsg('');
        setPasswordError('');
        setPasswordSuccess(false);
    }, [active]);

    const handleSaveProfile = async () => {
        setSavingProfile(true);
        setProfileMsg('');
        try {
            const { error } = await supabase.auth.updateUser({ data: { full_name: displayName } });
            setProfileMsg(error ? error.message : 'Saved');
        } catch (e: any) {
            setProfileMsg(e.message ?? 'Error');
        } finally {
            setSavingProfile(false);
        }
    };

    const handleChangePassword = async () => {
        setPasswordError('');
        setPasswordSuccess(false);
        if (newPassword !== confirmPassword) { setPasswordError('Passwords do not match'); return; }
        if (newPassword.length < 8) { setPasswordError('Password must be at least 8 characters'); return; }
        setSavingPassword(true);
        try {
            const { error } = await supabase.auth.updateUser({ password: newPassword });
            if (error) { setPasswordError(error.message); }
            else { setPasswordSuccess(true); setNewPassword(''); setConfirmPassword(''); }
        } catch (e: any) {
            setPasswordError(e.message ?? 'Error');
        } finally {
            setSavingPassword(false);
        }
    };

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
                await refreshChannels();
            }
        } catch (e) { console.error(e); }
        finally { setCreating(false); }
    };

    const userInitials = user?.user_metadata?.full_name
        ? user.user_metadata.full_name.split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2)
        : user?.email?.slice(0, 2).toUpperCase() ?? '';
    const userEmail = user?.email ?? '';
    const userName  = displayName || userEmail.split('@')[0];

    const inputCls = 'w-full px-4 py-2.5 rounded-xl text-sm outline-none transition-colors';
    const inputStyle: React.CSSProperties = {
        background: 'rgba(250,249,245,0.03)',
        color: '#faf9f5',
        border: '1px solid rgba(250,249,245,0.08)',
    };
    const modalInputStyle: React.CSSProperties = {
        background: '#111110',
        border: '1px solid rgba(250,249,245,0.1)',
        color: '#faf9f5',
    };

    return (
        <div className="max-w-2xl px-10 py-10 w-full">

            {/* Account */}
            {active === 'account' && (
                <div>
                    <div className="mb-8">
                        <h1 className="text-2xl font-semibold mb-1" style={{ color: '#faf9f5' }}>Account</h1>
                        <p className="text-sm" style={{ color: 'rgba(250,249,245,0.4)' }}>Manage your profile and account preferences</p>
                    </div>

                    {/* Profile card */}
                    <div className="rounded-2xl p-7 mb-4" style={{ background: '#181817' }}>
                        <div className="flex items-center gap-4 mb-7">
                            <div className="w-14 h-14 rounded-full flex items-center justify-center shrink-0" style={{ background: '#faf9f5' }}>
                                <span className="text-lg font-bold" style={{ color: '#141413' }}>{userInitials}</span>
                            </div>
                            <div>
                                <p className="text-base font-medium" style={{ color: '#faf9f5' }}>{userName}</p>
                                <p className="text-sm mt-0.5" style={{ color: 'rgba(250,249,245,0.4)' }}>{userEmail}</p>
                            </div>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="block text-[10px] font-medium uppercase tracking-wider mb-2" style={{ color: 'rgba(250,249,245,0.4)' }}>Display name</label>
                                <input
                                    type="text"
                                    value={displayName}
                                    onChange={e => setDisplayName(e.target.value)}
                                    placeholder="Your name"
                                    className={`${inputCls} placeholder:opacity-25`}
                                    style={inputStyle}
                                />
                            </div>
                            <div>
                                <label className="block text-[10px] font-medium uppercase tracking-wider mb-2" style={{ color: 'rgba(250,249,245,0.4)' }}>Email</label>
                                <input
                                    type="email"
                                    value={userEmail}
                                    readOnly
                                    className={inputCls}
                                    style={{ ...inputStyle, opacity: 0.5, cursor: 'not-allowed' }}
                                />
                            </div>
                        </div>

                        <div className="flex items-center justify-end gap-3 mt-5">
                            {profileMsg && (
                                <span className="text-xs" style={{ color: profileMsg === 'Saved' ? 'rgba(74,222,128,0.8)' : 'rgba(248,113,113,0.8)' }}>
                                    {profileMsg}
                                </span>
                            )}
                            <button
                                onClick={handleSaveProfile}
                                disabled={savingProfile}
                                className="px-5 py-2.5 rounded-xl text-sm font-semibold transition-opacity hover:opacity-90 disabled:opacity-50"
                                style={{ background: '#faf9f5', color: '#141413' }}
                            >
                                {savingProfile ? 'Saving…' : 'Save changes'}
                            </button>
                        </div>
                    </div>

                    {/* Password card */}
                    <div className="rounded-2xl p-7 mb-8" style={{ background: '#181817' }}>
                        <h3 className="text-base font-medium mb-5" style={{ color: '#faf9f5' }}>Change Password</h3>
                        <div className="space-y-4">
                            {[
                                { label: 'New password',     value: newPassword,    set: setNewPassword },
                                { label: 'Confirm password', value: confirmPassword, set: setConfirmPassword },
                            ].map(f => (
                                <div key={f.label}>
                                    <label className="block text-[10px] font-medium uppercase tracking-wider mb-2" style={{ color: 'rgba(250,249,245,0.4)' }}>
                                        {f.label}
                                    </label>
                                    <div className="relative">
                                        <input
                                            type={showPasswords ? 'text' : 'password'}
                                            value={f.value}
                                            onChange={e => f.set(e.target.value)}
                                            placeholder="••••••••"
                                            className={`${inputCls} pr-10 placeholder:opacity-25`}
                                            style={inputStyle}
                                        />
                                        <button
                                            onClick={() => setShowPasswords(v => !v)}
                                            className="absolute right-3 top-1/2 -translate-y-1/2 transition-opacity hover:opacity-100"
                                            style={{ color: 'rgba(250,249,245,0.35)' }}
                                        >
                                            {showPasswords ? <EyeOff size={15} /> : <Eye size={15} />}
                                        </button>
                                    </div>
                                </div>
                            ))}
                        </div>
                        {passwordError   && <p className="mt-3 text-xs" style={{ color: 'rgba(248,113,113,0.9)' }}>{passwordError}</p>}
                        {passwordSuccess && <p className="mt-3 text-xs" style={{ color: 'rgba(74,222,128,0.8)' }}>Password updated successfully</p>}
                        <div className="flex justify-end mt-5">
                            <button
                                onClick={handleChangePassword}
                                disabled={savingPassword || !newPassword}
                                className="px-5 py-2.5 rounded-xl text-sm font-semibold transition-opacity hover:opacity-90 disabled:opacity-50"
                                style={{ background: '#faf9f5', color: '#141413' }}
                            >
                                {savingPassword ? 'Updating…' : 'Update password'}
                            </button>
                        </div>
                    </div>

                    {/* Danger zone */}
                    <div className="rounded-2xl p-7" style={{ background: '#181817' }}>
                        <h3 className="text-base font-medium mb-1" style={{ color: '#faf9f5' }}>Danger Zone</h3>
                        <p className="text-sm mb-5" style={{ color: 'rgba(250,249,245,0.4)' }}>Permanent actions that cannot be undone</p>
                        <button
                            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-colors hover:bg-red-500/10"
                            style={{ color: 'rgba(239,68,68,0.7)', border: '1px solid rgba(239,68,68,0.15)' }}
                        >
                            <Trash2 size={15} />
                            Delete Account
                        </button>
                    </div>
                </div>
            )}

            {/* Channels */}
            {active === 'channels' && (
                <div>
                    <div className="flex items-start justify-between mb-8">
                        <div>
                            <h1 className="text-2xl font-semibold mb-1" style={{ color: '#faf9f5' }}>Channels</h1>
                            <p className="text-sm" style={{ color: 'rgba(250,249,245,0.4)' }}>Manage your content channels</p>
                        </div>
                        <button
                            onClick={() => setShowCreateModal(true)}
                            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-colors hover:bg-[#e5e5e5]"
                            style={{ background: '#faf9f5', color: '#141413' }}
                        >
                            <Plus size={15} />
                            New Channel
                        </button>
                    </div>

                    <div className="rounded-2xl overflow-hidden" style={{ background: '#181817' }}>
                        {channelLoading ? (
                            <div className="p-6 space-y-3">
                                {[...Array(2)].map((_, i) => (
                                    <div key={i} className="h-16 rounded-xl animate-pulse" style={{ background: 'rgba(250,249,245,0.04)' }} />
                                ))}
                            </div>
                        ) : channels.length === 0 ? (
                            <div className="py-16 text-center">
                                <p className="text-sm" style={{ color: 'rgba(250,249,245,0.3)' }}>No channels yet. Create your first channel.</p>
                            </div>
                        ) : (
                            <div>
                                {channels.map((ch: any, i: number) => (
                                    <div
                                        key={ch.id}
                                        className="flex items-center justify-between px-6 py-4"
                                        style={{ borderBottom: i < channels.length - 1 ? '1px solid rgba(250,249,245,0.05)' : undefined }}
                                    >
                                        <div>
                                            <p className="text-sm font-medium" style={{ color: '#faf9f5' }}>
                                                {ch.display_name || ch.name || ch.id}
                                            </p>
                                            {ch.niche && (
                                                <p className="text-xs mt-0.5" style={{ color: 'rgba(250,249,245,0.4)' }}>{ch.niche}</p>
                                            )}
                                        </div>
                                        <span
                                            className="text-xs px-2.5 py-1 rounded-lg"
                                            style={{ color: 'rgba(250,249,245,0.35)', background: 'rgba(250,249,245,0.05)' }}
                                        >
                                            {ch.id}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Coming soon */}
            {COMING_SOON.includes(active) && (
                <div>
                    <div className="mb-8">
                        <h1 className="text-2xl font-semibold mb-1" style={{ color: '#faf9f5' }}>
                            {SECTION_LABELS[active]}
                        </h1>
                        <p className="text-sm" style={{ color: 'rgba(250,249,245,0.4)' }}>Coming soon</p>
                    </div>
                    <div className="rounded-2xl py-20 flex items-center justify-center" style={{ background: '#181817' }}>
                        <p className="text-sm" style={{ color: 'rgba(250,249,245,0.2)' }}>This section is not yet available</p>
                    </div>
                </div>
            )}

            {/* Create Channel Modal */}
            {showCreateModal && (
                <div
                    className="fixed inset-0 flex items-center justify-center z-50"
                    style={{ background: 'rgba(0,0,0,0.8)' }}
                    onClick={() => setShowCreateModal(false)}
                >
                    <div
                        className="rounded-2xl p-6 w-full max-w-md mx-4"
                        style={{ background: '#1c1c1b', border: '1px solid rgba(250,249,245,0.07)' }}
                        onClick={e => e.stopPropagation()}
                    >
                        <h3 className="text-base font-semibold mb-5" style={{ color: '#faf9f5' }}>Create New Channel</h3>
                        <div className="space-y-4">
                            <div>
                                <label className="block text-xs mb-1.5" style={{ color: 'rgba(250,249,245,0.4)' }}>Channel Name *</label>
                                <input
                                    type="text"
                                    value={newChannel.name}
                                    onChange={e => setNewChannel({ ...newChannel, name: e.target.value })}
                                    placeholder="My Channel"
                                    className="w-full rounded-xl px-3 py-2.5 text-sm outline-none transition-colors placeholder:opacity-30"
                                    style={modalInputStyle}
                                />
                            </div>
                            <div>
                                <label className="block text-xs mb-1.5" style={{ color: 'rgba(250,249,245,0.4)' }}>Niche</label>
                                <input
                                    type="text"
                                    value={newChannel.niche}
                                    onChange={e => setNewChannel({ ...newChannel, niche: e.target.value })}
                                    placeholder="e.g. Tech, Comedy, Finance"
                                    className="w-full rounded-xl px-3 py-2.5 text-sm outline-colors placeholder:opacity-30"
                                    style={modalInputStyle}
                                />
                            </div>
                            <div>
                                <label className="block text-xs mb-1.5" style={{ color: 'rgba(250,249,245,0.4)' }}>Description</label>
                                <textarea
                                    value={newChannel.description}
                                    onChange={e => setNewChannel({ ...newChannel, description: e.target.value })}
                                    placeholder="What is this channel about?"
                                    rows={3}
                                    className="w-full rounded-xl px-3 py-2.5 text-sm outline-none transition-colors resize-none placeholder:opacity-30"
                                    style={modalInputStyle}
                                />
                            </div>
                        </div>
                        <div className="flex gap-3 mt-5">
                            <button
                                onClick={() => setShowCreateModal(false)}
                                className="flex-1 py-2.5 rounded-xl text-sm font-medium transition-colors hover:text-[#faf9f5]"
                                style={{ border: '1px solid rgba(250,249,245,0.1)', color: 'rgba(250,249,245,0.5)' }}
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleCreateChannel}
                                disabled={!newChannel.name.trim() || creating}
                                className="flex-1 py-2.5 bg-white text-black rounded-xl text-sm font-medium hover:bg-[#e5e5e5] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {creating ? 'Creating…' : 'Create Channel'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default function SettingsPage() {
    return (
        <Suspense>
            <SettingsContent />
        </Suspense>
    );
}
