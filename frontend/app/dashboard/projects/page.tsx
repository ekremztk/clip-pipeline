"use client";

import React, { useState, useEffect, useRef, useMemo, useCallback, Suspense } from "react";
import {
    Download, Check, X, Play, FileVideo, MoreHorizontal, ArrowLeft,
    Upload, Scissors, FolderOpen, ChevronRight,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useChannel } from "../layout";
import { authFetch } from "@/lib/api";
import { toast } from "@/lib/toast";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Clip {
    id: string;
    channel_id: string;
    job_id: string;
    hook_text: string;
    duration_s: number;
    standalone_score: number;        // 0-100 single score (new schema)
    clip_strategy_role: string;
    posting_order: number;
    is_successful: boolean | null;
    is_published: boolean | null;
    standalone_result?: string;      // "pass" | "fixable"
    quality_notes?: string;
    file_url: string | null;
    suggested_title: string | null;
    suggested_description: string | null;
    start_time?: number;
    end_time?: number;
    video_landscape_path?: string | null;
    video_reframed_path?: string | null;
    video_captioned_path?: string | null;
    reframe_metadata?: any | null;
    caption_metadata?: any | null;
}

interface TranscriptWord {
    word: string;
    start: number;
    end: number;
}

type FilterType = "all" | "successful" | "failed" | "published";

// ─── Helpers ──────────────────────────────────────────────────────────────────

// Returns the best available video URL: captioned > reframed > raw 16:9
const getBestUrl = (clip: Clip): string | null =>
    clip.video_captioned_path || clip.video_reframed_path || clip.file_url || null;

const STEP_LABELS: Record<string, string> = {
    initializing: "Initializing...",
    s01_audio_extract: "Extracting Audio...",
    s02_transcribe: "Transcribing...",
    s03_speaker_id: "Identifying Speakers...",
    s04_labeled_transcript: "Building Transcript...",
    s05_unified_discovery: "Analyzing Video with AI...",
    s06_batch_evaluation: "Evaluating Clips...",
    s07_precision_cut: "Calculating Cut Points...",
    s08_export: "Exporting & Uploading...",
    finished: "Complete!",
};

function getStepLabel(step: string | undefined): string {
    if (!step) return "Processing...";
    return STEP_LABELS[step] || step.replace(/_/g, " ").replace(/^s\d+\s?/, "");
}

const formatDate = (dateStr?: string) => {
    if (!dateStr) return "Just now";
    const diff = Date.now() - new Date(dateStr).getTime();
    const hours = diff / (1000 * 60 * 60);
    const days = Math.floor(hours / 24);
    if (hours < 1) { const mins = Math.floor(hours * 60); return mins <= 1 ? "Just now" : `${mins}m ago`; }
    if (hours < 24) return "Today";
    if (days === 1) return "Yesterday";
    return `${days}d ago`;
};

const formatDuration = (seconds: number) => {
    if (!seconds) return "0:00";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
};

const formatTranscriptTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
};

const getScoreColor = (score: number) => {
    if (score >= 80) return "text-green-400";
    if (score >= 60) return "text-yellow-400";
    return "text-red-400";
};

const getScoreBarColor = (score: number) => {
    if (score >= 80) return "bg-green-500";
    if (score >= 60) return "bg-yellow-500";
    return "bg-red-500";
};

const getScoreHex = (score: number) => {
    if (score >= 80) return "#4ade80";
    if (score >= 60) return "#facc15";
    return "#f87171";
};

// ─── Open in Editor Button ────────────────────────────────────────────────────

const OpenInEditorButton = ({ clip, guestName }: { clip: Clip; guestName?: string | null }) => {
    if (!getBestUrl(clip)) {
        return (
            <button disabled style={{ border: "1px solid rgba(250,249,245,0.08)", color: "#ababab" }} className="w-full flex items-center justify-center gap-2 py-2 rounded-xl font-medium cursor-not-allowed text-xs">
                <Scissors className="w-3.5 h-3.5" /> Open in Editor
            </button>
        );
    }
    const params = new URLSearchParams({ clipUrl: getBestUrl(clip)! });
    if (clip.suggested_title) params.set("clipTitle", clip.suggested_title);
    if (clip.suggested_description) params.set("clipDesc", clip.suggested_description);
    if (guestName) params.set("clipGuestName", guestName);
    if (clip.job_id) params.set("clipJobId", clip.job_id);
    // Pass clip ID so the editor can fetch reframe keyframes + caption words
    params.set("clipId", clip.id);
    const href = `https://edit.prognot.com/editor/${crypto.randomUUID()}?${params.toString()}`;

    const handleClick = async (e: React.MouseEvent) => {
        e.preventDefault();
        try {
            await authFetch("/director/events", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    module_name: "editor", event_type: "clip_opened_in_editor",
                    payload: { clip_id: clip.id, job_id: clip.job_id, channel_id: clip.channel_id },
                    channel_id: clip.channel_id,
                }),
            });
        } catch { /* non-critical */ }
        window.open(href, "_blank", "noopener,noreferrer");
    };

    return (
        <button onClick={handleClick} style={{ background: "rgba(250,249,245,0.07)", border: "1px solid rgba(250,249,245,0.1)", color: "#ababab" }} className="w-full flex items-center justify-center gap-2 py-2 rounded-xl font-medium hover:text-[#faf9f5] transition-colors text-xs">
            <Scissors className="w-3.5 h-3.5" /> Open in Editor
        </button>
    );
};

// ─── Clip Modal ───────────────────────────────────────────────────────────────

