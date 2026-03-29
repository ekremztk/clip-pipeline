"use client";

import { useReframeMetadataStore } from "@/stores/reframe-metadata-store";
import { TIMELINE_CONSTANTS } from "@/constants/timeline-constants";

interface SceneCutMarkersProps {
	zoomLevel: number;
}

/**
 * Renders vertical scene-cut markers on the timeline ruler.
 * Markers are populated by the reframe engine after a job completes.
 * Each marker is a thin vertical line at the cut timestamp.
 */
export function SceneCutMarkers({ zoomLevel }: SceneCutMarkersProps) {
	const sceneCutMarkers = useReframeMetadataStore((s) => s.sceneCutMarkers);

	if (sceneCutMarkers.length === 0) return null;

	return (
		<>
			{sceneCutMarkers.map((time_s, i) => {
				const left = time_s * TIMELINE_CONSTANTS.PIXELS_PER_SECOND * zoomLevel;
				return (
					<div
						// biome-ignore lint/suspicious/noArrayIndexKey: stable ordered list
						key={i}
						className="pointer-events-none absolute top-0 z-10 h-full"
						style={{ left: `${left}px` }}
						title={`Scene cut at ${time_s.toFixed(2)}s`}
					>
						{/* Top diamond marker */}
						<div
							className="absolute -translate-x-1/2"
							style={{ top: "2px" }}
						>
							<div className="size-1.5 rotate-45 bg-orange-400" />
						</div>
						{/* Vertical line */}
						<div
							className="absolute -translate-x-px w-px bg-orange-400/50"
							style={{ top: "8px", bottom: 0 }}
						/>
					</div>
				);
			})}
		</>
	);
}
