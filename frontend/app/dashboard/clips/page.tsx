"use client";

import React, { useState, useEffect } from "react";
import { Download, Check, X, Video, ChevronDown, Play, FileVideo } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Channel {
    id: string;
    name: string;
}

interface Clip {
    id: string;
    channel_id: string;
    job_id: string;
    hook_text: string;
    duration: number;
    standalone_score: number;
    hook_score: number;
    arc_score: number;
    strategy_role: string;
    posting_order: number;
    is_successful: boolean | null;
    why_failed: string | null;
    ai_reasoning: string;
    file_url: string | null;
}

type FilterType = "all" | "successful" | "failed" | "pending";

export default function ClipLibraryPage() {
    const [channels, setChannels] = useState<Channel[]>([]);
    const [activeChannelId, setActiveChannelId] = useState<string>("");
    const [clips, setClips] = useState<Clip[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [filter, setFilter] = useState<FilterType>("all");
    const [selectedClip, setSelectedClip] = useState<Clip | null>(null);

    useEffect(() => {
        fetchChannels();
    }, []);

    useEffect(() => {
        if (activeChannelId) {
            fetchClips();
        } else {
            setClips([]);
            setLoading(false);
        }
    }, [activeChannelId]);

    const fetchChannels = async () => {
        try {
            const res = await fetch(`${API}/channels`);
            if (res.ok) {
                const data = await res.json();
                setChannels(data);
                if (data.length > 0) {
                    setActiveChannelId(data[0].id);
                } else {
                    setLoading(false);
                }
            }
        } catch (error) {
            console.error("Failed to fetch channels", error);
            setLoading(false);
        }
    };

    const fetchClips = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API}/clips?channel_id=${activeChannelId}&limit=50`);
            if (res.ok) {
                const data = await res.json();
                setClips(data);
            }
        } catch (error) {
            console.error("Failed to fetch clips", error);
        } finally {
            setLoading(false);
        }
    };

    const handleApprove = async (id: string) => {
        try {
            const res = await fetch(`${API}/clips/${id}/approve`, { method: "PATCH" });
            if (res.ok) {
                setClips(clips.map(c => c.id === id ? { ...c, is_successful: true } : c));
                if (selectedClip?.id === id) {
                    setSelectedClip({ ...selectedClip, is_successful: true });
                }
            }
        } catch (error) {
            console.error("Failed to approve clip", error);
        }
    };

    const handleReject = async (id: string) => {
        try {
            const res = await fetch(`${API}/clips/${id}/reject`, { method: "PATCH" });
            if (res.ok) {
                setClips(clips.map(c => c.id === id ? { ...c, is_successful: false } : c));
                if (selectedClip?.id === id) {
                    setSelectedClip({ ...selectedClip, is_successful: false });
                }
            }
        } catch (error) {
            console.error("Failed to reject clip", error);
        }
    };

    const handleDownload = (id: string) => {
        window.open(`${API}/downloads/clips/${id}`, "_blank");
    };

    const getScoreColor = (score: number) => {
        if (score >= 7) return "text-green-400";
        if (score >= 5) return "text-yellow-400";
        return "text-red-400";
    };

    const getRoleColor = (role: string) => {
        switch (role?.toLowerCase()) {
            case "launch": return "bg-purple-500/20 text-purple-400 border-purple-500/30";
            case "viral": return "bg-cyan-500/20 text-cyan-400 border-cyan-500/30";
            case "fan_service": return "bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
            case "context_builder": return "bg-gray-500/20 text-gray-400 border-gray-500/30";
            default: return "bg-gray-800 text-gray-400 border-gray-700";
        }
    };

    const filteredClips = clips.filter((clip) => {
        if (filter === "all") return true;
        if (filter === "successful") return clip.is_successful === true;
        if (filter === "failed") return clip.is_successful === false;
        if (filter === "pending") return clip.is_successful === null;
        return true;
    });

    const formatDuration = (seconds: number) => {
        if (!seconds) return "0:00";
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, "0")}`;
    };

    return (
        <div className="min-h-screen bg-black text-white p-6 pb-24 flex">
            <div className="flex-1 transition-all duration-300">
                {/* Header Row */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
                    <h1 className="text-2xl font-bold">Clip Library</h1>

                    <div className="flex items-center gap-4 bg-[#0d0d0d] p-1.5 rounded-lg border border-gray-800">
                        {(["all", "successful", "failed", "pending"] as FilterType[]).map((f) => (
                            <button
                                key={f}
                                onClick={() => setFilter(f)}
                                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${filter === f
                                    ? "bg-purple-600 text-white"
                                    : "text-gray-400 hover:text-white hover:bg-white/5"
                                    }`}
                            >
                                {f.charAt(0).toUpperCase() + f.slice(1)}
                            </button>
                        ))}
                    </div>

                    <div className="relative">
                        <select
                            value={activeChannelId}
                            onChange={(e) => setActiveChannelId(e.target.value)}
                            className="appearance-none bg-[#0d0d0d] border border-gray-800 text-white px-4 py-2 pr-10 rounded-lg focus:outline-none focus:ring-1 focus:ring-purple-500"
                        >
                            {channels.length === 0 ? (
                                <option value="">No channels</option>
                            ) : (
                                channels.map((ch) => (
                                    <option key={ch.id} value={ch.id}>
                                        {ch.name}
                                    </option>
                                ))
                            )}
                        </select>
                        <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                    </div>
                </div>

                {/* Content */}
                {loading ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {[...Array(6)].map((_, i) => (
                            <div key={i} className="bg-[#0d0d0d] border border-gray-800 rounded-xl overflow-hidden animate-pulse">
                                <div className="w-full aspect-[9/16] bg-[#141414]"></div>
                                <div className="p-4 space-y-3">
                                    <div className="h-4 bg-gray-800 rounded w-3/4"></div>
                                    <div className="h-4 bg-gray-800 rounded w-1/2"></div>
                                    <div className="flex gap-2 pt-2">
                                        <div className="h-6 bg-gray-800 rounded w-16"></div>
                                        <div className="h-6 bg-gray-800 rounded w-16"></div>
                                        <div className="h-6 bg-gray-800 rounded w-16"></div>
                                    </div>
                                    <div className="h-6 bg-gray-800 rounded w-24"></div>
                                </div>
                            </div>
                        ))}
                    </div>
                ) : filteredClips.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-20 bg-[#0d0d0d] border border-gray-800 rounded-xl">
                        <FileVideo className="w-16 h-16 text-gray-700 mb-4" />
                        <h3 className="text-xl font-medium text-gray-300">No clips yet</h3>
                        <p className="text-[#6b7280] mt-2">Start your first job to extract clips</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {filteredClips.map((clip) => (
                            <div
                                key={clip.id}
                                className="bg-[#0d0d0d] border border-gray-800 hover:border-purple-500/50 rounded-xl overflow-hidden cursor-pointer transition-colors group flex flex-col"
                                onClick={() => setSelectedClip(clip)}
                            >
                                {/* Thumbnail Area */}
                                <div className="w-full aspect-[9/16] bg-[#141414] relative flex items-center justify-center group-hover:bg-[#1a1a1a] transition-colors overflow-hidden">
                                    {clip.file_url ? (
                                        <video
                                            src={clip.file_url}
                                            className="w-full h-full object-cover"
                                            muted
                                            playsInline
                                            preload="metadata"
                                        />
                                    ) : (
                                        <Play className="w-12 h-12 text-white/20" />
                                    )}
                                    <div className="absolute bottom-2 right-2 bg-black/80 px-2 py-1 rounded text-xs font-medium text-white">
                                        {formatDuration(clip.duration)}
                                    </div>
                                    {clip.is_successful === true && (
                                        <div className="absolute top-2 right-2 bg-green-500/90 text-white p-1 rounded-full">
                                            <Check className="w-4 h-4" />
                                        </div>
                                    )}
                                    {clip.is_successful === false && (
                                        <div className="absolute top-2 right-2 bg-red-500/90 text-white p-1 rounded-full">
                                            <X className="w-4 h-4" />
                                        </div>
                                    )}
                                </div>

                                {/* Info Area */}
                                <div className="p-4 flex flex-col flex-1">
                                    <p className="text-sm text-gray-300 line-clamp-2 mb-3 h-10">
                                        "{clip.hook_text || "No hook text generated..."}"
                                    </p>

                                    <div className="flex gap-3 text-xs font-medium mb-3">
                                        <span className={getScoreColor(clip.standalone_score)}>
                                            St: {clip.standalone_score || 0}/10
                                        </span>
                                        <span className={getScoreColor(clip.hook_score)}>
                                            Hk: {clip.hook_score || 0}/10
                                        </span>
                                        <span className={getScoreColor(clip.arc_score)}>
                                            Ar: {clip.arc_score || 0}/10
                                        </span>
                                    </div>

                                    <div className="mb-4">
                                        <span className={`text-xs px-2 py-1 rounded-md border ${getRoleColor(clip.strategy_role)}`}>
                                            {clip.strategy_role || "unassigned"}
                                        </span>
                                    </div>

                                    <div className="mt-auto flex items-center justify-between pt-3 border-t border-gray-800">
                                        <button
                                            onClick={(e) => { e.stopPropagation(); handleDownload(clip.id); }}
                                            className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
                                            title="Download"
                                        >
                                            <Download className="w-4 h-4" />
                                        </button>
                                        <div className="flex items-center gap-2">
                                            <button
                                                onClick={(e) => { e.stopPropagation(); handleApprove(clip.id); }}
                                                className="p-2 text-gray-400 hover:text-green-400 hover:bg-green-400/10 rounded-lg transition-colors"
                                                title="Approve"
                                            >
                                                <Check className="w-4 h-4" />
                                            </button>
                                            <button
                                                onClick={(e) => { e.stopPropagation(); handleReject(clip.id); }}
                                                className="p-2 text-gray-400 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-colors"
                                                title="Reject"
                                            >
                                                <X className="w-4 h-4" />
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Slide-in Detail Panel */}
            <div
                className={`fixed inset-y-0 right-0 w-full md:w-[450px] bg-[#0d0d0d] border-l border-gray-800 shadow-2xl transform transition-transform duration-300 ease-in-out z-50 flex flex-col ${selectedClip ? "translate-x-0" : "translate-x-full"
                    }`}
            >
                {selectedClip && (
                    <>
                        <div className="p-4 border-b border-gray-800 flex items-center justify-between">
                            <h2 className="text-lg font-semibold">Clip Details</h2>
                            <button
                                onClick={() => setSelectedClip(null)}
                                className="p-2 text-gray-400 hover:text-white rounded-lg transition-colors"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto p-6 space-y-8">
                            {/* Video Player Placeholder */}
                            <div className="w-full aspect-[9/16] bg-[#141414] rounded-xl flex items-center justify-center border border-gray-800 relative overflow-hidden">
                                {selectedClip.file_url ? (
                                    <video
                                        src={selectedClip.file_url}
                                        controls
                                        playsInline
                                        className="w-full h-full rounded-xl"
                                    />
                                ) : (
                                    <div className="flex items-center justify-center h-full text-gray-500">
                                        No video available
                                    </div>
                                )}
                            </div>

                            {/* Hook Text */}
                            <div>
                                <h3 className="text-sm font-medium text-gray-400 mb-2">Hook Text</h3>
                                <p className="text-base leading-relaxed bg-black/50 p-4 rounded-lg border border-gray-800">
                                    {selectedClip.hook_text || "No hook text generated"}
                                </p>
                            </div>

                            {/* Strategy & Order */}
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <h3 className="text-sm font-medium text-gray-400 mb-2">Strategy Role</h3>
                                    <span className={`inline-block text-xs px-2.5 py-1 rounded-md border ${getRoleColor(selectedClip.strategy_role)}`}>
                                        {selectedClip.strategy_role || "unassigned"}
                                    </span>
                                </div>
                                <div>
                                    <h3 className="text-sm font-medium text-gray-400 mb-2">Posting Order</h3>
                                    <div className="text-lg font-medium">#{selectedClip.posting_order || 0}</div>
                                </div>
                            </div>

                            {/* Scores */}
                            <div>
                                <h3 className="text-sm font-medium text-gray-400 mb-4">Quality Scores</h3>
                                <div className="space-y-4">
                                    {[
                                        { label: "Standalone", value: selectedClip.standalone_score },
                                        { label: "Hook", value: selectedClip.hook_score },
                                        { label: "Arc", value: selectedClip.arc_score }
                                    ].map((score, idx) => (
                                        <div key={idx}>
                                            <div className="flex justify-between text-sm mb-1.5">
                                                <span className="text-gray-300">{score.label}</span>
                                                <span className={`font-medium ${getScoreColor(score.value)}`}>
                                                    {score.value || 0}/10
                                                </span>
                                            </div>
                                            <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                                                <div
                                                    className={`h-full rounded-full ${score.value >= 7 ? "bg-green-500" : score.value >= 5 ? "bg-yellow-500" : "bg-red-500"}`}
                                                    style={{ width: `${(score.value || 0) * 10}%` }}
                                                />
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {/* AI Reasoning */}
                            <div>
                                <h3 className="text-sm font-medium text-gray-400 mb-2">AI Reasoning</h3>
                                <p className="text-sm text-gray-300 leading-relaxed bg-black/50 p-4 rounded-lg border border-gray-800">
                                    {selectedClip.ai_reasoning || "No reasoning provided."}
                                </p>
                            </div>

                            {/* Why Failed */}
                            {selectedClip.is_successful === false && selectedClip.why_failed && (
                                <div>
                                    <h3 className="text-sm font-medium text-red-400 mb-2">Failure Reason</h3>
                                    <p className="text-sm text-red-200 leading-relaxed bg-red-500/10 p-4 rounded-lg border border-red-500/20">
                                        {selectedClip.why_failed}
                                    </p>
                                </div>
                            )}
                        </div>

                        {/* Actions Footer */}
                        <div className="p-4 border-t border-gray-800 bg-[#0d0d0d] flex gap-3">
                            <button
                                onClick={() => handleDownload(selectedClip.id)}
                                className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-gray-800 hover:bg-gray-700 text-white rounded-lg font-medium transition-colors"
                            >
                                <Download className="w-4 h-4" /> Download
                            </button>
                            <button
                                onClick={() => handleApprove(selectedClip.id)}
                                className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-green-500/10 hover:bg-green-500/20 text-green-400 border border-green-500/20 rounded-lg font-medium transition-colors"
                            >
                                <Check className="w-4 h-4" /> Approve
                            </button>
                            <button
                                onClick={() => handleReject(selectedClip.id)}
                                className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 rounded-lg font-medium transition-colors"
                            >
                                <X className="w-4 h-4" /> Reject
                            </button>
                        </div>
                    </>
                )}
            </div>

            {/* Overlay for Detail Panel */}
            {selectedClip && (
                <div
                    className="fixed inset-0 bg-black/50 z-40 md:hidden"
                    onClick={() => setSelectedClip(null)}
                />
            )}
        </div>
    );
}
