import { authFetch } from '@/lib/api';

/**
 * Multipart upload of one file straight to R2.
 *
 * The same protocol the single-file dashboard uses, lifted into a function so a
 * batch can run ten of them at once. It is a copy rather than a shared import
 * on purpose: the dashboard flow is what publishes every day, and a batch bug
 * must not be able to reach it.
 *
 * A single presigned PUT stalls around 40% of a 100 Mbit link on multi-GB files
 * — one TCP stream to a distant edge never opens its window. Parts in parallel
 * are what saturate it.
 */

// R2 requires >=5 MiB per part and at most 10,000 parts. 64 MiB keeps a 5 GB
// file well under the cap while staying small enough that six in flight fill
// the link.
const PART_SIZE = 64 * 1024 * 1024;
const MAX_PART_ATTEMPTS = 3;

export interface UploadHandle {
    uploadId: string;
    durationSeconds: number;
}

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

async function signPart(uploadId: string, partNumber: number): Promise<string> {
    const res = await authFetch('/jobs/mpu/sign-part', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ upload_id: uploadId, part_number: partNumber }),
    });
    if (!res.ok) throw new Error('sign failed');
    return (await res.json()).url;
}

function putPart(url: string, blob: Blob, onBytes: (n: number) => void): Promise<string> {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('PUT', url, true);
        xhr.upload.onprogress = ev => { if (ev.lengthComputable) onBytes(ev.loaded); };
        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                // R2 returns the part ETag here; complete() is rejected without it.
                // Requires the bucket's CORS rule to list ETag in ExposeHeaders.
                const etag = xhr.getResponseHeader('ETag') || xhr.getResponseHeader('etag');
                etag ? resolve(etag) : reject(new Error('missing ETag — check R2 CORS ExposeHeaders'));
            } else {
                reject(new Error(`part failed: ${xhr.status}`));
            }
        };
        xhr.onerror = () => reject(new Error('network error'));
        xhr.send(blob);
    });
}

/**
 * `concurrency` is per file. The batch modal runs several files at once, so the
 * real number of open connections is this times the number of active files —
 * kept low here for that reason.
 */
export async function uploadFileMultipart(
    file: File,
    onProgress: (pct: number) => void,
    concurrency = 3,
): Promise<UploadHandle> {
    const initRes = await authFetch('/jobs/mpu/init', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            filename: file.name,
            content_type: file.type || 'video/mp4',
            size_bytes: file.size,
        }),
    });
    if (!initRes.ok) {
        const err = await initRes.json().catch(() => ({}));
        throw new Error(err.detail || 'Could not prepare upload');
    }
    const { upload_id } = await initRes.json();

    const partCount = Math.max(1, Math.ceil(file.size / PART_SIZE));
    const sent = new Array(partCount).fill(0);
    const report = () => onProgress(Math.min(99, Math.round((sent.reduce((a, b) => a + b, 0) / file.size) * 100)));

    const collected: { part_number: number; etag: string }[] = [];
    let nextPart = 0;
    let failure: Error | null = null;

    const worker = async () => {
        while (!failure) {
            const idx = nextPart++;
            if (idx >= partCount) return;

            const start = idx * PART_SIZE;
            const blob = file.slice(start, Math.min(start + PART_SIZE, file.size));

            for (let attempt = 1; attempt <= MAX_PART_ATTEMPTS; attempt++) {
                try {
                    const url = await signPart(upload_id, idx + 1);
                    const etag = await putPart(url, blob, n => { sent[idx] = n; report(); });
                    collected.push({ part_number: idx + 1, etag });
                    sent[idx] = blob.size;
                    report();
                    break;
                } catch (e) {
                    sent[idx] = 0;
                    report();
                    if (attempt === MAX_PART_ATTEMPTS) {
                        failure = e instanceof Error ? e : new Error('part failed');
                        return;
                    }
                    await sleep(1000 * attempt);
                }
            }
        }
    };

    await Promise.all(Array.from({ length: Math.min(concurrency, partCount) }, worker));

    if (failure) {
        // Release the R2 handle so the storage does not leak a half-written object.
        await authFetch('/jobs/mpu/abort', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ upload_id }),
        }).catch(() => { });
        throw failure;
    }

    const completeRes = await authFetch('/jobs/mpu/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            upload_id,
            parts: collected.sort((a, b) => a.part_number - b.part_number),
        }),
    });
    if (!completeRes.ok) {
        const err = await completeRes.json().catch(() => ({}));
        throw new Error(err.detail || 'Could not finalize upload');
    }
    const body = await completeRes.json();
    onProgress(100);
    return { uploadId: upload_id, durationSeconds: Number(body.duration_seconds) || 0 };
}