interface ClipModalProps {
    clip: Clip;
    guestName?: string | null;
    onClose: () => void;
    onApprove: (id: string) => void;
    onReject: (id: string) => void;
    onPublish: (id: string) => void;
    onDownload: (id: string) => void;
}

function ClipModal({ clip, guestName, onClose, onApprove, onReject, onPublish, onDownload }: ClipModalProps) {
    const videoRef = useRef<HTMLVideoElement>(null);
    const transcriptContainerRef = useRef<HTMLDivElement>(null);
    const wordRefs = useRef<(HTMLSpanElement | null)[]>([]);

    const [transcriptWords, setTranscriptWords] = useState<TranscriptWord[]>([]);
    const [transcriptLoading, setTranscriptLoading] = useState(true);
    const [currentTime, setCurrentTime] = useState(0);
    const [userScrolling, setUserScrolling] = useState(false);
    const userScrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Fetch transcript
    useEffect(() => {
        setTranscriptLoading(true);
        setTranscriptWords([]);
        authFetch(`/clips/${clip.id}/transcript`)
            .then(r => r.ok ? r.json() : { words: [] })
            .then(data => setTranscriptWords(data.words || []))
            .catch(() => setTranscriptWords([]))
            .finally(() => setTranscriptLoading(false));
    }, [clip.id]);

    // Current word index from video time
    const currentWordIndex = useMemo(() => {
        if (!transcriptWords.length || currentTime <= 0) return -1;
        for (let i = 0; i < transcriptWords.length; i++) {
            const w = transcriptWords[i];
            const next = transcriptWords[i + 1];
            const end = next ? next.start : (w.end || w.start + 0.5);
            if (currentTime >= w.start && currentTime < end) return i;
        }
        return -1;
    }, [currentTime, transcriptWords]);

    // Auto-scroll transcript to current word
    useEffect(() => {
        if (userScrolling || currentWordIndex < 0) return;
        const wordEl = wordRefs.current[currentWordIndex];
        const container = transcriptContainerRef.current;
        if (!wordEl || !container) return;

        const wordTop = wordEl.offsetTop;
        const wordHeight = wordEl.offsetHeight;
        const containerHeight = container.clientHeight;
        const targetScroll = wordTop - containerHeight / 2 + wordHeight / 2;

        if (Math.abs(container.scrollTop - targetScroll) > 40) {
            container.scrollTo({ top: Math.max(0, targetScroll), behavior: "smooth" });
        }
    }, [currentWordIndex, userScrolling]);

    // Detect manual scroll
    const handleTranscriptScroll = useCallback(() => {
        setUserScrolling(true);
        if (userScrollTimerRef.current) clearTimeout(userScrollTimerRef.current);
        userScrollTimerRef.current = setTimeout(() => setUserScrolling(false), 2500);
    }, []);

    const handleTimeUpdate = useCallback(() => {
        if (videoRef.current) setCurrentTime(videoRef.current.currentTime);
    }, []);

    // Close on Escape
    useEffect(() => {
        const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
        document.addEventListener("keydown", handler);
        return () => document.removeEventListener("keydown", handler);
    }, [onClose]);

    // Build transcript segments with timestamp markers
    const transcriptSegments = useMemo(() => {
        type Seg = { type: "timestamp"; time: number } | { type: "word"; word: TranscriptWord; index: number };
        const segs: Seg[] = [];
        let lastMarkerTime = -999;
        for (let i = 0; i < transcriptWords.length; i++) {
            const w = transcriptWords[i];
            const prev = transcriptWords[i - 1];
            const gapToPrev = prev ? w.start - prev.start : 0;
            if (i === 0 || gapToPrev >= 5 || (w.start - lastMarkerTime) >= 12) {
                segs.push({ type: "timestamp", time: w.start });
                lastMarkerTime = w.start;
            }
            segs.push({ type: "word", word: w, index: i });
        }
        return segs;
    }, [transcriptWords]);

    const score = clip.standalone_score ?? 0;
    const scoreHex = getScoreHex(score);

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-6 md:p-10"
            onClick={onClose}
        >
            {/* Backdrop */}
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />

            {/* Panel */}
            <div
                className="relative z-10 w-full max-w-[980px] rounded-2xl flex overflow-hidden"
                style={{
                    height: "min(88vh, 760px)",
                    background: '#181817',
                    border: '1px solid rgba(250,249,245,0.07)',
                    boxShadow: '0 24px 80px rgba(0,0,0,0.8)',
                }}
                onClick={e => e.stopPropagation()}
            >
                {/* ── Left: Video + Actions ── */}
                <div className="w-[300px] flex-shrink-0 flex flex-col" style={{ borderRight: '1px solid rgba(250,249,245,0.06)' }}>
                    {/* Video */}
                    <div className="relative flex-1 min-h-0 m-4 mb-3 rounded-xl overflow-hidden" style={{ background: '#111110' }}>
                        {getBestUrl(clip) ? (
                            <video
                                ref={videoRef}
                                src={getBestUrl(clip)!}
                                className="w-full h-full object-contain"
                                controls
                                playsInline
                                onTimeUpdate={handleTimeUpdate}
                            />
                        ) : (
                            <div className="flex items-center justify-center h-full">
                                <Play size={32} style={{ color: 'rgba(250,249,245,0.12)' }} />
                            </div>
                        )}

                        {/* Score Badge — top-left */}
                        <div
                            className="absolute top-2.5 left-2.5 backdrop-blur-sm rounded-xl px-2.5 py-1.5 flex items-baseline gap-0.5"
                            style={{ background: 'rgba(0,0,0,0.8)', border: '1px solid rgba(250,249,245,0.1)' }}
                        >
                            <span className="text-lg font-bold leading-none" style={{ color: scoreHex }}>
                                {score}
                            </span>
                            <span className="text-[10px] leading-none" style={{ color: '#ababab' }}>/100</span>
                        </div>

                        {/* Verdict Badge — top-right */}
                        {clip.standalone_result && (
                            <div className={`absolute top-2.5 right-2.5 rounded-full px-2 py-0.5 text-[9px] font-semibold uppercase tracking-widest border ${
                                clip.standalone_result === "pass"
                                    ? "bg-green-500/15 text-green-400 border-green-500/25"
                                    : "bg-yellow-500/15 text-yellow-400 border-yellow-500/25"
                            }`}>
                                {clip.standalone_result}
                            </div>
                        )}

                        {/* Approval indicator — bottom-right */}
                        {clip.is_successful === true && (
                            <div className="absolute bottom-2.5 right-2.5 bg-green-500/90 text-white p-1 rounded-full">
                                <Check className="w-3 h-3" />
                            </div>
                        )}
                        {clip.is_successful === false && (
                            <div className="absolute bottom-2.5 right-2.5 bg-red-500/90 text-white p-1 rounded-full">
                                <X className="w-3 h-3" />
                            </div>
                        )}
                    </div>

                    {/* Hook Text */}
                    <div className="px-4 pb-3 flex-shrink-0">
                        <p className="text-[9px] uppercase tracking-widest mb-1.5" style={{ color: '#ababab' }}>Hook</p>
                        <p className="text-xs leading-relaxed line-clamp-2" style={{ color: '#ababab' }}>
                            &ldquo;{clip.hook_text || "No hook text"}&rdquo;
                        </p>
                    </div>

                    {/* Score bar */}
                    <div className="px-4 pb-3 flex-shrink-0">
                        <div className="flex items-center justify-between mb-1">
                            <span className="text-[9px] uppercase tracking-widest" style={{ color: '#ababab' }}>Score</span>
                            <span className={`text-[10px] font-semibold ${getScoreColor(score)}`}>{score}/100</span>
                        </div>
                        <div className="h-1 rounded-full overflow-hidden" style={{ background: 'rgba(250,249,245,0.08)' }}>
                            <div
                                className={`h-full rounded-full transition-all ${getScoreBarColor(score)}`}
                                style={{ width: `${score}%` }}
                            />
                        </div>
                    </div>

                    {/* Action buttons */}
                    <div
                        className="flex-shrink-0 px-4 pb-4 space-y-1.5 pt-3"
                        style={{ borderTop: '1px solid rgba(250,249,245,0.06)' }}
                    >
                        <button
                            onClick={() => onDownload(clip.id)}
                            className="w-full flex items-center justify-center gap-2 py-2 rounded-xl font-medium transition-colors text-xs hover:bg-white/10"
                            style={{ background: 'rgba(250,249,245,0.06)', color: '#faf9f5', border: '1px solid rgba(250,249,245,0.08)' }}
                        >
                            <Download className="w-3.5 h-3.5" /> Download
                        </button>
                        <div className="flex gap-1.5">
                            <button
                                onClick={() => onApprove(clip.id)}
                                className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-xl text-xs font-medium transition-colors border ${
                                    clip.is_successful === true
                                        ? "bg-green-500/20 text-green-400 border-green-500/30"
                                        : "border-[rgba(250,249,245,0.08)] text-[rgba(250,249,245,0.4)] hover:border-green-500/30 hover:text-green-400"
                                }`}
                            >
                                <Check className="w-3 h-3" /> Approve
                            </button>
                            <button
                                onClick={() => onReject(clip.id)}
                                className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-xl text-xs font-medium transition-colors border ${
                                    clip.is_successful === false
                                        ? "bg-red-500/20 text-red-400 border-red-500/30"
                                        : "border-[rgba(250,249,245,0.08)] text-[rgba(250,249,245,0.4)] hover:border-red-500/30 hover:text-red-400"
                                }`}
                            >
                                <X className="w-3 h-3" /> Reject
                            </button>
                        </div>
                        <button
                            onClick={() => onPublish(clip.id)}
                            className={`w-full flex items-center justify-center gap-2 py-2 rounded-xl font-medium text-xs transition-colors border ${
                                clip.is_published
                                    ? "border-[rgba(250,249,245,0.08)] text-[rgba(250,249,245,0.4)] hover:text-[#faf9f5]"
                                    : "bg-white text-black border-white hover:bg-[#e5e5e5]"
                            }`}
                        >
                            <Upload className="w-3.5 h-3.5" />
                            {clip.is_published ? "Mark Unpublished" : "Mark Published"}
                        </button>
                        <OpenInEditorButton clip={clip} guestName={guestName} />
                    </div>
                </div>

                {/* ── Right: Transcript + Metadata ── */}
                <div className="flex-1 flex flex-col overflow-hidden min-w-0">
                    {/* Header */}
                    <div
                        className="flex-shrink-0 flex items-center justify-between px-5 py-4"
                        style={{ borderBottom: '1px solid rgba(250,249,245,0.06)' }}
                    >
                        <div className="flex items-center gap-2 min-w-0 mr-4">
                            <span className="text-sm font-semibold truncate" style={{ color: '#faf9f5' }}>
                                {clip.suggested_title || "Clip Details"}
                            </span>
                            <span
                                className="flex-shrink-0 text-[10px] px-2 py-0.5 rounded-full"
                                style={{ color: '#ababab', background: 'rgba(250,249,245,0.06)', border: '1px solid rgba(250,249,245,0.08)' }}
                            >
                                {formatDuration(clip.duration_s)}
                            </span>
                        </div>
                        <button
                            onClick={onClose}
                            className="flex-shrink-0 p-1.5 rounded-lg transition-colors hover:bg-white/5"
                            style={{ color: '#ababab' }}
                        >
                            <X className="w-4 h-4" />
                        </button>
                    </div>

                    {/* Scrollable right content */}
                    <div className="flex-1 overflow-y-auto">

                        {/* Transcript */}
                        <div className="p-5" style={{ borderBottom: '1px solid rgba(250,249,245,0.06)' }}>
                            <p className="text-[9px] uppercase tracking-widest mb-3" style={{ color: '#ababab' }}>Transcript</p>
                            <div
                                ref={transcriptContainerRef}
                                onScroll={handleTranscriptScroll}
                                className="h-52 overflow-y-auto rounded-xl p-4 scroll-smooth"
                                style={{
                                    background: '#111110',
                                    border: '1px solid rgba(250,249,245,0.06)',
                                    scrollbarWidth: "thin",
                                    scrollbarColor: "rgba(250,249,245,0.1) transparent",
                                }}
                            >
                                {transcriptLoading ? (
                                    <div className="flex items-center justify-center h-full">
                                        <p className="text-xs" style={{ color: '#ababab' }}>Loading transcript...</p>
                                    </div>
                                ) : transcriptWords.length === 0 ? (
                                    <div className="flex items-center justify-center h-full">
                                        <p className="text-xs" style={{ color: '#ababab' }}>No transcript available</p>
                                    </div>
                                ) : (
                                    <div className="leading-7">
                                        {transcriptSegments.map((seg, si) => {
                                            if (seg.type === "timestamp") {
                                                return (
                                                    <span key={`ts-${si}`} className="inline-block text-[10px] font-mono mr-2 mb-0.5 align-middle" style={{ color: '#ababab' }}>
                                                        {formatTranscriptTime(seg.time)}
                                                    </span>
                                                );
                                            }
                                            const { word, index } = seg;
                                            const isActive = index === currentWordIndex;
                                            return (
                                                <span
                                                    key={`w-${index}`}
                                                    ref={el => { wordRefs.current[index] = el; }}
                                                    className="inline mr-0.5 mb-0.5 px-0.5 py-0.5 rounded text-sm transition-colors duration-75"
                                                    style={{
                                                        background: isActive ? '#faf9f5' : 'transparent',
                                                        color: isActive ? '#141413' : 'rgba(250,249,245,0.7)',
                                                        fontWeight: isActive ? 500 : undefined,
                                                    }}
                                                >
                                                    {word.word}
                                                </span>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Quality Notes (fixable clips) */}
                        {clip.quality_notes && (
                            <div className="px-5 py-4" style={{ borderBottom: '1px solid rgba(250,249,245,0.06)' }}>
                                <p className="text-[9px] uppercase tracking-widest mb-2" style={{ color: '#ababab' }}>AI Notes</p>
                                <p
                                    className="text-xs leading-relaxed px-3 py-2.5 rounded-xl"
                                    style={{ color: '#ababab', background: '#111110', border: '1px solid rgba(250,249,245,0.06)' }}
                                >
                                    {clip.quality_notes}
                                </p>
                            </div>
                        )}

                        {/* Meta Row */}
                        <div className="px-5 py-4" style={{ borderBottom: '1px solid rgba(250,249,245,0.06)' }}>
                            <div className="flex gap-3">
                                <div className="flex-1 rounded-xl p-3" style={{ background: '#111110', border: '1px solid rgba(250,249,245,0.06)' }}>
                                    <p className="text-[9px] uppercase tracking-widest mb-1.5" style={{ color: '#ababab' }}>Posting Order</p>
                                    <p className="text-xl font-bold" style={{ color: '#faf9f5' }}>#{clip.posting_order || "—"}</p>
                                </div>
                                <div className="flex-1 rounded-xl p-3" style={{ background: '#111110', border: '1px solid rgba(250,249,245,0.06)' }}>
                                    <p className="text-[9px] uppercase tracking-widest mb-1.5" style={{ color: '#ababab' }}>Strategy</p>
                                    <p className="text-sm capitalize font-medium" style={{ color: '#faf9f5' }}>{clip.clip_strategy_role || "—"}</p>
                                    <p className="text-[10px] mt-0.5 capitalize" style={{ color: '#ababab' }}>role</p>
                                </div>
                            </div>
                        </div>

                        {/* YouTube Metadata */}
                        {(clip.suggested_title || clip.suggested_description) && (
                            <div className="px-5 py-4">
                                <p className="text-[9px] uppercase tracking-widest mb-3" style={{ color: '#ababab' }}>YouTube Metadata</p>
                                <div className="space-y-2">
                                    {clip.suggested_title && (
                                        <div className="rounded-xl p-3" style={{ background: '#111110', border: '1px solid rgba(250,249,245,0.06)' }}>
                                            <p className="text-[9px] uppercase tracking-widest mb-1.5" style={{ color: '#ababab' }}>Title</p>
                                            <p className="text-xs font-medium leading-relaxed" style={{ color: '#faf9f5' }}>{clip.suggested_title}</p>
                                        </div>
                                    )}
                                    {clip.suggested_description && (
                                        <div className="rounded-xl p-3" style={{ background: '#111110', border: '1px solid rgba(250,249,245,0.06)' }}>
                                            <p className="text-[9px] uppercase tracking-widest mb-1.5" style={{ color: '#ababab' }}>Description</p>
                                            <p className="text-xs leading-relaxed whitespace-pre-wrap" style={{ color: '#ababab' }}>{clip.suggested_description}</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

// ─── Main Page (wrapped in Suspense for useSearchParams) ──────────────────────

export default function ProjectsPage() {
    return (
        <Suspense fallback={<div className="min-h-screen bg-black" />}>
            <ProjectsContent />
        </Suspense>
    );
}

function ProjectsContent() {
    const searchParams = useSearchParams();
    const router = useRouter();
    const { channels, activeChannelId, isLoading: channelLoading } = useChannel();

    const jobIdParam = searchParams.get("job");
    const clipIdParam = searchParams.get("clip");

    const [jobs, setJobs] = useState<any[]>([]);
    const [clips, setClips] = useState<Clip[]>([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState<FilterType>("all");
    const [selectedJob, setSelectedJob] = useState<any | null>(null);
    const [selectedClip, setSelectedClip] = useState<Clip | null>(null);
    const [openMenuId, setOpenMenuId] = useState<string | null>(null);
    const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
    const urlRestoredRef = useRef(false);

    const fetchData = async (silent = false) => {
        if (!silent) setLoading(true);
        try {
            const [jobsRes, clipsRes] = await Promise.all([
                authFetch(`/jobs?channel_id=${activeChannelId}&limit=50`),
                authFetch(`/clips?channel_id=${activeChannelId}&limit=200`),
            ]);
            if (jobsRes.ok) setJobs(await jobsRes.json());
            if (clipsRes.ok) setClips(await clipsRes.json());
        } catch (err) { console.error(err); }
        finally { if (!silent) setLoading(false); }
    };

    useEffect(() => {
        if (channelLoading) return;
        if (activeChannelId) { urlRestoredRef.current = false; fetchData(); }
        else { setJobs([]); setClips([]); setLoading(false); }
    }, [activeChannelId, channelLoading]);

    // Auto-refresh while jobs are active
    useEffect(() => {
        if (!activeChannelId) return;
        const hasActive = jobs.some(j => ["processing", "queued", "running"].includes(j.status));
        if (!hasActive) return;
        const interval = setInterval(() => fetchData(true), 4000);
        return () => clearInterval(interval);
    }, [activeChannelId, jobs]);

    // Restore state from URL params after data loads
    useEffect(() => {
        if (urlRestoredRef.current || loading || !jobs.length) return;
        urlRestoredRef.current = true;
        if (jobIdParam) {
            const job = jobs.find(j => j.id === jobIdParam);
            if (job) {
                setSelectedJob(job);
                if (clipIdParam) {
                    const clip = clips.find(c => c.id === clipIdParam);
                    if (clip) setSelectedClip(clip);
                }
            }
        }
    }, [loading, jobs, clips, jobIdParam, clipIdParam]);

    // Navigation helpers
    const selectJob = useCallback((job: any) => {
        setSelectedJob(job);
        setSelectedClip(null);
        router.replace(`/dashboard/projects?job=${job.id}`);
    }, [router]);

    const selectClip = useCallback((clip: Clip) => {
        setSelectedClip(clip);
        router.replace(`/dashboard/projects?job=${clip.job_id}&clip=${clip.id}`);
    }, [router]);

    const closeClip = useCallback(() => {
        setSelectedClip(null);
        if (selectedJob) router.replace(`/dashboard/projects?job=${selectedJob.id}`);
    }, [router, selectedJob]);

    const goBack = useCallback(() => {
        setSelectedJob(null);
        setSelectedClip(null);
        router.replace("/dashboard/projects");
    }, [router]);

    // Actions
    const handleDeleteProject = async (jobId: string) => {
        try {
            const res = await authFetch(`/jobs/${jobId}`, { method: "DELETE" });
            if (res.ok) {
                setJobs(jobs.filter(j => j.id !== jobId));
                if (selectedJob?.id === jobId) { setSelectedJob(null); router.replace("/dashboard/projects"); }
                toast.success('Project deleted.');
            } else {
                toast.error('Failed to delete project.');
            }
        } catch { toast.error('Failed to delete project.'); }
        setDeleteConfirmId(null);
    };

    const handleApprove = async (id: string) => {
        const clip = clips.find(c => c.id === id);
        if (!clip) return;
        const endpoint = clip.is_successful === true ? `/clips/${id}/unset-approval` : `/clips/${id}/approve`;
        try {
            const res = await authFetch(endpoint, { method: "PATCH" });
            if (res.ok) {
                const newVal = clip.is_successful === true ? null : true;
                const updated = clips.map(c => c.id === id ? { ...c, is_successful: newVal } : c);
                setClips(updated);
                if (selectedClip?.id === id) setSelectedClip({ ...selectedClip, is_successful: newVal });
                toast.success(newVal === true ? 'Clip approved.' : 'Approval removed.');
            } else { toast.error('Failed to update clip.'); }
        } catch { toast.error('Failed to update clip.'); }
    };

    const handleReject = async (id: string) => {
        const clip = clips.find(c => c.id === id);
        if (!clip) return;
        const endpoint = clip.is_successful === false ? `/clips/${id}/unset-approval` : `/clips/${id}/reject`;
        try {
            const res = await authFetch(endpoint, { method: "PATCH" });
            if (res.ok) {
                const newVal = clip.is_successful === false ? null : false;
                const updated = clips.map(c => c.id === id ? { ...c, is_successful: newVal } : c);
                setClips(updated);
                if (selectedClip?.id === id) setSelectedClip({ ...selectedClip, is_successful: newVal });
                toast.success(newVal === false ? 'Clip rejected.' : 'Rejection removed.');
            } else { toast.error('Failed to update clip.'); }
        } catch { toast.error('Failed to update clip.'); }
    };

    const handlePublish = async (id: string) => {
        const clip = clips.find(c => c.id === id) || selectedClip;
        if (!clip) return;
        const endpoint = clip.is_published ? `/clips/${id}/unpublish` : `/clips/${id}/publish`;
        try {
            const res = await authFetch(endpoint, { method: "PATCH" });
            if (res.ok) {
                const newVal = !clip.is_published;
                const updated = clips.map(c => c.id === id ? { ...c, is_published: newVal } : c);
                setClips(updated);
                if (selectedClip?.id === id) setSelectedClip({ ...selectedClip, is_published: newVal });
                toast.success(newVal ? 'Clip marked as published.' : 'Clip unpublished.');
            } else { toast.error('Failed to update clip.'); }
        } catch { toast.error('Failed to update clip.'); }
    };

    const handleDownload = (id: string) => {
        const clip = clips.find(c => c.id === id) || selectedClip;
        if (clip) { const u = getBestUrl(clip); if (u) window.open(u, "_blank"); }
    };

    // Derived data
    const activeJobs = jobs.filter(j => ["processing", "queued", "running"].includes(j.status));
    const completedJobs = jobs.filter(j => ["completed", "failed", "error"].includes(j.status));

    const filteredProjects = completedJobs.filter(job => {
        const jobClips = clips.filter(c => c.job_id === job.id);
        if (filter === "all") return true;
        if (filter === "successful") return jobClips.some(c => c.is_successful === true);
        if (filter === "failed") return jobClips.some(c => c.is_successful === false);
        if (filter === "published") return jobClips.some(c => c.is_published === true);
        return true;
    });

    const projectClips = selectedJob ? clips.filter(c => c.job_id === selectedJob.id) : [];
    const filteredProjectClips = projectClips.filter(clip => {
        if (filter === "all") return true;
        if (filter === "successful") return clip.is_successful === true;
        if (filter === "failed") return clip.is_successful === false;
        if (filter === "published") return clip.is_published === true;
        return true;
    });

    // No channel
    if (!channelLoading && !loading && !activeChannelId) {
        return (
            <div className="min-h-screen flex items-center justify-center p-8" style={{ background: '#141413' }}>
                <div className="text-center max-w-sm">
                    <div
                        className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-5"
                        style={{ background: '#181817', border: '1px solid rgba(250,249,245,0.07)' }}
                    >
                        <FolderOpen className="w-6 h-6" style={{ color: '#ababab' }} />
                    </div>
                    <h2 className="text-lg font-semibold mb-2" style={{ color: '#faf9f5' }}>No channel yet</h2>
                    <p className="text-sm mb-6" style={{ color: '#ababab' }}>Create a channel first to start managing your projects.</p>
                    <Link href="/dashboard/settings" className="inline-flex items-center gap-2 bg-white hover:bg-[#e5e5e5] text-black text-sm font-medium px-5 py-2.5 rounded-xl transition-colors">
                        Add Channel
                    </Link>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen p-6 pb-24" style={{ background: '#141413', color: '#faf9f5' }}>
            {/* Header */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
                <div>
                    {selectedJob ? (
                        <div>
                            <button
                                onClick={goBack}
                                className="inline-flex items-center gap-1.5 text-xs mb-2 transition-colors hover:!text-[#faf9f5]"
                                style={{ color: '#ababab' }}
                            >
                                <ArrowLeft className="w-3.5 h-3.5" /> Projects
                            </button>
                            <div className="flex items-center gap-2">
                                <h1 className="text-2xl font-semibold" style={{ color: '#faf9f5' }}>{selectedJob.video_title || "Project Clips"}</h1>
                                <ChevronRight className="w-4 h-4" style={{ color: '#ababab' }} />
                                <span className="text-sm" style={{ color: '#ababab' }}>{projectClips.length} clips</span>
                            </div>
                            <p className="text-xs mt-0.5" style={{ color: '#ababab' }}>{formatDate(selectedJob.created_at)}</p>
                        </div>
                    ) : (
                        <div>
                            <h1 className="text-2xl font-semibold" style={{ color: '#faf9f5' }}>Projects</h1>
                            <p className="text-sm mt-0.5" style={{ color: '#ababab' }}>All your video projects in one place</p>
                        </div>
                    )}
                </div>

                {/* Filter Tabs */}
                <div
                    className="flex items-center p-1 rounded-xl gap-1"
                    style={{ background: 'rgba(250,249,245,0.03)' }}
                >
                    {(["all", "successful", "failed", "published"] as FilterType[]).map(f => (
                        <button
                            key={f}
                            onClick={() => setFilter(f)}
                            className="px-4 py-2 rounded-lg text-sm capitalize font-medium transition-all"
                            style={{
                                background: filter === f ? 'rgba(250,249,245,0.08)' : 'transparent',
                                color: filter === f ? '#faf9f5' : 'rgba(250,249,245,0.4)',
                            }}
                        >
                            {f.charAt(0).toUpperCase() + f.slice(1)}
                        </button>
                    ))}
                </div>
            </div>

            {/* Content */}
            {loading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    {[...Array(8)].map((_, i) => (
                        <div key={i} className="rounded-2xl overflow-hidden" style={{ background: '#181817' }}>
                            <div className="aspect-video shimmer-load" style={{ background: 'rgba(250,249,245,0.06)' }} />
                            <div className="p-4 space-y-2">
                                <div className="h-3 rounded w-3/4 animate-pulse" style={{ background: 'rgba(250,249,245,0.06)' }} />
                                <div className="h-2 rounded w-1/2 animate-pulse" style={{ background: 'rgba(250,249,245,0.04)' }} />
                            </div>
                        </div>
                    ))}
                </div>
            ) : !selectedJob ? (
                /* ── Projects grid ── */
                <div>
                    {/* Active Jobs */}
                    {activeJobs.length > 0 && (
                        <div className="mb-8">
                            <div className="flex items-center gap-2 mb-4">
                                <h2 className="text-sm font-medium" style={{ color: '#ababab' }}>Active Jobs</h2>
                                <span className="w-2 h-2 rounded-full pulse-dot" style={{ background: '#faf9f5' }} />
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                {activeJobs.map(job => {
                                    const progress = job.progress_pct ?? job.progress ?? 0;
                                    return (
                                        <div key={job.id} className="rounded-2xl overflow-hidden" style={{ background: '#181817' }}>
                                            <div className="aspect-video flex items-center justify-center p-4 text-center" style={{ background: '#1c1c1b' }}>
                                                <div>
                                                    <div className="flex items-center justify-center gap-2 mb-2">
                                                        <div className="w-1.5 h-1.5 rounded-full pulse-dot" style={{ background: '#faf9f5' }} />
                                                        <span className="text-[10px] uppercase tracking-wider" style={{ color: '#ababab' }}>Processing</span>
                                                    </div>
                                                    <p className="text-xs" style={{ color: '#faf9f5' }}>
                                                        {getStepLabel(job.current_step || job.step)} {progress > 0 && `(${progress}%)`}
                                                    </p>
                                                </div>
                                            </div>
                                            <div className="p-3" style={{ borderTop: '1px solid rgba(250,249,245,0.06)' }}>
                                                <p className="text-xs font-medium truncate" style={{ color: '#faf9f5' }}>{job.video_title || "Untitled"}</p>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {/* Completed Projects */}
                    {filteredProjects.length === 0 ? (
                        <div
                            className="flex flex-col items-center justify-center py-20 rounded-2xl"
                            style={{ background: '#181817' }}
                        >
                            <FileVideo className="w-12 h-12 mb-3" style={{ color: 'rgba(250,249,245,0.1)' }} />
                            <p className="text-sm" style={{ color: '#ababab' }}>No projects yet. Start a new job to create clips.</p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                            {filteredProjects.map(job => {
                                const jobClips = clips.filter(c => c.job_id === job.id);
                                const firstClip = jobClips.find(c => c.file_url);
                                return (
                                    <div
                                        key={job.id}
                                        className="group rounded-2xl cursor-pointer hover:-translate-y-1 transition-all duration-300"
                                        style={{ background: '#181817', overflow: 'visible', position: 'relative', zIndex: openMenuId === job.id ? 50 : 1 }}
                                        onClick={() => selectJob(job)}
                                        onMouseLeave={() => setOpenMenuId(null)}
                                    >
                                        <div
                                            className="relative aspect-video flex items-center justify-center rounded-t-2xl overflow-hidden"
                                            style={{ background: '#1c1c1b' }}
                                        >
                                            {firstClip && getBestUrl(firstClip) ? (
                                                <video
                                                    src={getBestUrl(firstClip)!}
                                                    className="w-full h-full object-cover"
                                                    muted loop playsInline preload="metadata"
                                                    onMouseEnter={e => e.currentTarget.play()}
                                                    onMouseLeave={e => { e.currentTarget.pause(); e.currentTarget.currentTime = 0; }}
                                                />
                                            ) : (
                                                <Play size={20} style={{ color: 'rgba(250,249,245,0.15)' }} className="group-hover:opacity-60 transition-opacity" />
                                            )}
                                            <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors" />
                                            {/* More button — overlay on thumbnail */}
                                            <div className="absolute top-2.5 right-2.5" style={{ zIndex: 9999 }}>
                                                <button
                                                    className="w-7 h-7 rounded-lg flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                                                    style={{ background: 'rgba(0,0,0,0.6)', color: '#ababab' }}
                                                    onClick={e => { e.stopPropagation(); setOpenMenuId(openMenuId === job.id ? null : job.id); }}
                                                >
                                                    <MoreHorizontal size={14} />
                                                </button>
                                                <div
                                                    className="absolute right-0 top-full mt-1 rounded-xl shadow-2xl w-36 overflow-hidden py-1"
                                                    style={{
                                                        background: '#1c1c1b',
                                                        border: '1px solid rgba(250,249,245,0.08)',
                                                        zIndex: 9999,
                                                        opacity: openMenuId === job.id ? 1 : 0,
                                                        transform: openMenuId === job.id ? 'scale(1) translateY(0)' : 'scale(0.95) translateY(-4px)',
                                                        pointerEvents: openMenuId === job.id ? 'auto' : 'none',
                                                        transition: 'opacity 150ms ease, transform 150ms ease',
                                                        transformOrigin: 'top right',
                                                    }}
                                                >
                                                    <button
                                                        className="w-full text-left px-4 py-2.5 text-xs font-medium hover:bg-white/5 transition-colors"
                                                        style={{ color: '#ababab' }}
                                                        onClick={e => { e.stopPropagation(); setOpenMenuId(null); selectJob(job); }}
                                                    >
                                                        View Clips
                                                    </button>
                                                    <button
                                                        className="w-full text-left px-4 py-2.5 text-xs font-medium hover:bg-red-500/10 transition-colors text-red-400"
                                                        onClick={e => { e.stopPropagation(); setOpenMenuId(null); setDeleteConfirmId(job.id); }}
                                                    >
                                                        Delete
                                                    </button>
                                                </div>
                                            </div>
                                        </div>
                                        <div className="p-4">
                                            <p className="text-sm font-medium truncate" style={{ color: '#faf9f5' }}>{job.video_title || "Untitled"}</p>
                                            <div className="flex items-center gap-1.5 mt-1 text-[10px]" style={{ color: '#ababab' }}>
                                                <span>{jobClips.length} clips</span>
                                                <span>·</span>
                                                <span>{formatDate(job.created_at)}</span>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            ) : (
                /* ── Clips grid for a project ── */
                <div>
                    {filteredProjectClips.length === 0 ? (
                        <div
                            className="flex flex-col items-center justify-center py-20 rounded-2xl"
                            style={{ background: '#181817' }}
                        >
                            <p className="text-sm" style={{ color: '#ababab' }}>No clips found</p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                            {filteredProjectClips.map(clip => {
                                const score = clip.standalone_score ?? 0;
                                return (
                                    <div
                                        key={clip.id}
                                        className="rounded-2xl overflow-hidden cursor-pointer transition-all group flex flex-col hover:-translate-y-1 duration-300"
                                        style={{ background: '#181817' }}
                                        onClick={() => selectClip(clip)}
                                    >
                                        <div
                                            className="relative aspect-[9/16] overflow-hidden flex items-center justify-center"
                                            style={{ background: '#1c1c1b' }}
                                        >
                                            {getBestUrl(clip) ? (
                                                <video src={getBestUrl(clip)!} className="w-full h-full object-cover" muted playsInline preload="metadata" />
                                            ) : (
                                                <Play size={20} style={{ color: 'rgba(250,249,245,0.15)' }} />
                                            )}
                                            {/* Duration */}
                                            <div
                                                className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded text-[10px]"
                                                style={{ background: 'rgba(0,0,0,0.75)', color: '#faf9f5' }}
                                            >
                                                {formatDuration(clip.duration_s)}
                                            </div>
                                            {/* Score pill */}
                                            <div
                                                className={`absolute top-2 left-2 rounded-lg px-1.5 py-0.5 text-[10px] font-bold ${getScoreColor(score)}`}
                                                style={{ background: 'rgba(0,0,0,0.75)' }}
                                            >
                                                {score}
                                            </div>
                                            {/* Approval indicator */}
                                            {clip.is_successful === true && (
                                                <div className="absolute top-2 right-2 bg-green-500/90 text-white p-0.5 rounded-full">
                                                    <Check className="w-3 h-3" />
                                                </div>
                                            )}
                                            {clip.is_successful === false && (
                                                <div className="absolute top-2 right-2 bg-red-500/90 text-white p-0.5 rounded-full">
                                                    <X className="w-3 h-3" />
                                                </div>
                                            )}
                                        </div>
                                        <div className="p-3 flex flex-col flex-1">
                                            <p
                                                className="text-[10px] line-clamp-2 flex-1 leading-relaxed"
                                                style={{ color: '#ababab' }}
                                            >
                                                &ldquo;{clip.hook_text || "No hook text"}&rdquo;
                                            </p>
                                            <div className="flex items-center justify-between mt-2">
                                                <span className="text-[9px] capitalize" style={{ color: '#ababab' }}>{clip.clip_strategy_role || "—"}</span>
                                                <span className="text-[9px]" style={{ color: '#ababab' }}>#{clip.posting_order || "—"}</span>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            )}

            {/* Clip Modal */}
            {selectedClip && (
                <ClipModal
                    clip={selectedClip}
                    guestName={selectedJob?.guest_name}
                    onClose={closeClip}
                    onApprove={handleApprove}
                    onReject={handleReject}
                    onPublish={handlePublish}
                    onDownload={handleDownload}
                />
            )}

            {/* ── Delete Confirmation Modal ── */}
            {deleteConfirmId && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center p-4"
                    style={{ backdropFilter: 'blur(8px)', background: 'rgba(0,0,0,0.6)' }}
                    onClick={() => setDeleteConfirmId(null)}
                >
                    <div
                        className="relative w-full max-w-md rounded-2xl p-7"
                        style={{
                            background: 'rgba(30,29,28,0.72)',
                            backdropFilter: 'blur(32px) saturate(180%)',
                            WebkitBackdropFilter: 'blur(32px) saturate(180%)',
                            boxShadow: '0 8px 48px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.06)',
                        }}
                        onClick={e => e.stopPropagation()}
                    >
                        {/* Close */}
                        <button
                            className="absolute top-4 right-4 w-7 h-7 rounded-lg flex items-center justify-center transition-colors hover:bg-white/5"
                            style={{ color: '#ababab' }}
                            onClick={() => setDeleteConfirmId(null)}
                        >
                            <X size={14} />
                        </button>

                        <div className="mb-1">
                            <p className="text-base font-semibold mb-2" style={{ color: '#faf9f5' }}>Delete project?</p>
                            <p className="text-sm" style={{ color: '#ababab' }}>
                                This will permanently delete the project and all its clips. This action cannot be undone.
                            </p>
                        </div>

                        <div className="flex items-center justify-end gap-2 mt-6">
                            <button
                                className="px-4 py-2 text-sm font-medium rounded-xl transition-colors hover:bg-white/5"
                                style={{ color: '#faf9f5', border: '1px solid rgba(250,249,245,0.12)' }}
                                onClick={() => setDeleteConfirmId(null)}
                            >
                                Cancel
                            </button>
                            <button
                                className="px-4 py-2 text-sm font-medium rounded-xl transition-colors hover:brightness-110"
                                style={{ background: '#ef4444', color: '#fff' }}
                                onClick={() => handleDeleteProject(deleteConfirmId)}
                            >
                                Delete
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
