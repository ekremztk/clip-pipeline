"use client";

/**
 * The clip detail view — player, transcript, metadata, review controls — plus
 * the small helpers that describe a clip.
 *
 * Lifted out of the projects page unchanged so the batch pages can open the same
 * screen. Clicking a clip inside a batch used to jump straight to the raw video
 * file, which skipped everything a clip is judged by.
 */

import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import {
    Download, Check, X, Play, FileVideo, Scissors, ChevronRight, Upload,
} from "lucide-react";
import Link from "next/link";
import { authFetch } from "@/lib/api";
import { toast } from "@/lib/toast";

export interface Clip {
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
    stock_review_status?: "unreviewed" | "selected" | "rejected" | "posted";
    stock_review_note?: string | null;
    stock_batch_id?: string | null;
    main_person?: string | null;
}

export interface TranscriptWord {
    word: string;
    start: number;
    end: number;
}

// Returns the best available video URL: captioned > reframed > raw 16:9
export const getBestUrl = (clip: Clip): string | null =>
    clip.video_captioned_path || clip.video_reframed_path || clip.file_url || null;

export const formatDuration = (seconds: number) => {
    if (!seconds) return "0:00";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
};

export const formatTranscriptTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
};

export const getScoreColor = (score: number) => {
    if (score >= 80) return "text-green-400";
    if (score >= 60) return "text-yellow-400";
    return "text-red-400";
};

export const getScoreBarColor = (score: number) => {
    if (score >= 80) return "bg-green-500";
    if (score >= 60) return "bg-yellow-500";
    return "bg-red-500";
};

export const getScoreHex = (score: number) => {
    if (score >= 80) return "#4ade80";
    if (score >= 60) return "#facc15";
    return "#f87171";
};

// ─── Open in Editor Button ────────────────────────────────────────────────────

export const OpenInEditorButton = ({ clip, targetGuest }: { clip: Clip; targetGuest?: string | null }) => {
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
    if (targetGuest) params.set("clipGuestName", targetGuest);
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
    targetGuest?: string | null;
    onClose: () => void;
    onApprove: (id: string) => void;
    onReject: (id: string) => void;
    onPublish: (id: string) => void;
    onDownload: (id: string) => void;
    onStockReview: (id: string, status: "unreviewed" | "selected" | "rejected" | "posted", note: string) => Promise<void>;
}

export function ClipModal({ clip, targetGuest, onClose, onApprove, onReject, onPublish, onDownload, onStockReview }: ClipModalProps) {
    const videoRef = useRef<HTMLVideoElement>(null);
    const transcriptContainerRef = useRef<HTMLDivElement>(null);
    const wordRefs = useRef<(HTMLSpanElement | null)[]>([]);

    const [transcriptWords, setTranscriptWords] = useState<TranscriptWord[]>([]);
    const [transcriptLoading, setTranscriptLoading] = useState(true);
    const [currentTime, setCurrentTime] = useState(0);
    const [userScrolling, setUserScrolling] = useState(false);
    const [stockReviewStatus, setStockReviewStatus] = useState<"unreviewed" | "selected" | "rejected" | "posted">(clip.stock_review_status || "unreviewed");
    const [stockReviewNote, setStockReviewNote] = useState(clip.stock_review_note || "");
    const [stockReviewSaving, setStockReviewSaving] = useState(false);
    const userScrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    useEffect(() => {
        setStockReviewStatus(clip.stock_review_status || "unreviewed");
        setStockReviewNote(clip.stock_review_note || "");
    }, [clip.id, clip.stock_review_status, clip.stock_review_note]);

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

    const saveStockReview = useCallback(async (status = stockReviewStatus, note = stockReviewNote) => {
        setStockReviewSaving(true);
        try {
            await onStockReview(clip.id, status, note);
            setStockReviewStatus(status);
        } catch {
            // Toast is handled by the parent action.
        } finally {
            setStockReviewSaving(false);
        }
    }, [clip.id, onStockReview, stockReviewNote, stockReviewStatus]);

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
                        <OpenInEditorButton clip={clip} targetGuest={targetGuest} />
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

                        {(clip.stock_batch_id || clip.main_person) && (
                            <div className="px-5 py-4" style={{ borderBottom: '1px solid rgba(250,249,245,0.06)' }}>
                                <div className="flex items-center justify-between gap-3 mb-3">
                                    <p className="text-[9px] uppercase tracking-widest" style={{ color: '#ababab' }}>Stock Review</p>
                                    {stockReviewSaving && <span className="text-[10px]" style={{ color: '#ababab' }}>Saving...</span>}
                                </div>
                                <div className="grid grid-cols-4 gap-1.5 mb-2.5">
                                    {(["unreviewed", "selected", "rejected", "posted"] as const).map(status => (
                                        <button
                                            key={status}
                                            onClick={() => saveStockReview(status, stockReviewNote)}
                                            className="py-1.5 rounded-lg text-[10px] font-medium capitalize transition-colors"
                                            style={{
                                                background: stockReviewStatus === status ? '#faf9f5' : '#111110',
                                                color: stockReviewStatus === status ? '#141413' : '#ababab',
                                                border: '1px solid rgba(250,249,245,0.08)',
                                            }}
                                        >
                                            {status}
                                        </button>
                                    ))}
                                </div>
                                <textarea
                                    value={stockReviewNote}
                                    onChange={e => setStockReviewNote(e.target.value)}
                                    onKeyDown={e => {
                                        if (e.key === 'Enter' && !e.shiftKey) {
                                            e.preventDefault();
                                            saveStockReview(stockReviewStatus, stockReviewNote);
                                        }
                                    }}
                                    placeholder="Why selected or rejected?"
                                    rows={2}
                                    className="w-full resize-none rounded-xl px-3 py-2 text-xs outline-none"
                                    style={{
                                        background: '#111110',
                                        color: '#faf9f5',
                                        border: '1px solid rgba(250,249,245,0.08)',
                                    }}
                                />
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
