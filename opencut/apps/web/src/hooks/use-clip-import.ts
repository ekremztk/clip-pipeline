"use client";

import { useEffect, useRef } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { toast } from "sonner";
import { useEditor } from "@/hooks/use-editor";
import { useYouTubeStore } from "@/stores/youtube-store";
import { useReframeMetadataStore } from "@/stores/reframe-metadata-store";
import type { PrecomputedReframe, CaptionWord } from "@/stores/reframe-metadata-store";
import { processMediaAssets } from "@/lib/media/processing";
import { createClient } from "@/lib/supabase/client";

/**
 * Reads ?clipUrl, ?clipTitle, ?clipDesc URL params.
 * On first load: imports the video as a media asset and pre-fills YouTube metadata.
 * After importing, removes the params from the URL so page refreshes don't re-import.
 * Must be called inside EditorProvider (project must be loaded).
 */
export function useClipImport(projectId: string) {
	const searchParams = useSearchParams();
	const router = useRouter();
	const pathname = usePathname();
	const editor = useEditor();
	const { loadForProject } = useYouTubeStore();
	const { setJobId, setClipId, setPrecomputedReframe, setCaptionWords, setSceneCutMarkers } = useReframeMetadataStore();
	const hasRun = useRef(false);

	const clipUrl = searchParams.get("clipUrl");
	const clipTitle = searchParams.get("clipTitle");
	const clipDesc = searchParams.get("clipDesc");
	const clipGuestName = searchParams.get("clipGuestName");
	const clipJobId = searchParams.get("clipJobId");
	const clipId = searchParams.get("clipId");

	useEffect(() => {
		// Always load YouTube metadata for this project (from localStorage or URL params)
		loadForProject(projectId, {
			title: clipTitle ?? "",
			description: clipDesc ?? "",
			guestName: clipGuestName ?? "",
		});

		// Store job_id for reframe diarization (if clip came from pipeline)
		if (clipJobId) {
			setJobId(clipJobId);
		}

		// If clip came from pipeline, fetch its reframe + caption metadata
		if (clipId) {
			setClipId(clipId);
			fetchClipMetadata(clipId, setPrecomputedReframe, setCaptionWords, setSceneCutMarkers);
		}

		if (!clipUrl || hasRun.current) return;
		hasRun.current = true;

		const importClip = async () => {
			try {
				const activeProject = editor.project.getActiveOrNull();
				if (!activeProject) return;

				toast.loading("Importing clip from Prognot...", { id: "clip-import" });

				// Proxy through backend to avoid R2 CORS restrictions
				const apiBase = process.env.NEXT_PUBLIC_PROGNOT_API_URL ?? "";
				const proxyUrl = apiBase
					? `${apiBase}/proxy/clip?url=${encodeURIComponent(clipUrl)}`
					: clipUrl;

				const supabase = createClient();
				const { data: sessionData } = await supabase.auth.getSession();
				const token = sessionData?.session?.access_token;

				const response = await fetch(proxyUrl, {
					headers: token ? { Authorization: `Bearer ${token}` } : {},
				});
				if (!response.ok) throw new Error(`Fetch failed: ${response.status}`);

				const blob = await response.blob();
				const rawName = clipUrl.split("/").pop()?.split("?")[0] ?? "clip.mp4";
				const filename = decodeURIComponent(rawName);
				const file = new File([blob], filename, { type: "video/mp4" });

				const dt = new DataTransfer();
				dt.items.add(file);

				const processedAssets = await processMediaAssets({
					files: dt.files,
					onProgress: () => {},
				});

				for (const asset of processedAssets) {
					await editor.media.addMediaAsset({
						projectId: activeProject.metadata.id,
						asset,
					});
				}

				toast.success("Clip imported! Find it in the Media panel.", { id: "clip-import" });

				// Remove clip params from URL so refreshing the page won't re-import
				const params = new URLSearchParams(searchParams.toString());
				params.delete("clipUrl");
				params.delete("clipTitle");
				params.delete("clipDesc");
				params.delete("clipGuestName");
				params.delete("clipJobId");
				params.delete("clipId");
				const newUrl = params.size > 0 ? `${pathname}?${params.toString()}` : pathname;
				router.replace(newUrl);
			} catch (error) {
				console.error("[ClipImport]", error);
				toast.error("Failed to import clip", { id: "clip-import" });
			}
		};

		importClip();
	// eslint-disable-next-line react-hooks/exhaustive-deps
	}, []);
}

/**
 * Fetches pipeline clip metadata from backend and populates the reframe metadata store.
 * Non-blocking — failures are silently ignored (metadata is a bonus, not required).
 */
async function fetchClipMetadata(
	clipId: string,
	setPrecomputedReframe: (data: PrecomputedReframe | null) => void,
	setCaptionWords: (words: CaptionWord[]) => void,
	setSceneCutMarkers: (markers: number[]) => void,
): Promise<void> {
	try {
		const supabase = createClient();
		const { data: sessionData } = await supabase.auth.getSession();
		const token = sessionData?.session?.access_token;

		const apiBase = process.env.NEXT_PUBLIC_PROGNOT_API_URL ?? "";
		const res = await fetch(`${apiBase}/clips/${clipId}`, {
			headers: token ? { Authorization: `Bearer ${token}` } : {},
		});

		if (!res.ok) {
			console.warn("[ClipImport] Failed to fetch clip metadata:", res.status);
			return;
		}

		const clip = await res.json();

		// Load pre-computed reframe data (from S09 podcast analysis)
		const meta = clip.reframe_metadata;
		if (meta && meta.keyframes && meta.keyframes.length > 0) {
			const precomputed: PrecomputedReframe = {
				keyframes: meta.keyframes,
				scene_cuts: meta.scene_cuts ?? [],
				src_w: meta.src_w ?? 0,
				src_h: meta.src_h ?? 0,
				fps: meta.fps ?? 30,
				duration_s: meta.duration_s ?? 0,
				crop_w: meta.crop_w ?? 0,
				crop_h: meta.crop_h ?? 0,
			};
			setPrecomputedReframe(precomputed);

			// Also pre-populate scene cut markers on the timeline
			if (meta.scene_cuts && meta.scene_cuts.length > 0) {
				setSceneCutMarkers(meta.scene_cuts);
			}

			console.log(
				`[ClipImport] Loaded pre-computed reframe: ${precomputed.keyframes.length} keyframes, ` +
				`${precomputed.scene_cuts.length} scene cuts`,
			);
		}

		// Load pre-computed caption words (from S10)
		const captionMeta = clip.caption_metadata;
		if (captionMeta && captionMeta.words && captionMeta.words.length > 0) {
			setCaptionWords(captionMeta.words as CaptionWord[]);
			console.log(`[ClipImport] Loaded ${captionMeta.words.length} caption words from pipeline`);
		}
	} catch (err) {
		// Non-critical — editor still works without pre-computed metadata
		console.warn("[ClipImport] Could not load clip metadata:", err);
	}
}
