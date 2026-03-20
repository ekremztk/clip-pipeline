// EDITOR MODULE — Isolated module, no dependencies on other app files
"use client"

import { useEffect, useState } from 'react'

interface ExportModalProps {
    isOpen: boolean
    onClose: () => void
    onExport: (quality: 'draft' | 'final') => void
    isRendering: boolean
    renderProgress: number
}

export default function ExportModal({
    isOpen,
    onClose,
    onExport,
    isRendering,
    renderProgress
}: ExportModalProps) {
    const [selected, setSelected] = useState<'draft' | 'final'>('draft')

    useEffect(() => {
        const handleEscape = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose()
        }
        if (isOpen) {
            document.addEventListener('keydown', handleEscape)
        }
        return () => document.removeEventListener('keydown', handleEscape)
    }, [isOpen, onClose])

    if (!isOpen) return null

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center" onClick={onClose}>
            <div
                className="max-w-sm w-full bg-[#1a1a1a] rounded-xl border border-[#2a2a2a] p-6 shadow-2xl relative"
                onClick={(e) => e.stopPropagation()}
            >
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 text-[#6b7280] hover:text-white transition-colors"
                >
                    ✕
                </button>

                <h2 className="text-xl font-semibold text-white mb-6">Export Video</h2>

                <div className="space-y-3 mb-6">
                    <button
                        onClick={() => !isRendering && setSelected('draft')}
                        disabled={isRendering}
                        className={`w-full flex items-start p-4 rounded-lg border text-left transition-colors ${selected === 'draft'
                                ? 'border-indigo-500 bg-indigo-500/10'
                                : 'border-[#2a2a2a] hover:border-[#3a3a3a] bg-[#1a1a1a]'
                            } ${isRendering ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        <span className="text-2xl mr-3">⚡</span>
                        <div>
                            <div className="text-sm font-medium text-white mb-1">Draft Preview</div>
                            <div className="text-xs text-[#6b7280]">720p · Fast render (~20s) · For review only</div>
                        </div>
                    </button>

                    <button
                        onClick={() => !isRendering && setSelected('final')}
                        disabled={isRendering}
                        className={`w-full flex items-start p-4 rounded-lg border text-left transition-colors ${selected === 'final'
                                ? 'border-indigo-500 bg-indigo-500/10'
                                : 'border-[#2a2a2a] hover:border-[#3a3a3a] bg-[#1a1a1a]'
                            } ${isRendering ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        <span className="text-2xl mr-3">🎬</span>
                        <div>
                            <div className="text-sm font-medium text-white mb-1">Final Export</div>
                            <div className="text-xs text-[#6b7280]">1080×1920 · Best quality (~60s) · YouTube ready</div>
                        </div>
                    </button>
                </div>

                <div className="relative">
                    <button
                        onClick={() => onExport(selected)}
                        disabled={isRendering}
                        className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-[#2a2a2a] text-white font-medium py-3 rounded-lg transition-colors relative overflow-hidden"
                    >
                        {isRendering ? (
                            <>
                                <div
                                    className="absolute inset-y-0 left-0 bg-indigo-600 transition-all duration-300 ease-out"
                                    style={{ width: `${renderProgress}%` }}
                                />
                                <span className="relative z-10 text-[#9ca3af]">Rendering {renderProgress}%...</span>
                            </>
                        ) : (
                            `Export ${selected === 'draft' ? 'Draft' : 'Final'}`
                        )}
                    </button>
                </div>
            </div>
        </div>
    )
}
