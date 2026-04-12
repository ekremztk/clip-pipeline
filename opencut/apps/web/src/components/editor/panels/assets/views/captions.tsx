"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Spinner } from "@/components/ui/spinner";
import { Label } from "@/components/ui/label";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { extractTimelineAudio } from "@/lib/media/mediabunny";
import { decodeAudioToFloat32 } from "@/lib/media/audio";
import { useEditor } from "@/hooks/use-editor";
import { DEFAULT_TEXT_ELEMENT } from "@/constants/text-constants";
import { DEFAULT_TRANSFORM } from "@/constants/timeline-constants";
import { TRANSCRIPTION_LANGUAGES } from "@/constants/transcription-constants";
import { DEFAULT_CAPTION_TEMPLATE } from "@/constants/caption-templates";
import { DEFAULT_CANVAS_SIZE } from "@/constants/project-constants";
import { transcriptionService } from "@/services/transcription/service";
import { transcribeWithDeepgram } from "@/services/transcription/deepgram-service";
import {
	buildCaptionChunks,
	buildCaptionChunksFromWords,
} from "@/lib/transcription/caption";
import { captionChunksToSrt, downloadSrt } from "@/lib/transcription/srt";
import type {
	CaptionChunk,
	TranscriptionLanguage,
	TranscriptionWord,
	TranscriptionSegment,
} from "@/types/transcription";
import { Cloud, Cpu, Download, RotateCcw, Zap } from "lucide-react";
import { cn } from "@/utils/ui";
import { useReframeMetadataStore } from "@/stores/reframe-metadata-store";

type Engine = "deepgram" | "whisper";

const CHAR_PRESETS = [
	{ label: "Short", value: 20 },
	{ label: "Medium", value: 32 },
	{ label: "Long", value: 42 },
];

