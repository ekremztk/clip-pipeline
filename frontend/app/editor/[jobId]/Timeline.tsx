// EDITOR MODULE — Isolated module, no dependencies on other app files
"use client"

import React, { useRef, useState, useEffect, useCallback, ReactNode } from 'react'
import { useEditorStore, EditorStoreType } from '../../../lib/editor/store'
import {
    VideoTrackItem,
    AudioTrackItem,
    SubtitleTrackItem,
    OverlayTrackItem
} from '../../../lib/editor/types'
import { Scissors, Trash2, Minus, Plus, Maximize, Video, Music, Type, MoreVertical } from 'lucide-react'

const BASE_PPS = 40        // pixels per second at 1x zoom
const LABEL_WIDTH = 80     // px — left label column width
const TRACK_HEIGHT = 96    // px — h-24, ALL tracks same height
const SPEAKER_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#8b5cf6']

const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60)
    const s = Math.floor(seconds % 60)
    return `${m}:${s.toString().padStart(2, '0')}`
}

export default function Timeline() {
    const {
        duration,
        videoTrack,
        audioTrack,
        subtitleTrack,
        overlayTrack,
        ui,
        setUI,
        setCurrentTime,
        setIsPlaying,
        updateVideoItem,
        pushHistory,
        selectedItem,
        setSelectedItem
    } = useEditorStore()

    const scrollContainerRef = useRef<HTMLDivElement>(null)
    const [scrollLeft, setScrollLeft] = useState(0)
    const [containerWidth, setContainerWidth] = useState(0)
    const [selectedCutIndex, setSelectedCutIndex] = useState<number | null>(null)

    const pps = BASE_PPS * ui.zoom
    const timeToPixel = useCallback((time: number) => time * pps, [pps])
    const pixelToTime = useCallback((px: number) => px / pps, [pps])

    // Update container width and sync scroll Left
    useEffect(() => {
        if (!scrollContainerRef.current) return

        const updateWidth = () => {
            if (scrollContainerRef.current) {
                setContainerWidth(scrollContainerRef.current.clientWidth)
            }
        }

        updateWidth()
        window.addEventListener('resize', updateWidth)
        return () => window.removeEventListener('resize', updateWidth)
    }, [])

    const handleScroll = useCallback(() => {
        if (scrollContainerRef.current) {
            setScrollLeft(scrollContainerRef.current.scrollLeft)
        }
    }, [])

    // Zoom and scroll sync
    useEffect(() => {
        const container = scrollContainerRef.current
        if (!container) return
        const store = useEditorStore.getState()
        const playheadPx = store.currentTime * BASE_PPS * ui.zoom
        const newScrollLeft = playheadPx - container.clientWidth / 2
        container.scrollLeft = Math.max(0, newScrollLeft)
    }, [ui.zoom])

    // Zoom controls
    const zoomOut = () => setUI({ zoom: Math.max(1, ui.zoom - 0.5) })
    const zoomIn = () => setUI({ zoom: Math.min(10, ui.zoom + 0.5) })
    const zoomFit = () => {
        if (!scrollContainerRef.current || duration === 0) return
        const w = scrollContainerRef.current.clientWidth
        const newZoom = Math.max(1, (w - 200) / (duration * BASE_PPS)) // 200px padding
        setUI({ zoom: newZoom })
    }

    const handleCut = () => {
        const time = useEditorStore.getState().currentTime
        const clip = videoTrack[0]
        if (!clip) return
        const newCut = {
            removeFrom: Math.max(clip.start, time - 1),
            removeTo: Math.min(clip.end, time + 1)
        }
        updateVideoItem(clip.id, { cuts: [...(clip.cuts ?? []), newCut] })
        pushHistory()
    }

    const handleDeleteCut = () => {
        const clip = videoTrack[0]
        if (!clip || selectedCutIndex === null) return
        const newCuts = [...(clip.cuts ?? [])]
        newCuts.splice(selectedCutIndex, 1)
        updateVideoItem(clip.id, { cuts: newCuts })
        setSelectedCutIndex(null)
        pushHistory()
    }

    const handleTrackAreaClick = (e: React.MouseEvent<HTMLDivElement>) => {
        if ((e.target as HTMLElement).closest('[data-clip]')) return
        if ((e.target as HTMLElement).closest('[data-cut]')) return
        const rect = e.currentTarget.getBoundingClientRect()
        const clickX = e.clientX - rect.left + scrollLeft // adjust with scrollLeft because we are listening on scroll container child

        // Wait, the instructions say:
        // scrollLeft already accounted for — element is inside scroll container
        // Actually, if the element is inside scroll container, e.clientX - rect.left gives coordinate WITHIN the element! So we DON'T add scrollLeft.
        const px = e.clientX - rect.left
        const newTime = Math.max(0, Math.min(pixelToTime(px), duration))
        setCurrentTime(newTime)
        setIsPlaying(false)
        setSelectedItem(null)
    }

    // Ctrl+Scroll zoom
    const handleWheel = useCallback((e: WheelEvent) => {
        if (e.ctrlKey || e.metaKey) {
            e.preventDefault()
            const delta = e.deltaY > 0 ? -0.5 : 0.5
            setUI({ zoom: Math.max(1, Math.min(10, ui.zoom + delta)) })
        }
    }, [ui.zoom, setUI])

    useEffect(() => {
        const container = scrollContainerRef.current
        if (container) {
            container.addEventListener('wheel', handleWheel, { passive: false })
            return () => container.removeEventListener('wheel', handleWheel)
        }
    }, [handleWheel])

    const totalWidth = timeToPixel(duration) + 200

    return (
        <div className="flex flex-col h-full w-full bg-[#0f0f0f] border-t border-[#2a2a2a] select-none">
            {/* TOOLBAR */}
            <div className="h-8 bg-[#1a1a1a] border-b border-[#2a2a2a] flex items-center px-3 gap-2 shrink-0">
                <button
                    onClick={handleCut}
                    className="p-1 text-[#6b7280] hover:text-white rounded hover:bg-[#2a2a2a] transition-colors flex items-center gap-1"
                    title="Cut (C)"
                >
                    <Scissors className="w-4 h-4" />
                    <span className="text-xs">Cut</span>
                </button>
                <button
                    onClick={handleDeleteCut}
                    disabled={selectedCutIndex === null}
                    className="p-1 text-[#6b7280] hover:text-red-400 disabled:opacity-50 disabled:hover:text-[#6b7280] disabled:hover:bg-transparent rounded hover:bg-[#2a2a2a] transition-colors flex items-center gap-1"
                    title="Delete Cut"
                >
                    <Trash2 className="w-4 h-4" />
                </button>

                <div className="flex-1" />

                <button onClick={zoomOut} className="text-[#6b7280] hover:text-white px-2">
                    <Minus className="w-4 h-4" />
                </button>
                <span className="text-xs text-[#6b7280] w-10 text-center">{ui.zoom.toFixed(1)}x</span>
                <button onClick={zoomIn} className="text-[#6b7280] hover:text-white px-2">
                    <Plus className="w-4 h-4" />
                </button>
                <div className="w-px h-4 bg-[#2a2a2a] mx-1" />
                <button onClick={zoomFit} className="text-[#6b7280] hover:text-white px-2">
                    <Maximize className="w-4 h-4" />
                </button>
            </div>

            {/* TIMELINE AREA */}
            <div className="flex flex-1 overflow-hidden relative">

                {/* Fixed Labels Column */}
                <div
                    className="flex flex-col shrink-0 border-r border-[#2a2a2a] z-30 bg-[#0f0f0f]"
                    style={{ width: LABEL_WIDTH }}
                >
                    {/* Empty corner for TimeRuler */}
                    <div className="h-8 bg-[#1a1a1a] border-b border-[#2a2a2a]" />

                    <TrackLabel label="Video" accentColor="#6366f1" isOdd={true} />
                    {useEditorStore.getState().cropSegments.length > 0 && (
                        <div style={{ height: 32, backgroundColor: '#1a1a1a', borderLeft: '3px solid #8b5cf6' }} className="flex items-center px-2 text-[10px] text-[#6b7280] font-medium border-b border-[#2a2a2a]/50">
                            Reframe
                        </div>
                    )}
                    <TrackLabel label="Audio" accentColor="#10b981" isOdd={false} />
                    <TrackLabel label="Subtitle" accentColor="#f59e0b" isOdd={true} />
                    <TrackLabel label="Overlay" accentColor="#8b5cf6" isOdd={false} />
                </div>

                {/* Scrollable Area */}
                <div
                    ref={scrollContainerRef}
                    onScroll={handleScroll}
                    className="flex-1 overflow-x-auto relative scrollbar-hide"
                    style={{ overflowY: 'hidden' }}
                >
                    <div style={{ width: totalWidth, position: 'relative', minHeight: '100%' }}>

                        {/* Time Ruler */}
                        <TimeRuler duration={duration} pps={pps} />

                        {/* Tracks */}
                        <div className="flex flex-col">
                            {/* Video Track */}
                            <TrackContent isOdd={true} onClick={handleTrackAreaClick}>
                                {videoTrack.map((item: VideoTrackItem) => (
                                    <VideoClip
                                        key={item.id}
                                        item={item}
                                        pps={pps}
                                        isSelected={selectedItem?.id === item.id}
                                    />
                                ))}
                            </TrackContent>

                            {/* Reframe Indicator */}
                            {useEditorStore.getState().cropSegments.length > 0 && (
                                <div style={{ width: totalWidth }}>
                                    <ReframeIndicator pps={pps} />
                                </div>
                            )}

                            {/* Audio Track */}
                            <TrackContent isOdd={false} onClick={handleTrackAreaClick}>
                                {audioTrack.map((item: AudioTrackItem) => (
                                    <AudioClip
                                        key={item.id}
                                        item={item}
                                        pps={pps}
                                        isSelected={selectedItem?.id === item.id}
                                    />
                                ))}
                            </TrackContent>

                            {/* Subtitle Track */}
                            <TrackContent isOdd={true} onClick={handleTrackAreaClick}>
                                {subtitleTrack.map((item: SubtitleTrackItem) => (
                                    <SubtitleClip
                                        key={item.id}
                                        item={item}
                                        pps={pps}
                                        scrollLeft={scrollLeft}
                                        containerWidth={containerWidth}
                                    />
                                ))}
                            </TrackContent>

                            {/* Overlay Track */}
                            <TrackContent isOdd={false} onClick={handleTrackAreaClick}>
                                {overlayTrack.map((item: OverlayTrackItem) => (
                                    <OverlayClip
                                        key={item.id}
                                        item={item}
                                        pps={pps}
                                        isSelected={selectedItem?.id === item.id}
                                    />
                                ))}
                            </TrackContent>
                        </div>

                        {/* Cut Markers (Overlay on all tracks) */}
                        <CutMarkers
                            pps={pps}
                            selectedIndex={selectedCutIndex}
                            onSelect={setSelectedCutIndex}
                        />

                        {/* Playhead */}
                        <Playhead pps={pps} />

                    </div>
                </div>

            </div>
        </div>
    )
}

