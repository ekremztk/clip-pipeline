"use client";

// EDITOR MODULE — Isolated module, no dependencies on other app files

import React, { useState, useEffect } from 'react';
import { useEditorStore, EditorStoreType } from '@/lib/editor/store';
import { RightPanelTab, OverlayTrackItem } from '@/lib/editor/types';
import { Settings, Type, LayoutTemplate, Volume2, Plus, Trash2 } from 'lucide-react';

export default function RightPanel() {
    const activeTab = useEditorStore((state: EditorStoreType) => state.ui.rightPanelTab);
    const setUI = useEditorStore((state: EditorStoreType) => state.setUI);

    const tabs: { id: RightPanelTab; label: string; icon: React.ReactNode }[] = [
        { id: 'transform', label: 'Transform', icon: <Settings className="w-4 h-4" /> },
        { id: 'subtitle', label: 'Subtitle', icon: <Type className="w-4 h-4" /> },
        { id: 'overlay', label: 'Overlay', icon: <LayoutTemplate className="w-4 h-4" /> },
        { id: 'audio', label: 'Audio', icon: <Volume2 className="w-4 h-4" /> },
    ];

    return (
        <div className="h-full flex flex-col bg-[#1a1a1a] text-white">
            <div className="flex border-b border-[#2a2a2a] shrink-0 overflow-x-auto no-scrollbar">
                {tabs.map(tab => (
                    <button
                        key={tab.id}
                        onClick={() => setUI({ rightPanelTab: tab.id })}
                        className={`flex-1 flex flex-col items-center py-2 px-1 text-xs font-medium border-b-2 transition-colors min-w-[64px] ${activeTab === tab.id ? 'border-[#6366f1] text-[#6366f1]' : 'border-transparent text-[#6b7280] hover:text-[#f1f1f1]'}`}
                    >
                        {tab.icon}
                        <span className="mt-1">{tab.label}</span>
                    </button>
                ))}
            </div>

            <div className="flex-1 overflow-y-auto p-4">
                {activeTab === 'transform' && <TransformTab />}
                {activeTab === 'subtitle' && <SubtitleTab />}
                {activeTab === 'overlay' && <OverlayTab />}
                {activeTab === 'audio' && <AudioTab />}
            </div>
        </div>
    );
}

