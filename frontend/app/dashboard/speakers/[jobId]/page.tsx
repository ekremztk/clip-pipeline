'use client';

import { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface SpeakerState {
    role: 'host' | 'guest';
    name: string;
    predictedRole: string;
}

export default function ConfirmSpeakersPage() {
    const router = useRouter();
    const params = useParams();
    const jobId = params.jobId as string;

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [speakers, setSpeakers] = useState<Record<string, SpeakerState>>({});
    const [submitting, setSubmitting] = useState(false);
    const [jobTitle, setJobTitle] = useState('');

    useEffect(() => {
        async function fetchJob() {
            if (!jobId) return;
            try {
                const res = await fetch(`${API}/jobs/${jobId}`);
                if (!res.ok) throw new Error('Failed to fetch job details');
                const data = await res.json();
                setJobTitle(data.video_title || data.job?.video_title || '');

                const initialSpeakers: Record<string, SpeakerState> = {};
                const map = data.speaker_map || data.job?.speaker_map || {};

                Object.entries(map).forEach(([key, val]: [string, any]) => {
                    let predicted = 'Guest';
                    let defaultRole: 'host' | 'guest' = 'guest';

                    if (typeof val === 'string') {
                        predicted = val;
                        defaultRole = val.toLowerCase().includes('host') ? 'host' : 'guest';
                    } else if (val && typeof val === 'object') {
                        predicted = val.role || 'Guest';
                        defaultRole = predicted.toLowerCase().includes('host') ? 'host' : 'guest';
                    }

                    initialSpeakers[key] = {
                        role: defaultRole,
                        name: val?.name || '',
                        predictedRole: predicted
                    };
                });

                setSpeakers(initialSpeakers);
            } catch (err: any) {
                setError(err.message || 'An error occurred');
            } finally {
                setLoading(false);
            }
        }
        fetchJob();
    }, [jobId]);

    const handleRoleChange = (key: string, role: 'host' | 'guest') => {
        setSpeakers(prev => ({ ...prev, [key]: { ...prev[key], role } }));
    };

    const handleNameChange = (key: string, name: string) => {
        setSpeakers(prev => ({ ...prev, [key]: { ...prev[key], name } }));
    };

    const handleSubmit = async () => {
        setSubmitting(true);
        try {
            const payload: Record<string, { role: string; name: string }> = {};
            Object.entries(speakers).forEach(([key, state]) => {
                payload[key] = { role: state.role, name: state.name.trim() };
            });

            const res = await fetch(`${API}/jobs/${jobId}/confirm-speakers`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ speaker_map: payload }),
            });

            if (!res.ok) throw new Error('Failed to confirm speakers');
            router.push('/dashboard');
        } catch (err: any) {
            alert(err.message || 'Error confirming speakers');
            setSubmitting(false);
        }
    };

    if (loading) {
        return (
            <div className="min-h-screen bg-black flex items-center justify-center">
                <div className="w-6 h-6 border-2 border-[#262626] border-t-white rounded-full animate-spin" />
            </div>
        );
    }

    if (error) {
        return (
            <div className="min-h-screen bg-black p-8">
                <div className="max-w-2xl mx-auto mt-8">
                    <div className="bg-[#0a0a0a] border border-red-500/20 rounded-xl p-6 text-red-400">
                        <p className="text-sm mb-4">{error}</p>
                        <Link href="/dashboard" className="text-[#a3a3a3] hover:text-white text-sm transition-colors">
                            ← Back to Dashboard
                        </Link>
                    </div>
                </div>
            </div>
        );
    }

    const speakerKeys = Object.keys(speakers).sort();

    return (
        <div className="min-h-screen bg-black p-8">
            <div className="max-w-2xl mx-auto">
                {/* Back link */}
                <Link
                    href="/dashboard"
                    className="inline-flex items-center gap-2 text-sm text-[#737373] hover:text-white transition-colors mb-8"
                >
                    <ArrowLeft className="w-4 h-4" />
                    Back to Dashboard
                </Link>

                {/* Header */}
                <div className="mb-8">
                    <h1 className="text-2xl font-semibold text-white mb-1">Confirm Speakers</h1>
                    {jobTitle && <p className="text-sm text-[#737373]">{jobTitle}</p>}
                    <p className="text-sm text-[#525252] mt-1">Identify who is speaking to improve clip accuracy</p>
                </div>

                {speakerKeys.length === 0 ? (
                    <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl p-8 text-center text-[#525252]">
                        No speakers found for this job.
                    </div>
                ) : (
                    <div className="space-y-4">
                        {speakerKeys.map((key) => {
                            const speaker = speakers[key];
                            const displayName = key.replace('SPEAKER_', 'Speaker ');

                            return (
                                <div key={key} className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl p-5">
                                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
                                        <div>
                                            <h3 className="text-base font-medium text-white">{displayName}</h3>
                                            <span className="inline-block mt-1 bg-[#1a1a1a] text-[#a3a3a3] text-xs px-2 py-0.5 rounded">
                                                Predicted: {speaker.predictedRole}
                                            </span>
                                        </div>

                                        {/* Role toggle */}
                                        <div className="flex bg-black p-1 rounded-lg border border-[#1a1a1a]">
                                            <button
                                                onClick={() => handleRoleChange(key, 'host')}
                                                className={`flex-1 md:flex-none px-5 py-1.5 rounded-md text-sm font-medium transition-colors ${
                                                    speaker.role === 'host'
                                                        ? 'bg-white text-black'
                                                        : 'text-[#737373] hover:text-white hover:bg-[#1a1a1a]'
                                                }`}
                                            >
                                                Host
                                            </button>
                                            <button
                                                onClick={() => handleRoleChange(key, 'guest')}
                                                className={`flex-1 md:flex-none px-5 py-1.5 rounded-md text-sm font-medium transition-colors ${
                                                    speaker.role === 'guest'
                                                        ? 'bg-white text-black'
                                                        : 'text-[#737373] hover:text-white hover:bg-[#1a1a1a]'
                                                }`}
                                            >
                                                Guest
                                            </button>
                                        </div>
                                    </div>

                                    <div>
                                        <label className="block text-xs text-[#737373] mb-1.5">Speaker Name (optional)</label>
                                        <input
                                            type="text"
                                            value={speaker.name}
                                            onChange={(e) => handleNameChange(key, e.target.value)}
                                            placeholder="Enter name"
                                            className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2.5 text-sm text-white placeholder-[#525252] focus:outline-none focus:border-[#404040] transition-colors"
                                        />
                                    </div>
                                </div>
                            );
                        })}

                        <div className="pt-2">
                            <button
                                onClick={handleSubmit}
                                disabled={submitting}
                                className="w-full bg-white hover:bg-[#e5e5e5] text-black font-medium py-3 px-6 rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                            >
                                {submitting ? (
                                    <>
                                        <div className="w-4 h-4 border-2 border-black/20 border-t-black rounded-full animate-spin" />
                                        <span>Saving...</span>
                                    </>
                                ) : (
                                    'Confirm & Continue'
                                )}
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