/* ==============================================================================
   SUB-COMPONENTS
============================================================================== */

const ReframeIndicator = React.memo(({ pps }: { pps: number }) => {
    // Reactive reads are OK here — this component only re-renders when
    // cropSegments or cropOverrides change (not every frame)
    const cropSegments = useEditorStore(s => s.cropSegments)
    const cropOverrides = useEditorStore(s => s.cropOverrides)
    const setSelectedCropSegmentIndex = useEditorStore(s => s.setSelectedCropSegmentIndex)
    const setUI = useEditorStore(s => s.setUI)
    const setSelectedItem = useEditorStore(s => s.setSelectedItem)
    const videoTrack = useEditorStore(s => s.videoTrack)

    if (cropSegments.length === 0) return null

    return (
        <div className="flex" style={{ height: 32, backgroundColor: '#161616' }}>
            {/* Fixed label — outside scroll container, same width as LABEL_WIDTH */}
            <div
                className="flex-shrink-0 flex items-center justify-center text-[10px] text-[#6b7280]"
                style={{ width: LABEL_WIDTH, borderLeft: '3px solid #8b5cf6', backgroundColor: '#1a1a1a' }}
            >
                Reframe
            </div>

            {/* Segments — inside scroll container */}
            <div className="relative flex-1 overflow-hidden" style={{ height: 32 }}>
                {cropSegments.map((seg, idx) => {
                    const hasOverride = cropOverrides[idx] !== undefined
                    const isUndetected = !seg.detected && !hasOverride
                    const speakerColor = SPEAKER_COLORS[seg.speakerId % SPEAKER_COLORS.length]
                    const displayCropX = cropOverrides[idx] ?? seg.cropX

                    return (
                        <div
                            key={idx}
                            style={{
                                position: 'absolute',
                                left: seg.start * pps,
                                width: Math.max(4, (seg.end - seg.start) * pps - 1),
                                height: 24,
                                top: 4,
                                backgroundColor: isUndetected
                                    ? 'rgba(239,68,68,0.25)'
                                    : speakerColor + 'aa',
                                border: isUndetected
                                    ? '1px dashed #ef4444'
                                    : `1px solid ${speakerColor}`,
                                borderRadius: 3,
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: 2,
                            }}
                            title={[
                                `Speaker ${seg.speakerId}`,
                                `cropX: ${displayCropX.toFixed(2)}`,
                                `confidence: ${(seg.confidence * 100).toFixed(0)}%`,
                                isUndetected ? '⚠️ Face not detected' : '',
                                hasOverride ? '✏️ Manually overridden' : '',
                            ].filter(Boolean).join(' | ')}
                            onClick={() => {
                                setSelectedCropSegmentIndex(idx)
                                setUI({ rightPanelTab: 'transform' })
                                if (videoTrack[0]) setSelectedItem(videoTrack[0])
                            }}
                        >
                            {isUndetected && (
                                <span className="text-red-400 text-[8px] pointer-events-none">⚠</span>
                            )}
                            {hasOverride && (
                                <span className="text-yellow-400 text-[8px] pointer-events-none">✏</span>
                            )}
                        </div>
                    )
                })}
            </div>
        </div>
    )
})
ReframeIndicator.displayName = 'ReframeIndicator'

