/**
 * Reframe V2 — Frontend Tipleri
 * Backend ReframeResult ve keyframe yapısını yansıtır.
 */

export interface ReframeKeyframe {
	time_s: number;
	offset_x: number;
	offset_y: number;              // V2 YENİ — dynamic_xy modda Y offset (x_only = 0.0)
	interpolation: "linear" | "hold";
}

export type ReframeStrategy = "podcast" | "single" | "gaming" | "generic";
export type ReframeAspectRatio = "9:16" | "1:1" | "4:5" | "16:9";
export type ReframeTrackingMode = "x_only" | "dynamic_xy";
export type ReframeContentType = "auto" | "podcast" | "single" | "gaming" | "generic";

export interface ReframeOptions {
	strategy: ReframeStrategy;
	aspectRatio: ReframeAspectRatio;
	trackingMode: ReframeTrackingMode;
	contentType: ReframeContentType;  // V2 YENİ — "auto" = backend otomatik tespit
}

/** Her hedef aspect ratio için canvas boyutu (piksel). */
export const ASPECT_RATIO_CANVAS: Record<ReframeAspectRatio, { width: number; height: number }> = {
	"9:16": { width: 1080, height: 1920 },
	"1:1": { width: 1080, height: 1080 },
	"4:5": { width: 1080, height: 1350 },
	"16:9": { width: 1920, height: 1080 },
};