// ============================================================================
// TRANSFORM TAB
// ============================================================================
function TransformTab() {
    const videoTrack = useEditorStore((state: EditorStoreType) => state.videoTrack[0]);
    const updateVideoItem = useEditorStore((state: EditorStoreType) => state.updateVideoItem);
    const pushHistory = useEditorStore((state: EditorStoreType) => state.pushHistory);
    const cropSegments = useEditorStore((state: EditorStoreType) => state.cropSegments);
    const cropOverrides = useEditorStore((state: EditorStoreType) => state.cropOverrides);
    const selectedCropSegmentIndex = useEditorStore((state: EditorStoreType) => state.selectedCropSegmentIndex);
    const setCropOverride = useEditorStore((state: EditorStoreType) => state.setCropOverride);
    const clearCropOverride = useEditorStore((state: EditorStoreType) => state.clearCropOverride);

    const [cropX, setCropX] = useState(videoTrack?.cropX || 0.5);
    const [scale, setScale] = useState(videoTrack?.scale || 1.0);
    const [speed, setSpeed] = useState(videoTrack?.speed || 1.0);

    const selectedSeg = selectedCropSegmentIndex !== null && cropSegments.length > 0
        ? cropSegments[selectedCropSegmentIndex]
        : null;
    const currentCropX = selectedCropSegmentIndex !== null && cropSegments.length > 0
        ? (cropOverrides[selectedCropSegmentIndex] ?? selectedSeg?.cropX ?? 0.5)
        : 0.5;
    const [localCropX, setLocalCropX] = useState(currentCropX);

    // Sync local state when selected segment changes
    useEffect(() => {
        setLocalCropX(currentCropX);
    }, [selectedCropSegmentIndex, currentCropX]);

    // Sync local state if track changes externally
    useEffect(() => {
        if (videoTrack) {
            setCropX(videoTrack.cropX);
            setScale(videoTrack.scale);
            setSpeed(videoTrack.speed);
        }
    }, [videoTrack]);

    if (!videoTrack) return <div className="text-sm text-[#6b7280]">No video track found.</div>;

    const handleCropModeChange = (mode: 'center' | 'manual') => {
        updateVideoItem(videoTrack.id, { cropMode: mode });
        pushHistory();
    };

    return (
        <div className="space-y-6">
            <div>
                <label className="block text-sm text-[#6b7280] mb-2">Crop Mode</label>
                <div className="flex rounded-md overflow-hidden border border-[#3a3a3a]">
                    <button
                        onClick={() => handleCropModeChange('center')}
                        className={`flex-1 py-1.5 text-sm transition-colors ${videoTrack.cropMode === 'center' ? 'bg-[#6366f1] text-white' : 'bg-[#2a2a2a] text-[#6b7280] hover:bg-[#3a3a3a]'}`}
                    >
                        Center
                    </button>
                    <button
                        onClick={() => handleCropModeChange('manual')}
                        className={`flex-1 py-1.5 text-sm transition-colors ${videoTrack.cropMode === 'manual' ? 'bg-[#6366f1] text-white' : 'bg-[#2a2a2a] text-[#6b7280] hover:bg-[#3a3a3a]'}`}
                    >
                        Manual
                    </button>
                </div>
            </div>

            {videoTrack.cropMode === 'manual' && (
                <div>
                    <div className="flex justify-between items-center mb-1">
                        <label className="text-sm text-[#6b7280]">Crop Position (X)</label>
                        <span className="text-xs font-mono">{cropX.toFixed(2)}</span>
                    </div>
                    <input
                        type="range"
                        min="0" max="1" step="0.01"
                        value={cropX}
                        onChange={(e) => {
                            const val = parseFloat(e.target.value);
                            setCropX(val);
                            updateVideoItem(videoTrack.id, { cropX: val });
                        }}
                        onMouseUp={pushHistory}
                        onTouchEnd={pushHistory}
                        className="w-full"
                    />
                </div>
            )}

            <div>
                <div className="flex justify-between items-center mb-1">
                    <label className="text-sm text-[#6b7280]">Scale</label>
                    <span className="text-xs font-mono">{scale.toFixed(2)}x</span>
                </div>
                <input
                    type="range"
                    min="0.5" max="2.0" step="0.05"
                    value={scale}
                    onChange={(e) => {
                        const val = parseFloat(e.target.value);
                        setScale(val);
                        updateVideoItem(videoTrack.id, { scale: val });
                    }}
                    onMouseUp={pushHistory}
                    onTouchEnd={pushHistory}
                    className="w-full"
                />
            </div>

            <div>
                <div className="flex justify-between items-center mb-1">
                    <label className="text-sm text-[#6b7280]">Speed</label>
                    <span className="text-xs font-mono">{speed.toFixed(2)}x</span>
                </div>
                <input
                    type="range"
                    min="0.5" max="2.0" step="0.1"
                    value={speed}
                    onChange={(e) => {
                        const val = parseFloat(e.target.value);
                        setSpeed(val);
                        updateVideoItem(videoTrack.id, { speed: val });
                    }}
                    onMouseUp={pushHistory}
                    onTouchEnd={pushHistory}
                    className="w-full"
                />
            </div>

            {/* Smart Reframe Section */}
            {cropSegments.length > 0 && selectedCropSegmentIndex !== null && selectedSeg && (
                <div className="mt-4 pt-4 border-t border-[#2a2a2a]">
                    {/* Header */}
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-xs text-[#6b7280]">Smart Reframe</span>
                        {cropOverrides[selectedCropSegmentIndex] !== undefined && (
                            <button
                                onClick={() => { clearCropOverride(selectedCropSegmentIndex); pushHistory() }}
                                className="text-[10px] text-red-400 hover:text-red-300 transition-colors"
                                aria-label="Reset to AI detected crop"
                            >
                                Reset to AI
                            </button>
                        )}
                    </div>

                    {/* Segment metadata card */}
                    <div className="bg-[#2a2a2a] rounded p-2 mb-3 space-y-0.5">
                        <div className="text-[10px] text-[#6b7280]">
                            Segment {selectedCropSegmentIndex + 1} / {cropSegments.length}
                            {' · '}Speaker {selectedSeg.speakerId}
                        </div>
                        <div className="text-[10px] text-[#6b7280]">
                            {selectedSeg.detected
                                ? `Face detected (${(selectedSeg.confidence * 100).toFixed(0)}% confidence)`
                                : <span className="text-red-400">⚠️ Face not detected — fallback used</span>
                            }
                        </div>
                        {cropOverrides[selectedCropSegmentIndex] !== undefined && (
                            <div className="text-[10px] text-yellow-400">✏️ Manually overridden</div>
                        )}
                    </div>

                    {/* Crop position slider — local state + onMouseUp history pattern */}
                    <label className="text-xs text-[#6b7280] mb-1 flex justify-between">
                        <span>Horizontal Position</span>
                        <span className="text-white">{(localCropX * 100).toFixed(0)}%</span>
                    </label>
                    <input
                        type="range"
                        min={0} max={1} step={0.01}
                        value={localCropX}
                        onChange={(e) => {
                            const val = Number(e.target.value)
                            setLocalCropX(val)
                            setCropOverride(selectedCropSegmentIndex, val) // live preview, no history
                        }}
                        onMouseUp={() => pushHistory()} // history only on release
                        className="w-full accent-indigo-500"
                        aria-label="Horizontal crop position"
                    />

                    {/* Quick position buttons */}
                    <div className="flex gap-1 mt-2">
                        {[
                            { label: 'Left', value: 0.2 },
                            { label: 'Center', value: 0.5 },
                            { label: 'Right', value: 0.8 },
                        ].map(({ label, value }) => (
                            <button
                                key={label}
                                onClick={() => {
                                    setLocalCropX(value)
                                    setCropOverride(selectedCropSegmentIndex, value)
                                    pushHistory()
                                }}
                                className="flex-1 text-[10px] py-1.5 rounded bg-[#2a2a2a] text-[#6b7280] hover:text-white hover:bg-[#3a3a3a] transition-colors"
                                aria-label={`Set crop to ${label}`}
                            >
                                {label}
                            </button>
                        ))}
                    </div>

                    {/* Apply current cropX to all undetected segments */}
                    {cropSegments.some((s: any) => !s.detected) && (
                        <button
                            onClick={() => {
                                cropSegments.forEach((seg: any, idx: number) => {
                                    if (!seg.detected) setCropOverride(idx, localCropX)
                                })
                                pushHistory()
                            }}
                            className="mt-2 w-full text-[10px] py-1.5 rounded bg-[#2a2a2a] text-[#6b7280] hover:text-white hover:bg-[#3a3a3a] transition-colors"
                            aria-label="Apply to all undetected segments"
                        >
                            Apply to all ⚠️ undetected ({cropSegments.filter((s: any) => !s.detected).length})
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}

// ============================================================================
// SUBTITLE TAB
// ============================================================================
function SubtitleTab() {
    const subtitleTrack = useEditorStore((state: EditorStoreType) => state.subtitleTrack[0]);
    const updateSubtitleItem = useEditorStore((state: EditorStoreType) => state.updateSubtitleItem);
    const pushHistory = useEditorStore((state: EditorStoreType) => state.pushHistory);

    const [fontSize, setFontSize] = useState(subtitleTrack?.style.fontSize || 48);

    useEffect(() => {
        if (subtitleTrack) {
            setFontSize(subtitleTrack.style.fontSize);
        }
    }, [subtitleTrack]);

    if (!subtitleTrack) return <div className="text-sm text-[#6b7280]">No subtitle track found.</div>;

    const COLORS = [
        { name: 'White', value: '&H00FFFFFF' },
        { name: 'Yellow', value: '&H0000FFFF' },
        { name: 'Cyan', value: '&H00FFFF00' },
        { name: 'Red', value: '&H000000FF' },
        { name: 'Green', value: '&H0000FF00' },
        { name: 'Black', value: '&H00000000' }
    ];

    const updateStyle = (patch: Partial<typeof subtitleTrack.style>) => {
        updateSubtitleItem(subtitleTrack.id, { style: { ...subtitleTrack.style, ...patch } });
        pushHistory();
    };

    return (
        <div className="space-y-6">
            <div>
                <label className="block text-sm text-[#6b7280] mb-1">Font Family</label>
                <select
                    value={subtitleTrack.style.fontFamily}
                    onChange={(e) => updateStyle({ fontFamily: e.target.value as any })}
                    className="w-full bg-[#2a2a2a] border border-[#3a3a3a] text-white text-sm rounded-md p-2 outline-none focus:border-[#6366f1]"
                >
                    <option value="Montserrat">Montserrat</option>
                    <option value="TheBoldFont">TheBoldFont</option>
                    <option value="Roboto">Roboto</option>
                </select>
            </div>

            <div>
                <div className="flex justify-between items-center mb-1">
                    <label className="text-sm text-[#6b7280]">Font Size</label>
                    <span className="text-xs font-mono">{fontSize}px</span>
                </div>
                <input
                    type="range"
                    min="24" max="96" step="1"
                    value={fontSize}
                    onChange={(e) => {
                        const val = parseInt(e.target.value);
                        setFontSize(val);
                        updateSubtitleItem(subtitleTrack.id, { style: { ...subtitleTrack.style, fontSize: val } });
                    }}
                    onMouseUp={pushHistory}
                    onTouchEnd={pushHistory}
                    className="w-full"
                />
            </div>

            <div>
                <label className="block text-sm text-[#6b7280] mb-2">Text Color</label>
                <div className="grid grid-cols-6 gap-2">
                    {COLORS.map(c => (
                        <button
                            key={`text-${c.value}`}
                            onClick={() => updateStyle({ color: c.value })}
                            className={`w-full aspect-square rounded-full border-2 transition-transform ${subtitleTrack.style.color === c.value ? 'border-[#6366f1] scale-110' : 'border-transparent hover:scale-105'}`}
                            style={{ backgroundColor: c.name.toLowerCase() }}
                            title={c.name}
                        />
                    ))}
                </div>
            </div>

            <div>
                <label className="block text-sm text-[#6b7280] mb-2">Outline Color</label>
                <div className="grid grid-cols-6 gap-2">
                    {COLORS.map(c => (
                        <button
                            key={`outline-${c.value}`}
                            onClick={() => updateStyle({ outlineColor: c.value })}
                            className={`w-full aspect-square rounded-full border-2 transition-transform ${subtitleTrack.style.outlineColor === c.value ? 'border-[#6366f1] scale-110' : 'border-transparent hover:scale-105'}`}
                            style={{ backgroundColor: c.name.toLowerCase() }}
                            title={c.name}
                        />
                    ))}
                </div>
            </div>

            <div>
                <label className="block text-sm text-[#6b7280] mb-2">Position</label>
                <div className="flex rounded-md overflow-hidden border border-[#3a3a3a]">
                    {(['top', 'center', 'bottom'] as const).map(pos => (
                        <button
                            key={pos}
                            onClick={() => updateStyle({ position: pos })}
                            className={`flex-1 py-1.5 text-xs capitalize transition-colors ${subtitleTrack.style.position === pos ? 'bg-[#6366f1] text-white' : 'bg-[#2a2a2a] text-[#6b7280] hover:bg-[#3a3a3a]'}`}
                        >
                            {pos}
                        </button>
                    ))}
                </div>
            </div>

            <div>
                <label className="block text-sm text-[#6b7280] mb-1">Animation</label>
                <select
                    value={subtitleTrack.style.animationStyle}
                    onChange={(e) => updateStyle({ animationStyle: e.target.value as any })}
                    className="w-full bg-[#2a2a2a] border border-[#3a3a3a] text-white text-sm rounded-md p-2 outline-none focus:border-[#6366f1]"
                >
                    <option value="word-highlight">Word Highlight</option>
                    <option value="word-pop">Word Pop</option>
                    <option value="karaoke">Karaoke</option>
                </select>
            </div>
        </div>
    );
}

// ============================================================================
// OVERLAY TAB
// ============================================================================
function OverlayTab() {
    const overlayTrack = useEditorStore((state: EditorStoreType) => state.overlayTrack);
    const addOverlayItem = useEditorStore((state: EditorStoreType) => state.addOverlayItem);
    const updateOverlayItem = useEditorStore((state: EditorStoreType) => state.updateOverlayItem);
    const removeOverlayItem = useEditorStore((state: EditorStoreType) => state.removeOverlayItem);
    const pushHistory = useEditorStore((state: EditorStoreType) => state.pushHistory);
    const currentTime = useEditorStore((state: EditorStoreType) => state.currentTime);
    const duration = useEditorStore((state: EditorStoreType) => state.duration);

    const handleAdd = () => {
        const item: OverlayTrackItem = {
            id: `overlay-${Date.now()}`,
            type: 'overlay',
            start: currentTime,
            end: Math.min(currentTime + 3, duration),
            text: 'Key Insight:',
            position: 'top',
            backgroundColor: '#ffffff',
            textColor: '#000000'
        };
        addOverlayItem(item);
        pushHistory();
    };

    return (
        <div className="space-y-4">
            <button
                onClick={handleAdd}
                className="w-full flex items-center justify-center space-x-2 py-2 bg-[#2a2a2a] hover:bg-[#3a3a3a] border border-[#3a3a3a] rounded-md text-sm transition-colors"
            >
                <Plus className="w-4 h-4" />
                <span>Add Commentary Card</span>
            </button>

            <div className="space-y-4">
                {overlayTrack.map((overlay: OverlayTrackItem) => (
                    <div key={overlay.id} className="bg-[#2a2a2a] border border-[#3a3a3a] rounded-lg p-3 space-y-3 relative group">
                        <button
                            onClick={() => { removeOverlayItem(overlay.id); pushHistory(); }}
                            className="absolute top-2 right-2 p-1 text-[#6b7280] hover:text-red-500 transition-colors"
                            aria-label="Delete"
                        >
                            <Trash2 className="w-4 h-4" />
                        </button>

                        <div className="pr-6">
                            <input
                                type="text"
                                value={overlay.text}
                                onChange={(e) => updateOverlayItem(overlay.id, { text: e.target.value })}
                                onBlur={pushHistory}
                                className="w-full bg-[#1a1a1a] border border-[#3a3a3a] text-white text-sm rounded px-2 py-1 outline-none focus:border-[#6366f1]"
                                placeholder="Text..."
                            />
                        </div>

                        <div className="flex space-x-2">
                            <select
                                value={overlay.position}
                                onChange={(e) => {
                                    updateOverlayItem(overlay.id, { position: e.target.value as any });
                                    pushHistory();
                                }}
                                className="flex-1 bg-[#1a1a1a] border border-[#3a3a3a] text-white text-xs rounded px-2 py-1 outline-none"
                            >
                                <option value="top">Top</option>
                                <option value="center">Center</option>
                                <option value="bottom">Bottom</option>
                            </select>

                            <div className="flex-1 flex items-center justify-center bg-[#1a1a1a] border border-[#3a3a3a] rounded text-xs font-mono text-[#6b7280]">
                                {overlay.start.toFixed(1)}s - {overlay.end.toFixed(1)}s
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

// ============================================================================
// AUDIO TAB
// ============================================================================
function AudioTab() {
    const audioTrack = useEditorStore((state: EditorStoreType) => state.audioTrack);
    const updateAudioItem = useEditorStore((state: EditorStoreType) => state.updateAudioItem);
    const pushHistory = useEditorStore((state: EditorStoreType) => state.pushHistory);

    const bgMusic = audioTrack.find((a: any) => a.isBackgroundMusic);

    const [volume, setVolume] = useState(bgMusic?.volume || 0.5);
    const [duckLevelDb, setDuckLevelDb] = useState(bgMusic?.duckLevelDb || -12);
    const [fadeIn, setFadeIn] = useState(bgMusic?.fadeIn || 1);
    const [fadeOut, setFadeOut] = useState(bgMusic?.fadeOut || 1);

    useEffect(() => {
        if (bgMusic) {
            setVolume(bgMusic.volume);
            setDuckLevelDb(bgMusic.duckLevelDb);
            setFadeIn(bgMusic.fadeIn);
            setFadeOut(bgMusic.fadeOut);
        }
    }, [bgMusic]);

    if (!bgMusic) {
        return (
            <div className="text-center text-[#6b7280] text-sm mt-8">
                No background music added.<br />Go to Assets tab to add music.
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div>
                <div className="flex justify-between items-center mb-1">
                    <label className="text-sm text-[#6b7280]">Volume</label>
                    <span className="text-xs font-mono">{Math.round(volume * 100)}%</span>
                </div>
                <input
                    type="range"
                    min="0" max="1" step="0.05"
                    value={volume}
                    onChange={(e) => {
                        const val = parseFloat(e.target.value);
                        setVolume(val);
                        updateAudioItem(bgMusic.id, { volume: val });
                    }}
                    onMouseUp={pushHistory}
                    onTouchEnd={pushHistory}
                    className="w-full"
                />
            </div>

            <div>
                <div className="flex justify-between items-center mb-1">
                    <label className="text-sm text-[#6b7280]">Duck Level (Speech)</label>
                    <span className="text-xs font-mono">{duckLevelDb} dB</span>
                </div>
                <input
                    type="range"
                    min="-20" max="-6" step="1"
                    value={duckLevelDb}
                    onChange={(e) => {
                        const val = parseInt(e.target.value);
                        setDuckLevelDb(val);
                        updateAudioItem(bgMusic.id, { duckLevelDb: val });
                    }}
                    onMouseUp={pushHistory}
                    onTouchEnd={pushHistory}
                    className="w-full"
                />
            </div>

            <div>
                <div className="flex justify-between items-center mb-1">
                    <label className="text-sm text-[#6b7280]">Fade In</label>
                    <span className="text-xs font-mono">{fadeIn.toFixed(1)}s</span>
                </div>
                <input
                    type="range"
                    min="0" max="3" step="0.1"
                    value={fadeIn}
                    onChange={(e) => {
                        const val = parseFloat(e.target.value);
                        setFadeIn(val);
                        updateAudioItem(bgMusic.id, { fadeIn: val });
                    }}
                    onMouseUp={pushHistory}
                    onTouchEnd={pushHistory}
                    className="w-full"
                />
            </div>

            <div>
                <div className="flex justify-between items-center mb-1">
                    <label className="text-sm text-[#6b7280]">Fade Out</label>
                    <span className="text-xs font-mono">{fadeOut.toFixed(1)}s</span>
                </div>
                <input
                    type="range"
                    min="0" max="3" step="0.1"
                    value={fadeOut}
                    onChange={(e) => {
                        const val = parseFloat(e.target.value);
                        setFadeOut(val);
                        updateAudioItem(bgMusic.id, { fadeOut: val });
                    }}
                    onMouseUp={pushHistory}
                    onTouchEnd={pushHistory}
                    className="w-full"
                />
            </div>
        </div>
    );
}