const TrackLabel = React.memo(({ label, accentColor, isOdd }: { label: string, accentColor: string, isOdd: boolean }) => {
    return (
        <div
            className={`flex items-center px-2 text-xs text-[#6b7280] font-medium border-b border-[#2a2a2a]/50`}
            style={{
                height: TRACK_HEIGHT,
                backgroundColor: isOdd ? '#1a1a1a' : '#161616',
                borderLeft: `3px solid ${accentColor}`
            }}
        >
            {label}
        </div>
    )
})
TrackLabel.displayName = 'TrackLabel'

const TrackContent = ({ isOdd, onClick, children }: { isOdd: boolean, onClick: React.MouseEventHandler<HTMLDivElement>, children: ReactNode }) => {
    return (
        <div
            onClick={onClick}
            className={`relative border-b border-[#2a2a2a]/50`}
            style={{
                height: TRACK_HEIGHT,
                backgroundColor: isOdd ? '#1a1a1a' : '#161616'
            }}
        >
            {children}
        </div>
    )
}

const TimeRuler = React.memo(({ duration, pps }: { duration: number, pps: number }) => {
    const zoom = pps / BASE_PPS
    let interval = 5
    if (zoom >= 2 && zoom <= 5) interval = 2
    if (zoom > 5) interval = 1

    const markers = []
    for (let t = 0; t <= duration; t += interval) {
        markers.push(t)
    }

    return (
        <div className="h-8 bg-[#1a1a1a] border-b border-[#2a2a2a] relative w-full pointer-events-none">
            {markers.map(t => (
                <div
                    key={t}
                    className="absolute top-0 bottom-0 border-l border-[#2a2a2a] flex flex-col justify-end pb-1"
                    style={{ left: t * pps }}
                >
                    <span className="text-[10px] text-[#6b7280] pl-1">{formatTime(t)}</span>
                </div>
            ))}
        </div>
    )
})
TimeRuler.displayName = 'TimeRuler'

