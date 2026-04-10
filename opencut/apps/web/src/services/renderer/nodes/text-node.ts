import type { CanvasRenderer } from "../canvas-renderer";
import { createOffscreenCanvas } from "../canvas-utils";
import { BaseNode } from "./base-node";
import type { TextElement, KaraokeWord } from "@/types/timeline";
import {
	DEFAULT_TEXT_BACKGROUND,
	DEFAULT_TEXT_ELEMENT,
	DEFAULT_LINE_HEIGHT,
	FONT_SIZE_SCALE_REFERENCE,
	CORNER_RADIUS_MAX,
	CORNER_RADIUS_MIN,
} from "@/constants/text-constants";
import {
	getMetricAscent,
	getMetricDescent,
	getTextBackgroundRect,
	measureTextBlock,
} from "@/lib/text/layout";
import {
	getElementLocalTime,
	resolveColorAtTime,
	resolveNumberAtTime,
	resolveOpacityAtTime,
	resolveTransformAtTime,
} from "@/lib/animation";
import { resolveEffectParamsAtTime } from "@/lib/animation/effect-param-channel";
import { getEffect } from "@/lib/effects";
import { webglEffectRenderer } from "../webgl-effect-renderer";
import { clamp } from "@/utils/math";

function scaleFontSize({
	fontSize,
	canvasHeight,
}: {
	fontSize: number;
	canvasHeight: number;
}): number {
	return fontSize * (canvasHeight / FONT_SIZE_SCALE_REFERENCE);
}

function quoteFontFamily({ fontFamily }: { fontFamily: string }): string {
	return `"${fontFamily.replace(/"/g, '\\"')}"`;
}

const TEXT_DECORATION_THICKNESS_RATIO = 0.07;
const STRIKETHROUGH_VERTICAL_RATIO = 0.35;

function drawTextDecoration({
	ctx,
	textDecoration,
	lineWidth,
	lineY,
	metrics,
	scaledFontSize,
	textAlign,
}: {
	ctx: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;
	textDecoration: string;
	lineWidth: number;
	lineY: number;
	metrics: TextMetrics;
	scaledFontSize: number;
	textAlign: CanvasTextAlign;
}): void {
	if (textDecoration === "none" || !textDecoration) return;

	const thickness = Math.max(1, scaledFontSize * TEXT_DECORATION_THICKNESS_RATIO);
	const ascent = getMetricAscent({ metrics, fallbackFontSize: scaledFontSize });
	const descent = getMetricDescent({ metrics, fallbackFontSize: scaledFontSize });

	let xStart = -lineWidth / 2;
	if (textAlign === "left") xStart = 0;
	if (textAlign === "right") xStart = -lineWidth;

	if (textDecoration === "underline") {
		const underlineY = lineY + descent + thickness;
		ctx.fillRect(xStart, underlineY, lineWidth, thickness);
	}

	if (textDecoration === "line-through") {
		const strikeY = lineY - (ascent - descent) * STRIKETHROUGH_VERTICAL_RATIO;
		ctx.fillRect(xStart, strikeY, lineWidth, thickness);
	}
}

// ── Karaoke per-word rendering ────────────────────────────────────────────────

function applyTextTransformToWord(word: string, tt: string | undefined): string {
	if (tt === "uppercase") return word.toUpperCase();
	if (tt === "lowercase") return word.toLowerCase();
	if (tt === "capitalize") return word.replace(/^\w/, (c) => c.toUpperCase());
	return word;
}

