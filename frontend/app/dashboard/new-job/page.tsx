"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Upload, CheckCircle2, AlertCircle, Clock } from "lucide-react";
import { useChannel } from "../layout";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Job = {
    id: string;
    video_title: string;
    status: string;
    progress?: number;
    step?: string;
    created_at?: string;
    error?: string;
};

export default function NewJobPage() {
    const router = useRouter();
    const { channels, activeChannelId, setActiveChannelId } = useChannel();
    const fileInputRef = useRef<HTMLInputElement>(null);

    const [isDragging, setIsDragging] = useState(false);
    const [file, setFile] = useState<File | null>(null);
    const [title, setTitle] = useState("");
    const [guestName, setGuestName] = useState("");
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [submitError, setSubmitError] = useState("");
    const [uploadStatus, setUploadStatus] = useState("");

    const [jobs, setJobs] = useState<Job[]>([]);

    // Fetch recent jobs
    useEffect(() => {
        if (!activeChannelId) return;

        const fetchJobs = async () => {
            try {
                const jobsRes = await fetch(`${API}/jobs?channel_id=${activeChannelId}&limit=5`);
                if (jobsRes.ok) {
                    const jobsData = await jobsRes.json();
                    setJobs(jobsData);
                }
            } catch (err) {
                console.error("Dashboard fetch error", err);
            }
        };

        fetchJobs();
    }, [activeChannelId]);

    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(true);
    };
    const handleDragLeave = () => setIsDragging(false);
    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        if (e.dataTransfer.files?.length) setFile(e.dataTransfer.files[0]);
    };

    const handleStartProcessing = async () => {
        if (!file || !title || !activeChannelId) return;

        setIsSubmitting(true);
        setSubmitError("");

        const formData = new FormData();
        formData.append("video", file);
        formData.append("title", title);
        formData.append("channel_id", activeChannelId);
        if (guestName) formData.append("guest_name", guestName);

        try {
            const response = await fetch(`${API}/jobs`, {
                method: "POST",
                body: formData,
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                setSubmitError(err.detail || 'Failed to start processing');
                setIsSubmitting(false);
                return;
            }

            const job = await response.json();
            const jobId = job?.id || job?.job_id || job?.job?.id || job?.job?.job_id || job?.data?.id || job?.data?.job_id;

            if (!jobId) {
                setSubmitError('No job ID returned');
                setIsSubmitting(false);
                return;
            }

            // Clear form
            setFile(null);
            setTitle("");
            setGuestName("");

            // Poll job status until it changes from queued/processing
            setUploadStatus('Processing video...');
            let attempts = 0;
            const maxAttempts = 30; // 60 seconds max

            const pollStatus = async () => {
                try {
                    const statusRes = await fetch(`${API}/jobs/${jobId}`);
                    const jobData = await statusRes.json();
                    const status = jobData?.status;

                    if (status === 'awaiting_speaker_confirm') {
                        router.push(`/dashboard/speakers/${jobId}`);
                        return;
                    }

                    if (status === 'completed' || status === 'done') {
                        router.push('/dashboard');
                        return;
                    }

                    if (status === 'failed' || status === 'error') {
                        setSubmitError('Pipeline failed. Please try again.');
                        setIsSubmitting(false);
                        setUploadStatus('');
                        return;
                    }

                    // Update status message based on current step
                    const step = jobData?.current_step || '';
                    if (step.includes('s01')) setUploadStatus('Extracting audio...');
                    else if (step.includes('s02')) setUploadStatus('Transcribing...');
                    else if (step.includes('s03')) setUploadStatus('Identifying speakers...');

                    attempts++;
                    if (attempts < maxAttempts) {
                        setTimeout(pollStatus, 2000);
                    } else {
                        router.push('/dashboard');
                    }
                } catch (e) {
                    attempts++;
                    if (attempts < maxAttempts) {
                        setTimeout(pollStatus, 2000);
                    }
                }
            };

            setTimeout(pollStatus, 2000);

        } catch (err: any) {
            console.error(err);
            setSubmitError(err.message || "Failed to start processing. Please try again.");
            setIsSubmitting(false);
        }
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
            className="max-w-3xl mx-auto"
        >
            <h1 className="text-2xl font-bold mb-8">New Clip Job</h1>

            <div className="space-y-6">
                {/* Dropzone */}
                <input
                    ref={fileInputRef}
                    type="file"
                    accept=".mp4,.mov,.webm,video/*"
                    className="hidden"
                    onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) setFile(file);
                    }}
                />
                <div
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                    onClick={() => fileInputRef.current?.click()}
                    className={`border-2 border-dashed rounded-lg p-12 flex flex-col items-center justify-center text-center cursor-pointer transition-colors ${isDragging
                        ? "border-[#7c3aed] bg-[#7c3aed]/10"
                        : file
                            ? "border-green-500/50 bg-green-500/5"
                            : "border-[#7c3aed]/30 bg-[#0d0d0d] hover:border-[#7c3aed]/50 hover:bg-white/[0.02]"
                        }`}
                >
                    {file ? (
                        <>
                            <CheckCircle2 className="w-12 h-12 text-green-500 mb-3" />
                            <div className="text-sm font-medium">{file.name}</div>
                            <div className="text-xs text-[#6b7280] mt-1">{(file.size / (1024 * 1024)).toFixed(2)} MB</div>
                            <button
                                onClick={(e) => { e.stopPropagation(); setFile(null); }}
                                className="mt-4 text-xs text-red-400 hover:text-red-300"
                            >
                                Remove file
                            </button>
                        </>
                    ) : (
                        <>
                            <Upload className={`w-12 h-12 mb-3 ${isDragging ? "text-[#7c3aed]" : "text-[#6b7280]"}`} />
                            <div className="text-sm font-medium mb-1">Drag and drop video file here</div>
                            <div className="text-xs text-[#6b7280]">or click to browse • MP4, MOV, WEBM</div>
                        </>
                    )}
                </div>

                {submitError && (
                    <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm flex items-center gap-2">
                        <AlertCircle className="w-4 h-4" />
                        {submitError}
                    </div>
                )}

                {/* Form Fields */}
                <div className="bg-[#0d0d0d] border border-white/[0.06] rounded-lg p-6 space-y-5">
                    <div>
                        <label className="block text-xs font-medium text-[#6b7280] mb-1.5 uppercase tracking-wider">
                            Video Title *
                        </label>
                        <input
                            type="text"
                            value={title}
                            onChange={(e) => setTitle(e.target.value)}
                            placeholder="e.g. Joe Rogan #2054 - Elon Musk"
                            className="w-full bg-[#1a1a1a] border border-white/[0.1] rounded px-3 py-2 text-sm text-white placeholder-[#6b7280] focus:outline-none focus:border-[#7c3aed] transition-colors"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-[#6b7280] mb-1.5 uppercase tracking-wider">
                            Guest Name <span className="lowercase normal-case">(optional)</span>
                        </label>
                        <input
                            type="text"
                            value={guestName}
                            onChange={(e) => setGuestName(e.target.value)}
                            placeholder="e.g. Elon Musk"
                            className="w-full bg-[#1a1a1a] border border-white/[0.1] rounded px-3 py-2 text-sm text-white placeholder-[#6b7280] focus:outline-none focus:border-[#7c3aed] transition-colors"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-[#6b7280] mb-1.5 uppercase tracking-wider">
                            Channel
                        </label>
                        <select
                            value={activeChannelId}
                            onChange={(e) => setActiveChannelId(e.target.value)}
                            className="w-full bg-[#1a1a1a] border border-white/[0.1] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-[#7c3aed] transition-colors appearance-none"
                        >
                            {channels.length > 0 ? (
                                channels.map(c => <option key={c.id} value={c.id}>{c.name}</option>)
                            ) : (
                                <option value="speedy_cast">Speedy Cast</option>
                            )}
                        </select>
                    </div>
                </div>

                <motion.button
                    onClick={handleStartProcessing}
                    whileHover={!isSubmitting && file && title ? { scale: 1.02 } : {}}
                    whileTap={!isSubmitting && file && title ? { scale: 0.98 } : {}}
                    className={`w-full py-3 rounded text-sm font-semibold transition-all flex items-center justify-center gap-2 ${file && title && !isSubmitting
                        ? "bg-gradient-to-r from-[#7c3aed] to-[#6d28d9] text-white shadow-lg shadow-[#7c3aed]/20"
                        : "bg-[#1a1a1a] text-[#6b7280] cursor-not-allowed border border-white/[0.06]"
                        }`}
                    disabled={!file || !title || isSubmitting}
                >
                    {isSubmitting ? (
                        <>
                            <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                            Uploading...
                        </>
                    ) : (
                        "Start Processing"
                    )}
                </motion.button>

                {isSubmitting && uploadStatus && (
                    <div className="text-center text-sm text-[#7c3aed] animate-pulse mt-2">
                        {uploadStatus}
                    </div>
                )}
            </div>

            {/* Recent Jobs */}
            <div className="mt-12">
                <h2 className="text-[13px] uppercase tracking-wider text-[#6b7280] font-semibold mb-4">Recent Jobs</h2>
                <div className="space-y-2">
                    {jobs.length === 0 ? (
                        <p className="text-sm text-[#6b7280] p-4 text-center border border-white/[0.06] rounded-lg bg-[#0d0d0d]">No recent jobs</p>
                    ) : (
                        jobs.slice(0, 5).map((job, i) => (
                            <motion.div
                                key={job.id}
                                initial={{ opacity: 0, x: -12 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: i * 0.06 }}
                                className="flex items-center justify-between p-3 bg-[#0d0d0d] border border-white/[0.06] rounded-lg"
                            >
                                <div className="text-sm line-clamp-1 flex-1 pr-4">{job.video_title}</div>
                                <div className="flex items-center gap-3 shrink-0">
                                    {job.status === "done" || job.status === "completed" ? (
                                        <span className="text-xs font-medium text-green-500 bg-green-500/10 px-2 py-0.5 rounded flex items-center gap-1">
                                            <CheckCircle2 className="w-3 h-3" /> Done
                                        </span>
                                    ) : job.status === "error" || job.status === "failed" ? (
                                        <span className="text-xs font-medium text-red-500 bg-red-500/10 px-2 py-0.5 rounded flex items-center gap-1">
                                            <AlertCircle className="w-3 h-3" /> Failed
                                        </span>
                                    ) : (
                                        <span className="text-xs font-medium text-[#7c3aed] bg-[#7c3aed]/10 px-2 py-0.5 rounded flex items-center gap-1 capitalize">
                                            <Clock className="w-3 h-3" /> {job.status}
                                        </span>
                                    )}
                                </div>
                            </motion.div>
                        ))
                    )}
                </div>
            </div>
        </motion.div>
    );
}