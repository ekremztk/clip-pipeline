/**
 * Backend-powered reframe engine — split-based mode.
 *
 * Instead of using hold+hold keyframes to simulate scene cuts (which causes
 * 1-2 frame glitches), we actually SPLIT the video element at each scene
 * boundary. Each segment gets its own static transform for the crop position.
 * Within-shot panning still uses linear keyframes.
 *
 * Flow:
 *   1. Collect video elements from the timeline
 *   2. POST /reframe/process → get reframe_job_id
 *   3. Poll GET /reframe/status/{id} every 2s
 *   4. When done: split element at scene cuts + apply transforms per segment
 *   5. Set canvas to target aspect ratio
 *   6. Store scene_cuts in metadata store for timeline markers
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

		onProgress({ step: `Applying reframe${label}...`, percent: 97 });

		// Apply to timeline using split-based approach
		const segmentCount = applyReframeWithSplits(editor, trackId, element, keyframes, scene_cuts, src_w, src_h, fps, options);

		// Collect scene cuts for timeline markers (convert to timeline time)
		if (scene_cuts.length > 0) {
			const trimStart = element.trimStart ?? 0;
			for (const cut of scene_cuts) {
				const timelineCut = element.startTime + (cut - trimStart);
				if (timelineCut > element.startTime && timelineCut < element.startTime + element.duration) {
					allSceneCuts.push(timelineCut);
				}
			}
		}

		results.push({ elementId: element.id, keyframeCount: segmentCount, debugVideoUrl, reframeJobId: reframe_job_id });
	}

	// Store scene cuts in metadata store so timeline can render markers
	setSceneCutMarkers(allSceneCuts);

	// Set canvas to target aspect ratio
	const canvasSize = ASPECT_RATIO_CANVAS[options.aspectRatio];
	await editor.project.updateSettings({
		settings: { canvasSize },
	});

	onProgress({ step: "Done! Reframe applied to timeline.", percent: 100 });
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
	// Allow up to 5 consecutive transient server errors (Supabase 502, Railway restart, etc.)
	// before giving up. 4xx errors (auth, not found) still throw immediately.
	const MAX_TRANSIENT_ERRORS = 5;
	let transientErrorCount = 0;

	for (let attempt = 0; attempt < maxAttempts; attempt++) {
		await sleep(POLL_INTERVAL_MS);

		// Refresh token on each poll to handle session expiry during long jobs
		const statusToken = await getAuthToken();
		const res = await fetch(`${PROGNOT_API}/reframe/status/${reframeJobId}`, {
			headers: statusToken ? { Authorization: `Bearer ${statusToken}` } : {},
		});
		if (!res.ok) {
			if (res.status >= 500) {
				// Transient server error — pipeline may still be running
				transientErrorCount++;
				console.warn(`[Reframe] Status check returned ${res.status} (${transientErrorCount}/${MAX_TRANSIENT_ERRORS} transient errors)`);
				if (transientErrorCount >= MAX_TRANSIENT_ERRORS) {
					throw new Error(`Status check failed with ${transientErrorCount} consecutive server errors: ${res.status}`);
				}
				continue; // retry next poll cycle
			}
			throw new Error(`Status check failed: ${res.status}`);
		}
		transientErrorCount = 0; // reset on successful response

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

/**
 * Segment: a contiguous range of the video between scene cuts.
 * Each segment has its own crop position (static or with panning keyframes).
 */
interface Segment {
	startVideoTime: number; // absolute video time (source)
	endVideoTime: number;   // absolute video time (source)
	keyframes: ReframeKeyframe[]; // only linear keyframes within this segment
}

/**
 * Split-based reframe: instead of hold+hold keyframes at scene boundaries,
 * actually split the video element and apply static transforms per segment.
 *
 * This eliminates the 1-2 frame glitch caused by keyframe timing mismatch
 * with the video decoder.
 */
