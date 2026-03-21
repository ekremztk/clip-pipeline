// EDITOR MODULE — Isolated module, no dependencies on other app files

import { EditorJob, UploadUrlResponse, JobStatus, EditSpecPayload, EditDecisions, CropSegment } from './types'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || ''

/**
 * Triggers AI auto-edit analysis for a job.
 * After calling this, poll via streamJobProgress.
 * When status === 'completed', job.editSpec contains decisions.
 */
export async function triggerAutoEdit(jobId: string): Promise<void> {
    const res = await fetch(`${API_BASE}/api/editor/job/${jobId}/auto-edit`, {
        method: 'POST',
    })
    if (!res.ok) {
        const error = await res.json().catch(() => ({}))
        throw new Error(error.detail ?? `Auto edit failed: ${res.status}`)
    }
}

/**
 * Maps raw backend snake_case edit decisions to frontend camelCase EditDecisions.
 * _reasoning field is intentionally dropped here — frontend does not need it.
 */
export function mapEditDecisions(raw: Record<string, unknown>): EditDecisions {
    return {
        hookStart: raw.hook_start as number,
        hookReason: raw.hook_reason as string,
        hookScore: raw.hook_score as number,
        cuts: (raw.cuts as Array<Record<string, unknown>>).map(c => ({
            removeFrom: c.remove_from as number,
            removeTo: c.remove_to as number,
            reason: c.reason as string,
        })),
        speedSections: ((raw.speed_sections as Array<Record<string, unknown>>) || []).map(s => ({
            from: s.from as number,
            to: s.to as number,
            multiplier: s.multiplier as number,
        })),
        commentaryCards: ((raw.commentary_cards as Array<Record<string, unknown>>) || []).map(c => ({
            text: c.text as string,
            at: c.at as number,
            duration: c.duration as number,
            position: c.position as 'top' | 'center' | 'bottom',
        })),
        titleSuggestion: raw.title_suggestion as string,
        descriptionSuggestion: raw.description_suggestion as string,
        totalDurationEstimate: raw.total_duration_estimate as number,
    }
}

/**
 * Creates an upload URL for a new file.
 * @param filename Name of the file to upload
 * @param contentType MIME type of the file
 * @param userId ID of the user uploading the file
 * @returns Promise resolving to upload URL details
 */