function formatTime(seconds: number): string {
	const m = Math.floor(seconds / 60);
	const s = Math.floor(seconds % 60);
	return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function captionStorageKey(projectId: string) {
	return `captions_draft_${projectId}`;
}

/** Build chunks from whatever raw transcript data is available */
function rebuildChunks({
	words,
	segments,
	maxCharsPerLine,
	maxLines,
}: {
	words: TranscriptionWord[] | null;
	segments: TranscriptionSegment[] | null;
	maxCharsPerLine: number;
	maxLines: 1 | 2;
}): CaptionChunk[] {
	if (words && words.length > 0) {
		return buildCaptionChunksFromWords({ words, maxCharsPerLine, maxLines, cleanPunctuation: true });
	}
	if (segments && segments.length > 0) {
		return buildCaptionChunks({ segments });
	}
	return [];
}

export function Captions() {
	const editor = useEditor();
	const captionWords = useReframeMetadataStore((s) => s.captionWords);

	// ── Transcription settings ────────────────────────────────────────────────
	const [engine, setEngine] = useState<Engine>("deepgram");
	const [language, setLanguage] = useState<TranscriptionLanguage>("auto");

	// Preset buttons — sets presetMaxChars; manual input overrides when non-empty
	const [presetMaxChars, setPresetMaxChars] = useState(32);
	const [manualMaxCharsStr, setManualMaxCharsStr] = useState("");
	const [maxLines, setMaxLines] = useState<1 | 2>(1);

	/** The effective maxChars used for building: manual wins when valid */
	const effectiveMaxChars = (() => {
		const parsed = parseInt(manualMaxCharsStr, 10);
		return !Number.isNaN(parsed) && parsed > 0 ? parsed : presetMaxChars;
	})();

	// ── State ────────────────────────────────────────────────────────────────
	const [isProcessing, setIsProcessing] = useState(false);
	const [processingStep, setProcessingStep] = useState("");
	const [error, setError] = useState<string | null>(null);

	// Raw transcript data — kept so we can rebuild when settings change
	const [rawWords, setRawWords] = useState<TranscriptionWord[] | null>(null);
	const [rawSegments, setRawSegments] = useState<
		TranscriptionSegment[] | null
	>(null);

	const [captions, setCaptions] = useState<CaptionChunk[] | null>(() => {
		try {
			const projectId = editor.project.getActiveOrNull()?.metadata.id;
			if (!projectId) return null;
			const saved = localStorage.getItem(captionStorageKey(projectId));
			return saved ? (JSON.parse(saved) as CaptionChunk[]) : null;
		} catch {
			return null;
		}
	});

	// Track that holds the applied captions — used for live rebuilds
	const [appliedTrackId, setAppliedTrackId] = useState<string | null>(null);

	const containerRef = useRef<HTMLDivElement>(null);
	/** Debounce handle for live timeline rebuild */
	const rebuildTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

	// ── Draft persistence ─────────────────────────────────────────────────────

	const saveCaptionsDraft = useCallback(
		(chunks: CaptionChunk[]) => {
			try {
				const projectId = editor.project.getActiveOrNull()?.metadata.id;
				if (!projectId) return;
				localStorage.setItem(
					captionStorageKey(projectId),
					JSON.stringify(chunks),
				);
			} catch {}
		},
		[editor],
	);

	const clearCaptionsDraft = useCallback(() => {
		try {
			const projectId = editor.project.getActiveOrNull()?.metadata.id;
			if (!projectId) return;
			localStorage.removeItem(captionStorageKey(projectId));
		} catch {}
	}, [editor]);

	// ── Apply chunks to timeline ──────────────────────────────────────────────

	/**
	 * Remove existing caption track (if any) and create a new one with the
	 * provided chunks.  Preserves current style by reading first element; falls
	 * back to DEFAULT_CAPTION_TEMPLATE when no track exists yet.
	 */
	const applyToTimeline = useCallback(
		(chunks: CaptionChunk[], existingTrackId: string | null) => {
			// Read current style from the existing track's first element, if any
			let styleOverrides: Partial<typeof DEFAULT_TEXT_ELEMENT> = {
				fontSize: DEFAULT_CAPTION_TEMPLATE.fontSize,
				fontFamily: DEFAULT_CAPTION_TEMPLATE.fontFamily,
				fontWeight: DEFAULT_CAPTION_TEMPLATE.fontWeight,
				fontStyle: DEFAULT_CAPTION_TEMPLATE.fontStyle,
				color: DEFAULT_CAPTION_TEMPLATE.color,
				textAlign: DEFAULT_CAPTION_TEMPLATE.textAlign,
				letterSpacing: DEFAULT_CAPTION_TEMPLATE.letterSpacing,
				lineHeight: DEFAULT_CAPTION_TEMPLATE.lineHeight,
				background: DEFAULT_CAPTION_TEMPLATE.background,
				stroke: DEFAULT_CAPTION_TEMPLATE.stroke,
				shadow: DEFAULT_CAPTION_TEMPLATE.shadow,
			};

			// Compute canvas-size-aware position: 75% from top for any aspect ratio
			// 9:16 (h=1920): y=+480  |  16:9 (h=1080): y=+270  |  1:1 (h=1080): y=+270
			const canvasHeight =
				editor.project.getActiveOrNull()?.settings.canvasSize?.height ??
				DEFAULT_CANVAS_SIZE.height;
			// 0.078 ratio: y≈150 on 9:16 (h=1920), y≈84 on 16:9 (h=1080) — default safe zone
		const canvasAwarePosition = { x: 0, y: Math.round(canvasHeight * 0.078) };

		// Read style + position from existing track BEFORE removing it
			let savedPosition = canvasAwarePosition;
			let savedKaraokeHighlightColor: string | undefined;

			if (existingTrackId) {
				const existingTrack = editor.timeline.getTrackById({
					trackId: existingTrackId,
				});
				if (existingTrack && existingTrack.elements.length > 0) {
					const src = existingTrack.elements[0] as typeof DEFAULT_TEXT_ELEMENT;
					styleOverrides = {
						fontSize: src.fontSize,
						fontFamily: src.fontFamily,
						fontWeight: src.fontWeight,
						fontStyle: src.fontStyle ?? "normal",
						color: src.color,
						textAlign: src.textAlign,
						letterSpacing: src.letterSpacing ?? 0,
						lineHeight: src.lineHeight ?? 1.2,
						background: src.background,
						stroke: src.stroke,
						shadow: src.shadow,
						textTransform: src.textTransform ?? "none",
					};
					savedPosition = src.transform.position;
					savedKaraokeHighlightColor = src.karaokeHighlightColor;
				}
				editor.timeline.removeTrack({ trackId: existingTrackId });
			}

			const trackId = editor.timeline.addTrack({ type: "text", index: 0 });
			const templatePosition = savedPosition;

			for (let i = 0; i < chunks.length; i++) {
				const caption = chunks[i];
				// Convert absolute word times → relative to element start
				const karaokeWords = caption.words
					? caption.words.map((w) => ({
							word: w.word,
							startTime: w.startTime - caption.startTime,
							endTime: w.endTime - caption.startTime,
						}))
					: undefined;
				editor.timeline.insertElement({
					placement: { mode: "explicit", trackId },
					element: {
						...DEFAULT_TEXT_ELEMENT,
						...styleOverrides,
						name: `Caption ${i + 1}`,
						content: caption.text,
						duration: caption.duration,
						startTime: caption.startTime,
						transform: {
							...DEFAULT_TRANSFORM,
							position: { ...templatePosition },
						},
						karaokeWords,
						karaokeHighlightColor: savedKaraokeHighlightColor,
					},
				});
			}

			return trackId;
		},
		[editor],
	);

	// ── Live rebuild when settings change (debounced 400 ms) ─────────────────

	useEffect(() => {
		// Only rebuild if we already have raw data and an applied track
		if ((!rawWords && !rawSegments) || !appliedTrackId) return;

		if (rebuildTimerRef.current) clearTimeout(rebuildTimerRef.current);

		rebuildTimerRef.current = setTimeout(() => {
			const newChunks = rebuildChunks({
				words: rawWords,
				segments: rawSegments,
				maxCharsPerLine: effectiveMaxChars,
				maxLines,
			});
			setCaptions(newChunks);
			saveCaptionsDraft(newChunks);
			const newTrackId = applyToTimeline(newChunks, appliedTrackId);
			setAppliedTrackId(newTrackId);
		}, 400);

		return () => {
			if (rebuildTimerRef.current) clearTimeout(rebuildTimerRef.current);
		};
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [effectiveMaxChars, maxLines]);

	// ── Reset ─────────────────────────────────────────────────────────────────

	const reset = () => {
		setCaptions(null);
		setRawWords(null);
		setRawSegments(null);
		setError(null);
		clearCaptionsDraft();
		if (appliedTrackId) {
			editor.timeline.removeTrack({ trackId: appliedTrackId });
			setAppliedTrackId(null);
		}
	};

	// ── Generate ─────────────────────────────────────────────────────────────

	const handleGenerate = async () => {
		try {
			setIsProcessing(true);
			setError(null);
			setCaptions(null);
			setRawWords(null);
			setRawSegments(null);

			// Remove any previously applied track before regenerating
			if (appliedTrackId) {
				editor.timeline.removeTrack({ trackId: appliedTrackId });
				setAppliedTrackId(null);
			}

			setProcessingStep("Extracting audio from timeline...");
			const audioBlob = await extractTimelineAudio({
				tracks: editor.timeline.getTracks(),
				mediaAssets: editor.media.getAssets(),
				totalDuration: editor.timeline.getTotalDuration(),
			});

			let chunks: CaptionChunk[] = [];

			if (engine === "deepgram") {
				const result = await transcribeWithDeepgram({
					audioBlob,
					language: language === "auto" ? undefined : language,
					onProgress: setProcessingStep,
				});

				setProcessingStep("Building captions...");

				if (result.words && result.words.length > 0) {
					setRawWords(result.words);
					chunks = buildCaptionChunksFromWords({
						words: result.words,
						maxCharsPerLine: effectiveMaxChars,
						maxLines,
						cleanPunctuation: true,
					});
				} else {
					setRawSegments(result.segments);
					chunks = buildCaptionChunks({ segments: result.segments });
				}
			} else {
				setProcessingStep("Loading Whisper model...");
				const { samples } = await decodeAudioToFloat32({ audioBlob });

				const result = await transcriptionService.transcribe({
					audioData: samples,
					language: language === "auto" ? undefined : language,
					onProgress: (p) => {
						if (p.status === "loading-model") {
							setProcessingStep(`Loading model ${Math.round(p.progress)}%`);
						} else {
							setProcessingStep("Transcribing...");
						}
					},
				});

				setProcessingStep("Building captions...");
				setRawSegments(result.segments);
				chunks = buildCaptionChunks({ segments: result.segments });
			}

			setCaptions(chunks);
			saveCaptionsDraft(chunks);

			// Auto-apply to timeline with default template
			const newTrackId = applyToTimeline(chunks, null);
			setAppliedTrackId(newTrackId);
		} catch (err) {
			console.error("[Captions]", err);
			setError(err instanceof Error ? err.message : "Unexpected error");
		} finally {
			setIsProcessing(false);
			setProcessingStep("");
		}
	};

	const handleUsePipelineCaptions = () => {
		if (!captionWords || captionWords.length === 0) return;
		try {
			// CaptionWord and TranscriptionWord have identical shapes — direct cast
			const words = captionWords as unknown as TranscriptionWord[];
			setRawWords(words);
			setRawSegments(null);

			const chunks = buildCaptionChunksFromWords({
				words,
				maxCharsPerLine: effectiveMaxChars,
				maxLines,
				cleanPunctuation: true,
			});

			setCaptions(chunks);
			saveCaptionsDraft(chunks);

			if (appliedTrackId) {
				editor.timeline.removeTrack({ trackId: appliedTrackId });
			}
			const newTrackId = applyToTimeline(chunks, null);
			setAppliedTrackId(newTrackId);
		} catch (err) {
			console.error("[Captions] Pipeline captions error:", err);
			setError(err instanceof Error ? err.message : "Failed to apply pipeline captions");
		}
	};

	const handleDownloadSrt = () => {
		if (!captions || captions.length === 0) return;
		const srtContent = captionChunksToSrt(captions);
		downloadSrt(srtContent, "subtitles.srt");
	};

	// ── Render ────────────────────────────────────────────────────────────────

	return (
		<ScrollArea className="h-full scrollbar-hidden">
			<div ref={containerRef} className="flex flex-col gap-5 p-4">

				{/* Engine selector */}
				<div>
					<Label className="mb-2 block">Transcription Engine</Label>
					<div className="grid grid-cols-2 gap-2">
						{(["deepgram", "whisper"] as Engine[]).map((e) => (
							<button
								key={e}
								type="button"
								onClick={() => {
									setEngine(e);
									reset();
								}}
								className={cn(
									"flex flex-col items-center gap-1.5 rounded-md border p-3 text-xs font-medium transition-colors",
									engine === e
										? "border-primary bg-primary/10 text-primary"
										: "border-border text-muted-foreground hover:border-muted-foreground",
								)}
							>
								{e === "deepgram" ? (
									<Cloud className="size-4" />
								) : (
									<Cpu className="size-4" />
								)}
								{e === "deepgram" ? "Deepgram (Cloud)" : "Whisper (Local)"}
							</button>
						))}
					</div>
					{engine === "deepgram" && (
						<p className="text-muted-foreground mt-2 text-xs">
							Faster, more accurate. Uses Prognot backend.
						</p>
					)}
					{engine === "whisper" && (
						<p className="text-muted-foreground mt-2 text-xs">
							Runs in browser. Downloads model on first use (~150 MB).
						</p>
					)}
				</div>

				{/* Language */}
				<div>
					<Label className="mb-2 block">Language</Label>
					<Select
						value={language}
						onValueChange={(v) => setLanguage(v as TranscriptionLanguage)}
					>
						<SelectTrigger>
							<SelectValue placeholder="Select language" />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="auto">Auto detect</SelectItem>
							{TRANSCRIPTION_LANGUAGES.map((l) => (
								<SelectItem key={l.code} value={l.code}>
									{l.name}
								</SelectItem>
							))}
						</SelectContent>
					</Select>
				</div>

				{/* Characters per line + line count (Deepgram only) */}
				{engine === "deepgram" && (
					<>
						<div>
							<Label className="mb-2 block">Characters per line</Label>

							{/* Preset buttons */}
							<div className="grid grid-cols-3 gap-2">
								{CHAR_PRESETS.map((opt) => (
									<button
										key={opt.value}
										type="button"
										onClick={() => {
											setPresetMaxChars(opt.value);
											setManualMaxCharsStr(""); // clear manual override
										}}
										className={cn(
											"rounded-md border px-2 py-1.5 text-xs font-medium transition-colors",
											// active when preset matches AND no manual override
											presetMaxChars === opt.value &&
											manualMaxCharsStr === ""
												? "border-primary bg-primary/10 text-primary"
												: "border-border text-muted-foreground hover:border-muted-foreground",
										)}
									>
										{opt.label} ({opt.value})
									</button>
								))}
							</div>

							{/* Manual override input */}
							<div className="mt-2 flex items-center gap-2">
								<input
									type="number"
									min={5}
									max={200}
									placeholder={`Manual (${presetMaxChars})`}
									value={manualMaxCharsStr}
									onChange={(e) => setManualMaxCharsStr(e.target.value)}
									className={cn(
										"flex-1 rounded-md border bg-black px-2 py-1.5 text-xs",
										"border-[#262626] focus:border-[#404040] focus:outline-none",
										"text-white placeholder-[#525252]",
										manualMaxCharsStr !== ""
											? "border-primary"
											: "",
									)}
								/>
								{manualMaxCharsStr !== "" && (
									<button
										type="button"
										onClick={() => setManualMaxCharsStr("")}
										className="text-[10px] text-[#737373] hover:text-white transition-colors"
									>
										Reset
									</button>
								)}
							</div>

							{manualMaxCharsStr !== "" && (
								<p className="mt-1 text-[10px] text-[#737373]">
									Manual value active ({effectiveMaxChars} chars)
								</p>
							)}
						</div>


					<div>
							<Label className="mb-2 block">Lines per subtitle</Label>
							<div className="grid grid-cols-2 gap-2">
								{([1, 2] as const).map((n) => (
									<button
										key={n}
										type="button"
										onClick={() => setMaxLines(n)}
										className={cn(
											"rounded-md border py-1.5 text-xs font-medium transition-colors",
											maxLines === n
												? "border-primary bg-primary/10 text-primary"
												: "border-border text-muted-foreground hover:border-muted-foreground",
										)}
									>
										{n === 1 ? "1 line" : "2 lines"}
									</button>
								))}
							</div>
						</div>
					</>
				)}

				{/* Error */}
				{error && (
					<div className="bg-destructive/10 border-destructive/20 rounded-md border p-3">
						<p className="text-destructive text-sm">{error}</p>
					</div>
				)}

				{/* Pipeline captions fast-path */}
				{!captions && captionWords.length > 0 && (
					<div className="rounded-md border border-[#1a1a1a] bg-[#0a0a0a] p-3">
						<p className="mb-2 text-xs font-medium text-white">Pipeline captions available</p>
						<p className="mb-3 text-[11px] text-[#737373]">
							{captionWords.length} words from auto-transcription — no re-processing needed.
						</p>
						<Button
							className="w-full bg-white text-black hover:bg-[#e5e5e5]"
							onClick={handleUsePipelineCaptions}
						>
							<Zap className="mr-2 size-4" />
							Use Pipeline Captions
						</Button>
						<button
							type="button"
							onClick={handleGenerate}
							disabled={isProcessing}
							className="mt-2 w-full text-center text-xs text-[#737373] hover:text-white transition-colors"
						>
							{isProcessing ? processingStep : "Re-transcribe instead"}
						</button>
					</div>
				)}

			{/* Generate button */}
				{!captions && captionWords.length === 0 && (
					<Button
						className="w-full"
						onClick={handleGenerate}
						disabled={isProcessing}
					>
						{isProcessing && <Spinner className="mr-2" />}
						{isProcessing ? processingStep : "Generate Subtitles"}
					</Button>
				)}

				{/* Caption preview + actions */}
				{captions && captions.length > 0 && (
					<div className="flex flex-col gap-3">
						<div className="flex items-center justify-between">
							<p className="text-sm font-medium">
								{captions.length} subtitles
							</p>
							<button
								type="button"
								onClick={reset}
								className="text-muted-foreground hover:text-foreground flex items-center gap-1 text-xs transition-colors"
							>
								<RotateCcw className="size-3" /> Redo
							</button>
						</div>

						<p className="text-muted-foreground text-xs">
							Applied to timeline. Select a caption to choose a template on
							the right panel.
						</p>

						{/* Scrollable preview list */}
						<div className="border-border max-h-52 overflow-y-auto rounded-md border">
							{captions.map((chunk, i) => (
								<div
									key={i}
									className={cn(
										"border-border px-3 py-2 text-xs",
										i < captions.length - 1 && "border-b",
									)}
								>
									<span className="text-muted-foreground mr-2 font-mono">
										{formatTime(chunk.startTime)}
									</span>
									<span>{chunk.text}</span>
								</div>
							))}
						</div>

						<Button
							variant="outline"
							className="w-full"
							onClick={handleDownloadSrt}
						>
							<Download className="mr-2 size-4" />
							Download .srt
						</Button>
					</div>
				)}

			</div>
		</ScrollArea>
	);
}