function applyReframeWithSplits(
	editor: EditorCore,
	trackId: string,
	element: VideoElement,
	keyframes: ReframeKeyframe[],
	sceneCuts: number[],
	src_w: number,
	src_h: number,
	videoFps: number,
	options: ReframeOptions,
): number {
	const trimStart = element.trimStart ?? 0;
	const trimEnd = trimStart + element.duration;

	// Snap time to nearest video frame boundary for ALL FPS types.
	// Works for 23.976, 25, 29.97, 30, 50, 59.94, 60 etc.
	const snapToFrame = (t: number): number => Math.round(t * videoFps) / videoFps;

	console.log(
		`[Reframe] Element: id=${element.id} duration=${element.duration} trimStart=${trimStart} trimEnd=${trimEnd} fps=${videoFps}`,
	);
	console.log(`[Reframe] Backend keyframes: ${keyframes.length}, scene cuts: ${sceneCuts.length}`);

	// ── Step 1: Compute scale and position conversion factors ──
	const { width: canvasWidth, height: canvasHeight } = ASPECT_RATIO_CANVAS[options.aspectRatio];

	const Y_HEADROOM_ZOOM = 1.12;
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

	const rendererContainScale = Math.max(canvasWidth / src_w, canvasHeight / src_h);
	const transformScale = containScale / rendererContainScale;

	// ── Step 2: Filter scene cuts to those within this element's range ──
	// Scene cuts are absolute video times. Filter to within [trimStart, trimEnd).
	// Each must land exactly on a frame boundary.
	const validCuts = sceneCuts
		.map((cut) => snapToFrame(cut))
		.filter((cut) => cut > trimStart && cut < trimEnd)
		// Remove duplicates that could arise from snapping
		.filter((cut, idx, arr) => idx === 0 || Math.abs(cut - arr[idx - 1]) > 0.5 / videoFps);

	console.log(`[Reframe] Valid scene cuts within element: ${validCuts.length}`, validCuts);

	// ── Step 3: Build segments from scene cuts ──
	// Segment boundaries: [trimStart, cut1, cut2, ..., trimEnd]
	const boundaries = [trimStart, ...validCuts, trimEnd];
	const segments: Segment[] = [];

	// Linear keyframes define within-shot panning movement.
	// Hold keyframes define per-shot static crop positions (at scene cut boundaries).
	const linearKeyframes = keyframes.filter((kf) => kf.interpolation === "linear");
	const sortedAllKeyframes = [...keyframes].sort((a, b) => a.time_s - b.time_s);

	// Frame tolerance for matching keyframes to segment boundaries.
	const FRAME_TOLERANCE = 1.5 / videoFps;

	// For each segment, find the "anchor" keyframe that defines its crop position.
	// Segment 0  → earliest keyframe overall (linear at t=0).
	// Segment s>0 → the hold keyframe exactly AT validCuts[s-1] (new-shot position),
	//               NOT the "before-cut" hold which is ~1 frame earlier.
	const getAnchorKeyframe = (s: number): ReframeKeyframe | null => {
		if (s === 0) return sortedAllKeyframes[0] ?? null;
		const cutTime = validCuts[s - 1];
		const candidates = sortedAllKeyframes.filter((kf) => Math.abs(kf.time_s - cutTime) < FRAME_TOLERANCE);
		if (candidates.length === 0) return null;
		// Among candidates near the cut, take the latest time_s = the "at-cut" hold (new shot)
		return candidates[candidates.length - 1];
	};

	for (let s = 0; s < boundaries.length - 1; s++) {
		const segStart = boundaries[s];
		const segEnd = boundaries[s + 1];

		// Linear panning keyframes within this segment's video time range
		const segLinearKfs = linearKeyframes.filter(
			(kf) => kf.time_s >= segStart - FRAME_TOLERANCE && kf.time_s <= segEnd + FRAME_TOLERANCE,
		);

		// If no linear keyframes, use the anchor (hold) keyframe for static crop position
		const segKfs =
			segLinearKfs.length > 0
				? segLinearKfs
				: (() => {
						const anchor = getAnchorKeyframe(s);
						return anchor ? [anchor] : [];
					})();

		segments.push({
			startVideoTime: segStart,
			endVideoTime: segEnd,
			keyframes: segKfs,
		});
	}

	console.log(`[Reframe] ${segments.length} segments created from ${validCuts.length} scene cuts`);

	// ── Step 4: If no scene cuts, just apply keyframes to the original element ──
	if (validCuts.length === 0) {
		applySegmentToElement(editor, trackId, element.id, element, segments[0], trimStart, videoFps, canvasWidth, canvasHeight, scaledWidth, scaledHeight, containScale, transformScale);
		return 1;
	}

	// ── Step 5: Split the element at each scene cut (in reverse order!) ──
	// We split from the last cut to the first to preserve element IDs and
	// timeline positions. Each split produces a right-side element.
	//
	// splitTime is in TIMELINE time: element.startTime + (cutVideoTime - trimStart)

	// First, enable coverMode and set scale on the original element BEFORE splitting.
	// All split children inherit these properties.
	editor.timeline.updateElements({
		updates: [{ trackId, elementId: element.id, updates: { coverMode: true, transform: { ...element.transform, scale: transformScale } } }],
	});

	// Track element IDs: start with the original, splits produce new right-side IDs
	// After all splits, we'll have N segments with known IDs.
	const splitResults: Array<{ elementId: string; segmentIndex: number }> = [];

	// Current element ID being split (starts as original, stays as left side after each split)
	let currentElementId = element.id;

	// Split from last cut to first (reverse order preserves positions)
	for (let c = validCuts.length - 1; c >= 0; c--) {
		const cutVideoTime = validCuts[c];
		const splitTimelineTime = element.startTime + (cutVideoTime - trimStart);

		// Paranoid validation: splitTime must be within element bounds
		const elemStart = element.startTime;
		const elemEnd = element.startTime + element.duration;
		if (splitTimelineTime <= elemStart || splitTimelineTime >= elemEnd) {
			console.warn(
				`[Reframe] SKIP: scene cut at ${cutVideoTime}s maps to timeline ${splitTimelineTime}s ` +
				`which is outside element bounds [${elemStart}, ${elemEnd}]`,
			);
			continue;
		}

		// Paranoid: verify it's on a frame boundary
		const frameNumber = Math.round(cutVideoTime * videoFps);
		const snappedTime = frameNumber / videoFps;
		if (Math.abs(cutVideoTime - snappedTime) > 0.001 / videoFps) {
			console.warn(
				`[Reframe] WARNING: scene cut ${cutVideoTime}s is NOT on frame boundary ` +
				`(nearest: ${snappedTime}s, delta: ${Math.abs(cutVideoTime - snappedTime) * 1000}ms)`,
			);
		}

		console.log(
			`[Reframe] Splitting at scene cut ${c}: videoTime=${cutVideoTime}s, ` +
			`timelineTime=${splitTimelineTime}s, frame=${frameNumber}`,
		);

		const rightElements = editor.timeline.splitElements({
			elements: [{ trackId, elementId: currentElementId }],
			splitTime: splitTimelineTime,
			retainSide: "both",
		});

		if (rightElements.length > 0) {
			// Right side = segment index (c + 1) because we're going in reverse
			splitResults.push({ elementId: rightElements[0].elementId, segmentIndex: c + 1 });
		}
		// currentElementId stays the same — it's now the left portion
	}

	// The original (now leftmost) element is segment 0
	splitResults.push({ elementId: currentElementId, segmentIndex: 0 });

	// Sort by segment index
	splitResults.sort((a, b) => a.segmentIndex - b.segmentIndex);

	console.log(`[Reframe] Split complete: ${splitResults.length} segments`);

	// ── Step 6: Apply transforms to each segment ──
	for (const { elementId, segmentIndex } of splitResults) {
		if (segmentIndex >= segments.length) {
			console.warn(`[Reframe] Segment index ${segmentIndex} out of range (${segments.length} segments)`);
			continue;
		}

		// Re-fetch element after splits (state has changed)
		const track = editor.timeline.getTrackById({ trackId });
		if (!track) continue;
		const el = track.elements.find((e) => e.id === elementId);
		if (!el) {
			console.warn(`[Reframe] Element ${elementId} not found after split`);
			continue;
		}

		const segment = segments[segmentIndex];
		applySegmentToElement(
			editor, trackId, elementId, el as VideoElement, segment,
			el.trimStart ?? 0, videoFps,
			canvasWidth, canvasHeight, scaledWidth, scaledHeight,
			containScale, transformScale,
		);
	}

	return splitResults.length;
}

