/**
 * Backend-powered reframe engine — keyframe mode.
 *
 * Instead of rendering a new video, the backend returns per-frame crop
 * positions converted to canvas keyframes. These are applied directly to
 * the timeline element so the user can manually adjust any frame.
 *
 * Flow:
 *   1. Collect video elements from the timeline
 *   2. POST /reframe/process → get reframe_job_id
 *   3. Poll GET /reframe/status/{id} every 2s
 *   4. When done: apply keyframes to element + set canvas to target aspect ratio
 *   5. Store scene_cuts in metadata store for timeline markers
 */

import type { EditorCore } from "@/core";
import type { VideoTrack, VideoElement } from "@/types/timeline";
import type { AnimationPropertyPath, AnimationInterpolation } from "@/types/animation";
import { useReframeMetadataStore } from "@/stores/reframe-metadata-store";
import { createClient } from "@/lib/supabase/client";
import type { ReframeKeyframe, ReframeOptions } from "./types";
import { ASPECT_RATIO_CANVAS } from "./types";

async function getAuthToken(): Promise<string | null> {
	try {
		const supabase = createClient();
		const { data } = await supabase.auth.getSession();
		return data?.session?.access_token ?? null;
	} catch {
		return null;
	}
}

const PROGNOT_API = process.env.NEXT_PUBLIC_PROGNOT_API_URL ?? "";
const POLL_INTERVAL_MS = 2000;

export interface ReframeProgress {
	step: string;
	percent: number;
}

export interface ReframeResult {
	elementId: string;
	keyframeCount: number;
}

export type { ReframeOptions };

