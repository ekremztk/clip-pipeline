import type { TextBackground, TextStroke, TextShadow } from "@/types/timeline";

export type CaptionAnimationStyle = "none" | "pop" | "karaoke";

export interface CaptionTemplate {
	id: string;
	name: string;
	/** Used as identifier when stored in channel_dna for pipeline (S10) */
	pipelineKey: string;
	animationStyle: CaptionAnimationStyle;
	maxWidth: number;
	fontSize: number;
	fontFamily: string;
	fontWeight: "normal" | "bold";
	fontStyle: "normal" | "italic";
	color: string;
	textAlign: "left" | "center" | "right";
	letterSpacing: number;
	lineHeight: number;
	background: TextBackground;
	stroke: TextStroke;
	shadow: TextShadow;
	textTransform?: "none" | "uppercase" | "capitalize" | "lowercase";
	/** When set, enables karaoke mode: active word shown in this color, others in `color` */
	karaokeHighlightColor?: string;
	position: { x: number; y: number };
}

// ── Shared bases ──────────────────────────────────────────────────────────────

const NO_BG: TextBackground = {
	enabled: false,
	color: "#000000",
	cornerRadius: 0,
	paddingX: 30,
	paddingY: 42,
	offsetX: 0,
	offsetY: 0,
};

const NO_STROKE: TextStroke = {
	enabled: false,
	color: "#000000",
	width: 4,
	outsideOnly: true,
};

const NO_SHADOW: TextShadow = {
	enabled: false,
	color: "#000000",
	offsetX: 3,
	offsetY: 3,
	blur: 6,
	opacity: 0.8,
};

/** Default safe position: y=150 (slightly below center, safe zone) */
const DEFAULT_POS = { x: 0, y: 150 };

// ── Templates ─────────────────────────────────────────────────────────────────

