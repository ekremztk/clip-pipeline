import { create } from "zustand";

/**
 * Stores metadata passed from the Prognot dashboard when opening a clip
 * in the editor. Used by the reframe engine to fetch diarization data
 * and to display scene cut markers on the timeline.
 */
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
}

export const useReframeMetadataStore = create<ReframeMetadataStore>((set) => ({
	jobId: null,
	setJobId: (id) => set({ jobId: id }),

	clipId: null,
	setClipId: (id) => set({ clipId: id }),

	sceneCutMarkers: [],
	setSceneCutMarkers: (markers) => set({ sceneCutMarkers: markers }),
}));
