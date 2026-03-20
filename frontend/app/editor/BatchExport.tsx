// EDITOR MODULE — Isolated module, no dependencies on other app files
"use client"

import React, { useState } from 'react'
import { EditorJob } from '@/lib/editor/types'
import { Loader2 } from 'lucide-react'

interface BatchExportProps {
    jobs: EditorJob[]
    onBatchStart: (jobIds: string[], quality: 'draft' | 'final') => void
    isBatchRendering: boolean
}

export default function BatchExport({ jobs, onBatchStart, isBatchRendering }: BatchExportProps) {
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
    const [quality, setQuality] = useState<'draft' | 'final'>('final')

    const validJobs = jobs.filter(j => j.status === 'completed' && j.editSpec)
    const isSelectable = (j: EditorJob) => j.status === 'completed' && !!j.editSpec

    const handleToggle = (id: string) => {
        const next = new Set(selectedIds)
        if (next.has(id)) next.delete(id)
        else next.add(id)
        setSelectedIds(next)
    }

    const handleSelectAll = () => {
        setSelectedIds(new Set(validJobs.map(j => j.id)))
    }

    const handleDeselectAll = () => {
        setSelectedIds(new Set())
    }

    const handleExport = () => {
        if (selectedIds.size === 0) return
        onBatchStart(Array.from(selectedIds), quality)
    }

    return (
        <div className="bg-[#1a1a1a] border border-[#2a2a2a] rounded-xl p-6">
            <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold text-white flex items-center gap-2">
                    Batch Export
                    <span className="bg-[#2a2a2a] text-[#a1a1aa] text-xs px-2 py-0.5 rounded-full">
                        {jobs.length} total
                    </span>
                </h2>
                <div className="flex gap-2">
                    <button
                        onClick={handleSelectAll}
                        className="text-xs text-[#6b7280] hover:text-white px-2 py-1 rounded"
                    >
                        Select All
                    </button>
                    <button
                        onClick={handleDeselectAll}
                        className="text-xs text-[#6b7280] hover:text-white px-2 py-1 rounded"
                    >
                        Deselect All
                    </button>
                </div>
            </div>

            <div className="space-y-2 mb-6 max-h-[400px] overflow-y-auto pr-2 custom-scrollbar">
                {jobs.map(job => {
                    const selectable = isSelectable(job)
                    return (
                        <div
                            key={job.id}
                            className={`flex items-center justify-between p-3 rounded-lg border ${selectable
                                    ? selectedIds.has(job.id)
                                        ? 'border-indigo-500/50 bg-indigo-500/10'
                                        : 'border-[#2a2a2a] bg-[#1f1f1f] hover:border-[#3a3a3a]'
                                    : 'border-[#2a2a2a] bg-[#1a1a1a] opacity-50 cursor-not-allowed'
                                }`}
                        >
                            <div className="flex items-center gap-3">
                                <input
                                    type="checkbox"
                                    checked={selectedIds.has(job.id)}
                                    onChange={() => selectable && handleToggle(job.id)}
                                    disabled={!selectable || isBatchRendering}
                                    className="w-4 h-4 rounded border-[#3a3a3a] text-indigo-600 focus:ring-indigo-500 bg-[#0f0f0f]"
                                />
                                <div className="font-mono text-sm text-[#e5e7eb]">
                                    {job.id.slice(0, 8)}
                                </div>
                            </div>
                            <div className="flex items-center gap-3">
                                <div className="text-xs text-[#6b7280]">
                                    {job.status === 'processing' ? `${job.progress}%` : job.status}
                                </div>
                                {!selectable && (
                                    <div className="text-[10px] text-[#ef4444]" title="Run Auto Edit first">
                                        ⚠ Needs Auto Edit
                                    </div>
                                )}
                            </div>
                        </div>
                    )
                })}
                {jobs.length === 0 && (
                    <div className="text-center text-[#6b7280] text-sm py-4">
                        No jobs available
                    </div>
                )}
            </div>

            <div className="flex items-center gap-4">
                <div className="flex bg-[#0f0f0f] rounded-lg p-1 border border-[#2a2a2a]">
                    <button
                        onClick={() => setQuality('draft')}
                        className={`px-4 py-1.5 text-sm rounded-md transition-colors ${quality === 'draft' ? 'bg-[#2a2a2a] text-white' : 'text-[#6b7280] hover:text-white'
                            }`}
                        disabled={isBatchRendering}
                    >
                        Draft Preview
                    </button>
                    <button
                        onClick={() => setQuality('final')}
                        className={`px-4 py-1.5 text-sm rounded-md transition-colors ${quality === 'final' ? 'bg-[#2a2a2a] text-white' : 'text-[#6b7280] hover:text-white'
                            }`}
                        disabled={isBatchRendering}
                    >
                        Final Export
                    </button>
                </div>

                <button
                    onClick={handleExport}
                    disabled={selectedIds.size === 0 || isBatchRendering}
                    className="flex-1 flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-[#2a2a2a] disabled:text-[#6b7280] text-white font-medium py-2 px-4 rounded-lg transition-colors"
                >
                    {isBatchRendering ? (
                        <>
                            <Loader2 className="w-4 h-4 animate-spin" />
                            <span>Queuing Batch...</span>
                        </>
                    ) : (
                        <span>Export Selected ({selectedIds.size})</span>
                    )}
                </button>
            </div>
        </div>
    )
}