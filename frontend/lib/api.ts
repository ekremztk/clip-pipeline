export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface Job {
    id: string;
    [key: string]: any;
}

export interface Clip {
    id: string;
    [key: string]: any;
}

export interface Channel {
    id: string;
    [key: string]: any;
}

export interface CostResponse {
    [key: string]: any;
}

async function fetchApi<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${API_URL}${endpoint}`;

    const headers = {
        ...options.headers,
    };

    const response = await fetch(url, {
        ...options,
        headers,
    });

    if (!response.ok) {
        const errorBody = await response.text().catch(() => '');
        throw new Error(`API error ${response.status}: ${errorBody || response.statusText}`);
    }

    // Handle empty responses (like 204 No Content)
    if (response.status === 204 || response.headers.get('content-length') === '0') {
        return {} as T;
    }

    return response.json();
}

// 1. uploadVideo(formData: FormData) -> POST /jobs
export async function uploadVideo(formData: FormData): Promise<Job> {
    // Omit headers here so the browser can automatically set the boundary for multipart/form-data
    const response = await fetch(`${API_URL}/jobs`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const errorBody = await response.text().catch(() => '');
        throw new Error(`API error ${response.status}: ${errorBody || response.statusText}`);
    }

    return response.json();
}

// 2. getJob(jobId: string) -> GET /jobs/{jobId}
export async function getJob(jobId: string): Promise<Job> {
    return fetchApi<Job>(`/jobs/${jobId}`);
}

// 3. getJobs(channelId?: string) -> GET /jobs
export async function getJobs(channelId?: string): Promise<Job[]> {
    const query = channelId ? `?channel_id=${encodeURIComponent(channelId)}` : '';
    return fetchApi<Job[]>(`/jobs${query}`);
}

// 4. deleteJob(jobId: string) -> DELETE /jobs/{jobId}
export async function deleteJob(jobId: string): Promise<void> {
    return fetchApi<void>(`/jobs/${jobId}`, {
        method: 'DELETE',
    });
}

// 5. getClips(jobId: string) -> GET /clips?job_id={jobId}
export async function getClips(jobId: string): Promise<Clip[]> {
    return fetchApi<Clip[]>(`/clips?job_id=${encodeURIComponent(jobId)}`);
}

// 6. approveClip(clipId: string, notes?: string) -> PATCH /clips/{clipId}/approve
export async function approveClip(clipId: string, notes?: string): Promise<Clip> {
    return fetchApi<Clip>(`/clips/${clipId}/approve`, {
        method: 'PATCH',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ notes }),
    });
}

// 7. rejectClip(clipId: string, notes?: string) -> PATCH /clips/{clipId}/reject
export async function rejectClip(clipId: string, notes?: string): Promise<Clip> {
    return fetchApi<Clip>(`/clips/${clipId}/reject`, {
        method: 'PATCH',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ notes }),
    });
}

// 8. confirmSpeakers(jobId: string, speakerMap: Record<string, {role: string, name?: string}>) -> POST /jobs/{jobId}/confirm-speakers
export async function confirmSpeakers(jobId: string, speakerMap: Record<string, { role: string, name?: string }>): Promise<any> {
    return fetchApi<any>(`/jobs/${jobId}/confirm-speakers`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ speaker_map: speakerMap }),
    });
}

// 9. getChannels() -> GET /channels
export async function getChannels(): Promise<Channel[]> {
    return fetchApi<Channel[]>('/channels');
}

// 10. getChannel(channelId: string) -> GET /channels/{channelId}
export async function getChannel(channelId: string): Promise<Channel> {
    return fetchApi<Channel>(`/channels/${channelId}`);
}

// 11. publishClip(clipId: string, youtubeVideoId: string) -> POST /feedback/clips/{clipId}/publish
export async function publishClip(clipId: string, youtubeVideoId: string): Promise<any> {
    return fetchApi<any>(`/feedback/clips/${clipId}/publish`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ youtube_video_id: youtubeVideoId }),
    });
}

// 12. approveRag(clipId: string, approved: boolean) -> POST /feedback/clips/{clipId}/approve-rag
export async function approveRag(clipId: string, approved: boolean): Promise<any> {
    return fetchApi<any>(`/feedback/clips/${clipId}/approve-rag`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ approved }),
    });
}

// 13. getJobCost(jobId: string) -> GET /jobs/{jobId} (extract cost from audit trail later)
export async function getJobCost(jobId: string): Promise<CostResponse> {
    return fetchApi<CostResponse>(`/jobs/${jobId}`);
}