/* ================== CLIPS ================== */

const VideoClip = React.memo(({ item, pps, isSelected }: { item: VideoTrackItem, pps: number, isSelected: boolean }) => {
    const { updateVideoItem, setSelectedItem, setUI, pushHistory, duration } = useEditorStore()

    const activeMoveRef = useRef<((e: MouseEvent) => void) | null>(null)
    const activeUpRef = useRef<(() => void) | null>(null)

    useEffect(() => {
        return () => {
            if (activeMoveRef.current) window.removeEventListener('mousemove', activeMoveRef.current)
            if (activeUpRef.current) window.removeEventListener('mouseup', activeUpRef.current)
        }
    }, [])

    const handleMouseDown = (e: React.MouseEvent) => {
        e.stopPropagation()
        setSelectedItem(item)
        setUI({ rightPanelTab: 'transform' })

        const startX = e.clientX
        const originalStart = item.start
        const clipDuration = item.end - item.start

        const handleMove = (ev: MouseEvent) => {
            const deltaTime = (ev.clientX - startX) / pps
            const newStart = Math.max(0, Math.min(originalStart + deltaTime, duration - clipDuration))
            updateVideoItem(item.id, { start: newStart, end: newStart + clipDuration })
        }

        const handleUp = () => {
            pushHistory()
            window.removeEventListener('mousemove', handleMove)
            window.removeEventListener('mouseup', handleUp)
            activeMoveRef.current = null
            activeUpRef.current = null
        }

        activeMoveRef.current = handleMove
        activeUpRef.current = handleUp
        window.addEventListener('mousemove', handleMove)
        window.addEventListener('mouseup', handleUp)
    }

    const handleResizeLeft = (e: React.MouseEvent) => {
        e.stopPropagation()
        const startX = e.clientX
        const originalStart = item.start

        const handleMove = (ev: MouseEvent) => {
            const deltaTime = (ev.clientX - startX) / pps
            const newStart = Math.max(0, Math.min(originalStart + deltaTime, item.end - 1))
            updateVideoItem(item.id, { start: newStart })
        }

        const handleUp = () => {
            pushHistory()
            window.removeEventListener('mousemove', handleMove)
            window.removeEventListener('mouseup', handleUp)
            activeMoveRef.current = null
            activeUpRef.current = null
        }

        activeMoveRef.current = handleMove
        activeUpRef.current = handleUp
        window.addEventListener('mousemove', handleMove)
        window.addEventListener('mouseup', handleUp)
    }

    const handleResizeRight = (e: React.MouseEvent) => {
        e.stopPropagation()
        const startX = e.clientX
        const originalEnd = item.end

        const handleMove = (ev: MouseEvent) => {
            const deltaTime = (ev.clientX - startX) / pps
            const newEnd = Math.max(item.start + 1, Math.min(originalEnd + deltaTime, duration))
            updateVideoItem(item.id, { end: newEnd })
        }

        const handleUp = () => {
            pushHistory()
            window.removeEventListener('mousemove', handleMove)
            window.removeEventListener('mouseup', handleUp)
            activeMoveRef.current = null
            activeUpRef.current = null
        }

        activeMoveRef.current = handleMove
        activeUpRef.current = handleUp
        window.addEventListener('mousemove', handleMove)
        window.addEventListener('mouseup', handleUp)
    }

    return (
        <div
            data-clip="true"
            onMouseDown={handleMouseDown}
            className={`absolute rounded-md cursor-grab active:cursor-grabbing overflow-hidden flex flex-col justify-center px-2 select-none group border-2 ${isSelected ? 'border-white ring-2 ring-white ring-opacity-50' : 'border-[#6366f1]'}`}
            style={{
                left: item.start * pps,
                width: Math.max(40, (item.end - item.start) * pps),
                top: 4,
                height: TRACK_HEIGHT - 8,
                backgroundColor: 'rgba(99, 102, 241, 0.8)'
            }}
        >
            <div className="flex items-center gap-2 pointer-events-none">
                <Video className="w-4 h-4 text-white" />
                <span className="text-xs text-white font-medium truncate">Video</span>
                <span className="text-[10px] text-white/70 ml-auto">{((item.end - item.start)).toFixed(1)}s</span>
            </div>

            {/* Resize Handles */}
            <div
                onMouseDown={handleResizeLeft}
                className="absolute left-0 top-0 bottom-0 w-2 cursor-ew-resize hover:bg-white/20 z-10"
            />
            <div
                onMouseDown={handleResizeRight}
                className="absolute right-0 top-0 bottom-0 w-2 cursor-ew-resize hover:bg-white/20 z-10"
            />
        </div>
    )
})
VideoClip.displayName = 'VideoClip'

