/**
 * Shared types for the frontend reframe system.
 * These mirror the backend ReframeResult / backend keyframe shape.
 */

export interface ReframeKeyframe {
	time_s: number;
	offset_x: number;
	interpolation: "linear" | "hold";
}

export type ReframeStrategy = "podcast";
export type ReframeAspectRatio = "9:16" | "1:1" | "4:5" | "16:9";
export type ReframeTrackingMode = "x_only" | "dynamic_xy";

export interface ReframeOptions {
	strategy: ReframeStrategy;
	aspectRatio: ReframeAspectRatio;
	trackingMode: ReframeTrackingMode;
}

/** Canvas size in pixels for each target aspect ratio (portrait/square at 1080px width). */
export const ASPECT_RATIO_CANVAS: Record<ReframeAspectRatio, { width: number; height: number }> = {
	"9:16": { width: 1080, height: 1920 },
	"1:1": { width: 1080, height: 1080 },
	"4:5": { width: 1080, height: 1350 },
	"16:9": { width: 1920, height: 1080 },
};
