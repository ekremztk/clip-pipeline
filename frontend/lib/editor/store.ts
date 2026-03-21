// EDITOR MODULE — Isolated module, no dependencies on other app files

import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import {
    EditorJob,
    VideoTrackItem,
    AudioTrackItem,
    SubtitleTrackItem,
    OverlayTrackItem,
    SelectedItemType,
    EditorUIState,
    EditSpecPayload,
    EditDecisions,
    CropSegment,
} from './types'
import { generateASSContent } from './ass-generator'

/**
 * Represents a historical snapshot of all tracks combined.
 */
export interface HistorySnapshot {
    videoTrack: VideoTrackItem[]
    audioTrack: AudioTrackItem[]
    subtitleTrack: SubtitleTrackItem[]
    overlayTrack: OverlayTrackItem[]
}

/**
 * EditorStore defines the comprehensive state and actions for the video editor.
 */
export interface EditorStore {
    // Job state
    job: EditorJob | null
    setJob: (job: EditorJob | null) => void
    updateJobProgress: (progress: number) => void

    // Playback
    currentTime: number
    setCurrentTime: (time: number) => void
    isPlaying: boolean
    setIsPlaying: (playing: boolean) => void
    duration: number
    setDuration: (duration: number) => void

    // Tracks
    videoTrack: VideoTrackItem[]
    setVideoTrack: (track: VideoTrackItem[]) => void
    updateVideoItem: (id: string, updates: Partial<VideoTrackItem>) => void

    audioTrack: AudioTrackItem[]
    setAudioTrack: (track: AudioTrackItem[]) => void
    updateAudioItem: (id: string, updates: Partial<AudioTrackItem>) => void

    subtitleTrack: SubtitleTrackItem[]
    setSubtitleTrack: (track: SubtitleTrackItem[]) => void
    updateSubtitleItem: (id: string, updates: Partial<SubtitleTrackItem>) => void

    overlayTrack: OverlayTrackItem[]
    setOverlayTrack: (track: OverlayTrackItem[]) => void
    updateOverlayItem: (id: string, updates: Partial<OverlayTrackItem>) => void
    addOverlayItem: (item: OverlayTrackItem) => void
    removeOverlayItem: (id: string) => void

    // Selection
    selectedItem: SelectedItemType
    setSelectedItem: (item: SelectedItemType) => void

    // Speed Sections
    speedSections: EditDecisions['speedSections']
    setSpeedSections: (sections: EditDecisions['speedSections']) => void

    // UI
    ui: EditorUIState
    setUI: (patch: Partial<EditorUIState>) => void

    // History
    history: HistorySnapshot[]
    historyIndex: number
    pushHistory: () => void
    undo: () => void
    redo: () => void
    canUndo: boolean
    canRedo: boolean

    // ── Smart Reframe ─────────────────────────────────────────────
    cropSegments: CropSegment[]
    setCropSegments: (segments: CropSegment[]) => void

    // Manual overrides: key = segment index, value = overridden cropX (0.0-1.0)
    cropOverrides: Record<number, number>
    setCropOverride: (segmentIndex: number, cropX: number) => void
    clearCropOverride: (segmentIndex: number) => void
    clearAllCropOverrides: () => void

    // Selected segment index for RightPanel override UI
    selectedCropSegmentIndex: number | null
    setSelectedCropSegmentIndex: (index: number | null) => void

    // Actions
    loadFromJob: (job: EditorJob | null) => void
    loadFromEditDecisions: (decisions: EditDecisions) => void
    buildEditSpec: () => EditSpecPayload
    resetEditor: () => void
}

const initialUIState: EditorUIState = {
    isProcessing: false,
    isRendering: false,
    renderProgress: 0,
    rightPanelTab: 'transform',
    zoom: 1,
    showWaveform: true,
}