const AudioClip = React.memo(({ item, pps, isSelected }: { item: AudioTrackItem, pps: number, isSelected: boolean }) => {
    const { updateAudioItem, setSelectedItem, setUI, pushHistory, duration } = useEditorStore()

    const activeMoveRef = useRef<((e: MouseEvent) => void) | null>(null)
    const activeUpRef = useRef<(() => void) | null>(null)

    useEffect(() => {
        return () => {
            if (activeMoveRef.current) window.removeEventListener('mousemove', activeMoveRef.current)
            if (activeUpRef.current) window.removeEventListener('mouseup', activeUpRef.current)
        }
    }, [])

    // Seed logic for deterministic waveforms
    const seed = item.id.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0)
    const bars = Array.from({ length: 30 }).map((_, i) => {
        const heightPercent = 20 + ((seed * (i + 1) * 2654435761) % 70)
        return heightPercent
    })

    const handleMouseDown = (e: React.MouseEvent) => {
        e.stopPropagation()
        setSelectedItem(item)
        setUI({ rightPanelTab: 'audio' })

        const startX = e.clientX
        const originalStart = item.start
        const clipDuration = item.end - item.start

        const handleMove = (ev: MouseEvent) => {
            const deltaTime = (ev.clientX - startX) / pps
            const newStart = Math.max(0, Math.min(originalStart + deltaTime, duration - clipDuration))
            updateAudioItem(item.id, { start: newStart, end: newStart + clipDuration })
        }

        const handleUp = () => {
            pushHistory()
            window.removeEventListener('mousemove', handleMove)
            window.removeEventListener('mouseup', handleUp)
            activeMoveRef.current = null
            activeUpRef.current = null
        }

        activeMoveRef.current = handleMove
        activeUpRef.current = handleUp
        window.addEventListener('mousemove', handleMove)
        window.addEventListener('mouseup', handleUp)
    }

    const handleResizeLeft = (e: React.MouseEvent) => {
        e.stopPropagation()
        const startX = e.clientX
        const originalStart = item.start

        const handleMove = (ev: MouseEvent) => {
            const deltaTime = (ev.clientX - startX) / pps
            const newStart = Math.max(0, Math.min(originalStart + deltaTime, item.end - 1))
            updateAudioItem(item.id, { start: newStart })
        }

        const handleUp = () => {
            pushHistory()
            window.removeEventListener('mousemove', handleMove)
            window.removeEventListener('mouseup', handleUp)
            activeMoveRef.current = null
            activeUpRef.current = null
        }

        activeMoveRef.current = handleMove
        activeUpRef.current = handleUp
        window.addEventListener('mousemove', handleMove)
        window.addEventListener('mouseup', handleUp)
    }

    const handleResizeRight = (e: React.MouseEvent) => {
        e.stopPropagation()
        const startX = e.clientX
        const originalEnd = item.end

        const handleMove = (ev: MouseEvent) => {
            const deltaTime = (ev.clientX - startX) / pps
            const newEnd = Math.max(item.start + 1, Math.min(originalEnd + deltaTime, duration))
            updateAudioItem(item.id, { end: newEnd })
        }

        const handleUp = () => {
            pushHistory()
            window.removeEventListener('mousemove', handleMove)
            window.removeEventListener('mouseup', handleUp)
            activeMoveRef.current = null
            activeUpRef.current = null
        }

        activeMoveRef.current = handleMove
        activeUpRef.current = handleUp
        window.addEventListener('mousemove', handleMove)
        window.addEventListener('mouseup', handleUp)
    }

    return (
        <div
            data-clip="true"
            onMouseDown={handleMouseDown}
            className={`absolute rounded-md cursor-grab active:cursor-grabbing overflow-hidden flex flex-col justify-center px-2 select-none group border-2 ${isSelected ? 'border-white ring-2 ring-white ring-opacity-50' : 'border-[#10b981]'}`}
            style={{
                left: item.start * pps,
                width: Math.max(40, (item.end - item.start) * pps),
                top: 4,
                height: TRACK_HEIGHT - 8,
                backgroundColor: 'rgba(16, 185, 129, 0.7)'
            }}
        >
            <div className="absolute inset-0 flex items-center justify-between px-1 opacity-40 pointer-events-none">
                {bars.map((h, i) => (
                    <div key={i} className="w-[2px] bg-white rounded-full" style={{ height: `${h}%` }} />
                ))}
            </div>

            <div className="flex items-center gap-2 pointer-events-none relative z-10">
                <Music className="w-4 h-4 text-white" />
                <span className="text-xs text-white font-medium truncate">Audio</span>
                <span className="text-[10px] text-white/70 ml-auto">{((item.end - item.start)).toFixed(1)}s</span>
            </div>

            {/* Resize Handles */}
            <div
                onMouseDown={handleResizeLeft}
                className="absolute left-0 top-0 bottom-0 w-2 cursor-ew-resize hover:bg-white/20 z-20"
            />
            <div
                onMouseDown={handleResizeRight}
                className="absolute right-0 top-0 bottom-0 w-2 cursor-ew-resize hover:bg-white/20 z-20"
            />
        </div>
    )
})
AudioClip.displayName = 'AudioClip'

