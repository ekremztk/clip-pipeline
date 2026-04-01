"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Spinner } from "@/components/ui/spinner";
import { useEditor } from "@/hooks/use-editor";
import { runReframe, type ReframeProgress, type ReframeResult, type ReframeOptions } from "@/lib/reframe/engine";
import type { ReframeAspectRatio, ReframeContentType, ReframeTrackingMode } from "@/lib/reframe/types";
import { CheckCheck, ExternalLink, RotateCcw, Smartphone } from "lucide-react";

const ASPECT_RATIO_OPTIONS: { value: ReframeAspectRatio; label: string }[] = [
	{ value: "9:16", label: "9:16 — Vertical" },
	{ value: "1:1", label: "1:1 — Square" },
	{ value: "4:5", label: "4:5 — Portrait" },
	{ value: "16:9", label: "16:9 — Landscape" },
];

const CONTENT_TYPE_OPTIONS: { value: ReframeContentType; label: string; description: string }[] = [
	{ value: "auto", label: "Auto Detect", description: "Let AI decide" },
	{ value: "podcast", label: "Podcast", description: "Interview / talk show" },
	{ value: "single", label: "Single Speaker", description: "Vlog / presentation" },
	{ value: "gaming", label: "Gaming", description: "Stream / gameplay" },
];

const TRACKING_MODE_OPTIONS: { value: ReframeTrackingMode; label: string; description: string }[] = [
	{ value: "x_only", label: "Horizontal only", description: "Pan left/right to follow speaker" },
	{ value: "dynamic_xy", label: "Dynamic X+Y", description: "Pan and tilt for moving subjects" },
];