export async function runReframe(
	editor: EditorCore,
	onProgress: (p: ReframeProgress) => void,
	options: ReframeOptions = { strategy: "podcast", aspectRatio: "9:16", trackingMode: "x_only" },
): Promise<ReframeResult[]> {
	const videoElements = collectVideoElements(editor);
	if (videoElements.length === 0) {
		throw new Error("No video elements on timeline");
	}

	if (!PROGNOT_API) {
		throw new Error("NEXT_PUBLIC_PROGNOT_API_URL is not configured");
	}

	const { jobId, clipId } = useReframeMetadataStore.getState();
	const { setSceneCutMarkers } = useReframeMetadataStore.getState();

	const results: ReframeResult[] = [];
	const allSceneCuts: number[] = [];

	for (let i = 0; i < videoElements.length; i++) {
		const { trackId, element } = videoElements[i];
		const label = videoElements.length > 1 ? ` (clip ${i + 1}/${videoElements.length})` : "";

		const asset = editor.media.getAssets().find((a) => a.id === element.mediaId);
		if (!asset?.file && !asset?.url) {
			console.warn(`[Reframe] No file/URL for element ${element.id}, skipping`);
			continue;
		}

		onProgress({ step: `Starting reframe${label}...`, percent: 2 });

		// Resolve a backend-accessible URL.
		// blob: URLs only exist in the browser — upload the file first.
		let clipUrl: string | null = null;
		let clipLocalPath: string | null = null;

		if (asset.url && !asset.url.startsWith("blob:")) {
			clipUrl = asset.url;
		} else if (asset.file) {
			onProgress({ step: `Uploading video${label}...`, percent: 5 });
			clipLocalPath = await uploadFileToBackend(asset.file);
		} else {
			throw new Error("No accessible video source for reframe");
		}

		// Start reframe job on backend
		const token = await getAuthToken();
		const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
		const startRes = await fetch(`${PROGNOT_API}/reframe/process`, {
			method: "POST",
			headers: { "Content-Type": "application/json", ...authHeaders },
			body: JSON.stringify({
				clip_url: clipUrl,
				clip_local_path: clipLocalPath,
				clip_id: clipId ?? undefined,
				job_id: jobId ?? undefined,
				clip_start: element.trimStart ?? 0,
				clip_end: element.trimStart != null ? element.trimStart + element.duration : null,
				strategy: options.strategy,
				aspect_ratio: options.aspectRatio,
				tracking_mode: options.trackingMode,
			}),
		});

		if (!startRes.ok) {
			throw new Error(`Reframe start failed: ${startRes.status}`);
		}

		const { reframe_job_id } = await startRes.json();

		// Poll for completion
		const { keyframes, scene_cuts, src_w, src_h } = await pollReframeJob(
			reframe_job_id,
			(step, percent) => {
				onProgress({ step: step + label, percent });
			},
		);

		onProgress({ step: `Applying keyframes${label}...`, percent: 97 });

		// Apply to timeline
		const keyframeCount = applyReframeToElement(editor, trackId, element, keyframes, src_w, src_h, options);

		// Collect scene cuts for timeline markers
		if (scene_cuts.length > 0) {
			allSceneCuts.push(...scene_cuts);
		}

		results.push({ elementId: element.id, keyframeCount });
	}

	// Store scene cuts in metadata store so timeline can render markers
	setSceneCutMarkers(allSceneCuts);

	// Set canvas to target aspect ratio
	const canvasSize = ASPECT_RATIO_CANVAS[options.aspectRatio];
	await editor.project.updateSettings({
		settings: { canvasSize },
	});

	onProgress({ step: "Done! Keyframes applied to timeline.", percent: 100 });
	return results;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function collectVideoElements(editor: EditorCore): Array<{ trackId: string; element: VideoElement }> {
	const result: Array<{ trackId: string; element: VideoElement }> = [];
	for (const track of editor.timeline.getTracks()) {
		if (track.type !== "video") continue;
		for (const el of (track as VideoTrack).elements) {
			if (el.type === "video") {
				result.push({ trackId: track.id, element: el as VideoElement });
			}
		}
	}
	return result;
}

async function pollReframeJob(
	reframeJobId: string,
	onProgress: (step: string, percent: number) => void,
): Promise<{ keyframes: ReframeKeyframe[]; scene_cuts: number[]; src_w: number; src_h: number }> {
	const maxAttempts = 300; // ~10 minutes

	for (let attempt = 0; attempt < maxAttempts; attempt++) {
		await sleep(POLL_INTERVAL_MS);

		// Refresh token on each poll to handle session expiry during long jobs
		const statusToken = await getAuthToken();
		const res = await fetch(`${PROGNOT_API}/reframe/status/${reframeJobId}`, {
			headers: statusToken ? { Authorization: `Bearer ${statusToken}` } : {},
		});
		if (!res.ok) {
			throw new Error(`Status check failed: ${res.status}`);
		}

		const data = await res.json();
		onProgress(data.step ?? "Processing...", data.percent ?? 0);

		if (data.status === "done") {
			if (!data.keyframes) throw new Error("Reframe succeeded but no keyframes returned");
			console.log(
				`[Reframe] Backend done — ${data.keyframes.length} keyframes, ` +
				`${(data.scene_cuts ?? []).length} scene cuts, src=${data.src_w}x${data.src_h}`,
			);
			return {
				keyframes: data.keyframes as ReframeKeyframe[],
				scene_cuts: (data.scene_cuts ?? []) as number[],
				src_w: data.src_w as number,
				src_h: data.src_h as number,
			};
		}

		if (data.status === "error") {
			throw new Error(`Reframe failed: ${data.error ?? "Unknown error"}`);
		}
	}

	throw new Error("Reframe timed out after 10 minutes");
}

function applyReframeToElement(
	editor: EditorCore,
	trackId: string,
	element: VideoElement,
	keyframes: ReframeKeyframe[],
	src_w: number,
	src_h: number,
	options: ReframeOptions,
): number {
	const trimStart = element.trimStart ?? 0;

	console.log(
		`[Reframe] Element: id=${element.id} duration=${element.duration} trimStart=${trimStart} trimEnd=${element.trimEnd}`,
	);
	console.log(`[Reframe] Backend keyframes received: ${keyframes.length}`, keyframes.slice(0, 5));

	// Enable cover mode so the video fills the target canvas
	editor.timeline.updateElements({
		updates: [{ trackId, elementId: element.id, updates: { coverMode: true } }],
	});

	// Convert backend offset_x (source-pixel crop left edge) to transform.position.x
	// (canvas-pixel offset from center).
	//
	// The renderer draws: x = canvasWidth/2 + posX - scaledWidth/2
	// To show source pixel `offset_x` at the canvas left edge (x=0):
	//   posX = scaledWidth/2 - canvasWidth/2 - offset_x * containScale
	//
	// where containScale = max(canvasW/srcW, canvasH/srcH) (coverMode fill scale)
	//       scaledWidth   = src_w * containScale
	const { width: canvasWidth, height: canvasHeight } = ASPECT_RATIO_CANVAS[options.aspectRatio];
	const containScale = Math.max(canvasWidth / src_w, canvasHeight / src_h);
	const scaledWidth = src_w * containScale;

	// Convert backend keyframes (absolute video time) to element-local time.
	// Clamp negative times to 0 (pre-trim frames) rather than filtering them out.
	// upsertKeyframes already bounds time to [0, element.duration] internally.
	const kfBatch = keyframes.map((kf) => {
		const posX = scaledWidth / 2 - canvasWidth / 2 - kf.offset_x * containScale;
		return {
			trackId,
			elementId: element.id,
			propertyPath: "transform.position.x" as AnimationPropertyPath,
			time: Math.max(0, kf.time_s - trimStart),
			value: posX,
			interpolation: (kf.interpolation ?? "linear") as AnimationInterpolation,
		};
	});

	console.log(`[Reframe] Applying ${kfBatch.length} keyframes to element ${element.id}`);

	if (kfBatch.length > 0) {
		editor.timeline.upsertKeyframes({ keyframes: kfBatch });
	}

	return kfBatch.length;
}

async function uploadFileToBackend(file: File): Promise<string> {
	const formData = new FormData();
	formData.append("file", file);

	const uploadToken = await getAuthToken();
	const res = await fetch(`${PROGNOT_API}/reframe/upload`, {
		method: "POST",
		body: formData,
		headers: uploadToken ? { Authorization: `Bearer ${uploadToken}` } : {},
	});

	if (!res.ok) {
		throw new Error(`Video upload failed: ${res.status}`);
	}

	const { local_path } = await res.json();
	return local_path as string;
}

function sleep(ms: number): Promise<void> {
	return new Promise((resolve) => setTimeout(resolve, ms));
}
