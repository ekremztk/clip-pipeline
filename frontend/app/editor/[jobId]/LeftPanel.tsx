"use client";

// EDITOR MODULE — Isolated module, no dependencies on other app files

import React, { useState, useEffect, useRef } from 'react';
import { useEditorStore, EditorStoreType } from '@/lib/editor/store';
import { AudioTrackItem, SubtitleWord } from '@/lib/editor/types';
import { Search, Music, Plus, Play } from 'lucide-react';

const PRESET_TRACKS = [
    { id: 'bgm-lofi', name: 'Lo-fi Chill', duration: 120, src: 'preset://lofi-chill' },
    { id: 'bgm-upbeat', name: 'Upbeat Rhythm', duration: 90, src: 'preset://upbeat-rhythm' },
    { id: 'bgm-dramatic', name: 'Dramatic Build', duration: 150, src: 'preset://dramatic-build' },
];

export default function LeftPanel() {
    const [activeTab, setActiveTab] = useState<'transcript' | 'assets'>('transcript');

    return (
        <div className="h-full flex flex-col bg-[#1a1a1a] text-white">
            {/* Tabs */}
            <div className="flex border-b border-[#2a2a2a] shrink-0">
                <button
                    onClick={() => setActiveTab('transcript')}
                    className={`flex-1 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'transcript' ? 'border-[#6366f1] text-white' : 'border-transparent text-[#6b7280] hover:text-[#f1f1f1]'
                        }`}
                >
                    Transcript
                </button>
                <button
                    onClick={() => setActiveTab('assets')}
                    className={`flex-1 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'assets' ? 'border-[#6366f1] text-white' : 'border-transparent text-[#6b7280] hover:text-[#f1f1f1]'
                        }`}
                >
                    Assets
                </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-hidden relative">
                {activeTab === 'transcript' ? <TranscriptTab /> : <AssetsTab />}
            </div>
        </div>
    );
}