const SubtitleClip = React.memo(({ item, pps, scrollLeft, containerWidth }: { item: SubtitleTrackItem, pps: number, scrollLeft: number, containerWidth: number }) => {
    const { setSelectedItem, setUI } = useEditorStore()

    const handleClick = (e: React.MouseEvent) => {
        e.stopPropagation()
        setSelectedItem(item)
        setUI({ rightPanelTab: 'subtitle' })
    }

    const visibleWords = item.words.filter(word => {
        const left = word.start * pps
        const right = word.end * pps
        return right >= scrollLeft - 200 && left <= scrollLeft + containerWidth + 200
    })

    return (
        <div
            data-clip="true"
            onClick={handleClick}
            className="absolute top-0 bottom-0 left-0 right-0 cursor-pointer"
        >
            {visibleWords.map((word, index) => (
                <div
                    key={`${word.start}-${index}`}
                    style={{
                        position: 'absolute',
                        left: word.start * pps,
                        width: Math.max(28, (word.end - word.start) * pps - 2),
                        top: '50%',
                        transform: 'translateY(-50%)',
                        height: 28,
                        backgroundColor: SPEAKER_COLORS[word.speaker % SPEAKER_COLORS.length]
                    }}
                    title={`${word.word} (${word.start.toFixed(2)}s)`}
                    className="rounded-full px-1.5 flex items-center overflow-hidden hover:brightness-110 transition-all border border-white/20 shadow-sm"
                >
                    <span className="text-[10px] text-white truncate font-medium">{word.word}</span>
                </div>
            ))}
        </div>
    )
})
SubtitleClip.displayName = 'SubtitleClip'

