"use client";

import React, { useState, useRef, useCallback } from "react";
import { X, Upload, Check, AlertCircle, Loader2 } from "lucide-react";
import { authFetch } from "@/lib/api";
import { uploadFileMultipart } from "@/lib/batchUpload";
import { toast } from "@/lib/toast";

const MAX_SOURCES = 10;
// Mirrors MAX_PARALLEL in backend/app/api/routes/batches.py. S01-S07 share one
// Railway container; a higher number here would just be clamped server-side.
const MAX_PARALLEL = 3;

const DURATION_PRESETS = [
    { label: "<30s", min: 5, max: 30 },
    { label: "<60s", min: 10, max: 60 },
    { label: "10-90s", min: 10, max: 90 },
    { label: "30-60s", min: 30, max: 60 },
    { label: "45-60s", min: 45, max: 60 },
    { label: "1m-3m", min: 60, max: 180 },
];

const CAPTION_TEMPLATES = [
    { key: "capcut_word_highlight_ii", label: "Word Highlight II" },
    { key: "yellow_center", label: "Yellow Center" },
    { key: "clean", label: "Legacy Clean" },
];

const ALLOWED_EXT = ["mp4", "mov", "avi", "mkv", "webm"];

type UploadState = "uploading" | "done" | "error";

interface SourceDraft {
    file: File;
    title: string;
    mainPerson: string;
    targetGuest: string;
    durationPreset: string;
    captionTemplate: string;
    s05Model: string;
    s06Model: string;
    progress: number;
    state: UploadState;
    uploadId?: string;
    error?: string;
}

interface Props {
    channelId: string;
    isAdmin: boolean;
    onClose: () => void;
    onCreated: (batchId: string) => void;
}

/** Strip the extension so a filename becomes a usable default title. */
const titleFromFile = (name: string) => name.replace(/\.[^.]+$/, "");