export const CAPTION_TEMPLATES: CaptionTemplate[] = [
	// 1 — Clean Standard  (Montserrat, Tt, white + 8px black stroke)
	{
		id: "clean",
		name: "Clean",
		pipelineKey: "clean",
		animationStyle: "none",
		maxWidth: 900,
		fontSize: 4,
		fontFamily: "Montserrat",
		fontWeight: "bold",
		fontStyle: "normal",
		color: "#ffffff",
		textAlign: "center",
		letterSpacing: 0,
		lineHeight: 1,
		background: NO_BG,
		stroke: { enabled: true, color: "#000000", width: 8, outsideOnly: true },
		shadow: NO_SHADOW,
		textTransform: "capitalize",
		position: DEFAULT_POS,
	},

	// 2 — Hormozi  (Montserrat, TT uppercase, karaoke: active word = yellow, others = white)
	{
		id: "hormozi",
		name: "Hormozi",
		pipelineKey: "hormozi",
		animationStyle: "karaoke",
		maxWidth: 900,
		fontSize: 4,
		fontFamily: "Montserrat",
		fontWeight: "bold",
		fontStyle: "normal",
		color: "#ffffff",
		textAlign: "center",
		letterSpacing: 1,
		lineHeight: 1,
		background: NO_BG,
		stroke: { enabled: true, color: "#000000", width: 8, outsideOnly: true },
		shadow: NO_SHADOW,
		textTransform: "uppercase",
		karaokeHighlightColor: "#FFE500",
		position: DEFAULT_POS,
	},

	// 3 — Outline  (Montserrat, white, 6px outline, POP animation)
	{
		id: "outline",
		name: "Outline",
		pipelineKey: "outline",
		animationStyle: "pop",
		maxWidth: 900,
		fontSize: 5,
		fontFamily: "Montserrat",
		fontWeight: "bold",
		fontStyle: "normal",
		color: "#ffffff",
		textAlign: "center",
		letterSpacing: 0,
		lineHeight: 1,
		background: NO_BG,
		stroke: { enabled: true, color: "#000000", width: 6, outsideOnly: true },
		shadow: NO_SHADOW,
		position: DEFAULT_POS,
	},

	// 4 — Pill  (Poppins, white, semi-transparent dark pill bg, w=200 h=100)
	{
		id: "pill",
		name: "Pill",
		pipelineKey: "pill",
		animationStyle: "none",
		maxWidth: 900,
		fontSize: 4,
		fontFamily: "Poppins",
		fontWeight: "bold",
		fontStyle: "normal",
		color: "#ffffff",
		textAlign: "center",
		letterSpacing: 0,
		lineHeight: 1,
		background: {
			enabled: true,
			color: "#000000",
			cornerRadius: 50,
			paddingX: 200,
			paddingY: 100,
			offsetX: 0,
			offsetY: 0,
			opacity: 50,
		},
		stroke: NO_STROKE,
		shadow: NO_SHADOW,
		position: DEFAULT_POS,
	},

	// 5 — Neon  (Bebas Neue, cyan glow)
	{
		id: "neon",
		name: "Neon",
		pipelineKey: "neon",
		animationStyle: "none",
		maxWidth: 900,
		fontSize: 6,
		fontFamily: "Bebas Neue",
		fontWeight: "normal",
		fontStyle: "normal",
		color: "#ffffff",
		textAlign: "center",
		letterSpacing: 2,
		lineHeight: 1,
		background: NO_BG,
		stroke: NO_STROKE,
		shadow: {
			enabled: true,
			color: "#00e5ff",
			offsetX: 0,
			offsetY: 0,
			blur: 24,
			opacity: 1,
		},
		position: DEFAULT_POS,
	},

	// 6 — Cinema  (Oswald, dark full-width bar, very bottom)
	{
		id: "cinematic",
		name: "Cinema",
		pipelineKey: "cinematic",
		animationStyle: "none",
		maxWidth: 1080,
		fontSize: 4,
		fontFamily: "Oswald",
		fontWeight: "normal",
		fontStyle: "normal",
		color: "#ffffff",
		textAlign: "center",
		letterSpacing: 1,
		lineHeight: 1,
		background: {
			enabled: true,
			color: "#000000",
			cornerRadius: 0,
			paddingX: 500,
			paddingY: 18,
			offsetX: 0,
			offsetY: 0,
		},
		stroke: NO_STROKE,
		shadow: NO_SHADOW,
		position: { x: 0, y: 400 },
	},

	// 7 — Bold Pop  (Montserrat, white, stroke + hard shadow)
	{
		id: "bold_pop",
		name: "Bold Pop",
		pipelineKey: "bold_pop",
		animationStyle: "none",
		maxWidth: 900,
		fontSize: 6,
		fontFamily: "Montserrat",
		fontWeight: "bold",
		fontStyle: "normal",
		color: "#ffffff",
		textAlign: "center",
		letterSpacing: 0,
		lineHeight: 1,
		background: NO_BG,
		stroke: { enabled: true, color: "#000000", width: 4, outsideOnly: true },
		shadow: {
			enabled: true,
			color: "#000000",
			offsetX: 4,
			offsetY: 4,
			blur: 0,
			opacity: 1,
		},
		position: DEFAULT_POS,
	},

	// 8 — Fire  (Oswald Bold, orange, red glow)
	{
		id: "fire",
		name: "Fire",
		pipelineKey: "fire",
		animationStyle: "none",
		maxWidth: 900,
		fontSize: 5,
		fontFamily: "Oswald",
		fontWeight: "bold",
		fontStyle: "normal",
		color: "#FF6B35",
		textAlign: "center",
		letterSpacing: 1,
		lineHeight: 1,
		background: NO_BG,
		stroke: { enabled: true, color: "#000000", width: 5, outsideOnly: true },
		shadow: {
			enabled: true,
			color: "#ff0000",
			offsetX: 0,
			offsetY: 0,
			blur: 12,
			opacity: 0.5,
		},
		position: DEFAULT_POS,
	},
];

export const DEFAULT_CAPTION_TEMPLATE = CAPTION_TEMPLATES[0];

// ── Helpers ───────────────────────────────────────────────────────────────────

export function detectActiveTemplateId(element: {
	fontSize: number;
	color: string;
	fontFamily?: string;
	letterSpacing?: number;
	textTransform?: string;
	stroke?: { enabled: boolean; color: string; width: number };
	shadow?: { enabled: boolean; color: string };
	background?: { enabled: boolean; cornerRadius?: number };
	karaokeHighlightColor?: string;
}): string | null {
	for (const t of CAPTION_TEMPLATES) {
		const fontMatch = !element.fontFamily || element.fontFamily === t.fontFamily;
		const strokeMatch =
			(element.stroke?.enabled ?? false) === t.stroke.enabled &&
			(!t.stroke.enabled || element.stroke?.color === t.stroke.color);
		const shadowMatch =
			(element.shadow?.enabled ?? false) === t.shadow.enabled &&
			(!t.shadow.enabled || element.shadow?.color === t.shadow.color);
		const bgMatch = (element.background?.enabled ?? false) === t.background.enabled;
		const colorMatch = element.color === t.color;
		const sizeMatch = element.fontSize === t.fontSize;
		const letterSpacingMatch = (element.letterSpacing ?? 0) === (t.letterSpacing ?? 0);
		const textTransformMatch = (element.textTransform ?? "none") === (t.textTransform ?? "none");
		const karaokeMatch = (element.karaokeHighlightColor ?? "") === (t.karaokeHighlightColor ?? "");

		if (fontMatch && strokeMatch && shadowMatch && bgMatch && colorMatch && sizeMatch && letterSpacingMatch && textTransformMatch && karaokeMatch) {
			return t.id;
		}
	}
	return null;
}