const OverlayClip = React.memo(({ item, pps, isSelected }: { item: OverlayTrackItem, pps: number, isSelected: boolean }) => {
    const { updateOverlayItem, setSelectedItem, setUI, pushHistory, duration, removeOverlayItem } = useEditorStore()
    const [showMenu, setShowMenu] = useState(false)
    const menuRef = useRef<HTMLDivElement>(null)

    const activeMoveRef = useRef<((e: MouseEvent) => void) | null>(null)
    const activeUpRef = useRef<(() => void) | null>(null)

    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
                setShowMenu(false)
            }
        }
        const handleEsc = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setShowMenu(false)
        }
        if (showMenu) {
            window.addEventListener('mousedown', handleClickOutside)
            window.addEventListener('keydown', handleEsc)
        }
        return () => {
            window.removeEventListener('mousedown', handleClickOutside)
            window.removeEventListener('keydown', handleEsc)
        }
    }, [showMenu])

    useEffect(() => {
        return () => {
            if (activeMoveRef.current) window.removeEventListener('mousemove', activeMoveRef.current)
            if (activeUpRef.current) window.removeEventListener('mouseup', activeUpRef.current)
        }
    }, [])

    const handleMouseDown = (e: React.MouseEvent) => {
        if (e.button !== 0) return // Only left click for drag
        e.stopPropagation()
        setSelectedItem(item)
        setUI({ rightPanelTab: 'overlay' })
        setShowMenu(false)

        const startX = e.clientX
        const originalStart = item.start
        const clipDuration = item.end - item.start

        const handleMove = (ev: MouseEvent) => {
            const deltaTime = (ev.clientX - startX) / pps
            const newStart = Math.max(0, Math.min(originalStart + deltaTime, duration - clipDuration))
            updateOverlayItem(item.id, { start: newStart, end: newStart + clipDuration })
        }

        const handleUp = () => {
            pushHistory()
            window.removeEventListener('mousemove', handleMove)
            window.removeEventListener('mouseup', handleUp)
            activeMoveRef.current = null
            activeUpRef.current = null
        }

        activeMoveRef.current = handleMove
        activeUpRef.current = handleUp
        window.addEventListener('mousemove', handleMove)
        window.addEventListener('mouseup', handleUp)
    }

    const handleContextMenu = (e: React.MouseEvent) => {
        e.preventDefault()
        e.stopPropagation()
        setShowMenu(true)
        setSelectedItem(item)
        setUI({ rightPanelTab: 'overlay' })
    }

    const handleDelete = (e: React.MouseEvent) => {
        e.stopPropagation()
        removeOverlayItem(item.id)
        setSelectedItem(null)
        pushHistory()
        setShowMenu(false)
    }

    const handleResizeLeft = (e: React.MouseEvent) => {
        e.stopPropagation()
        const startX = e.clientX
        const originalStart = item.start

        const handleMove = (ev: MouseEvent) => {
            const deltaTime = (ev.clientX - startX) / pps
            const newStart = Math.max(0, Math.min(originalStart + deltaTime, item.end - 0.5)) // min 0.5s duration
            updateOverlayItem(item.id, { start: newStart })
        }

        const handleUp = () => {
            pushHistory()
            window.removeEventListener('mousemove', handleMove)
            window.removeEventListener('mouseup', handleUp)
            activeMoveRef.current = null
            activeUpRef.current = null
        }

        activeMoveRef.current = handleMove
        activeUpRef.current = handleUp
        window.addEventListener('mousemove', handleMove)
        window.addEventListener('mouseup', handleUp)
    }

    const handleResizeRight = (e: React.MouseEvent) => {
        e.stopPropagation()
        const startX = e.clientX
        const originalEnd = item.end

        const handleMove = (ev: MouseEvent) => {
            const deltaTime = (ev.clientX - startX) / pps
            const newEnd = Math.max(item.start + 0.5, Math.min(originalEnd + deltaTime, duration))
            updateOverlayItem(item.id, { end: newEnd })
        }

        const handleUp = () => {
            pushHistory()
            window.removeEventListener('mousemove', handleMove)
            window.removeEventListener('mouseup', handleUp)
            activeMoveRef.current = null
            activeUpRef.current = null
        }

        activeMoveRef.current = handleMove
        activeUpRef.current = handleUp
        window.addEventListener('mousemove', handleMove)
        window.addEventListener('mouseup', handleUp)
    }

    return (
        <div
            data-clip="true"
            onMouseDown={handleMouseDown}
            onContextMenu={handleContextMenu}
            className={`absolute rounded-md cursor-grab active:cursor-grabbing overflow-visible flex flex-col justify-center px-2 select-none group border-2 ${isSelected ? 'border-white ring-2 ring-white ring-opacity-50' : 'border-[#f59e0b]'}`}
            style={{
                left: item.start * pps,
                width: Math.max(40, (item.end - item.start) * pps),
                top: 4,
                height: TRACK_HEIGHT - 8,
                backgroundColor: 'rgba(245, 158, 11, 0.7)'
            }}
        >
            <div className="flex items-center gap-2 pointer-events-none">
                <Type className="w-4 h-4 text-white shrink-0" />
                <span className="text-xs text-white font-medium truncate">{item.text || 'Text Overlay'}</span>
            </div>

            {/* Resize Handles */}
            <div
                onMouseDown={handleResizeLeft}
                className="absolute left-0 top-0 bottom-0 w-2 cursor-ew-resize hover:bg-white/20 z-10"
            />
            <div
                onMouseDown={handleResizeRight}
                className="absolute right-0 top-0 bottom-0 w-2 cursor-ew-resize hover:bg-white/20 z-10"
            />

            {/* Context Menu */}
            {showMenu && (
                <div
                    ref={menuRef}
                    className="absolute top-full left-0 mt-1 bg-[#1a1a1a] border border-[#2a2a2a] rounded-md shadow-xl py-1 z-50 min-w-[120px]"
                >
                    <button
                        onClick={handleDelete}
                        className="w-full text-left px-3 py-1.5 text-xs text-red-400 hover:bg-[#2a2a2a] flex items-center gap-2"
                    >
                        <Trash2 className="w-3 h-3" />
                        Delete
                    </button>
                </div>
            )}
        </div>
    )
})
OverlayClip.displayName = 'OverlayClip'

