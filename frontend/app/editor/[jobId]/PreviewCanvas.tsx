"use client";

// EDITOR MODULE — Isolated module, no dependencies on other app files

import React, { useRef, useEffect, useState, useMemo } from 'react';
import { Player, PlayerRef } from '@remotion/player';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, Video } from 'remotion';
import { useEditorStore, EditorStoreType, getEffectiveCropX } from '@/lib/editor/store';
import { Play, Pause } from 'lucide-react';
import { SubtitleWord, OverlayTrackItem } from '@/lib/editor/types';

// ============================================================================
// REMOTION COMPOSITION
// ============================================================================
const VideoComposition: React.FC<{ sourceVideoUrl: string }> = ({ sourceVideoUrl }) => {
    if (!sourceVideoUrl) {
        return <div style={{ width: '100%', height: '100%', background: '#0f0f0f' }} />
    }

    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();
    const currentTimeSec = frame / fps;

    const videoTrack = useEditorStore((state: EditorStoreType) => state.videoTrack[0]);
    const subtitleTrack = useEditorStore((state: EditorStoreType) => state.subtitleTrack[0]);
    const overlayTrack = useEditorStore((state: EditorStoreType) => state.overlayTrack);

    // Filter active subtitles
    const activeWords = useMemo(() => {
        if (!subtitleTrack) return [];
        return subtitleTrack.words.filter((w: SubtitleWord) => currentTimeSec >= w.start && currentTimeSec <= w.end);
    }, [subtitleTrack, currentTimeSec]);

    // Filter active overlays
    const activeOverlays = useMemo(() => {
        return overlayTrack.filter((o: OverlayTrackItem) => currentTimeSec >= o.start && currentTimeSec <= o.end);
    }, [overlayTrack, currentTimeSec]);

    // Non-reactive read — does NOT trigger re-render
    const { cropSegments, cropOverrides } = useEditorStore.getState();
    const effectiveCropX = getEffectiveCropX(currentTimeSec, cropSegments, cropOverrides);

    return (
        <AbsoluteFill style={{ backgroundColor: '#000' }}>
            <Video
                src={sourceVideoUrl}
                style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'cover',
                    // objectPosition maps cropX directly to a percentage:
                    // 0.0 → "0% center" (leftmost), 0.5 → "50% center" (center), 1.0 → "100% center" (rightmost)
                    objectPosition: `${effectiveCropX * 100}% center`,
                    transition: 'object-position 0.3s ease-in-out',
                    // The transition creates smooth camera pan between speakers.
                    // This is purely a CSS preview effect — actual EMA smoothing is done by FFmpeg backend.
                }}
            />

            {/* Overlays */}
            {activeOverlays.map((overlay: OverlayTrackItem) => {
                let top = '50%';
                let transformY = '-50%';
                if (overlay.position === 'top') { top = '15%'; transformY = '0'; }
                if (overlay.position === 'bottom') { top = '85%'; transformY = '-100%'; }

                return (
                    <div
                        key={overlay.id}
                        style={{
                            position: 'absolute',
                            top,
                            left: '50%',
                            transform: `translate(-50%, ${transformY})`,
                            backgroundColor: overlay.backgroundColor || '#ffffff',
                            color: overlay.textColor || '#000000',
                            padding: '24px 48px',
                            borderRadius: '16px',
                            fontSize: '48px',
                            fontWeight: 'bold',
                            textAlign: 'center',
                            boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
                            maxWidth: '80%'
                        }}
                    >
                        {String(overlay.text)}
                    </div>
                );
            })}

            {/* Subtitles */}
            {activeWords.length > 0 && subtitleTrack && (
                <div style={{
                    position: 'absolute',
                    bottom: subtitleTrack.style.position === 'bottom' ? '15%' : subtitleTrack.style.position === 'top' ? '85%' : '50%',
                    left: '0',
                    right: '0',
                    textAlign: 'center',
                    display: 'flex',
                    flexDirection: 'row',
                    justifyContent: 'center',
                    flexWrap: 'wrap',
                    gap: '16px',
                    padding: '0 48px',
                    transform: subtitleTrack.style.position === 'center' ? 'translateY(-50%)' : 'none'
                }}>
                    {activeWords.map((w: SubtitleWord, i: number) => (
                        <span key={i} style={{
                            fontFamily: subtitleTrack.style.fontFamily,
                            fontSize: `${subtitleTrack.style.fontSize}px`,
                            color: subtitleTrack.style.color.replace('&H00', '#'), // Very basic conversion
                            WebkitTextStroke: `${subtitleTrack.style.outlineWidth}px ${subtitleTrack.style.outlineColor.replace('&H00', '#')}`,
                            textShadow: `0 4px 8px rgba(0,0,0,0.5)`,
                            fontWeight: 900,
                            textTransform: 'uppercase'
                        }}>
                            {String(w.word)}
                        </span>
                    ))}
                </div>
            )}
        </AbsoluteFill>
    );
};

