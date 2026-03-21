// EDITOR MODULE — Isolated module, no dependencies on other app files
"use client"

import { useRouter } from 'next/navigation'
import { useState, useRef } from 'react'
import { createUploadUrl, uploadFileToR2, startJob } from '@/lib/editor/api'

export default function EditorHomePage() {
    const router = useRouter()
    const [isDragging, setIsDragging] = useState(false)
    const [isUploading, setIsUploading] = useState(false)
    const [uploadProgress, setUploadProgress] = useState(0)
    const [error, setError] = useState<string | null>(null)
    const fileInputRef = useRef<HTMLInputElement>(null)

    const handleFile = async (file: File) => {
        if (!file.type.startsWith('video/') && !file.name.match(/\.(mp4|mov|webm)$/i)) {
            setError('Invalid file type. Please upload MP4, MOV, or WebM.')
            return
        }
        if (file.size > 500 * 1024 * 1024) {
            setError('File too large. Maximum 500MB.')
            return
        }

        setError(null)
        setIsUploading(true)
        setUploadProgress(0)

        try {
            const { uploadUrl, r2Key, jobId } = await createUploadUrl(file.name, file.type, null)
            await uploadFileToR2(uploadUrl, file, (pct) => setUploadProgress(Math.round(pct)))
            await startJob(jobId)
            router.push(`/editor/${jobId}`)
        } catch (err) {
            setError(String(err))
            setIsUploading(false)
        }
    }

    const onDrop = (e: React.DragEvent) => {
        e.preventDefault()
        setIsDragging(false)
        const file = e.dataTransfer.files?.[0]
        if (file) handleFile(file)
    }

    return (
        <div className="min-h-screen bg-[#0f0f0f] flex flex-col">
            <div className="h-12 border-b border-[#2a2a2a] bg-[#1a1a1a] flex items-center px-4">
                <span className="font-bold text-[#6366f1] tracking-tight">Prognot Editor</span>
            </div>

            <div className="flex-1 flex items-center justify-center p-8">
                <div className="max-w-lg w-full">
                    <h1 className="text-2xl font-semibold text-white text-center mb-2">New Project</h1>
                    <p className="text-[#6b7280] text-center text-sm mb-8">Drop a video to start editing</p>

                    {error && (
                        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm flex items-center justify-between">
                            <span>{error}</span>
                            <button onClick={() => setError(null)} className="ml-2 hover:text-red-300">✕</button>
                        </div>
                    )}

                    {isUploading ? (
                        <div className="border-2 border-[#2a2a2a] rounded-xl p-12 text-center">
                            <div className="w-10 h-10 border-4 border-[#6366f1] border-t-transparent rounded-full animate-spin mx-auto mb-4" />
                            <p className="text-white font-medium mb-4">Uploading... {uploadProgress}%</p>
                            <div className="w-full h-2 bg-[#2a2a2a] rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-[#6366f1] transition-all duration-300"
                                    style={{ width: `${uploadProgress}%` }}
                                />
                            </div>
                        </div>
                    ) : (
                        <div
                            onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
                            onDragLeave={() => setIsDragging(false)}
                            onDrop={onDrop}
                            onClick={() => fileInputRef.current?.click()}
                            className={`border-2 border-dashed rounded-xl p-16 text-center cursor-pointer transition-all ${isDragging
                                    ? 'border-[#6366f1] bg-[#6366f1]/10'
                                    : 'border-[#2a2a2a] hover:border-[#6366f1]/50 bg-[#1a1a1a] hover:bg-[#1f1f1f]'
                                }`}
                        >
                            <input
                                ref={fileInputRef}
                                type="file"
                                className="hidden"
                                accept=".mp4,.mov,.webm,video/*"
                                onChange={(e) => {
                                    const file = e.target.files?.[0]
                                    if (file) handleFile(file)
                                }}
                            />
                            <div className="text-5xl mb-4">🎥</div>
                            <p className="text-white font-medium mb-1">Drop video here or click to browse</p>
                            <p className="text-sm text-[#6b7280]">MP4, MOV, WebM • up to 500MB</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