function drawKaraokeLine({
	ctx,
	karaokeWords,
	lineY,
	localTime,
	baseColor,
	highlightColor,
	textTransform,
	textAlign,
	stroke,
	applyShadow,
	clearShadow,
}: {
	ctx: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;
	karaokeWords: KaraokeWord[];
	lineY: number;
	localTime: number;
	baseColor: string;
	highlightColor: string;
	textTransform: string | undefined;
	textAlign: CanvasTextAlign;
	stroke: TextElement["stroke"];
	applyShadow: () => void;
	clearShadow: () => void;
}) {
	if (karaokeWords.length === 0) return;

	// Measure words (ctx.font and ctx.letterSpacing must already be set)
	const savedAlign = ctx.textAlign;
	ctx.textAlign = "left";
	const spaceWidth = ctx.measureText(" ").width;
	const displayWords = karaokeWords.map((kw) => applyTextTransformToWord(kw.word, textTransform));
	const wordWidths = displayWords.map((w) => ctx.measureText(w).width);
	const totalWidth =
		wordWidths.reduce((sum, w) => sum + w, 0) +
		spaceWidth * Math.max(0, karaokeWords.length - 1);

	let startX: number;
	if (savedAlign === "center") startX = -totalWidth / 2;
	else if (savedAlign === "right") startX = -totalWidth;
	else startX = 0;

	let x = startX;
	for (let i = 0; i < karaokeWords.length; i++) {
		const kw = karaokeWords[i];
		const isActive = localTime >= kw.startTime && localTime < kw.endTime;
		const wordColor = isActive ? highlightColor : baseColor;
		const displayWord = displayWords[i];

		ctx.fillStyle = wordColor;

		if (stroke?.enabled && stroke.width > 0) {
			ctx.strokeStyle = stroke.color;
			ctx.lineWidth = stroke.outsideOnly ? stroke.width * 2 : stroke.width;
			ctx.lineJoin = "round";
			applyShadow();
			ctx.strokeText(displayWord, x, lineY);
			clearShadow();
			ctx.fillText(displayWord, x, lineY);
		} else {
			applyShadow();
			ctx.fillText(displayWord, x, lineY);
			clearShadow();
		}

		x += wordWidths[i] + (i < karaokeWords.length - 1 ? spaceWidth : 0);
	}

	ctx.textAlign = savedAlign;
}

export type TextNodeParams = TextElement & {
	canvasCenter: { x: number; y: number };
	canvasHeight: number;
	textBaseline?: CanvasTextBaseline;
};

export class TextNode extends BaseNode<TextNodeParams> {
	isInRange({ time }: { time: number }) {
		return (
			time >= this.params.startTime &&
			time < this.params.startTime + this.params.duration
		);
	}

