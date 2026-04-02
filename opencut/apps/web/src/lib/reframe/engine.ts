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
	debugVideoUrl?: string;
	reframeJobId?: string;
}

export type { ReframeOptions };

export async function runReframe(
	editor: EditorCore,
	onProgress: (p: ReframeProgress) => void,
	options: ReframeOptions = { strategy: "podcast", aspectRatio: "9:16", trackingMode: "dynamic_xy", contentType: "auto" },
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
		const endpoint = options.debugMode ? "debug" : "process";
		const startRes = await fetch(`${PROGNOT_API}/reframe/${endpoint}`, {
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
				content_type: options.contentType ?? "auto",
			}),
		});

		if (!startRes.ok) {
			throw new Error(`Reframe start failed: ${startRes.status}`);
		}

		const { reframe_job_id } = await startRes.json();

		// Poll for completion
		const { keyframes, scene_cuts, src_w, src_h, fps, debugVideoUrl } = await pollReframeJob(
			reframe_job_id,
			(step, percent) => {
				onProgress({ step: step + label, percent });
			},
		);

		onProgress({ step: `Applying keyframes${label}...`, percent: 97 });

		// Apply to timeline
		const keyframeCount = applyReframeToElement(editor, trackId, element, keyframes, src_w, src_h, fps, options);

		// Collect scene cuts for timeline markers
		if (scene_cuts.length > 0) {
			allSceneCuts.push(...scene_cuts);
		}

		results.push({ elementId: element.id, keyframeCount, debugVideoUrl, reframeJobId: reframe_job_id });
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
): Promise<{ keyframes: ReframeKeyframe[]; scene_cuts: number[]; src_w: number; src_h: number; fps: number; debugVideoUrl?: string }> {
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
			// Debug mode: backend stores debug URL as "Done! Debug: <url>" in step field
			const debugVideoUrl = data.step?.includes("Debug: ")
				? (data.step.split("Debug: ")[1] ?? undefined)
				: undefined;
			console.log(
				`[Reframe] Backend done — ${data.keyframes.length} keyframes, ` +
				`${(data.scene_cuts ?? []).length} scene cuts, src=${data.src_w}x${data.src_h}` +
				(debugVideoUrl ? `, debug=${debugVideoUrl}` : ""),
			);
			return {
				keyframes: data.keyframes as ReframeKeyframe[],
				scene_cuts: (data.scene_cuts ?? []) as number[],
				src_w: data.src_w as number,
				src_h: data.src_h as number,
				fps: (data.fps as number) ?? 30,
				debugVideoUrl,
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
	videoFps: number,
	options: ReframeOptions,
): number {
	const trimStart = element.trimStart ?? 0;

	// Snap time to nearest video frame boundary to ensure keyframes
	// align with actual decoded frames. Without this, hold keyframes
	// land between frames, causing 1-frame glitches at transitions.
	const snapToFrame = (t: number): number => Math.round(t * videoFps) / videoFps;

	console.log(
		`[Reframe] Element: id=${element.id} duration=${element.duration} trimStart=${trimStart} trimEnd=${element.trimEnd}`,
	);
	console.log(`[Reframe] Backend keyframes received: ${keyframes.length}`, keyframes.slice(0, 5));

	// Enable cover mode so the video fills the target canvas
	editor.timeline.updateElements({
		updates: [{ trackId, elementId: element.id, updates: { coverMode: true } }],
	});

	// Convert backend offset_x/offset_y (source-pixel crop position) to
	// transform.position.x/y (canvas-pixel offset from center).
	//
	// The renderer draws: x = canvasWidth/2 + posX - scaledWidth/2
	// To show source pixel `offset_x` at the canvas left edge (x=0):
	//   posX = scaledWidth/2 - canvasWidth/2 - offset_x * containScale
	//
	// For dynamic_xy: the backend zooms in slightly (y_headroom_zoom) so the
	// video overflows the canvas vertically, giving Y panning room.
	// containScale is derived from crop dimensions (sent in metadata) to match.
	const { width: canvasWidth, height: canvasHeight } = ASPECT_RATIO_CANVAS[options.aspectRatio];

	// Compute crop dimensions matching the backend formula
	const Y_HEADROOM_ZOOM = 1.12; // Must match backend config.y_headroom_zoom
	const trackingMode = options.trackingMode ?? "dynamic_xy";
	let containScale: number;
	if (trackingMode === "dynamic_xy") {
		const cropH = Math.floor(src_h / Y_HEADROOM_ZOOM);
		const cropW = Math.floor(cropH * (canvasWidth / canvasHeight));
		containScale = Math.max(canvasWidth / cropW, canvasHeight / cropH);
	} else {
		containScale = Math.max(canvasWidth / src_w, canvasHeight / src_h);
	}
	const scaledWidth = src_w * containScale;
	const scaledHeight = src_h * containScale;

	// The renderer computes its own containScale from sourceWidth/sourceHeight
	// (the full decoded frame) using coverMode max(). For dynamic_xy the reframe
	// containScale is larger (zoomed in via crop dimensions). We must set
	// transform.scale to the ratio so the renderer's final scale matches ours.
	const rendererContainScale = Math.max(canvasWidth / src_w, canvasHeight / src_h);
	const transformScale = containScale / rendererContainScale;

	// Apply the scale to the element's base transform
	editor.timeline.updateElements({
		updates: [{ trackId, elementId: element.id, updates: { transform: { ...element.transform, scale: transformScale } } }],
	});

	// Convert backend keyframes (absolute video time) to element-local time.
	// Clamp negative times to 0 (pre-trim frames) rather than filtering them out.
	// upsertKeyframes already bounds time to [0, element.duration] internally.
	const kfBatch: Array<{
		trackId: string;
		elementId: string;
		propertyPath: AnimationPropertyPath;
		time: number;
		value: number;
		interpolation: AnimationInterpolation;
	}> = [];

	for (const kf of keyframes) {
		const localTime = snapToFrame(Math.max(0, kf.time_s - trimStart));
		const interp = (kf.interpolation ?? "linear") as AnimationInterpolation;

		// X keyframe — her zaman eklenir
		const posX = scaledWidth / 2 - canvasWidth / 2 - kf.offset_x * containScale;
		kfBatch.push({
			trackId,
			elementId: element.id,
			propertyPath: "transform.position.x" as AnimationPropertyPath,
			time: localTime,
			value: posX,
			interpolation: interp,
		});

		// Y keyframe — always emit for hold keyframes (shot/subject boundaries) so
		// Y position resets correctly even when offset_y=0. For linear keyframes,
		// skip zero-Y to avoid unnecessary keyframes.
		if (kf.offset_y !== undefined && (interp === "hold" || kf.offset_y !== 0)) {
			const posY = scaledHeight / 2 - canvasHeight / 2 - kf.offset_y * containScale;
			kfBatch.push({
				trackId,
				elementId: element.id,
				propertyPath: "transform.position.y" as AnimationPropertyPath,
				time: localTime,
				value: posY,
				interpolation: interp,
			});
		}
	}

	console.log(`[Reframe] Applying ${kfBatch.length} keyframes to element ${element.id}`);

	if (kfBatch.length > 0) {
		editor.timeline.upsertKeyframes({ keyframes: kfBatch });
	}

	return keyframes.length;
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

export async function analyzeDebugVideo(reframeJobId: string): Promise<string> {
	const token = await getAuthToken();
	const res = await fetch(`${PROGNOT_API}/reframe/analyze-debug/${reframeJobId}`, {
		method: "POST",
		headers: token ? { Authorization: `Bearer ${token}` } : {},
	});
	if (!res.ok) {
		const err = await res.json().catch(() => ({ detail: res.statusText }));
		throw new Error(err.detail ?? `Analysis failed: ${res.status}`);
	}
	const data = await res.json();
	return data.analysis as string;
}

function sleep(ms: number): Promise<void> {
	return new Promise((resolve) => setTimeout(resolve, ms));
}