function TranscriptTab() {
    const [search, setSearch] = useState('');
    const words = useEditorStore((state: EditorStoreType) => state.subtitleTrack[0]?.words || []);
    const currentTime = useEditorStore((state: EditorStoreType) => state.currentTime);
    const setCurrentTime = useEditorStore((state: EditorStoreType) => state.setCurrentTime);
    const setIsPlaying = useEditorStore((state: EditorStoreType) => state.setIsPlaying);

    const scrollRef = useRef<HTMLDivElement>(null);
    const activeWordRef = useRef<HTMLButtonElement>(null);

    const filteredWords = words.filter((w: SubtitleWord) => w.word.toLowerCase().includes(search.toLowerCase()));

    // Auto-scroll to active word
    useEffect(() => {
        if (activeWordRef.current && scrollRef.current) {
            const container = scrollRef.current;
            const element = activeWordRef.current;

            // Only scroll if element is not fully visible
            const containerRect = container.getBoundingClientRect();
            const elementRect = element.getBoundingClientRect();

            if (elementRect.top < containerRect.top || elementRect.bottom > containerRect.bottom) {
                element.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    }, [currentTime]);

    const handleWordClick = (start: number) => {
        setIsPlaying(false);
        setCurrentTime(start);
    };

    const getSpeakerColor = (speakerId: number) => {
        switch (speakerId) {
            case 0: return 'text-indigo-400 bg-indigo-400/10 border-indigo-400/20';
            case 1: return 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20';
            case 2: return 'text-amber-400 bg-amber-400/10 border-amber-400/20';
            default: return 'text-gray-300 bg-gray-800 border-gray-700';
        }
    };

    const formatTime = (seconds: number) => {
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    };

    return (
        <div className="h-full flex flex-col">
            <div className="p-3 shrink-0 border-b border-[#2a2a2a]">
                <div className="relative">
                    <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[#6b7280]" />
                    <input
                        type="text"
                        placeholder="Search transcript..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        className="w-full bg-[#2a2a2a] border border-[#3a3a3a] rounded-md py-1.5 pl-9 pr-3 text-sm text-white placeholder-[#6b7280] focus:outline-none focus:border-[#6366f1]"
                    />
                </div>
            </div>

            <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-2">
                {(!words || words.length === 0) ? (
                    <div className="flex flex-col items-center justify-center h-32 text-center px-4 py-4 mt-8">
                        <span className="text-3xl mb-2">📝</span>
                        <p className="text-xs text-[#6b7280] font-medium">No transcript yet</p>
                        <p className="text-[10px] text-[#4b5563] mt-1">
                            Click "Auto Edit" to generate captions and edit decisions
                        </p>
                    </div>
                ) : filteredWords.length === 0 ? (
                    <div className="text-center text-[#6b7280] text-sm mt-8">
                        No words found
                    </div>
                ) : (
                    filteredWords.map((wordObj: SubtitleWord, i: number) => {
                        const isActive = currentTime >= wordObj.start && currentTime <= wordObj.end;
                        const speakerStyles = getSpeakerColor(wordObj.speaker);

                        return (
                            <button
                                key={i}
                                ref={isActive ? activeWordRef : null}
                                onClick={() => handleWordClick(wordObj.start)}
                                className={`w-full text-left p-2 rounded-md border transition-all flex flex-col ${isActive
                                    ? 'border-[#6366f1] ring-1 ring-[#6366f1] bg-[#2a2a2a]'
                                    : 'border-transparent hover:bg-[#2a2a2a]'
                                    }`}
                            >
                                <div className="flex justify-between items-start mb-1">
                                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium border ${speakerStyles}`}>
                                        Speaker {wordObj.speaker}
                                    </span>
                                    <span className="text-[10px] text-[#6b7280] font-mono">
                                        {formatTime(wordObj.start)}
                                    </span>
                                </div>
                                <span className={`text-sm ${isActive ? 'text-white font-medium' : 'text-[#f1f1f1]'}`}>
                                    {wordObj.word}
                                </span>
                            </button>
                        );
                    })
                )}
            </div>
        </div>
    );
}

function AssetsTab() {
    const addAudioItem = useEditorStore((state: EditorStoreType) => state.setAudioTrack);
    const audioTrack = useEditorStore((state: EditorStoreType) => state.audioTrack);
    const pushHistory = useEditorStore((state: EditorStoreType) => state.pushHistory);
    const videoDuration = useEditorStore((state: EditorStoreType) => state.duration);

    const handleAddPreset = (track: typeof PRESET_TRACKS[0]) => {
        const newItem: AudioTrackItem = {
            id: `audio-${Date.now()}`,
            type: 'audio',
            start: 0,
            end: Math.min(track.duration, videoDuration || track.duration),
            src: track.src,
            volume: 0.5,
            fadeIn: 1,
            fadeOut: 1,
            isBackgroundMusic: true,
            duckLevelDb: -12,
        };

        // Replace existing background music if any, otherwise add
        const filtered = audioTrack.filter((a: AudioTrackItem) => !a.isBackgroundMusic);
        addAudioItem([...filtered, newItem]);
        pushHistory();
    };

    const formatDuration = (seconds: number) => {
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    };

    return (
        <div className="h-full overflow-y-auto p-4">
            <h3 className="text-xs font-semibold text-[#6b7280] uppercase tracking-wider mb-4 flex items-center">
                <Music className="w-3.5 h-3.5 mr-1.5" />
                Background Music
            </h3>

            <div className="space-y-3">
                {PRESET_TRACKS.map((track) => {
                    const isAdded = audioTrack.some((a: AudioTrackItem) => a.src === track.src);

                    return (
                        <div key={track.id} className="bg-[#2a2a2a] border border-[#3a3a3a] rounded-lg p-3">
                            <div className="flex justify-between items-start mb-2">
                                <span className="text-sm font-medium text-white">{track.name}</span>
                                <span className="text-[10px] bg-[#1a1a1a] text-[#6b7280] px-1.5 py-0.5 rounded font-mono border border-[#3a3a3a]">
                                    {formatDuration(track.duration)}
                                </span>
                            </div>

                            <div className="flex space-x-2 mt-3">
                                <button className="flex-1 flex items-center justify-center space-x-1 py-1.5 bg-[#1a1a1a] hover:bg-[#3a3a3a] rounded text-xs text-[#f1f1f1] border border-[#3a3a3a] transition-colors">
                                    <Play className="w-3 h-3" />
                                    <span>Preview</span>
                                </button>

                                <button
                                    onClick={() => handleAddPreset(track)}
                                    disabled={isAdded}
                                    className="flex-1 flex items-center justify-center space-x-1 py-1.5 bg-[#6366f1] hover:bg-[#4f46e5] disabled:bg-[#3a3a3a] disabled:text-[#6b7280] rounded text-xs text-white transition-colors"
                                >
                                    <Plus className="w-3 h-3" />
                                    <span>{isAdded ? 'Added' : 'Add'}</span>
                                </button>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
