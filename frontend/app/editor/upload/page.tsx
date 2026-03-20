// EDITOR MODULE — Isolated module, no dependencies on other app files
"use client"

import { useSearchParams, useRouter } from 'next/navigation'
import { useEffect, useState, useRef, Suspense } from 'react'
import { createUploadUrl, uploadFileToR2, startJob, createJobFromKey } from '@/lib/editor/api'

function UploadPageContent() {
    const searchParams = useSearchParams()
    const router = useRouter()
    const sourceKey = searchParams.get('sourceKey')
    const userId = "temp-user-id" // TODO: get from auth

    const [status, setStatus] = useState<'idle' | 'creating' | 'uploading' | 'processing' | 'error'>('idle')
    const [progress, setProgress] = useState(0)
    const [error, setError] = useState<string | null>(null)
    const fileInputRef = useRef<HTMLInputElement>(null)

    useEffect(() => {
        if (!sourceKey) return
        async function handleDirectSource() {
            setStatus('creating')
            try {
                const { jobId } = await createJobFromKey(sourceKey!, userId)
                await startJob(jobId)
                router.push(`/editor/${jobId}`)
            } catch (err) {
                setError(String(err))
                setStatus('error')
            }
        }
        handleDirectSource()
    }, [sourceKey, router])

    const handleFileSelect = async (file: File) => {
        if (!file) return

        // Client-side validation
        if (!file.type.startsWith('video/') && !file.name.match(/\.(mp4|mov|webm)$/i)) {
            setError("Invalid file type. Please upload MP4, MOV, or WebM.")
            return
        }
        if (file.size > 500 * 1024 * 1024) {
            setError("File too large. Maximum size is 500MB.")
            return
        }

        setError(null)
        setStatus('uploading')
        setProgress(0)

        try {
            const { uploadUrl, r2Key, jobId } = await createUploadUrl(file.name, file.type, userId)

            await uploadFileToR2(uploadUrl, file, (pct) => {
                setProgress(Math.round(pct))
            })

            setStatus('processing')
            await startJob(jobId)
            router.push(`/editor/${jobId}`)
        } catch (err) {
            setError(String(err))
            setStatus('error')
        }
    }

    const onDrop = (e: React.DragEvent) => {
        e.preventDefault()
        const file = e.dataTransfer.files?.[0]
        if (file) handleFileSelect(file)
    }

    if (sourceKey) {
        return (
            <div className="min-h-screen bg-[#0f0f0f] flex items-center justify-center p-4">
                <div className="bg-[#1a1a1a] rounded-xl border border-[#2a2a2a] p-8 max-w-sm w-full text-center flex flex-col items-center">
                    <div className="w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mb-4" />
                    <h2 className="text-white text-lg font-medium">Opening in Editor...</h2>
                    {status === 'error' && (
                        <p className="text-red-400 text-sm mt-4">{error}</p>
                    )}
                </div>
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-[#0f0f0f] flex flex-col items-center justify-center p-4">
            <div className="max-w-lg w-full bg-[#1a1a1a] rounded-xl border border-[#2a2a2a] p-8">
                <h1 className="text-2xl font-semibold text-white text-center mb-8">Open in Editor</h1>

                {error && (
                    <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm flex items-center justify-between">
                        <span>{error}</span>
                        <button onClick={() => setError(null)} className="hover:text-red-300">✕</button>
                    </div>
                )}

                {status === 'idle' || status === 'error' ? (
                    <div
                        className="border-2 border-dashed border-[#2a2a2a] hover:border-indigo-500/50 rounded-xl p-12 text-center cursor-pointer transition-colors"
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={onDrop}
                        onClick={() => fileInputRef.current?.click()}
                    >
                        <input
                            type="file"
                            ref={fileInputRef}
                            className="hidden"
                            accept=".mp4,.mov,.webm,video/*"
                            onChange={(e) => {
                                const file = e.target.files?.[0]
                                if (file) handleFileSelect(file)
                            }}
                        />
                        <div className="text-4xl mb-4">📁</div>
                        <p className="text-white font-medium mb-1">Drop video here or click to browse</p>
                        <p className="text-sm text-[#6b7280]">MP4, MOV, WebM up to 500MB</p>
                    </div>
                ) : (
                    <div className="text-center py-8">
                        <div className="w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-6" />

                        {status === 'uploading' && (
                            <>
                                <h3 className="text-white font-medium mb-4">Uploading... {progress}%</h3>
                                <div className="w-full h-2 bg-[#2a2a2a] rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-indigo-600 transition-all duration-300 ease-out"
                                        style={{ width: `${progress}%` }}
                                    />
                                </div>
                            </>
                        )}

                        {status === 'processing' && (
                            <h3 className="text-white font-medium">Starting Editor...</h3>
                        )}
                    </div>
                )}
            </div>
        </div>
    )
}

export default function EditorUploadPage() {
    return (
        <Suspense fallback={
            <div className="min-h-screen bg-[#0f0f0f] flex items-center justify-center">
                <div className="text-[#6b7280] text-sm">Loading...</div>
            </div>
        }>
            <UploadPageContent />
        </Suspense>
    )
}