export function ReframeView() {
	const editor = useEditor();

	const [aspectRatio, setAspectRatio] = useState<ReframeAspectRatio>("9:16");
	const [contentType, setContentType] = useState<ReframeContentType>("auto");
	const [trackingMode, setTrackingMode] = useState<ReframeTrackingMode>("dynamic_xy");
	const [debugMode, setDebugMode] = useState(false);

	const [isProcessing, setIsProcessing] = useState(false);
	const [progress, setProgress] = useState<ReframeProgress | null>(null);
	const [results, setResults] = useState<ReframeResult[] | null>(null);
	const [error, setError] = useState<string | null>(null);

	const reset = () => {
		setResults(null);
		setError(null);
		setProgress(null);
	};

	const handleReframe = async () => {
		try {
			setIsProcessing(true);
			setError(null);
			setResults(null);

			const options: ReframeOptions = {
				strategy: contentType === "auto" ? "podcast" : contentType as any,
				aspectRatio,
				trackingMode,
				contentType,
				debugMode,
			};

			const res = await runReframe(editor, (p) => setProgress(p), options);
			setResults(res);
		} catch (err) {
			console.error("[Reframe]", err);
			setError(err instanceof Error ? err.message : "Unexpected error");
		} finally {
			setIsProcessing(false);
		}
	};

	return (
		<ScrollArea className="h-full scrollbar-hidden">
			<div className="flex flex-col gap-5 p-4">

				{/* Description */}
				<div className="flex flex-col gap-2">
					<div className="flex items-center gap-2">
						<Smartphone className="size-4 text-primary" />
						<span className="text-sm font-medium">Auto Reframe</span>
					</div>
					<p className="text-muted-foreground text-xs leading-relaxed">
						AI face detection and speaker diarization — keyframes applied directly
						to your timeline. Scene cuts marked on the ruler. Drag any keyframe to
						manually adjust framing.
					</p>
				</div>

				{/* Aspect ratio */}
				<div className="flex flex-col gap-2">
					<span className="text-xs font-medium">Aspect ratio</span>
					<div className="grid grid-cols-2 gap-1.5">
						{ASPECT_RATIO_OPTIONS.map((opt) => (
							<button
								key={opt.value}
								onClick={() => setAspectRatio(opt.value)}
								disabled={isProcessing}
								className={`rounded-md border px-2.5 py-1.5 text-left text-xs transition-colors ${
									aspectRatio === opt.value
										? "border-white bg-white/10 text-white"
										: "border-[#262626] bg-black text-[#a3a3a3] hover:border-[#404040] hover:text-white"
								}`}
							>
								{opt.label}
							</button>
						))}
					</div>
				</div>

				{/* Content type */}
				<div className="flex flex-col gap-2">
					<span className="text-xs font-medium">Content type</span>
					<div className="grid grid-cols-2 gap-1.5">
						{CONTENT_TYPE_OPTIONS.map((opt) => (
							<button
								key={opt.value}
								onClick={() => setContentType(opt.value)}
								disabled={isProcessing}
								className={`flex flex-col gap-0.5 rounded-md border px-2.5 py-2 text-left transition-colors ${
									contentType === opt.value
										? "border-white bg-white/10"
										: "border-[#262626] bg-black hover:border-[#404040]"
								}`}
							>
								<span className={`text-xs font-medium ${contentType === opt.value ? "text-white" : "text-[#a3a3a3]"}`}>
									{opt.label}
								</span>
								<span className="text-[#525252] text-xs">{opt.description}</span>
							</button>
						))}
					</div>
				</div>

				{/* Tracking mode */}
				<div className="flex flex-col gap-2">
					<span className="text-xs font-medium">Tracking mode</span>
					<div className="flex flex-col gap-1.5">
						{TRACKING_MODE_OPTIONS.map((opt) => (
							<button
								key={opt.value}
								onClick={() => setTrackingMode(opt.value)}
								disabled={isProcessing}
								className={`flex flex-col gap-0.5 rounded-md border px-2.5 py-2 text-left transition-colors ${
									trackingMode === opt.value
										? "border-white bg-white/10"
										: "border-[#262626] bg-black hover:border-[#404040]"
								}`}
							>
								<span className={`text-xs font-medium ${trackingMode === opt.value ? "text-white" : "text-[#a3a3a3]"}`}>
									{opt.label}
								</span>
								<span className="text-[#737373] text-xs">{opt.description}</span>
							</button>
						))}
					</div>
				</div>

				{/* Debug mode */}
				<div className="flex items-center justify-between">
					<div className="flex flex-col gap-0.5">
						<span className="text-xs font-medium">Debug mode</span>
						<span className="text-[#525252] text-xs">Burns pipeline internals onto video</span>
					</div>
					<button
						onClick={() => setDebugMode((v) => !v)}
						disabled={isProcessing}
						className={`relative h-5 w-9 rounded-full transition-colors ${
							debugMode ? "bg-white" : "bg-[#262626]"
						}`}
					>
						<span
							className={`absolute top-0.5 h-4 w-4 rounded-full transition-transform ${
								debugMode ? "translate-x-4 bg-black" : "translate-x-0.5 bg-[#737373]"
							}`}
						/>
					</button>
				</div>

				{/* Error */}
				{error && (
					<div className="bg-destructive/10 border-destructive/20 rounded-md border p-3">
						<p className="text-destructive text-sm">{error}</p>
					</div>
				)}

				{/* Reframe button */}
				{!results && (
					<Button
						className="w-full"
						onClick={handleReframe}
						disabled={isProcessing}
					>
						{isProcessing && <Spinner className="mr-2" />}
						{isProcessing
							? (progress?.step ?? "Processing...")
							: `Reframe to ${aspectRatio}`}
					</Button>
				)}

				{/* Progress bar */}
				{isProcessing && progress && (
					<div className="flex flex-col gap-1.5">
						<div className="bg-secondary h-1.5 w-full overflow-hidden rounded-full">
							<div
								className="bg-primary h-full rounded-full transition-all duration-500"
								style={{ width: `${progress.percent}%` }}
							/>
						</div>
						<p className="text-muted-foreground text-center text-xs">
							{progress.percent}%
						</p>
					</div>
				)}

				{/* Result */}
				{results && results.length > 0 && (
					<div className="flex flex-col gap-3">
						<div className="bg-primary/10 border-primary/20 flex items-start gap-3 rounded-md border p-3">
							<CheckCheck className="text-primary mt-0.5 size-4 shrink-0" />
							<div className="flex flex-col gap-0.5">
								<p className="text-sm font-medium">Reframe applied!</p>
								<p className="text-muted-foreground text-xs">
									{results.reduce((sum, r) => sum + r.keyframeCount, 0)} keyframes
									added to {results.length} clip{results.length > 1 ? "s" : ""}.
									Scene cut markers added to timeline ruler.
								</p>
							</div>
						</div>

						{results.some((r) => r.debugVideoUrl) && (
							<div className="flex flex-col gap-1.5">
								<span className="text-xs font-medium text-[#a3a3a3]">Debug videos</span>
								{results.filter((r) => r.debugVideoUrl).map((r) => (
									<a
										key={r.elementId}
										href={r.debugVideoUrl}
										target="_blank"
										rel="noopener noreferrer"
										className="flex items-center gap-1.5 rounded-md border border-[#262626] px-2.5 py-2 text-xs text-[#a3a3a3] transition-colors hover:border-[#404040] hover:text-white"
									>
										<ExternalLink className="size-3 shrink-0" />
										<span className="truncate">{r.debugVideoUrl}</span>
									</a>
								))}
							</div>
						)}

						<button
							onClick={reset}
							className="text-muted-foreground hover:text-foreground flex items-center justify-center gap-1.5 text-xs transition-colors"
						>
							<RotateCcw className="size-3" /> Run again
						</button>
					</div>
				)}

			</div>
		</ScrollArea>
	);
}