/* ================== CUT MARKERS ================== */

const CutMarkers = React.memo(({ pps, selectedIndex, onSelect }: { pps: number, selectedIndex: number | null, onSelect: (idx: number | null) => void }) => {
    const cuts = useEditorStore((state: EditorStoreType) => state.videoTrack[0]?.cuts ?? [])

    return (
        <>
            {cuts.map((cut: { removeFrom: number; removeTo: number }, idx: number) => {
                const isSelected = selectedIndex === idx
                return (
                    <div
                        key={idx}
                        data-cut="true"
                        className={`absolute top-8 bottom-0 z-20 pointer-events-none flex items-center justify-center`}
                        style={{
                            left: cut.removeFrom * pps,
                            width: (cut.removeTo - cut.removeFrom) * pps,
                            backgroundColor: 'rgba(239, 68, 68, 0.15)',
                            borderLeft: `1px dashed ${isSelected ? '#ef4444' : '#ef4444'}`,
                            borderRight: `1px dashed ${isSelected ? '#ef4444' : '#ef4444'}`,
                            ...(isSelected ? { border: '2px solid #ef4444', borderStyle: 'dashed' } : {})
                        }}
                    >
                        <button
                            onClick={(e) => {
                                e.stopPropagation()
                                onSelect(idx)
                            }}
                            className={`pointer-events-auto p-1 rounded-full bg-[#1a1a1a] border ${isSelected ? 'border-red-500 text-red-500' : 'border-[#2a2a2a] text-red-400 hover:border-red-400'}`}
                            title="Select Cut"
                        >
                            <Scissors className="w-3 h-3" />
                        </button>
                    </div>
                )
            })}
        </>
    )
})
CutMarkers.displayName = 'CutMarkers'


/* ================== PLAYHEAD ================== */

const Playhead = React.memo(({ pps }: { pps: number }) => {
    const playheadRef = useRef<HTMLDivElement>(null)
    const rafRef = useRef<number>(0)

    useEffect(() => {
        const updatePlayhead = () => {
            const store = useEditorStore.getState()
            const px = store.currentTime * pps

            if (playheadRef.current) {
                playheadRef.current.style.left = `${px}px`
            }

            // Auto-scroll logic happens here if playing
            if (store.isPlaying) {
                const scrollContainer = playheadRef.current?.closest('.overflow-x-auto') as HTMLDivElement
                if (scrollContainer) {
                    const visibleRight = scrollContainer.scrollLeft + scrollContainer.clientWidth
                    if (px > visibleRight - 100) {
                        scrollContainer.scrollLeft = px - scrollContainer.clientWidth / 2
                    }
                }
            }

            rafRef.current = requestAnimationFrame(updatePlayhead)
        }

        rafRef.current = requestAnimationFrame(updatePlayhead)

        return () => cancelAnimationFrame(rafRef.current)
    }, [pps])

    return (
        <div
            ref={playheadRef}
            className="absolute top-0 bottom-0 w-[2px] bg-red-500 z-50 pointer-events-none"
            style={{ left: 0 }}
        >
            <div className="absolute -top-1 -left-1.5 w-0 h-0 border-l-[6px] border-l-transparent border-r-[6px] border-r-transparent border-t-[8px] border-t-red-500" />
        </div>
    )
})
Playhead.displayName = 'Playhead'
