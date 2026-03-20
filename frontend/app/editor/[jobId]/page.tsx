// EDITOR MODULE — Isolated module, no dependencies on other app files

import React from 'react';
import ProcessingScreen from './ProcessingScreen';
import EditorShell from './EditorShell';
import { generateR2PresignedUrl } from './s3-signer';
import { EditorJob } from '@/lib/editor/types';
import { notFound } from 'next/navigation';

async function getJobServer(jobId: string): Promise<EditorJob | null> {
    try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const response = await fetch(`${apiUrl}/api/editor/job/${jobId}`, {
            cache: 'no-store'
        });

        if (!response.ok) {
            if (response.status === 404) return null;
            throw new Error(`Failed to get job: ${response.statusText}`);
        }

        const data = await response.json();

        return {
            id: data.id,
            status: data.status,
            progress: data.progress,
            sourceR2Key: data.source_r2_key,
            outputR2Key: data.output_r2_key,
            transcript: data.transcript,
            speakerSegments: data.speaker_segments?.map((s: any) => ({
                start: s.start,
                end: s.end,
                speakerId: s.speaker_id
            })),
            silenceMap: data.silence_map ? {
                silentIntervals: data.silence_map.silent_intervals,
                speechIntervals: data.silence_map.speech_intervals,
            } : undefined,
            videoMetadata: data.video_metadata,
            errorMessage: data.error_message,
            createdAt: data.created_at
        };
    } catch (error) {
        console.error("Error fetching job on server:", error);
        return null;
    }
}

export default async function EditorPage({ params }: { params: { jobId: string } }) {
    const job = await getJobServer(params.jobId);

    if (!job) {
        return (
            <div className="min-h-screen bg-[#0f0f0f] flex items-center justify-center text-white">
                <div className="bg-[#1a1a1a] border border-[#2a2a2a] p-8 rounded-lg max-w-md w-full text-center">
                    <h1 className="text-2xl font-bold mb-2">Job Not Found</h1>
                    <p className="text-[#6b7280]">The editor job you are looking for does not exist or has been removed.</p>
                </div>
            </div>
        );
    }

    if (job.status === 'pending' || job.status === 'processing') {
        return <ProcessingScreen job={job} />;
    }

    // Status 'completed' or 'failed' (we show editor shell either way, perhaps editor shell handles error if no source, but usually it's fine)
    // Generate 24-hour presigned URL for the source video
    let sourceVideoUrl = '';
    if (job.sourceR2Key) {
        sourceVideoUrl = await generateR2PresignedUrl(job.sourceR2Key, 86400);
    }

    return <EditorShell job={job} sourceVideoUrl={sourceVideoUrl} />;
}