export default function BatchCreateModal({ channelId, isAdmin, onClose, onCreated }: Props) {
    const [sources, setSources] = useState<SourceDraft[]>([]);
    const [step, setStep] = useState(0);              // 0..n-1 = sources, n = settings
    const [batchName, setBatchName] = useState("");
    const [maxParallel, setMaxParallel] = useState(2);
    const [submitting, setSubmitting] = useState(false);
    const fileInputRef = useRef<HTMLInputElement | null>(null);

    const patch = useCallback((idx: number, updates: Partial<SourceDraft>) => {
        setSources(prev => prev.map((s, i) => (i === idx ? { ...s, ...updates } : s)));
    }, []);

    const handleFiles = (files: FileList | null) => {
        if (!files?.length) return;
        const picked = Array.from(files).slice(0, MAX_SOURCES - sources.length);
        const rejected: string[] = [];

        const drafts: SourceDraft[] = [];
        for (const file of picked) {
            const ext = file.name.split(".").pop()?.toLowerCase() || "";
            if (!ALLOWED_EXT.includes(ext)) { rejected.push(file.name); continue; }
            drafts.push({
                file,
                title: titleFromFile(file.name),
                mainPerson: "",
                targetGuest: "",
                durationPreset: "<60s",
                captionTemplate: CAPTION_TEMPLATES[0].key,
                s05Model: "opus-5",
                s06Model: "opus-5",
                progress: 0,
                state: "uploading",
            });
        }
        if (rejected.length) toast.error(`Unsupported: ${rejected.join(", ")}`);
        if (!drafts.length) return;

        const offset = sources.length;
        setSources(prev => [...prev, ...drafts]);

        // Uploads begin now and run while the operator fills in the forms —
        // the whole point of the stepper. Start is gated on them finishing.
        drafts.forEach((draft, i) => {
            const idx = offset + i;
            uploadFileMultipart(draft.file, pct => patch(idx, { progress: pct }))
                .then(handle => patch(idx, { state: "done", progress: 100, uploadId: handle.uploadId }))
                .catch(err => patch(idx, { state: "error", error: err?.message || "Upload failed" }));
        });
    };

    const retry = (idx: number) => {
        const src = sources[idx];
        if (!src) return;
        patch(idx, { state: "uploading", progress: 0, error: undefined });
        uploadFileMultipart(src.file, pct => patch(idx, { progress: pct }))
            .then(handle => patch(idx, { state: "done", progress: 100, uploadId: handle.uploadId }))
            .catch(err => patch(idx, { state: "error", error: err?.message || "Upload failed" }));
    };

    const allUploaded = sources.length > 0 && sources.every(s => s.state === "done");
    const anyFailed = sources.some(s => s.state === "error");
    const titlesOk = sources.every(s => s.title.trim().length > 0);

    const submit = async () => {
        if (!allUploaded || !titlesOk || submitting) return;
        setSubmitting(true);
        try {
            const res = await authFetch("/batches", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    channel_id: channelId,
                    name: batchName.trim() || null,
                    max_parallel: maxParallel,
                    sources: sources.map(s => {
                        const preset = DURATION_PRESETS.find(p => p.label === s.durationPreset) ?? DURATION_PRESETS[1];
                        return {
                            upload_id: s.uploadId,
                            title: s.title.trim(),
                            target_guest: s.targetGuest.trim() || null,
                            metadata_subject_name: s.mainPerson.trim() || null,
                            clip_duration_min: preset.min,
                            clip_duration_max: preset.max,
                            caption_template: s.captionTemplate,
                            s05_model: isAdmin ? s.s05Model : null,
                            s06_model: isAdmin ? s.s06Model : null,
                        };
                    }),
                }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                toast.error(err.detail || "Could not create batch");
                setSubmitting(false);
                return;
            }
            const body = await res.json();
            toast.success(`Batch queued — ${body.job_ids?.length ?? 0} sources`);
            onCreated(body.batch_id);
        } catch {
            toast.error("Network error creating batch");
            setSubmitting(false);
        }
    };

    const inputCls = "w-full px-3 py-2 rounded-lg text-sm outline-none transition-colors";
    const inputStyle = { background: "#0f0f0e", border: "1px solid #2a2a28", color: "#faf9f5" } as React.CSSProperties;
    const labelCls = "block text-[11px] uppercase tracking-wide mb-1.5";
    const labelStyle = { color: "#ababab" } as React.CSSProperties;

    const settingsStep = sources.length;
    const onSettings = step === settingsStep && sources.length > 0;
    const current = sources[step];

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.75)" }}>
            <div className="w-full max-w-3xl rounded-2xl flex flex-col" style={{ background: "#181817", maxHeight: "90vh" }}>

                <div className="flex items-center justify-between px-6 py-4" style={{ borderBottom: "1px solid #262624" }}>
                    <h2 className="text-lg font-semibold" style={{ color: "#faf9f5" }}>Create batch</h2>
                    <button onClick={onClose} className="p-1 rounded hover:bg-white/5 transition-colors">
                        <X className="w-5 h-5" style={{ color: "#ababab" }} />
                    </button>
                </div>

                {sources.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-20 px-6">
                        <div className="w-20 h-20 rounded-full flex items-center justify-center mb-5" style={{ background: "#232321" }}>
                            <Upload className="w-8 h-8" style={{ color: "#ababab" }} />
                        </div>
                        <p className="text-sm mb-1" style={{ color: "#faf9f5" }}>Select up to {MAX_SOURCES} videos</p>
                        <p className="text-xs mb-6" style={{ color: "#6f6f6b" }}>They upload while you fill in each one&apos;s settings</p>
                        <button
                            onClick={() => fileInputRef.current?.click()}
                            className="px-5 py-2 rounded-full text-sm font-medium transition-colors"
                            style={{ background: "#faf9f5", color: "#141413" }}
                        >
                            Select files
                        </button>
                    </div>
                ) : (
                    <>
                        {/* Step circles — Source 1..N then Settings */}
                        <div className="px-6 py-4 overflow-x-auto" style={{ borderBottom: "1px solid #262624" }}>
                            <div className="flex items-center gap-1 min-w-max">
                                {sources.map((s, i) => (
                                    <React.Fragment key={i}>
                                        {i > 0 && <div className="w-6 h-px" style={{ background: "#2a2a28" }} />}
                                        <button onClick={() => setStep(i)} className="flex flex-col items-center gap-1.5 px-1">
                                            <div
                                                className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-semibold"
                                                style={{
                                                    background: step === i ? "#faf9f5" : s.state === "done" ? "#2f6f3f" : s.state === "error" ? "#7f2f2f" : "#2a2a28",
                                                    color: step === i ? "#141413" : "#faf9f5",
                                                }}
                                            >
                                                {s.state === "done" ? <Check className="w-3 h-3" /> : s.state === "error" ? <AlertCircle className="w-3 h-3" /> : i + 1}
                                            </div>
                                            <span className="text-[10px] whitespace-nowrap" style={{ color: step === i ? "#faf9f5" : "#6f6f6b" }}>
                                                Source {i + 1}
                                            </span>
                                        </button>
                                    </React.Fragment>
                                ))}
                                <div className="w-6 h-px" style={{ background: "#2a2a28" }} />
                                <button onClick={() => setStep(settingsStep)} className="flex flex-col items-center gap-1.5 px-1">
                                    <div
                                        className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-semibold"
                                        style={{ background: onSettings ? "#faf9f5" : "#2a2a28", color: onSettings ? "#141413" : "#faf9f5" }}
                                    >
                                        ⚙
                                    </div>
                                    <span className="text-[10px] whitespace-nowrap" style={{ color: onSettings ? "#faf9f5" : "#6f6f6b" }}>Settings</span>
                                </button>
                            </div>
                        </div>

                        <div className="px-6 py-5 overflow-y-auto flex-1">
                            {onSettings ? (
                                <div className="space-y-5 max-w-md">
                                    <div>
                                        <label className={labelCls} style={labelStyle}>Batch name</label>
                                        <input className={inputCls} style={inputStyle} value={batchName}
                                            onChange={e => setBatchName(e.target.value)} placeholder="Optional" />
                                    </div>
                                    <div>
                                        <label className={labelCls} style={labelStyle}>Parallel jobs</label>
                                        <div className="flex gap-2">
                                            {Array.from({ length: MAX_PARALLEL }, (_, i) => i + 1).map(n => (
                                                <button key={n} onClick={() => setMaxParallel(n)}
                                                    className="px-4 py-2 rounded-lg text-sm transition-colors"
                                                    style={{
                                                        background: maxParallel === n ? "#faf9f5" : "#0f0f0e",
                                                        color: maxParallel === n ? "#141413" : "#ababab",
                                                        border: "1px solid #2a2a28",
                                                    }}>{n}</button>
                                            ))}
                                        </div>
                                        <p className="text-[11px] mt-2" style={{ color: "#6f6f6b" }}>
                                            How many run at once. The rest wait and start automatically as slots free up.
                                        </p>
                                    </div>
                                    <div className="pt-2 text-xs space-y-1" style={{ color: "#ababab" }}>
                                        <p>{sources.length} sources · {sources.filter(s => s.state === "done").length} uploaded</p>
                                        {anyFailed && <p style={{ color: "#e07a5f" }}>Some uploads failed — fix them before starting.</p>}
                                        {!titlesOk && <p style={{ color: "#e07a5f" }}>Every source needs a title.</p>}
                                    </div>
                                </div>
                            ) : current ? (
                                <div className="space-y-4 max-w-md">
                                    <div className="flex items-center gap-3 mb-1">
                                        <div className="flex-1 min-w-0">
                                            <p className="text-xs truncate" style={{ color: "#6f6f6b" }}>{current.file.name}</p>
                                            <div className="h-1 rounded-full mt-1.5 overflow-hidden" style={{ background: "#2a2a28" }}>
                                                <div className="h-full rounded-full transition-all"
                                                    style={{
                                                        width: `${current.progress}%`,
                                                        background: current.state === "error" ? "#e07a5f" : current.state === "done" ? "#5f9f6f" : "#faf9f5",
                                                    }} />
                                            </div>
                                        </div>
                                        <span className="text-[11px] w-16 text-right" style={{ color: "#ababab" }}>
                                            {current.state === "done" ? "Uploaded" : current.state === "error" ? "Failed" : `${current.progress}%`}
                                        </span>
                                    </div>
                                    {current.state === "error" && (
                                        <div className="flex items-center justify-between px-3 py-2 rounded-lg" style={{ background: "#2a1a18" }}>
                                            <span className="text-xs" style={{ color: "#e07a5f" }}>{current.error}</span>
                                            <button onClick={() => retry(step)} className="text-xs underline" style={{ color: "#faf9f5" }}>Retry</button>
                                        </div>
                                    )}

                                    <div>
                                        <label className={labelCls} style={labelStyle}>Title *</label>
                                        <input className={inputCls} style={inputStyle} value={current.title}
                                            onChange={e => patch(step, { title: e.target.value })} />
                                    </div>
                                    <div className="grid grid-cols-2 gap-3">
                                        <div>
                                            <label className={labelCls} style={labelStyle}>Main person</label>
                                            <input className={inputCls} style={inputStyle} value={current.mainPerson}
                                                onChange={e => patch(step, { mainPerson: e.target.value })} placeholder="Optional" />
                                        </div>
                                        <div>
                                            <label className={labelCls} style={labelStyle}>Target guest</label>
                                            <input className={inputCls} style={inputStyle} value={current.targetGuest}
                                                onChange={e => patch(step, { targetGuest: e.target.value })} placeholder="Optional" />
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-2 gap-3">
                                        <div>
                                            <label className={labelCls} style={labelStyle}>Clip duration</label>
                                            <select className={inputCls} style={inputStyle} value={current.durationPreset}
                                                onChange={e => patch(step, { durationPreset: e.target.value })}>
                                                {DURATION_PRESETS.map(p => <option key={p.label} value={p.label}>{p.label}</option>)}
                                            </select>
                                        </div>
                                        <div>
                                            <label className={labelCls} style={labelStyle}>Caption</label>
                                            <select className={inputCls} style={inputStyle} value={current.captionTemplate}
                                                onChange={e => patch(step, { captionTemplate: e.target.value })}>
                                                {CAPTION_TEMPLATES.map(t => <option key={t.key} value={t.key}>{t.label}</option>)}
                                            </select>
                                        </div>
                                    </div>
                                    {isAdmin && (
                                        <div className="grid grid-cols-2 gap-3">
                                            <div>
                                                <label className={labelCls} style={labelStyle}>S05 model</label>
                                                <select className={inputCls} style={inputStyle} value={current.s05Model}
                                                    onChange={e => patch(step, { s05Model: e.target.value })}>
                                                    <option value="opus-5">Opus 5</option>
                                                    <option value="opus-4-6">Opus 4.6</option>
                                                </select>
                                            </div>
                                            <div>
                                                <label className={labelCls} style={labelStyle}>S06 model</label>
                                                <select className={inputCls} style={inputStyle} value={current.s06Model}
                                                    onChange={e => patch(step, { s06Model: e.target.value })}>
                                                    <option value="opus-5">Opus 5</option>
                                                    <option value="opus-4-6">Opus 4.6</option>
                                                </select>
                                            </div>
                                        </div>
                                    )}

                                    <button
                                        onClick={() => {
                                            // The "reuse details" move: everything except the title,
                                            // which belongs to its own file.
                                            const { durationPreset, captionTemplate, s05Model, s06Model, mainPerson, targetGuest } = current;
                                            setSources(prev => prev.map((s, i) => i === step ? s
                                                : { ...s, durationPreset, captionTemplate, s05Model, s06Model, mainPerson, targetGuest }));
                                            toast.success("Applied to all sources");
                                        }}
                                        className="text-xs underline"
                                        style={{ color: "#ababab" }}
                                    >
                                        Apply these settings to all sources
                                    </button>
                                </div>
                            ) : null}
                        </div>

                        <div className="flex items-center justify-between px-6 py-4" style={{ borderTop: "1px solid #262624" }}>
                            <div className="flex items-center gap-2">
                                {sources.length < MAX_SOURCES && (
                                    <button onClick={() => fileInputRef.current?.click()}
                                        className="text-xs px-3 py-1.5 rounded-lg transition-colors"
                                        style={{ border: "1px solid #2a2a28", color: "#ababab" }}>
                                        + Add more
                                    </button>
                                )}
                            </div>
                            <div className="flex items-center gap-2">
                                <button disabled={step === 0} onClick={() => setStep(s => Math.max(0, s - 1))}
                                    className="px-4 py-2 rounded-full text-sm transition-colors disabled:opacity-30"
                                    style={{ border: "1px solid #2a2a28", color: "#faf9f5" }}>Back</button>
                                {onSettings ? (
                                    <button disabled={!allUploaded || !titlesOk || submitting} onClick={submit}
                                        className="px-5 py-2 rounded-full text-sm font-medium transition-colors disabled:opacity-40 flex items-center gap-2"
                                        style={{ background: "#faf9f5", color: "#141413" }}>
                                        {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                                        Start batch
                                    </button>
                                ) : (
                                    <button onClick={() => setStep(s => Math.min(settingsStep, s + 1))}
                                        className="px-5 py-2 rounded-full text-sm font-medium"
                                        style={{ background: "#faf9f5", color: "#141413" }}>Next</button>
                                )}
                            </div>
                        </div>
                    </>
                )}

                <input ref={fileInputRef} type="file" accept="video/*" multiple className="hidden"
                    onChange={e => { handleFiles(e.target.files); e.target.value = ""; }} />
            </div>
        </div>
    );
}
