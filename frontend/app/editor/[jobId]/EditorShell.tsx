"use client";

// EDITOR MODULE — Isolated module, no dependencies on other app files

import React, { useEffect, Component, ReactNode } from 'react';
import { EditorJob } from '@/lib/editor/types';
import { useEditorStore, EditorStoreType } from '@/lib/editor/store';

import TopBar from './TopBar';
import LeftPanel from './LeftPanel';
import PreviewCanvas from './PreviewCanvas';
import RightPanel from './RightPanel';

interface EditorShellProps {
    job: EditorJob | null;
    sourceVideoUrl?: string;
}

class EditorErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean, error: Error | null }> {
    constructor(props: { children: ReactNode }) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error: Error) {
        return { hasError: true, error };
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="min-h-screen bg-[#0f0f0f] flex items-center justify-center p-4">
                    <div className="bg-[#1a1a1a] border border-red-900/50 p-8 rounded-xl max-w-md w-full flex flex-col items-center">
                        <div className="w-16 h-16 rounded-full bg-red-900/20 flex items-center justify-center mb-6">
                            <svg className="w-8 h-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                            </svg>
                        </div>
                        <h2 className="text-xl font-semibold text-white mb-2 text-center">Editor Error</h2>
                        <p className="text-sm text-[#6b7280] text-center mb-8 break-words w-full">
                            {this.state.error?.message || 'Something went wrong in the editor.'}
                        </p>
                        <button
                            onClick={() => window.location.reload()}
                            className="bg-[#2a2a2a] hover:bg-[#3a3a3a] border border-[#3a3a3a] text-white px-6 py-2 rounded-md font-medium transition-colors w-full"
                        >
                            Reload Editor
                        </button>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}

function EditorLayout({ job, sourceVideoUrl }: EditorShellProps) {
    const loadFromJob = useEditorStore((state: EditorStoreType) => state.loadFromJob);

    useEffect(() => {
        loadFromJob(job);
    }, [job, loadFromJob]);

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            const target = e.target as HTMLElement
            if (['INPUT', 'TEXTAREA'].includes(target.tagName)) return
            if (target.isContentEditable) return

            const {
                currentTime, duration, isPlaying,
                setIsPlaying, setCurrentTime,
                canUndo, canRedo, undo, redo
            } = useEditorStore.getState()

            switch (true) {
                case e.code === 'Space':
                    e.preventDefault()
                    setIsPlaying(!isPlaying)
                    break
                case (e.metaKey || e.ctrlKey) && e.code === 'KeyZ' && !e.shiftKey:
                    e.preventDefault()
                    if (canUndo) undo()
                    break
                case (e.metaKey || e.ctrlKey) && e.code === 'KeyZ' && e.shiftKey:
                case (e.metaKey || e.ctrlKey) && e.code === 'KeyY':
                    e.preventDefault()
                    if (canRedo) redo()
                    break
                case e.code === 'ArrowLeft' && !e.shiftKey && !e.metaKey && !e.ctrlKey:
                    e.preventDefault()
                    setCurrentTime(Math.max(0, currentTime - 1))
                    break
                case e.code === 'ArrowRight' && !e.shiftKey && !e.metaKey && !e.ctrlKey:
                    e.preventDefault()
                    setCurrentTime(Math.min(duration, currentTime + 1))
                    break
                case e.code === 'ArrowLeft' && e.shiftKey:
                    e.preventDefault()
                    setCurrentTime(Math.max(0, currentTime - 5))
                    break
                case e.code === 'ArrowRight' && e.shiftKey:
                    e.preventDefault()
                    setCurrentTime(Math.min(duration, currentTime + 5))
                    break
            }
        }

        document.addEventListener('keydown', handleKeyDown)
        return () => document.removeEventListener('keydown', handleKeyDown)
    }, [])

    return (
        <div className="h-[100dvh] w-full bg-[#0f0f0f] text-white overflow-hidden flex flex-col relative">
            {job?.status === 'failed' && job.errorMessage && (
                <div className="absolute top-14 left-0 right-0 z-40 mx-4">
                    <div className="flex items-center gap-2 px-4 py-2 bg-red-500/10 border border-red-500/30 rounded-lg text-xs text-red-400">
                        <span>⚠</span>
                        <span className="flex-1 truncate">{job.errorMessage}</span>
                        <button className="text-red-400 hover:text-red-300 ml-2">✕</button>
                    </div>
                </div>
            )}

            <div className="h-[48px] shrink-0 border-b border-[#2a2a2a] bg-[#1a1a1a]">
                <TopBar />
            </div>

            <div className="flex-1 flex overflow-hidden">
                <div className="w-[256px] shrink-0 border-r border-[#2a2a2a] bg-[#1a1a1a]">
                    <LeftPanel />
                </div>

                <div className="flex-1 overflow-hidden relative">
                    <PreviewCanvas sourceVideoUrl={sourceVideoUrl || ''} />
                </div>

                <div className="w-[288px] shrink-0 border-l border-[#2a2a2a] bg-[#1a1a1a]">
                    <RightPanel />
                </div>
            </div>

            <div className="h-[192px] shrink-0 border-t border-[#2a2a2a] bg-[#1a1a1a]">
                {/* Timeline Placeholder */}
                <div className="w-full h-full flex items-center justify-center text-[#6b7280] italic">
                    Timeline (Built in next prompt)
                </div>
            </div>

            <div className="fixed bottom-4 left-4 text-[10px] text-[#3a3a3a] select-none pointer-events-none z-10">
                Space · ⌘Z · ←→
            </div>
        </div>
    );
}

export default function EditorShell(props: EditorShellProps) {
    return (
        <EditorErrorBoundary>
            <EditorLayout {...props} />
        </EditorErrorBoundary>
    );
}
