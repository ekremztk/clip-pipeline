// EDITOR MODULE — Isolated module, no dependencies on other app files

/**
 * Represents a single video track item.
 */
export interface VideoTrackItem {
    id: string
    type: 'video'
    start: number
    end: number
    src: string                   // R2 presigned URL
    cropMode: 'center' | 'manual'
    cropX: number                 // 0.0 - 1.0
    scale: number                 // 1.0 = original
    positionX: number
    positionY: number
    speed: number                 // 1.0 = normal
    cuts?: Array<{ removeFrom: number; removeTo: number }>
}

/**
 * Represents a single audio track item.
 */
export interface AudioTrackItem {
    id: string
    type: 'audio'
    start: number
    end: number
    src: string
    volume: number                // 0.0 - 1.0
    fadeIn: number
    fadeOut: number
    isBackgroundMusic: boolean
    duckLevelDb: number           // default -12
}

/**
 * Represents a single word in a subtitle track.
 */
export interface SubtitleWord {
    word: string
    start: number
    end: number
    speaker: number
    confidence: number
}

/**
 * Styling configuration for subtitles.
 */
export interface SubtitleStyle {
    fontFamily: 'Montserrat' | 'TheBoldFont' | 'Roboto'
    fontSize: number
    color: string
    outlineColor: string
    outlineWidth: number
    position: 'bottom' | 'center' | 'top'
    animationStyle: 'word-highlight' | 'word-pop' | 'karaoke'
}

/**
 * Represents a subtitle track item consisting of multiple words.
 */
export interface SubtitleTrackItem {
    id: string
    type: 'subtitle'
    start: number
    end: number
    words: SubtitleWord[]
    style: SubtitleStyle
}

/**
 * Represents a text overlay track item.
 */
export interface OverlayTrackItem {
    id: string
    type: 'overlay'
    start: number
    end: number
    text: string
    position: 'top' | 'center' | 'bottom'
    backgroundColor: string
    textColor: string
}

/**
 * Union type for all track items.
 */
export type TrackItem = VideoTrackItem | AudioTrackItem | SubtitleTrackItem | OverlayTrackItem

/**
 * Represents the currently selected item in the editor.
 */
export type SelectedItemType = TrackItem | null

/**
 * Status of the background job.
 */
export type JobStatus = 'pending' | 'processing' | 'completed' | 'failed'

/**
 * Defines a segment of time where a specific speaker is talking.
 */
export interface SpeakerSegment {
    start: number
    end: number
    speakerId: number
}

/**
 * A simple start and end time interval.
 */
export interface TimeInterval {
    start: number
    end: number
}

/**
 * Represents the silence map of the audio.
 */
export interface SilenceMap {
    silentIntervals: TimeInterval[]
    speechIntervals: TimeInterval[]
}

/**
 * Video metadata details.
 */
export interface VideoMetadata {
    duration: number
    fps: number
    width: number
    height: number
    codec: string
}

/**
 * Represents the overarching editor job state.
 */
export interface EditorJob {
    id: string
    status: JobStatus
    progress: number
    sourceR2Key: string
    outputR2Key?: string
    transcript?: SubtitleWord[]
    speakerSegments?: SpeakerSegment[]
    silenceMap?: SilenceMap
    videoMetadata?: VideoMetadata
    editSpec?: EditSpec
    errorMessage?: string
    createdAt: string
}

/**
 * Represents the user's edits in the UI (camelCase).
 * Converted to snake_case before API dispatch.
 */
export interface EditSpec {
    clip: { start: number; end: number }
    crop: { mode: 'center' | 'manual'; x: number }
    cuts: Array<{ removeFrom: number; removeTo: number }>
    subtitles: {
        enabled: boolean
        assContent: string
    }
    overlays: Array<{
        text: string
        start: number
        end: number
        position: 'top' | 'center' | 'bottom'
    }>
    audio: {
        backgroundMusicPath?: string
        duckLevelDb: number
    }
    output: {
        width: 1080
        height: 1920
        fps: 30
        quality: 'draft' | 'final'
    }
}

/**
 * Backend payload for edit specification (snake_case).
 * Used at API boundaries only.
 */
export interface EditSpecPayload {
    clip: { start: number; end: number }
    crop: { mode: 'center' | 'manual'; x: number }
    cuts: Array<{ remove_from: number; remove_to: number }>
    subtitles: {
        enabled: boolean
        ass_content: string
    }
    overlays: Array<{
        text: string
        start: number
        end: number
        position: 'top' | 'center' | 'bottom'
    }>
    audio: {
        background_music_path?: string
        duck_level_db: number
    }
    output: {
        width: 1080
        height: 1920
        fps: 30
        quality: 'draft' | 'final'
    }
}

/**
 * Response received when requesting an upload URL.
 */
export interface EditDecisions {
    // _reasoning is intentionally omitted from frontend type
    // It exists in backend output but frontend does not use it
    hookStart: number
    hookReason: string
    hookScore: number
    cuts: Array<{
        removeFrom: number
        removeTo: number
        reason: string
    }>
    speedSections: Array<{
        from: number
        to: number
        multiplier: number
    }>
    commentaryCards: Array<{
        text: string
        at: number
        duration: number
        position: 'top' | 'center' | 'bottom'
    }>
    titleSuggestion: string
    descriptionSuggestion: string
    totalDurationEstimate: number
}

export interface UploadUrlResponse {
    uploadUrl: string
    r2Key: string
    jobId: string
}

/**
 * Active tab in the right panel.
 */
export type RightPanelTab = 'transform' | 'subtitle' | 'overlay' | 'audio'

/** Single crop segment from smart reframe pipeline */
export interface CropSegment {
    start: number
    end: number
    speakerId: number
    cropX: number          // 0.0 - 1.0 normalized, used for preview + sent to backend
    cropXPixels: number    // pixel offset from backend (read-only, never recalculated on frontend)
    detected: boolean      // false = face not found, center fallback used
    confidence: number     // average detection confidence 0.0 - 1.0
}

/**
 * Global UI state for the editor.
 */
export interface EditorUIState {
    isProcessing: boolean
    isRendering: boolean
    renderProgress: number
    rightPanelTab: RightPanelTab
    zoom: number
    showWaveform: boolean
}