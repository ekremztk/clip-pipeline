import { create } from "zustand";

/**
 * Stores metadata passed from the Prognot dashboard when opening a clip
 * in the editor. Used by the reframe engine to fetch diarization data
 * and to display scene cut markers on the timeline.
 */

export interface PrecomputedReframe {
	keyframes: Array<{ time_s: number; offset_x: number; offset_y: number; interpolation: string }>;
	scene_cuts: number[];
	src_w: number;
	src_h: number;
	fps: number;
	duration_s: number;
	crop_w: number;
	crop_h: number;
}

export interface CaptionWord {
	word: string;
	punctuated_word: string;
	start: number;
	end: number;
	confidence: number;
}

interface ReframeMetadataStore {
	/** Pipeline job_id — used for diarization lookup during reframe */
	jobId: string | null;
	setJobId: (id: string | null) => void;

	/** Clip ID from the pipeline — used for reframe_metadata bridge endpoint */
	clipId: string | null;
	setClipId: (id: string | null) => void;

	/** Scene cut timestamps (seconds) from the last completed reframe job */
	sceneCutMarkers: number[];
	setSceneCutMarkers: (markers: number[]) => void;

	/**
	 * Pre-computed reframe data from the pipeline (S09).
	 * When set, the reframe engine can skip backend analysis and apply directly.
	 */
	precomputedReframe: PrecomputedReframe | null;
	setPrecomputedReframe: (data: PrecomputedReframe | null) => void;

	/**
	 * Pre-computed caption words from the pipeline (S10).
	 * When set, the editor can add these as timeline text elements without re-transcribing.
	 */
	captionWords: CaptionWord[];
	setCaptionWords: (words: CaptionWord[]) => void;
}

export const useReframeMetadataStore = create<ReframeMetadataStore>((set) => ({
	jobId: null,
	setJobId: (id) => set({ jobId: id }),

	clipId: null,
	setClipId: (id) => set({ clipId: id }),

	sceneCutMarkers: [],
	setSceneCutMarkers: (markers) => set({ sceneCutMarkers: markers }),

	precomputedReframe: null,
	setPrecomputedReframe: (data) => set({ precomputedReframe: data }),

	captionWords: [],
	setCaptionWords: (words) => set({ captionWords: words }),
}));
