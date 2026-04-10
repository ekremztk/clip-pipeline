"use client";

import { useEffect } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
	CAPTION_TEMPLATES,
	detectActiveTemplateId,
	type CaptionTemplate,
} from "@/constants/caption-templates";
import { DEFAULT_TRANSFORM } from "@/constants/timeline-constants";
import type { TextElement, TextTrack, TimelineTrack } from "@/types/timeline";
import type { AnimationPropertyPath } from "@/types/animation";
import { useEditor } from "@/hooks/use-editor";
import { cn } from "@/utils/ui";

// ── Font preloading ───────────────────────────────────────────────────────────

const TEMPLATE_FONTS = [
	"Montserrat:wght@700",
	"Anton",
	"Poppins:wght@700",
	"Bebas+Neue",
	"Oswald:wght@400;700",
];

function injectGoogleFont(family: string): void {
	const id = `gf-cap-${family.replace(/[^a-zA-Z0-9]/g, "-")}`;
	if (document.getElementById(id)) return;
	const link = document.createElement("link");
	link.id = id;
	link.rel = "stylesheet";
	link.href = `https://fonts.googleapis.com/css2?family=${family}&display=swap`;
	document.head.appendChild(link);
}


// ── Template preview card ─────────────────────────────────────────────────────

function TemplateCard({
	template,
	isActive,
	onClick,
}: {
	template: CaptionTemplate;
	isActive: boolean;
	onClick: () => void;
}) {
	// Scale preview font size relative to template's fontSize
	const previewFontSize = `${3 + template.fontSize * 1.1}px`;

	const textStyle: React.CSSProperties = {
		fontFamily: `"${template.fontFamily}", sans-serif`,
		fontWeight: template.fontWeight === "bold" ? 700 : 400,
		fontStyle: template.fontStyle,
		color: template.color,
		textAlign: template.textAlign,
		fontSize: previewFontSize,
		letterSpacing: template.letterSpacing !== 0 ? `${template.letterSpacing * 0.05}px` : undefined,
		lineHeight: template.lineHeight,
		textTransform: template.textTransform === "uppercase" ? "uppercase" : undefined,
		WebkitTextStroke: template.stroke.enabled
			? `${Math.max(0.4, template.stroke.width * 0.07)}px ${template.stroke.color}`
			: undefined,
		textShadow: template.shadow.enabled
			? `${template.shadow.offsetX * 0.06}px ${template.shadow.offsetY * 0.06}px ${template.shadow.blur * 0.08}px ${template.shadow.color}`
			: undefined,
		backgroundColor: template.background.enabled ? template.background.color : undefined,
		borderRadius: template.background.enabled
			? `${(template.background.cornerRadius ?? 0) * 0.06}px`
			: undefined,
		padding: template.background.enabled
			? `${(template.background.paddingY ?? 0) * 0.02}px ${(template.background.paddingX ?? 0) * 0.015}px`
			: undefined,
		display: "block",
		width: template.id === "cinematic" ? "calc(100% + 4px)" : undefined,
		whiteSpace: template.id === "cinematic" ? "nowrap" : undefined,
	};

	const hasAnim = template.animationStyle !== "none";
	const animLabel = template.animationStyle === "pop" ? "pop" : template.animationStyle === "karaoke" ? "karaoke" : null;

	// Preview text at correct vertical position based on template y
	// y=550 → ~80% from top on 9:16, y=700 → ~90%, y=SAFE_POS → ~78%
	const topPct = template.id === "cinematic" ? "85%" : "76%";

	return (
		<div className="flex flex-col gap-1">
			<button
				type="button"
				onClick={onClick}
				className={cn(
					"relative w-full overflow-hidden rounded border bg-[#0d0d0d] transition-colors",
					"aspect-[9/16]",
					isActive
						? "border-white ring-1 ring-white/30"
						: "border-[#1a1a1a] hover:border-[#404040]",
				)}
			>
				{/* Simulated scene background */}
				<div className="absolute inset-0 bg-gradient-to-b from-[#1c1c1c] via-[#111] to-[#0a0a0a]" />

				{/* Person silhouette hint */}
				<div className="absolute inset-x-0 bottom-[25%] flex justify-center opacity-10">
					<div className="w-[30%] h-[45%] rounded-full bg-white/20" />
				</div>

				{/* Caption text at correct position */}
				<div
					className="absolute left-0 right-0 flex justify-center px-[3px]"
					style={{ top: topPct }}
				>
					<span style={textStyle}>
						{template.textTransform === "uppercase" ? "CAPTION" : "Caption"}
					</span>
				</div>

				{/* Animation badge */}
				{hasAnim && animLabel && (
					<span className="absolute right-1 top-1 rounded bg-white/10 px-[3px] py-[1px] text-[5px] font-medium uppercase leading-none text-white/70 border border-white/10">
						{animLabel}
					</span>
				)}
			</button>

			<span
				className={cn(
					"text-center text-[9px] leading-none truncate",
					isActive ? "text-white" : "text-[#737373]",
				)}
			>
				{template.name}
			</span>
		</div>
	);
}