	async render({ renderer, time }: { renderer: CanvasRenderer; time: number }) {
		if (!this.isInRange({ time })) {
			return;
		}

		const localTime = getElementLocalTime({
			timelineTime: time,
			elementStartTime: this.params.startTime,
			elementDuration: this.params.duration,
		});
		const transform = resolveTransformAtTime({
			baseTransform: this.params.transform,
			animations: this.params.animations,
			localTime,
		});
		const opacity = resolveOpacityAtTime({
			baseOpacity: this.params.opacity,
			animations: this.params.animations,
			localTime,
		});

		const x = transform.position.x + this.params.canvasCenter.x;
		const y = transform.position.y + this.params.canvasCenter.y;

		const fontWeight = this.params.fontWeight === "bold" ? "bold" : "normal";
		const fontStyle = this.params.fontStyle === "italic" ? "italic" : "normal";
		const scaledFontSize = scaleFontSize({
			fontSize: this.params.fontSize,
			canvasHeight: this.params.canvasHeight,
		});
		const fontFamily = quoteFontFamily({ fontFamily: this.params.fontFamily });
		const fontString = `${fontStyle} ${fontWeight} ${scaledFontSize}px ${fontFamily}, sans-serif`;
		const letterSpacing = this.params.letterSpacing ?? 0;
		const lineHeight = this.params.lineHeight ?? DEFAULT_LINE_HEIGHT;
		const rawContent = this.params.content;
		const tt = this.params.textTransform;
		const transformedContent =
			tt === "uppercase" ? rawContent.toUpperCase() :
			tt === "lowercase" ? rawContent.toLowerCase() :
			tt === "capitalize" ? rawContent.replace(/(^|[\s\-])\w/g, (c) => c.toUpperCase()) :
			rawContent;
		const lines = transformedContent.split("\n");
		const lineHeightPx = scaledFontSize * lineHeight;
		const fontSizeRatio = this.params.fontSize / DEFAULT_TEXT_ELEMENT.fontSize;
		const baseline = this.params.textBaseline ?? "middle";
		const blendMode = (
			this.params.blendMode && this.params.blendMode !== "normal"
				? this.params.blendMode
				: "source-over"
		) as GlobalCompositeOperation;

	renderer.context.save();
		renderer.context.font = fontString;
		renderer.context.textBaseline = baseline;
		if ("letterSpacing" in renderer.context) {
			(renderer.context as CanvasRenderingContext2D & { letterSpacing: string }).letterSpacing = `${letterSpacing}px`;
		}
		const lineMetrics = lines.map((line) => renderer.context.measureText(line));
		renderer.context.restore();

		const lineCount = lines.length;
		const block = measureTextBlock({ lineMetrics, lineHeightPx, fallbackFontSize: scaledFontSize });

	const textColor = resolveColorAtTime({
			baseColor: this.params.color,
			animations: this.params.animations,
			propertyPath: "color",
			localTime,
		});
		const bg = this.params.background;
		const resolvedBackground = {
			...bg,
			color: resolveColorAtTime({
				baseColor: bg.color,
				animations: this.params.animations,
				propertyPath: "background.color",
				localTime,
			}),
			paddingX: resolveNumberAtTime({
				baseValue: bg.paddingX ?? DEFAULT_TEXT_BACKGROUND.paddingX,
				animations: this.params.animations,
				propertyPath: "background.paddingX",
				localTime,
			}),
			paddingY: resolveNumberAtTime({
				baseValue: bg.paddingY ?? DEFAULT_TEXT_BACKGROUND.paddingY,
				animations: this.params.animations,
				propertyPath: "background.paddingY",
				localTime,
			}),
			offsetX: resolveNumberAtTime({
				baseValue: bg.offsetX ?? DEFAULT_TEXT_BACKGROUND.offsetX,
				animations: this.params.animations,
				propertyPath: "background.offsetX",
				localTime,
			}),
			offsetY: resolveNumberAtTime({
				baseValue: bg.offsetY ?? DEFAULT_TEXT_BACKGROUND.offsetY,
				animations: this.params.animations,
				propertyPath: "background.offsetY",
				localTime,
			}),
			cornerRadius: resolveNumberAtTime({
				baseValue: bg.cornerRadius ?? CORNER_RADIUS_MIN,
				animations: this.params.animations,
				propertyPath: "background.cornerRadius",
				localTime,
			}),
		};

	const drawContent = (ctx: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D) => {
			ctx.font = fontString;
			ctx.textAlign = this.params.textAlign;
			ctx.textBaseline = baseline;
			ctx.fillStyle = textColor;
			if ("letterSpacing" in ctx) {
				(ctx as CanvasRenderingContext2D & { letterSpacing: string }).letterSpacing = `${letterSpacing}px`;
			}

			if (
				this.params.background.enabled &&
				this.params.background.color &&
				this.params.background.color !== "transparent" &&
				lineCount > 0
			) {
				const backgroundRect = getTextBackgroundRect({
					textAlign: this.params.textAlign,
					block,
					background: resolvedBackground,
					fontSizeRatio,
				});
				if (backgroundRect) {
					const p = clamp({ value: resolvedBackground.cornerRadius, min: CORNER_RADIUS_MIN, max: CORNER_RADIUS_MAX }) / 100;
					const radius = Math.min(backgroundRect.width, backgroundRect.height) / 2 * p;
				const bgAlpha = (bg.opacity !== undefined ? bg.opacity : 100) / 100;
				const savedAlpha = ctx.globalAlpha;
				ctx.globalAlpha = savedAlpha * bgAlpha;
				ctx.fillStyle = resolvedBackground.color;
				ctx.beginPath();
				ctx.roundRect(backgroundRect.left, backgroundRect.top, backgroundRect.width, backgroundRect.height, radius);
				ctx.fill();
				ctx.globalAlpha = savedAlpha;
				ctx.fillStyle = textColor;
				}
			}

			const stroke = this.params.stroke;
			const shadow = this.params.shadow;

			const applyShadow = () => {
				if (!shadow?.enabled) return;
				const r = parseInt(shadow.color.slice(1, 3), 16) || 0;
				const g = parseInt(shadow.color.slice(3, 5), 16) || 0;
				const b = parseInt(shadow.color.slice(5, 7), 16) || 0;
				ctx.shadowColor = `rgba(${r},${g},${b},${shadow.opacity ?? 1})`;
				ctx.shadowOffsetX = shadow.offsetX ?? 0;
				ctx.shadowOffsetY = shadow.offsetY ?? 0;
				ctx.shadowBlur = shadow.blur ?? 0;
			};
			const clearShadow = () => {
				ctx.shadowColor = "transparent";
				ctx.shadowOffsetX = 0;
				ctx.shadowOffsetY = 0;
				ctx.shadowBlur = 0;
			};

			// Precompute per-line word ranges for karaoke mode
			const karaokeWords = this.params.karaokeWords;
			const karaokeHighlight = this.params.karaokeHighlightColor;
			const isKaraoke = !!(karaokeWords && karaokeWords.length > 0 && karaokeHighlight);
			const lineWordRanges: Array<{ start: number; end: number }> = [];
			if (isKaraoke && karaokeWords) {
				let wordIdx = 0;
				for (let i = 0; i < lines.length; i++) {
					const lineWordCount = lines[i].trim() ? lines[i].trim().split(/\s+/).length : 0;
					lineWordRanges.push({ start: wordIdx, end: wordIdx + lineWordCount });
					wordIdx += lineWordCount;
				}
			}

			for (let i = 0; i < lineCount; i++) {
				const lineY = i * lineHeightPx - block.visualCenterOffset;

				if (isKaraoke && karaokeWords && lineWordRanges[i]) {
					// Karaoke mode: draw each word individually with per-word color
					const range = lineWordRanges[i];
					const lineKaraokeWords = karaokeWords.slice(range.start, range.end);
					ctx.fillStyle = textColor;
					drawKaraokeLine({
						ctx,
						karaokeWords: lineKaraokeWords,
						lineY,
						localTime,
						baseColor: textColor,
						highlightColor: karaokeHighlight,
						textTransform: this.params.textTransform,
						textAlign: this.params.textAlign,
						stroke,
						applyShadow,
						clearShadow,
					});
				} else if (stroke?.enabled && stroke.width > 0) {
					ctx.strokeStyle = stroke.color;
					ctx.lineWidth = stroke.outsideOnly ? stroke.width * 2 : stroke.width;
					ctx.lineJoin = "round";
					applyShadow();
					ctx.strokeText(lines[i], 0, lineY);
					clearShadow();
					ctx.fillText(lines[i], 0, lineY);
				} else {
					applyShadow();
					ctx.fillText(lines[i], 0, lineY);
					clearShadow();
				}

				drawTextDecoration({
					ctx,
					textDecoration: this.params.textDecoration ?? "none",
					lineWidth: lineMetrics[i].width,
					lineY,
					metrics: lineMetrics[i],
					scaledFontSize,
					textAlign: this.params.textAlign,
				});
			}
		};

		const applyTransform = (ctx: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D) => {
			ctx.translate(x, y);
			ctx.scale(transform.scale, transform.scale);
			if (transform.rotate) {
				ctx.rotate((transform.rotate * Math.PI) / 180);
			}
		};

		const enabledEffects = this.params.effects?.filter((effect) => effect.enabled) ?? [];

		if (enabledEffects.length === 0) {
			renderer.context.save();
			applyTransform(renderer.context);
			renderer.context.globalCompositeOperation = blendMode;
			renderer.context.globalAlpha = opacity;
			drawContent(renderer.context);
			renderer.context.restore();
			return;
		}

		// Effects path: render text to a same-size offscreen canvas so the blur
		// can spread into the surrounding transparent area without hard clipping.
		const offscreen = createOffscreenCanvas({ width: renderer.width, height: renderer.height });
		const offscreenCtx = offscreen.getContext("2d") as OffscreenCanvasRenderingContext2D | null;

		if (!offscreenCtx) {
		renderer.context.save();
			applyTransform(renderer.context);
			renderer.context.globalCompositeOperation = blendMode;
			renderer.context.globalAlpha = opacity;
			drawContent(renderer.context);
			renderer.context.restore();
			return;
		}

		offscreenCtx.save();
		applyTransform(offscreenCtx);
		drawContent(offscreenCtx);
		offscreenCtx.restore();

		let currentSource: CanvasImageSource = offscreen;
		for (const effect of enabledEffects) {
			const resolvedParams = resolveEffectParamsAtTime({
				effect,
				animations: this.params.animations,
				localTime,
			});
			const definition = getEffect({ effectType: effect.type });
			const passes = definition.renderer.passes.map((pass) => ({
				fragmentShader: pass.fragmentShader,
				uniforms: pass.uniforms({
					effectParams: resolvedParams,
					width: renderer.width,
					height: renderer.height,
				}),
			}));
			currentSource = webglEffectRenderer.applyEffect({
				source: currentSource,
				width: renderer.width,
				height: renderer.height,
				passes,
			});
		}

		renderer.context.save();
		renderer.context.globalCompositeOperation = blendMode;
		renderer.context.globalAlpha = opacity;
		renderer.context.drawImage(currentSource, 0, 0);
		renderer.context.restore();
	}
}