/**
 * Apply crop position to a single segment element.
 * If the segment has only 1 keyframe or all keyframes are at similar positions,
 * apply a static transform. Otherwise, use linear keyframes for panning.
 */
function applySegmentToElement(
	editor: EditorCore,
	trackId: string,
	elementId: string,
	element: VideoElement,
	segment: Segment,
	elementTrimStart: number,
	videoFps: number,
	canvasWidth: number,
	canvasHeight: number,
	scaledWidth: number,
	scaledHeight: number,
	containScale: number,
	transformScale: number,
): void {
	const toCanvasPosX = (offsetX: number): number => scaledWidth / 2 - canvasWidth / 2 - offsetX * containScale;
	const toCanvasPosY = (offsetY: number): number => scaledHeight / 2 - canvasHeight / 2 - offsetY * containScale;
	const snapToFrame = (t: number): number => Math.round(t * videoFps) / videoFps;

	// Enable cover mode, set scale, and clear any inherited old animations
	// (from a previous reframe run distributed via splitAnimationsAtTime).
	editor.timeline.updateElements({
		updates: [{
			trackId,
			elementId,
			updates: {
				coverMode: true,
				animations: { channels: {} },
				transform: {
					...element.transform,
					scale: transformScale,
				},
			},
		}],
	});

	const kfs = segment.keyframes;

	if (kfs.length === 0) {
		console.warn(`[Reframe] Segment [${segment.startVideoTime}-${segment.endVideoTime}] has no keyframes — skipped`);
		return;
	}

	// Check if all keyframes are at roughly the same position (static segment)
	const STATIC_THRESHOLD_PX = 10;
	const isStatic = kfs.every(
		(kf) =>
			Math.abs(kf.offset_x - kfs[0].offset_x) < STATIC_THRESHOLD_PX &&
			Math.abs((kf.offset_y ?? 0) - (kfs[0].offset_y ?? 0)) < STATIC_THRESHOLD_PX,
	);

	if (kfs.length === 1 || isStatic) {
		// Static position: set transform directly, no keyframes needed.
		// Use the first keyframe's position.
		const posX = toCanvasPosX(kfs[0].offset_x);
		const posY = toCanvasPosY(kfs[0].offset_y ?? 0);

		editor.timeline.updateElements({
			updates: [{
				trackId,
				elementId,
				updates: {
					transform: {
						position: { x: posX, y: posY },
						scale: transformScale,
						rotate: element.transform.rotate,
					},
				},
			}],
		});

		console.log(
			`[Reframe] Segment [${segment.startVideoTime.toFixed(3)}-${segment.endVideoTime.toFixed(3)}]: ` +
			`STATIC pos=(${posX.toFixed(1)}, ${posY.toFixed(1)})`,
		);
		return;
	}

	// Multiple keyframes with different positions: apply linear keyframes for panning.
	// Set base position to the first keyframe's position.
	const basePosX = toCanvasPosX(kfs[0].offset_x);
	const basePosY = toCanvasPosY(kfs[0].offset_y ?? 0);

	editor.timeline.updateElements({
		updates: [{
			trackId,
			elementId,
			updates: {
				transform: {
					position: { x: basePosX, y: basePosY },
					scale: transformScale,
					rotate: element.transform.rotate,
				},
			},
		}],
	});

	// Build keyframes in element-local time
	const kfBatch: Array<{
		trackId: string;
		elementId: string;
		propertyPath: AnimationPropertyPath;
		time: number;
		value: number;
		interpolation: AnimationInterpolation;
	}> = [];

	for (const kf of kfs) {
		const localTime = snapToFrame(Math.max(0, kf.time_s - elementTrimStart));

		// Clamp to element duration
		if (localTime > (element as VideoElement).duration) continue;

		const posX = toCanvasPosX(kf.offset_x);
		kfBatch.push({
			trackId,
			elementId,
			propertyPath: "transform.position.x" as AnimationPropertyPath,
			time: localTime,
			value: posX,
			interpolation: "linear" as AnimationInterpolation,
		});

		if (kf.offset_y !== undefined && kf.offset_y !== 0) {
			const posY = toCanvasPosY(kf.offset_y);
			kfBatch.push({
				trackId,
				elementId,
				propertyPath: "transform.position.y" as AnimationPropertyPath,
				time: localTime,
				value: posY,
				interpolation: "linear" as AnimationInterpolation,
			});
		}
	}

	if (kfBatch.length > 0) {
		editor.timeline.upsertKeyframes({ keyframes: kfBatch });
	}

	console.log(
		`[Reframe] Segment [${segment.startVideoTime.toFixed(3)}-${segment.endVideoTime.toFixed(3)}]: ` +
		`${kfBatch.length} panning keyframes applied`,
	);
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