export async function createUploadUrl(
    filename: string,
    contentType: string,
    userId: string | null
): Promise<UploadUrlResponse> {
    const response = await fetch(`${API_BASE}/api/editor/upload-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename, content_type: contentType, user_id: userId })
    })

    if (!response.ok) {
        throw new Error(`Failed to create upload URL: ${response.statusText}`)
    }

    const data = await response.json()
    return {
        uploadUrl: data.upload_url,
        r2Key: data.r2_key,
        jobId: data.job_id
    }
}

/**
 * Uploads a file to R2 using a pre-signed URL via XMLHttpRequest
 * to support upload progress tracking.
 * @param uploadUrl Pre-signed URL for the upload
 * @param file The file object to upload
 * @param onProgress Optional callback for progress updates (0-100)
 * @returns Promise resolving when upload is complete
 */
export async function uploadFileToR2(
    uploadUrl: string,
    file: File,
    onProgress?: (pct: number) => void
): Promise<void> {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest()

        xhr.upload.addEventListener('progress', (event) => {
            if (event.lengthComputable && onProgress) {
                const percentComplete = (event.loaded / event.total) * 100
                onProgress(percentComplete)
            }
        })

        xhr.addEventListener('load', () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                resolve()
            } else {
                reject(new Error(`Upload failed with status ${xhr.status}`))
            }
        })

        xhr.addEventListener('error', () => {
            reject(new Error('Network error occurred during upload'))
        })

        xhr.addEventListener('abort', () => {
            reject(new Error('Upload aborted'))
        })

        xhr.open('PUT', uploadUrl, true)
        xhr.setRequestHeader('Content-Type', file.type)
        xhr.send(file)
    })
}

/**
 * Starts processing a job after upload is complete.
 * @param jobId ID of the job to start
 * @returns Promise resolving when start request is successful
 */
export async function startJob(jobId: string): Promise<void> {
    const response = await fetch(`${API_BASE}/api/editor/job/${jobId}/start`, {
        method: 'POST'
    })

    if (!response.ok) {
        throw new Error(`Failed to start job: ${response.statusText}`)
    }
}

/**
 * Creates an editor job from an existing R2 key.
 * Used by Module 1's "Open in Editor" button to pass existing clips.
 * After calling this, immediately call startJob(jobId).
 */
export async function createJobFromKey(
    r2Key: string,
    userId: string | null
): Promise<{ jobId: string; r2Key: string }> {
    const res = await fetch(`${API_BASE}/api/editor/job-from-key`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ r2_key: r2Key, user_id: userId }),
    })
    if (!res.ok) {
        const error = await res.json().catch(() => ({}))
        throw new Error(error.detail ?? `Failed to create job from key: ${res.status}`)
    }
    const data = await res.json()
    return { jobId: data.job_id, r2Key: data.r2_key }
}

function mapCropSegments(raw: unknown): CropSegment[] {
    if (!Array.isArray(raw)) return []
    return raw.map(s => ({
        start: s.start as number,
        end: s.end as number,
        speakerId: s.speaker_id as number,
        cropX: s.crop_x as number,
        cropXPixels: s.crop_x_pixels as number,
        detected: s.detected as boolean,
        confidence: s.confidence as number,
    }))
}

/**
 * Fetches the current state of a job.
 * Maps snake_case backend response to camelCase EditorJob.
 * @param jobId ID of the job to fetch
 * @returns Promise resolving to the job details
 */
export async function getJob(jobId: string): Promise<EditorJob & { cropSegments?: CropSegment[] }> {
    const response = await fetch(`${API_BASE}/api/editor/job/${jobId}`)

    if (!response.ok) {
        throw new Error(`Failed to get job: ${response.statusText}`)
    }

    const data = await response.json()

    return {
        id: data.id,
        status: data.status,
        progress: data.progress,
        sourceR2Key: data.source_r2_key,
        outputR2Key: data.output_r2_key,
        transcript: data.transcript,
        speakerSegments: data.speaker_segments?.map((s: { start: number; end: number; speaker_id: number }) => ({
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
        createdAt: data.created_at,
        cropSegments: mapCropSegments(data.crop_segments)
    }
}

/**
 * Cancels an ongoing job.
 * @param jobId ID of the job to cancel
 * @returns Promise resolving when cancellation is successful
 */
export async function cancelJob(jobId: string): Promise<void> {
    const response = await fetch(`${API_BASE}/api/editor/job/${jobId}/cancel`, {
        method: 'POST'
    })

    if (!response.ok) {
        throw new Error(`Failed to cancel job: ${response.statusText}`)
    }
}

/**
 * Starts rendering a job with the provided edit specification.
 * @param jobId ID of the job to render
 * @param editSpecPayload Edit specification payload in snake_case format
 * @returns Promise resolving when render request is successful
 */
export async function startRender(
    jobId: string,
    editSpecPayload: EditSpecPayload
): Promise<void> {
    const response = await fetch(`${API_BASE}/api/editor/job/${jobId}/render`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editSpecPayload)
    })

    if (!response.ok) {
        throw new Error(`Failed to start render: ${response.statusText}`)
    }
}

/**
 * Subscribes to job progress using Server-Sent Events (SSE).
 * @param jobId ID of the job to track
 * @param onUpdate Callback for progress updates
 * @param onComplete Callback for when job completes
 * @param onError Callback for when job fails or encounters an error
 * @returns Cleanup function that closes the EventSource connection
 */
export function streamJobProgress(
    jobId: string,
    onUpdate: (status: JobStatus, progress: number) => void,
    onComplete: () => void,
    onError: (err: Error) => void
): () => void {
    const eventSource = new EventSource(`${API_BASE}/api/editor/job/${jobId}/stream`)

    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data)
            const status = data.status as JobStatus
            const progress = data.progress as number

            onUpdate(status, progress)

            if (status === 'completed') {
                onComplete()
                eventSource.close()
            } else if (status === 'failed') {
                onError(new Error(data.error_message || 'Job processing failed'))
                eventSource.close()
            }
        } catch (err) {
            onError(err instanceof Error ? err : new Error('Failed to parse SSE message'))
        }
    }

    eventSource.onerror = () => {
        onError(new Error('SSE connection error'))
        eventSource.close()
    }

    return () => {
        eventSource.close()
    }
}