export const useEditorStore = create<EditorStore>()(
    devtools((set, get) => ({
        // Job state
        job: null,
        setJob: (job) => set({ job }),
        updateJobProgress: (progress) =>
            set((state) => ({
                job: state.job ? { ...state.job, progress } : null,
            })),

        // Playback
        currentTime: 0,
        setCurrentTime: (time) => set({ currentTime: time }),
        isPlaying: false,
        setIsPlaying: (playing) => set({ isPlaying: playing }),
        duration: 0,
        setDuration: (duration) => set({ duration }),

        // Tracks
        videoTrack: [],
        setVideoTrack: (track) => set({ videoTrack: [...track] }),
        updateVideoItem: (id, updates) =>
            set((state) => ({
                videoTrack: state.videoTrack.map((item) =>
                    item.id === id ? { ...item, ...updates } : item
                ),
            })),

        audioTrack: [],
        setAudioTrack: (track) => set({ audioTrack: [...track] }),
        updateAudioItem: (id, updates) =>
            set((state) => ({
                audioTrack: state.audioTrack.map((item) =>
                    item.id === id ? { ...item, ...updates } : item
                ),
            })),

        subtitleTrack: [],
        setSubtitleTrack: (track) => set({ subtitleTrack: [...track] }),
        updateSubtitleItem: (id, updates) =>
            set((state) => ({
                subtitleTrack: state.subtitleTrack.map((item) =>
                    item.id === id ? { ...item, ...updates } : item
                ),
            })),

        overlayTrack: [],
        setOverlayTrack: (track) => set({ overlayTrack: [...track] }),
        updateOverlayItem: (id, updates) =>
            set((state) => ({
                overlayTrack: state.overlayTrack.map((item) =>
                    item.id === id ? { ...item, ...updates } : item
                ),
            })),
        addOverlayItem: (item) =>
            set((state) => ({
                overlayTrack: [...state.overlayTrack, item],
            })),
        removeOverlayItem: (id) =>
            set((state) => ({
                overlayTrack: state.overlayTrack.filter((item) => item.id !== id),
            })),

        // Selection
        selectedItem: null,
        setSelectedItem: (item) => set({ selectedItem: item }),

        // Speed Sections
        speedSections: [],
        setSpeedSections: (sections) => set({ speedSections: sections }),

        // UI
        ui: initialUIState,
        setUI: (patch) =>
            set((state) => ({
                ui: { ...state.ui, ...patch },
            })),

        // History
        history: [],
        historyIndex: -1,
        canUndo: false,
        canRedo: false,
        pushHistory: () => {
            set((state) => {
                const snapshot: HistorySnapshot = {
                    videoTrack: state.videoTrack.map((item) => ({ ...item })),
                    audioTrack: state.audioTrack.map((item) => ({ ...item })),
                    subtitleTrack: state.subtitleTrack.map((item) => ({
                        ...item,
                        words: item.words.map((w) => ({ ...w })),
                        style: { ...item.style },
                    })),
                    overlayTrack: state.overlayTrack.map((item) => ({ ...item })),
                }

                const newHistory = state.history.slice(0, state.historyIndex + 1)
                newHistory.push(snapshot)

                // Cap at max 30 snapshots
                if (newHistory.length > 30) {
                    newHistory.shift()
                }

                const newIndex = newHistory.length - 1

                return {
                    history: newHistory,
                    historyIndex: newIndex,
                    canUndo: newIndex > 0,
                    canRedo: false,
                }
            })
        },
        undo: () => {
            set((state) => {
                if (state.historyIndex <= 0) return state

                const newIndex = state.historyIndex - 1
                const snapshot = state.history[newIndex]

                return {
                    historyIndex: newIndex,
                    videoTrack: snapshot.videoTrack.map((item) => ({ ...item })),
                    audioTrack: snapshot.audioTrack.map((item) => ({ ...item })),
                    subtitleTrack: snapshot.subtitleTrack.map((item) => ({
                        ...item,
                        words: item.words.map((w) => ({ ...w })),
                        style: { ...item.style },
                    })),
                    overlayTrack: snapshot.overlayTrack.map((item) => ({ ...item })),
                    canUndo: newIndex > 0,
                    canRedo: newIndex < state.history.length - 1,
                }
            })
        },
        redo: () => {
            set((state) => {
                if (state.historyIndex >= state.history.length - 1) return state

                const newIndex = state.historyIndex + 1
                const snapshot = state.history[newIndex]

                return {
                    historyIndex: newIndex,
                    videoTrack: snapshot.videoTrack.map((item) => ({ ...item })),
                    audioTrack: snapshot.audioTrack.map((item) => ({ ...item })),
                    subtitleTrack: snapshot.subtitleTrack.map((item) => ({
                        ...item,
                        words: item.words.map((w) => ({ ...w })),
                        style: { ...item.style },
                    })),
                    overlayTrack: snapshot.overlayTrack.map((item) => ({ ...item })),
                    canUndo: newIndex > 0,
                    canRedo: newIndex < state.history.length - 1,
                }
            })
        },

        // ── Smart Reframe ─────────────────────────────────────────────
        cropSegments: [],
        setCropSegments: (segments) => set({ cropSegments: [...segments] }),

        cropOverrides: {},
        setCropOverride: (segmentIndex, cropX) => set((state) => ({
            cropOverrides: { ...state.cropOverrides, [segmentIndex]: cropX }
        })),
        clearCropOverride: (segmentIndex) => set((state) => {
            const { [segmentIndex]: _, ...rest } = state.cropOverrides
            return { cropOverrides: rest }
        }),
        clearAllCropOverrides: () => set({ cropOverrides: {} }),

        selectedCropSegmentIndex: null,
        setSelectedCropSegmentIndex: (index) => set({ selectedCropSegmentIndex: index }),

        // Actions
        loadFromEditDecisions: (decisions) => {
            set((state) => {
                const videoTrack = state.videoTrack.map((item, index) => {
                    if (index === 0) {
                        return { ...item, cuts: decisions.cuts }
                    }
                    return item
                })

                const overlayTrack = [...state.overlayTrack]
                decisions.commentaryCards.forEach(card => {
                    overlayTrack.push({
                        id: crypto.randomUUID(),
                        type: 'overlay',
                        start: card.at,
                        end: card.at + card.duration,
                        text: card.text,
                        position: card.position,
                        backgroundColor: 'rgba(0,0,0,0.7)',
                        textColor: '#ffffff'
                    })
                })

                return {
                    videoTrack,
                    overlayTrack,
                    speedSections: decisions.speedSections
                }
            })
            get().pushHistory()
        },

        loadFromJob: (job) => {
            if (!job) {
                set({
                    job: null,
                    duration: 0,
                    videoTrack: [],
                    audioTrack: [],
                    subtitleTrack: [],
                    overlayTrack: [],
                    speedSections: [],
                    currentTime: 0,
                    isPlaying: false,
                    selectedItem: null,
                    cropSegments: [],
                    cropOverrides: {},
                    selectedCropSegmentIndex: null,
                })
                get().pushHistory()
                return
            }

            const duration = job.videoMetadata?.duration || 0

            const initialVideoItem: VideoTrackItem = {
                id: 'video-1',
                type: 'video',
                start: 0,
                end: duration,
                src: job.sourceR2Key,
                cropMode:
                    job.speakerSegments && job.speakerSegments.length > 0
                        ? 'center'
                        : 'manual',
                cropX: 0.5,
                scale: 1.0,
                positionX: 0,
                positionY: 0,
                speed: 1.0,
            }

            let initialSubtitleTrack: SubtitleTrackItem[] = []
            if (job.transcript && job.transcript.length > 0) {
                initialSubtitleTrack = [
                    {
                        id: 'subtitle-1',
                        type: 'subtitle',
                        start: 0,
                        end: duration,
                        words: job.transcript,
                        style: {
                            fontFamily: 'Montserrat',
                            fontSize: 48,
                            color: '&H00FFFFFF',
                            outlineColor: '&H00000000',
                            outlineWidth: 2,
                            position: 'center',
                            animationStyle: 'word-highlight',
                        },
                    },
                ]
            }

            // Handle smart reframe crop segments
            // EditorJob now needs to have cropSegments added to its type, but it might come as a raw object.
            // Let's assume job.cropSegments will be mapped correctly in api.ts
            const cropSegments = (job as any).cropSegments || []

            set({
                job,
                duration,
                videoTrack: [initialVideoItem],
                audioTrack: [],
                subtitleTrack: initialSubtitleTrack,
                overlayTrack: [],
                speedSections: [],
                currentTime: 0,
                isPlaying: false,
                selectedItem: null,
                cropSegments,
                cropOverrides: {},
                selectedCropSegmentIndex: null,
            })

            // Push initial state to history after loading
            get().pushHistory()
        },

        buildEditSpec: (): EditSpecPayload => {
            const state = get()

            const videoDuration = state.duration || 0
            const clip = { start: 0, end: videoDuration }

            let crop: { mode: 'center' | 'manual'; x: number }
            let crop_segments: any[] | undefined

            if (state.cropSegments && state.cropSegments.length > 0) {
                crop = { mode: 'manual', x: 0.5 }
                crop_segments = state.cropSegments.map((seg, idx) => ({
                    start: seg.start,
                    end: seg.end,
                    speaker_id: seg.speakerId,
                    crop_x: state.cropOverrides[idx] ?? seg.cropX,
                    detected: seg.detected,
                    confidence: seg.confidence
                }))
            } else {
                crop = {
                    mode: state.videoTrack[0]?.cropMode || 'center',
                    x: state.videoTrack[0]?.cropX || 0.5,
                }
            }

            const videoItem = state.videoTrack[0]
            const cuts = (videoItem?.cuts || []).map((cut: { removeFrom: number; removeTo: number }) => ({
                remove_from: cut.removeFrom,
                remove_to: cut.removeTo,
            }))

            const bgAudio = state.audioTrack.find((a: AudioTrackItem) => a.isBackgroundMusic)
            const audio = {
                background_music_path: bgAudio?.src,
                duck_level_db: bgAudio?.duckLevelDb ?? -12,
            }

            const subtitleItem = state.subtitleTrack[0]
            const subtitles = {
                enabled: !!subtitleItem,
                ass_content: subtitleItem
                    ? generateASSContent(
                        subtitleItem.words,
                        subtitleItem.style,
                        videoDuration
                    )
                    : '',
            }

            const overlays = state.overlayTrack.map((o: OverlayTrackItem) => ({
                text: o.text,
                start: o.start,
                end: o.end,
                position: o.position,
            }))

            return {
                clip,
                crop,
                cuts,
                subtitles,
                overlays,
                audio,
                output: {
                    width: 1080,
                    height: 1920,
                    fps: 30,
                    quality: 'final',
                },
                ...(crop_segments ? { crop_segments } : {})
            } as EditSpecPayload // Casting here because EditSpecPayload does not strictly include crop_segments yet, or maybe it does on backend
        },

        resetEditor: () => {
            set({
                job: null,
                currentTime: 0,
                isPlaying: false,
                duration: 0,
                videoTrack: [],
                audioTrack: [],
                subtitleTrack: [],
                overlayTrack: [],
                speedSections: [],
                selectedItem: null,
                ui: initialUIState,
                history: [],
                historyIndex: -1,
                canUndo: false,
                canRedo: false,
                cropSegments: [],
                cropOverrides: {},
                selectedCropSegmentIndex: null,
            })
        },
    }))
)

export type { EditorStore as EditorStoreType }

/**
 * Returns the effective cropX at a given time.
 * Considers manual overrides first, falls back to AI-detected value.
 * Returns 0.5 (center) if no segment found.
 *
 * IMPORTANT: This function is designed for non-reactive use.
 * Call it with useEditorStore.getState() values inside RAF loops or
 * Remotion compositions to avoid triggering React re-renders.
 */
export function getEffectiveCropX(
    time: number,
    cropSegments: CropSegment[],
    cropOverrides: Record<number, number>
): number {
    const idx = cropSegments.findIndex((s) => time >= s.start && time < s.end)
    if (idx === -1) return 0.5
    if (cropOverrides[idx] !== undefined) return cropOverrides[idx]
    return cropSegments[idx].cropX
}
