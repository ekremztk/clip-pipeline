"use client";

// EDITOR MODULE — Isolated module, no dependencies on other app files

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { streamJobProgress } from '@/lib/editor/api';
import { useEditorStore, EditorStoreType } from '@/lib/editor/store';
import { EditorJob, JobStatus } from '@/lib/editor/types';

interface ProcessingScreenProps {
    job: EditorJob;
}

export default function ProcessingScreen({ job }: ProcessingScreenProps) {
    const router = useRouter();
    const updateJobProgress = useEditorStore((state: EditorStoreType) => state.updateJobProgress);
    const [progress, setProgress] = useState(job.progress || 0);
    const [status, setStatus] = useState<JobStatus>(job.status);
    const [errorMsg, setErrorMsg] = useState<string | null>(null);

    useEffect(() => {
        // Only stream if pending or processing
        if (status === 'completed' || status === 'failed') return;

        const cleanup = streamJobProgress(
            job.id,
            (newStatus: JobStatus, newProgress: number) => {
                setStatus(newStatus);
                setProgress(newProgress);
                updateJobProgress(newProgress);
            },
            () => {
                setStatus('completed');
                router.refresh();
            },
            (err: Error) => {
                setStatus('failed');
                setErrorMsg(err.message);
            }
        );

        return cleanup;
    }, [job.id, status, router, updateJobProgress]);

    const getSubtitle = (p: number) => {
        if (p < 20) return 'Analyzing video...';
        if (p < 60) return 'Transcribing audio...';
        if (p < 80) return 'Detecting silence...';
        if (p < 95) return 'Uploading to AI...';
        return 'Almost ready...';
    };

    if (status === 'failed') {
        return (
            <div className="min-h-screen bg-[#0f0f0f] flex items-center justify-center p-4">
                <div className="bg-[#1a1a1a] border border-red-900/50 p-8 rounded-xl max-w-md w-full flex flex-col items-center">
                    <div className="w-16 h-16 rounded-full bg-red-900/20 flex items-center justify-center mb-6">
                        <svg className="w-8 h-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </div>
                    <h2 className="text-xl font-semibold text-white mb-2 text-center">Processing Failed</h2>
                    <p className="text-sm text-[#6b7280] text-center mb-8">{errorMsg || 'An unknown error occurred during video processing.'}</p>
                    <button
                        onClick={() => window.location.reload()}
                        className="bg-red-600 hover:bg-red-700 text-white px-6 py-2 rounded-md font-medium transition-colors w-full"
                    >
                        Retry
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-[#0f0f0f] flex items-center justify-center p-4">
            <div className="bg-[#1a1a1a] border border-[#2a2a2a] p-8 rounded-xl max-w-md w-full flex flex-col items-center">
                {/* CSS Spinner */}
                <div className="relative w-16 h-16 mb-8">
                    <div className="absolute inset-0 rounded-full border-4 border-[#2a2a2a]"></div>
                    <div className="absolute inset-0 rounded-full border-4 border-[#6366f1] border-t-transparent animate-spin"></div>
                </div>

                <h2 className="text-xl font-semibold text-white mb-2 text-center">Preparing your video...</h2>
                <p className="text-sm text-[#6b7280] text-center mb-8 min-h-[20px]">
                    {getSubtitle(progress)}
                </p>

                {/* Progress bar */}
                <div className="w-full bg-[#2a2a2a] rounded-full h-2 mb-4 overflow-hidden">
                    <div
                        className="bg-[#6366f1] h-2 rounded-full transition-all duration-300 ease-out"
                        style={{ width: `${Math.max(5, progress)}%` }}
                    ></div>
                </div>

                <div className="text-3xl font-bold text-white tracking-tight">
                    {Math.round(progress)}<span className="text-[#6b7280] text-xl ml-1">%</span>
                </div>
            </div>
        </div>
    );
}
