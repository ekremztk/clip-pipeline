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
import { processMediaAssets } from "@/lib/media/processing";
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

const PROGNOT_API = "/api/backend";
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

	const { jobId, clipId, precomputedReframe } = useReframeMetadataStore.getState();
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

		// ── Fast path: use pre-computed pipeline data (skip backend) ──────────
		if (precomputedReframe && precomputedReframe.keyframes.length > 0) {
			onProgress({ step: `Applying pre-computed reframe${label}...`, percent: 80 });

			const keyframes = precomputedReframe.keyframes as ReframeKeyframe[];
			const { scene_cuts, src_w, src_h, fps } = precomputedReframe;

			const segmentCount = applyReframeWithSplits(
				editor, trackId, element, keyframes, scene_cuts, src_w, src_h, fps, options,
			);

			if (scene_cuts.length > 0) {
				const trimStart = element.trimStart ?? 0;
				for (const cut of scene_cuts) {
					const timelineCut = element.startTime + (cut - trimStart);
					if (timelineCut > element.startTime && timelineCut < element.startTime + element.duration) {
						allSceneCuts.push(timelineCut);
					}
				}
			}

			console.log(`[Reframe] Used pre-computed data: ${keyframes.length} keyframes, ${scene_cuts.length} scene cuts`);
			results.push({ elementId: element.id, keyframeCount: segmentCount });
			continue;
		}
		// ── End fast path ─────────────────────────────────────────────────────

		onProgress({ step: `Starting reframe${label}...`, percent: 2 });

		// Resolve a backend-accessible URL.
		// blob: URLs only exist in the browser — upload the file first.
		let clipUrl: string | null = null;
		let clipLocalPath: string | null = null;

		if (asset.url && !asset.url.startsWith("blob:")) {
			clipUrl = asset.url;
		} else if (asset.file) {
			onProgress({ step: `Uploading video${label}...`, percent: 5 });
			const uploaded = await uploadFileToBackend(asset.file);
			clipUrl = uploaded.clipUrl ?? null;
			clipLocalPath = uploaded.clipLocalPath ?? null;
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
				tracking_mode: options.contentType === "gaming" ? "x_only" : options.trackingMode,
				content_type: options.contentType ?? "auto",
				detection_engine: "yolo",
			}),
		});

		if (!startRes.ok) {
			throw new Error(`Reframe start failed: ${startRes.status}`);
		}

		const { reframe_job_id } = await startRes.json();

		// Poll for completion
		const { keyframes, scene_cuts, src_w, src_h, fps, debugVideoUrl, processedVideoUrl } = await pollReframeJob(
			reframe_job_id,
			(step, percent) => {
				onProgress({ step: step + label, percent });
			},
		);

		// Gaming mode: backend produced a fully composed 1080x1920 video — replace asset
		if (processedVideoUrl) {
			onProgress({ step: `Importing split-screen video${label}...`, percent: 95 });
			await replaceVideoWithGamingOutput(editor, trackId, element, processedVideoUrl);
			results.push({ elementId: element.id, keyframeCount: 0, reframeJobId: reframe_job_id });
			continue;
		}

		onProgress({ step: `Applying reframe${label}...`, percent: 97 });

		// Podcast mode: apply keyframes/splits to existing timeline element
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
): Promise<{ keyframes: ReframeKeyframe[]; scene_cuts: number[]; src_w: number; src_h: number; fps: number; debugVideoUrl?: string; processedVideoUrl?: string }> {
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
			if (!data.keyframes && !data.processed_video_url) throw new Error("Reframe succeeded but no keyframes or processed video URL returned");
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
				keyframes: (data.keyframes ?? []) as ReframeKeyframe[],
				scene_cuts: (data.scene_cuts ?? []) as number[],
				src_w: data.src_w as number,
				src_h: data.src_h as number,
				fps: (data.fps as number) ?? 30,
				debugVideoUrl,
				processedVideoUrl: (data.processed_video_url as string) ?? undefined,
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

	// Frame tolerance for matching hold keyframes to segment boundaries.
	const FRAME_TOLERANCE = 1.5 / videoFps;

	// For each segment, find the "anchor" HOLD keyframe that defines its crop position.
	// Segment 0  → earliest keyframe overall.
	// Segment s>0 → the hold keyframe AT validCuts[s-1] (new-shot position),
	//               NOT the "before-cut" hold which is 1 frame earlier.
	// Only searches HOLD keyframes to avoid confusing the old shot's final linear kf
	// (which is also at cut_time) with the new shot's starting position.
	const getAnchorKeyframe = (s: number): ReframeKeyframe | null => {
		if (s === 0) return sortedAllKeyframes[0] ?? null;
		const cutTime = validCuts[s - 1];
		const holdCandidates = sortedAllKeyframes.filter(
			(kf) => kf.interpolation === "hold" && Math.abs(kf.time_s - cutTime) < FRAME_TOLERANCE,
		);
		if (holdCandidates.length === 0) return null;
		// Among hold candidates near the cut, take the latest time_s = the "at-cut" hold (new shot)
		return holdCandidates[holdCandidates.length - 1];
	};

	for (let s = 0; s < boundaries.length - 1; s++) {
		const segStart = boundaries[s];
		const segEnd = boundaries[s + 1];

		// Linear panning keyframes within this segment's video time range.
		// For s > 0: use STRICT inequality at start (kf.time_s > segStart) to prevent
		// the previous segment's final keyframe (which sits AT cut_time = segStart) from
		// leaking into this segment and giving it the wrong starting crop position.
		// For s == 0: use a 0.5-frame tolerance to safely capture the t=0 keyframe.
		const segLinearKfs = linearKeyframes.filter(
			(kf) => (s === 0 ? kf.time_s >= segStart - 0.5 / videoFps : kf.time_s > segStart)
				&& kf.time_s <= segEnd + FRAME_TOLERANCE,
		);

		// Build this segment's keyframe list:
		// For s > 0: always prepend the anchor (HOLD kf at the cut boundary) so that:
		//   - Static segments get the correct new-shot position (no linear kfs).
		//   - Panning/tracking segments get the correct starting position (t=0 = anchor)
		//     followed by the within-shot linear kfs that define the animation.
		// For s == 0: use linear kfs directly; fall back to anchor only if empty.
		let segKfs: ReframeKeyframe[];
		if (s === 0) {
			if (segLinearKfs.length > 0) {
				segKfs = segLinearKfs;
			} else {
				const anchor = getAnchorKeyframe(0);
				segKfs = anchor ? [anchor] : [];
			}
		} else {
			const anchor = getAnchorKeyframe(s);
			// Prepend anchor to give the segment its correct starting crop position.
			// Even for panning segments, the anchor defines t=0; linear kfs animate from there.
			segKfs = anchor ? [anchor, ...segLinearKfs] : segLinearKfs;
		}

		segments.push({
			startVideoTime: segStart,
			endVideoTime: segEnd,
			keyframes: segKfs,
		});
	}

	console.log(`[Reframe] ${segments.length} segments created from ${validCuts.length} scene cuts`);

	// ── Step 4: Clear old animations on the original element ──
	// Must happen BEFORE any splits so splitAnimationsAtTime distributes nothing
	// to child segments. Also sets coverMode + scale inherited by all children.
	editor.timeline.updateElements({
		updates: [{ trackId, elementId: element.id, updates: { coverMode: true, animations: { channels: {} }, transform: { ...element.transform, scale: transformScale } } }],
	});

	// ── Step 5: If no scene cuts, apply directly to original element ──
	if (validCuts.length === 0) {
		// Re-fetch element state after the updateElements call above
		const track0 = editor.timeline.getTrackById({ trackId });
		const el0 = track0?.elements.find((e) => e.id === element.id) as VideoElement | undefined;
		if (el0) {
			applySegmentToElement(editor, trackId, element.id, el0, segments[0], trimStart, videoFps, canvasWidth, canvasHeight, scaledWidth, scaledHeight, containScale, transformScale);
		}
		return 1;
	}

	// ── Step 6: Split the element at each scene cut (in reverse order!) ──
	// We split from the last cut to the first to preserve element IDs and
	// timeline positions. Each split produces a right-side element.
	//
	// splitTime is in TIMELINE time: element.startTime + (cutVideoTime - trimStart)

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

	// ── Step 7: Apply transforms to each segment ──
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

	// Set coverMode + scale. Animations were already cleared on the original element
	// before splitting, so splitAnimationsAtTime distributed nothing to this segment.
	editor.timeline.updateElements({
		updates: [{
			trackId,
			elementId,
			updates: {
				coverMode: true,
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

/**
 * Gaming mode result handler.
 *
 * The backend rendered a new 1080x1920 vstack video (webcam top + gameplay bottom).
 * We fetch it from R2, register it as a new media asset, then swap the original
 * timeline element to point to the new asset with identity transforms.
 */
async function replaceVideoWithGamingOutput(
	editor: EditorCore,
	trackId: string,
	element: VideoElement,
	processedVideoUrl: string,
): Promise<void> {
	// 1. Fetch the processed video from R2 (public URL)
	const response = await fetch(processedVideoUrl);
	if (!response.ok) throw new Error(`Failed to fetch gaming reframe video: ${response.status}`);
	const blob = await response.blob();
	const file = new File([blob], "gaming_reframe.mp4", { type: "video/mp4" });

	// 2. Extract metadata (duration, dimensions) via processMediaAssets
	const processed = await processMediaAssets({ files: [file] });
	if (processed.length === 0) throw new Error("Failed to process gaming reframe video");
	const assetData = processed[0];

	// 3. Register as a new media asset — capture the ID by diffing before/after
	const projectId = editor.project.getActiveOrNull()?.metadata.id ?? "";
	const idsBefore = new Set(editor.media.getAssets().map((a) => a.id));

	await editor.media.addMediaAsset({ projectId, asset: assetData });

	const newAsset = editor.media.getAssets().find((a) => !idsBefore.has(a.id));
	if (!newAsset) throw new Error("Gaming reframe asset was not registered in media manager");

	// 4. Swap the original timeline element to the new asset, reset all transforms
	editor.timeline.updateElements({
		updates: [{
			trackId,
			elementId: element.id,
			updates: {
				mediaId: newAsset.id,
				coverMode: false,
				animations: { channels: {} },
				transform: {
					position: { x: 0, y: 0 },
					scale: 1,
					rotate: element.transform.rotate,
				},
			},
		}],
	});

	// 5. Set canvas to 9:16 — gaming output is always 1080x1920
	const canvasSize = ASPECT_RATIO_CANVAS["9:16"];
	await editor.project.updateSettings({ settings: { canvasSize } });
}

async function uploadFileToBackend(file: File): Promise<{ clipUrl?: string; clipLocalPath?: string }> {
	const formData = new FormData();
	formData.append("file", file);

	const uploadToken = await getAuthToken();
	const directApi = process.env.NEXT_PUBLIC_PROGNOT_API_URL ?? "";
	const res = await fetch(`${directApi}/reframe/upload`, {
		method: "POST",
		body: formData,
		headers: uploadToken ? { Authorization: `Bearer ${uploadToken}` } : {},
	});

	if (!res.ok) {
		throw new Error(`Video upload failed: ${res.status}`);
	}

	const data = await res.json();
	// MODAL_ENABLED=true → backend uploads to R2 and returns clip_url
	// MODAL_ENABLED=false → backend saves locally and returns local_path
	if (data.clip_url) {
		return { clipUrl: data.clip_url as string };
	}
	return { clipLocalPath: data.local_path as string };
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