// ============================================================================
// MAIN PREVIEW COMPONENT
// ============================================================================
export default function PreviewCanvas({ sourceVideoUrl }: { sourceVideoUrl: string }) {
    const playerRef = useRef<PlayerRef>(null);
    const duration = useEditorStore((state: EditorStoreType) => state.duration);
    const currentTime = useEditorStore((state: EditorStoreType) => state.currentTime);
    const setCurrentTime = useEditorStore((state: EditorStoreType) => state.setCurrentTime);
    const isPlaying = useEditorStore((state: EditorStoreType) => state.isPlaying);
    const setIsPlaying = useEditorStore((state: EditorStoreType) => state.setIsPlaying);

    const [scrubberValue, setScrubberValue] = useState(0);
    const isScrubbing = useRef(false);
    const fps = 30;
    const safeDuration = (typeof duration === 'number' && duration > 0) ? duration : 1;
    const durationInFrames = Math.max(1, Math.ceil(safeDuration * 30));

    // Rule 1: Remotion owns time when playing
    useEffect(() => {
        const player = playerRef.current;
        if (!player) return;

        const onTimeUpdate = () => {
            if (isPlaying && !isScrubbing.current) {
                const currentFrame = player.getCurrentFrame();
                const newTime = currentFrame / fps;
                setCurrentTime(newTime);
                setScrubberValue(newTime);
            }
        };

        player.addEventListener('frameupdate', onTimeUpdate);
        return () => player.removeEventListener('frameupdate', onTimeUpdate);
    }, [isPlaying, fps, setCurrentTime]);

    // Rule 2: Zustand owns time when NOT playing (e.g. external seek)
    useEffect(() => {
        if (!isPlaying && !isScrubbing.current && playerRef.current) {
            const targetFrame = Math.floor(currentTime * fps);
            if (playerRef.current.getCurrentFrame() !== targetFrame) {
                playerRef.current.seekTo(targetFrame);
                setScrubberValue(currentTime);
            }
        }
    }, [currentTime, isPlaying, fps]);

    // Handle Play/Pause sync
    useEffect(() => {
        if (playerRef.current) {
            if (isPlaying) playerRef.current.play();
            else playerRef.current.pause();
        }
    }, [isPlaying]);

    // Keyboard Spacebar
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.code === 'Space' && e.target === document.body) {
                e.preventDefault();
                setIsPlaying(!isPlaying);
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [isPlaying, setIsPlaying]);

    const formatTime = (seconds: number) => {
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    };

    return (
        <div className="w-full h-full flex flex-col bg-[#0f0f0f] items-center justify-center p-4">

            {/* Canvas Container: maintain 9:16 aspect ratio */}
            <div className="relative flex-1 w-full max-w-[360px] min-h-[400px] flex items-center justify-center">
                <div className="relative w-full" style={{ paddingBottom: '177.78%' /* 16:9 ratio */ }}>
                    <div className="absolute inset-0 bg-black rounded-lg overflow-hidden border border-[#2a2a2a] shadow-2xl">
                        {!sourceVideoUrl ? (
                            <div className="w-full h-full bg-[#111] flex items-center justify-center">
                                <div className="text-center px-6">
                                    <div className="text-4xl mb-3">🎥</div>
                                    <p className="text-[#6b7280] text-sm font-medium">No video loaded</p>
                                    <p className="text-[#4b5563] text-xs mt-1">Go to Media tab to add a video</p>
                                </div>
                            </div>
                        ) : durationInFrames >= 1 ? (
                            <Player
                                ref={playerRef}
                                component={VideoComposition}
                                inputProps={{ sourceVideoUrl }}
                                durationInFrames={durationInFrames}
                                compositionWidth={1080}
                                compositionHeight={1920}
                                fps={fps}
                                style={{ width: '100%', height: '100%' }}
                                controls={false}
                                acknowledgeRemotionLicense
                            />
                        ) : (
                            <div className="w-full h-full bg-[#111] flex items-center justify-center">
                                <div className="text-center">
                                    <div className="w-8 h-8 border-2 border-[#6366f1] border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                                    <p className="text-[#6b7280] text-xs">Loading video...</p>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Custom Controls */}
            <div className="w-full max-w-md mt-6 flex flex-col space-y-3">
                <div className="flex items-center space-x-4">
                    <button
                        onClick={() => setIsPlaying(!isPlaying)}
                        className="w-10 h-10 rounded-full bg-[#6366f1] hover:bg-[#4f46e5] flex items-center justify-center text-white transition-colors"
                        aria-label={isPlaying ? "Pause" : "Play"}
                    >
                        {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-1" />}
                    </button>

                    <div className="text-sm font-mono text-[#f1f1f1]">
                        {formatTime(scrubberValue)} <span className="text-[#6b7280]">/ {formatTime(safeDuration)}</span>
                    </div>
                </div>

                <div className="w-full relative h-6 flex items-center">
                    <input
                        type="range"
                        min={0}
                        max={safeDuration}
                        step={0.01}
                        value={scrubberValue}
                        onMouseDown={() => {
                            isScrubbing.current = true;
                            setIsPlaying(false);
                        }}
                        onChange={(e) => {
                            const val = parseFloat(e.target.value);
                            setScrubberValue(val);
                            if (playerRef.current) {
                                playerRef.current.seekTo(Math.floor(val * fps));
                            }
                        }}
                        onMouseUp={(e) => {
                            isScrubbing.current = false;
                            const val = parseFloat((e.target as HTMLInputElement).value);
                            setCurrentTime(val); // Sync back to Zustand
                        }}
                        className="w-full h-1.5 bg-[#2a2a2a] rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:bg-[#6366f1] [&::-webkit-slider-thumb]:rounded-full focus:outline-none"
                    />
                </div>
            </div>

        </div>
    );
}
