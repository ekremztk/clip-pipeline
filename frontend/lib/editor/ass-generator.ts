// EDITOR MODULE — Isolated module, no dependencies on other app files

import { SubtitleWord, SubtitleStyle } from './types'

/**
 * Converts seconds (float) to ASS format H:MM:SS.cc
 * @param seconds The time in seconds
 * @returns Formatted time string
 */
export function formatASSTime(seconds: number): string {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = Math.floor(seconds % 60)
    const cs = Math.floor((seconds % 1) * 100)

    return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}.${cs.toString().padStart(2, '0')}`
}

/**
 * Converts ASS format H:MM:SS.cc back to seconds (float)
 * @param assTime The time string in H:MM:SS.cc format
 * @returns Time in seconds
 */
export function parseASSTime(assTime: string): number {
    const match = assTime.match(/(\d+):(\d{2}):(\d{2})\.(\d{2})/)
    if (!match) return 0
    const [_, h, m, s, cs] = match
    return parseInt(h) * 3600 + parseInt(m) * 60 + parseInt(s) + parseInt(cs) / 100
}

/**
 * Groups words into lines based on word count and duration constraints.
 * @param words Array of subtitle words
 * @param maxWords Maximum words per line (default 6)
 * @param maxDuration Maximum duration per line in seconds (default 2.0)
 * @returns Array of word arrays, each representing a line
 */
export function wordsToLines(
    words: SubtitleWord[],
    maxWords: number = 6,
    maxDuration: number = 2.0
): SubtitleWord[][] {
    const lines: SubtitleWord[][] = []
    let currentLine: SubtitleWord[] = []
    let lineStartTime = 0

    for (const word of words) {
        if (currentLine.length === 0) {
            currentLine.push(word)
            lineStartTime = word.start
        } else {
            const lineDuration = word.end - lineStartTime
            if (currentLine.length >= maxWords || lineDuration > maxDuration) {
                lines.push(currentLine)
                currentLine = [word]
                lineStartTime = word.start
            } else {
                currentLine.push(word)
            }
        }
    }

    if (currentLine.length > 0) {
        lines.push(currentLine)
    }

    return lines
}

/**
 * Generates ASS subtitle content from SubtitleWord array.
 * CRITICAL: Do NOT subtract cut durations. Do NOT shift any timestamps.
 * Use exact original unmodified start and end times.
 * @param words Array of subtitle words
 * @param style Style configuration for subtitles
 * @param videoDuration Duration of the video in seconds
 * @returns ASS content string
 */
export function generateASSContent(
    words: SubtitleWord[],
    style: SubtitleStyle,
    videoDuration: number
): string {
    // Determine vertical margin based on position
    const marginV = style.position === 'bottom' ? 80 : style.position === 'top' ? 1760 : 960

    let ass = `[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,${style.fontFamily},${style.fontSize},${style.color},&H000000FF,${style.outlineColor},&H80000000,-1,0,0,0,100,100,0,0,1,${style.outlineWidth},0,2,40,40,${marginV},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
`

    const lines = wordsToLines(words)

    for (const line of lines) {
        if (line.length === 0) continue

        const start = formatASSTime(line[0].start)
        const end = formatASSTime(line[line.length - 1].end)

        let text = ''
        for (const word of line) {
            // Convert duration to centiseconds for \k tag
            const durationCs = Math.round((word.end - word.start) * 100)
            text += `{\\k${durationCs}}${word.word} `
        }

        ass += `Dialogue: 0,${start},${end},Default,,0,0,0,,${text.trim()}\n`
    }

    return ass
}