'use client';

import { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';

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

    useEffect(() => {
        async function fetchJob() {
            if (!jobId) return;
            try {
                const res = await fetch(`${API}/jobs/${jobId}`);
                if (!res.ok) throw new Error('Failed to fetch job details');
                const data = await res.json();

                const initialSpeakers: Record<string, SpeakerState> = {};
                const map = data.speaker_map || {};

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
                setError(err.message || 'An error occurred while fetching the job');
            } finally {
                setLoading(false);
            }
        }

        fetchJob();
    }, [jobId]);

    const handleRoleChange = (key: string, role: 'host' | 'guest') => {
        setSpeakers(prev => ({
            ...prev,
            [key]: { ...prev[key], role }
        }));
    };

    const handleNameChange = (key: string, name: string) => {
        setSpeakers(prev => ({
            ...prev,
            [key]: { ...prev[key], name }
        }));
    };

    const handleSubmit = async () => {
        setSubmitting(true);
        try {
            const payload: Record<string, { role: string; name: string }> = {};
            Object.entries(speakers).forEach(([key, state]) => {
                payload[key] = {
                    role: state.role,
                    name: state.name.trim()
                };
            });

            const res = await fetch(`${API}/jobs/${jobId}/confirm-speakers`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ speaker_map: payload }),
            });

            if (!res.ok) {
                throw new Error('Failed to confirm speakers');
            }

            router.push('/dashboard');
        } catch (err: any) {
            alert(err.message || 'Error confirming speakers');
            setSubmitting(false);
        }
    };

    if (loading) {
        return (
            <div className="min-h-screen bg-black text-white p-8 flex items-center justify-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500"></div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="min-h-screen bg-black text-white p-8">
                <div className="max-w-2xl mx-auto mt-8 p-4 bg-red-900/50 border border-red-500 rounded-lg text-red-200">
                    <p>{error}</p>
                    <Link href="/dashboard" className="text-purple-400 hover:text-purple-300 mt-4 inline-block">
                        &larr; Back to Dashboard
                    </Link>
                </div>
            </div>
        );
    }

    const speakerKeys = Object.keys(speakers).sort();

    return (
        <div className="min-h-screen bg-black text-white p-6 md:p-10">
            <div className="max-w-3xl mx-auto">
                <Link href="/dashboard" className="text-gray-400 hover:text-white mb-8 inline-flex items-center gap-2 transition-colors">
                    <span>&larr;</span> Back to dashboard
                </Link>

                <div className="mb-10">
                    <h1 className="text-3xl font-bold mb-2">Confirm Speakers</h1>
                    <p className="text-gray-400">Help us identify who is speaking</p>
                </div>

                {speakerKeys.length === 0 ? (
                    <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-8 text-center text-gray-400">
                        No speakers found for this job.
                    </div>
                ) : (
                    <div className="space-y-6">
                        {speakerKeys.map((key) => {
                            const speaker = speakers[key];
                            const displayName = key.replace('SPEAKER_', 'Speaker ');

                            return (
                                <div key={key} className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
                                    <div className="flex flex-col md:flex-row md:items-start justify-between gap-4 mb-6">
                                        <div>
                                            <h3 className="text-xl font-semibold mb-2">{displayName}</h3>
                                            <span className="inline-block bg-zinc-800 text-gray-300 text-xs px-2 py-1 rounded-md">
                                                Predicted: {speaker.predictedRole}
                                            </span>
                                        </div>

                                        <div className="flex bg-zinc-950 p-1 rounded-lg border border-zinc-800 w-full md:w-auto">
                                            <button
                                                onClick={() => handleRoleChange(key, 'host')}
                                                className={`flex-1 md:flex-none px-6 py-2 rounded-md text-sm font-medium transition-colors ${speaker.role === 'host'
                                                        ? 'bg-purple-600 text-white'
                                                        : 'text-gray-400 hover:text-white hover:bg-zinc-800'
                                                    }`}
                                            >
                                                Host
                                            </button>
                                            <button
                                                onClick={() => handleRoleChange(key, 'guest')}
                                                className={`flex-1 md:flex-none px-6 py-2 rounded-md text-sm font-medium transition-colors ${speaker.role === 'guest'
                                                        ? 'bg-purple-600 text-white'
                                                        : 'text-gray-400 hover:text-white hover:bg-zinc-800'
                                                    }`}
                                            >
                                                Guest
                                            </button>
                                        </div>
                                    </div>

                                    <div>
                                        <label className="block text-sm font-medium text-gray-400 mb-2">
                                            Speaker Name
                                        </label>
                                        <input
                                            type="text"
                                            value={speaker.name}
                                            onChange={(e) => handleNameChange(key, e.target.value)}
                                            placeholder="Enter name (optional)"
                                            className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                                        />
                                    </div>
                                </div>
                            );
                        })}

                        <div className="pt-6">
                            <button
                                onClick={handleSubmit}
                                disabled={submitting}
                                className="w-full bg-purple-600 hover:bg-purple-700 text-white font-medium py-4 px-6 rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                            >
                                {submitting ? (
                                    <>
                                        <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                                        <span>Saving...</span>
                                    </>
                                ) : (
                                    <span>Confirm & Continue</span>
                                )}
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
