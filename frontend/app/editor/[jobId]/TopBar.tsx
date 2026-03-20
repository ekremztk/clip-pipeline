"use client";

// EDITOR MODULE — Isolated module, no dependencies on other app files

import React, { useState } from 'react';
import { useEditorStore, EditorStoreType } from '@/lib/editor/store';
import { startRender, triggerAutoEdit, mapEditDecisions, getJob, streamJobProgress } from '@/lib/editor/api';
import { Undo2, Redo2, Sparkles, Loader2, PlaySquare, Download } from 'lucide-react';
import ExportModal from './ExportModal';

export default function TopBar() {
    const job = useEditorStore((state: EditorStoreType) => state.job);
    const canUndo = useEditorStore((state: EditorStoreType) => state.canUndo);
    const canRedo = useEditorStore((state: EditorStoreType) => state.canRedo);
    const undo = useEditorStore((state: EditorStoreType) => state.undo);
    const redo = useEditorStore((state: EditorStoreType) => state.redo);
    const buildEditSpec = useEditorStore((state: EditorStoreType) => state.buildEditSpec);

    const [showToast, setShowToast] = useState(false);
    const [toastMessage, setToastMessage] = useState("");
    const [isExportModalOpen, setIsExportModalOpen] = useState(false);
    const updateJobProgress = useEditorStore((state: EditorStoreType) => state.updateJobProgress);
    const setUI = useEditorStore((state: EditorStoreType) => state.setUI);
    const loadFromEditDecisions = useEditorStore((state: EditorStoreType) => state.loadFromEditDecisions);
    const isProcessing = useEditorStore((state: EditorStoreType) => state.ui.isProcessing);
    const isRendering = useEditorStore((state: EditorStoreType) => state.ui.isRendering);
    const renderProgress = useEditorStore((state: EditorStoreType) => state.ui.renderProgress);

    const handleAutoEdit = async () => {
        if (!job?.id) return;
        setUI({ isProcessing: true });

        try {
            await triggerAutoEdit(job.id);

            const cleanup = streamJobProgress(
                job.id,
                (status, progress) => updateJobProgress(progress),
                async () => {
                    // On complete: fetch updated job and apply decisions to timeline
                    try {
                        const updatedJob = await getJob(job.id);
                        if (updatedJob.editSpec) {
                            const decisions = mapEditDecisions(
                                updatedJob.editSpec as unknown as Record<string, unknown>
                            );
                            loadFromEditDecisions(decisions);
                        }
                    } catch (err) {
                        console.error('Failed to load edit decisions:', err);
                    } finally {
                        setUI({ isProcessing: false });
                        cleanup();
                        setToastMessage("✨ Auto edit applied!");
                        setShowToast(true);
                        setTimeout(() => setShowToast(false), 3000);
                    }
                },
                (err) => {
                    console.error('Auto edit stream error:', err);
                    setUI({ isProcessing: false });
                    cleanup();
                }
            );
        } catch (err) {
            console.error('Failed to trigger auto edit:', err);
            setUI({ isProcessing: false });
        }
    };

    const handleRender = async (quality: 'draft' | 'final') => {
        if (!job?.id) return;
        try {
            setUI({ isRendering: true, renderProgress: 0 });
            const editSpec = buildEditSpec();
            editSpec.output.quality = quality; // Override quality
            await startRender(job.id, editSpec);

            // Start polling or rely on SSE stream. For simplicity, we just show toast and close after a delay if no stream is connected here
            setToastMessage(`Render queued (${quality})`);
            setShowToast(true);
            setTimeout(() => setShowToast(false), 3000);
            setIsExportModalOpen(false);
        } catch (error) {
            console.error("Render failed", error);
            alert("Failed to queue render");
        } finally {
            setUI({ isRendering: false });
        }
    };

    return (
        <div className="w-full h-full flex items-center justify-between px-4 text-sm">
            {/* Left */}
            <div className="flex items-center space-x-3 w-1/3">
                <span className="font-bold text-[#6366f1] tracking-tight">Prognot Editor</span>
                {job && (
                    <span className="text-[#6b7280] font-mono text-xs hidden sm:inline-block">
                        #{job.id.slice(0, 8)}
                    </span>
                )}
            </div>

            {/* Center */}
            <div className="flex items-center justify-center w-1/3 relative">
                <button
                    onClick={handleAutoEdit}
                    disabled={isProcessing}
                    className="flex items-center space-x-2 bg-[#6366f1] hover:bg-[#4f46e5] text-white px-4 py-1.5 rounded-full font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    {isProcessing ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                        <Sparkles className="w-4 h-4" />
                    )}
                    <span>{isProcessing ? "Auto Editing..." : "Auto Edit"}</span>
                </button>

                {/* Toast Notification */}
                {showToast && (
                    <div className="absolute top-12 bg-[#2a2a2a] text-white px-4 py-2 rounded-md shadow-lg border border-[#3a3a3a] animate-in fade-in slide-in-from-top-2 z-50">
                        {toastMessage}
                    </div>
                )}
            </div>

            {/* Right */}
            <div className="flex items-center justify-end space-x-3 w-1/3">
                <button
                    onClick={undo}
                    disabled={!canUndo || isRendering}
                    className="text-[#f1f1f1] hover:text-white disabled:text-[#6b7280] disabled:cursor-not-allowed transition-colors"
                    title="Undo"
                >
                    <Undo2 className="w-5 h-5" />
                </button>
                <button
                    onClick={redo}
                    disabled={!canRedo || isRendering}
                    className="text-[#f1f1f1] hover:text-white disabled:text-[#6b7280] disabled:cursor-not-allowed transition-colors"
                    title="Redo"
                >
                    <Redo2 className="w-5 h-5" />
                </button>

                <div className="w-px h-5 bg-[#2a2a2a] mx-1"></div>

                <button
                    onClick={() => setIsExportModalOpen(true)}
                    className="flex items-center space-x-1.5 bg-[#6366f1] hover:bg-[#4f46e5] text-white px-4 py-1.5 rounded-md font-medium transition-colors"
                >
                    <Download className="w-4 h-4" />
                    <span>Export</span>
                </button>
            </div>

            <ExportModal
                isOpen={isExportModalOpen}
                onClose={() => setIsExportModalOpen(false)}
                onExport={handleRender}
                isRendering={isRendering}
                renderProgress={renderProgress}
            />
        </div>
    );
}