// ── Main section ──────────────────────────────────────────────────────────────

export function CaptionTemplateSection({ track }: { track: TimelineTrack }) {
	const editor = useEditor();

	// Preload all template fonts so preview cards render with correct typefaces
	useEffect(() => {
		for (const family of TEMPLATE_FONTS) {
			injectGoogleFont(family);
		}
	}, []);

	const textTrack = track as TextTrack;
	const first = textTrack.elements[0] as TextElement | undefined;
	const activeId = first ? detectActiveTemplateId(first) : null;

	function applyTemplate(template: CaptionTemplate) {
		const elements = textTrack.elements as TextElement[];
		if (elements.length === 0) return;

		// 1. Remove any existing scale/opacity keyframes (cleanup from previous pop template)
		const kfsToRemove: Array<{
			trackId: string;
			elementId: string;
			propertyPath: AnimationPropertyPath;
			keyframeId: string;
		}> = [];
		for (const el of elements) {
			const scaleKfs = (el.animations?.channels?.["transform.scale"] as { keyframes?: { id: string }[] } | undefined)?.keyframes ?? [];
			const opacityKfs = (el.animations?.channels?.["opacity"] as { keyframes?: { id: string }[] } | undefined)?.keyframes ?? [];
			for (const kf of scaleKfs) kfsToRemove.push({ trackId: track.id, elementId: el.id, propertyPath: "transform.scale", keyframeId: kf.id });
			for (const kf of opacityKfs) kfsToRemove.push({ trackId: track.id, elementId: el.id, propertyPath: "opacity", keyframeId: kf.id });
		}
		if (kfsToRemove.length > 0) editor.timeline.removeKeyframes({ keyframes: kfsToRemove });

		// 2. Batch-update all caption elements with new style
		editor.timeline.updateElements({
			updates: elements.map((el) => ({
				trackId: track.id,
				elementId: el.id,
				updates: {
					fontSize: template.fontSize,
					fontFamily: template.fontFamily,
					fontWeight: template.fontWeight,
					fontStyle: template.fontStyle,
					color: template.color,
					textAlign: template.textAlign,
					letterSpacing: template.letterSpacing,
					lineHeight: template.lineHeight,
					background: template.background,
					stroke: template.stroke,
					shadow: template.shadow,
					textTransform: template.textTransform ?? "none",
					karaokeHighlightColor: template.karaokeHighlightColor,
					transform: {
						...DEFAULT_TRANSFORM,
						position: { ...template.position },
					},
				},
			})),
		});

		// 3. Add pop keyframes if this template uses pop animation
		// scale: 0.7 → 1.0 over 150ms  |  opacity: 0 → 1 over 150ms
		if (template.animationStyle === "pop") {
			const kfs: Array<{
				trackId: string;
				elementId: string;
				propertyPath: AnimationPropertyPath;
				time: number;
				value: number;
				interpolation: "linear";
			}> = [];
			for (const el of elements) {
				kfs.push({ trackId: track.id, elementId: el.id, propertyPath: "transform.scale", time: 0, value: 0.7, interpolation: "linear" });
				kfs.push({ trackId: track.id, elementId: el.id, propertyPath: "transform.scale", time: 0.15, value: 1.0, interpolation: "linear" });
				kfs.push({ trackId: track.id, elementId: el.id, propertyPath: "opacity", time: 0, value: 0, interpolation: "linear" });
				kfs.push({ trackId: track.id, elementId: el.id, propertyPath: "opacity", time: 0.15, value: 1.0, interpolation: "linear" });
			}
			editor.timeline.upsertKeyframes({ keyframes: kfs });
		}
	}

	return (
		<ScrollArea className="h-full scrollbar-hidden">
			<div className="p-3">
				<p className="mb-3 text-[10px] text-[#525252]">
					Optimised for 9:16. Select a style — fine-tune via Caption / Track tabs.
				</p>

				<div className="grid grid-cols-4 gap-2">
					{CAPTION_TEMPLATES.map((template) => (
						<TemplateCard
							key={template.id}
							template={template}
							isActive={activeId === template.id}
							onClick={() => applyTemplate(template)}
						/>
					))}
				</div>

				<p className="mt-3 text-[10px] text-[#525252]">
					<span className="text-[#737373]">pop</span> templates animate scale + opacity on each caption entry.
				</p>
			</div>
		</ScrollArea>
	);
}
