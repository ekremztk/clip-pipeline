'use client';

import { useState, useRef } from 'react';
import { Upload, Film, Play, Clock, Scissors, Mic } from 'lucide-react';
import { authFetch } from '@/lib/api';

type Segment = {
  action: 'keep' | 'cut';
  start_time: number;
  end_time: number;
  transcript_excerpt?: string;
  reason: string;
};

type AnalysisResult = {
  clip_title: string;
  voiceover_text: string;
  segments: Segment[];
  kept_total_seconds: number;
  cut_total_seconds: number;
  total_duration_seconds: number;
  word_count: number;
};

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export default function StudioPage() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (f: File) => {
    setFile(f);
    setResult(null);
    setError(null);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f && f.type.startsWith('video/')) handleFile(f);
  };

  const handleAnalyze = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append('video', file);

      const res = await authFetch('/studio/analyze', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Error ${res.status}`);
      }

      const data: AnalysisResult = await res.json();
      setResult(data);
    } catch (e: any) {
      setError(e.message || 'Analysis failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '32px', maxWidth: 900 }}>
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 24, fontWeight: 600, color: '#faf9f5', marginBottom: 8 }}>
          Studio
        </h1>
        <p style={{ color: 'rgba(250,249,245,0.5)', fontSize: 14 }}>
          Upload an interview clip to analyze which segments to keep for your compilation video.
        </p>
      </div>

      {/* Upload area */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `2px dashed ${dragOver ? 'rgba(250,249,245,0.3)' : 'rgba(250,249,245,0.1)'}`,
          borderRadius: 16,
          padding: '48px 32px',
          textAlign: 'center',
          cursor: 'pointer',
          background: dragOver ? 'rgba(250,249,245,0.03)' : 'transparent',
          transition: 'all 0.2s',
          marginBottom: 24,
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept="video/*"
          style={{ display: 'none' }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
          }}
        />
        <Upload size={32} style={{ color: 'rgba(250,249,245,0.4)', marginBottom: 12 }} />
        {file ? (
          <div>
            <p style={{ color: '#faf9f5', fontWeight: 500 }}>{file.name}</p>
            <p style={{ color: 'rgba(250,249,245,0.4)', fontSize: 13, marginTop: 4 }}>
              {(file.size / (1024 * 1024)).toFixed(1)} MB
            </p>
          </div>
        ) : (
          <div>
            <p style={{ color: 'rgba(250,249,245,0.5)', fontSize: 14 }}>
              Drag & drop a video file or click to browse
            </p>
            <p style={{ color: 'rgba(250,249,245,0.3)', fontSize: 12, marginTop: 4 }}>
              MP4, MOV, AVI, MKV, WEBM
            </p>
          </div>
        )}
      </div>

      {/* Analyze button */}
      {file && !loading && (
        <button
          onClick={handleAnalyze}
          style={{
            background: '#faf9f5',
            color: '#000',
            border: 'none',
            borderRadius: 10,
            padding: '12px 28px',
            fontSize: 14,
            fontWeight: 600,
            cursor: 'pointer',
            marginBottom: 32,
          }}
        >
          Analyze Clip
        </button>
      )}

      {/* Loading */}
      {loading && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 32 }}>
          <div style={{
            width: 20, height: 20, borderRadius: '50%',
            border: '2px solid rgba(250,249,245,0.1)',
            borderTopColor: '#faf9f5',
            animation: 'spin 0.8s linear infinite',
          }} />
          <span style={{ color: 'rgba(250,249,245,0.6)', fontSize: 14 }}>
            Analyzing video (transcribing + AI analysis)...
          </span>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{
          background: 'rgba(239,68,68,0.1)',
          border: '1px solid rgba(239,68,68,0.3)',
          borderRadius: 10,
          padding: '12px 16px',
          color: '#ef4444',
          fontSize: 13,
          marginBottom: 24,
        }}>
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div>
          {/* Summary header */}
          <div style={{
            background: '#1c1c1b',
            border: '1px solid rgba(250,249,245,0.05)',
            borderRadius: 16,
            padding: 24,
            marginBottom: 24,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
              <Film size={18} style={{ color: '#faf9f5' }} />
              <h2 style={{ fontSize: 16, fontWeight: 600, color: '#faf9f5' }}>
                {result.clip_title}
              </h2>
            </div>

            {/* Stats row */}
            <div style={{ display: 'flex', gap: 24, marginBottom: 20, flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Clock size={14} style={{ color: 'rgba(250,249,245,0.4)' }} />
                <span style={{ color: 'rgba(250,249,245,0.6)', fontSize: 13 }}>
                  {formatTime(result.total_duration_seconds)} total
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Play size={14} style={{ color: '#4ade80' }} />
                <span style={{ color: '#4ade80', fontSize: 13 }}>
                  {formatTime(result.kept_total_seconds)} kept
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Scissors size={14} style={{ color: '#ef4444' }} />
                <span style={{ color: '#ef4444', fontSize: 13 }}>
                  {formatTime(result.cut_total_seconds)} cut
                </span>
              </div>
            </div>

            {/* Voiceover */}
            <div style={{
              background: 'rgba(250,249,245,0.03)',
              border: '1px solid rgba(250,249,245,0.08)',
              borderRadius: 10,
              padding: '14px 16px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <Mic size={14} style={{ color: 'rgba(250,249,245,0.5)' }} />
                <span style={{ color: 'rgba(250,249,245,0.5)', fontSize: 12, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Voiceover
                </span>
              </div>
              <p style={{ color: '#faf9f5', fontSize: 14, lineHeight: 1.5, margin: 0 }}>
                &ldquo;{result.voiceover_text}&rdquo;
              </p>
            </div>
          </div>

          {/* Segments */}
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#faf9f5', marginBottom: 12 }}>
            Segments ({result.segments.length})
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {result.segments.map((seg, i) => (
              <div
                key={i}
                style={{
                  background: '#1c1c1b',
                  border: `1px solid ${seg.action === 'keep' ? 'rgba(74,222,128,0.2)' : 'rgba(239,68,68,0.15)'}`,
                  borderRadius: 12,
                  padding: '14px 16px',
                  borderLeft: `3px solid ${seg.action === 'keep' ? '#4ade80' : '#ef4444'}`,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{
                      background: seg.action === 'keep' ? 'rgba(74,222,128,0.15)' : 'rgba(239,68,68,0.15)',
                      color: seg.action === 'keep' ? '#4ade80' : '#ef4444',
                      fontSize: 11,
                      fontWeight: 600,
                      padding: '2px 8px',
                      borderRadius: 4,
                      textTransform: 'uppercase',
                    }}>
                      {seg.action}
                    </span>
                    <span style={{ color: 'rgba(250,249,245,0.5)', fontSize: 12 }}>
                      {formatTime(seg.start_time)} → {formatTime(seg.end_time)}
                    </span>
                  </div>
                  <span style={{ color: 'rgba(250,249,245,0.3)', fontSize: 12 }}>
                    {(seg.end_time - seg.start_time).toFixed(1)}s
                  </span>
                </div>
                {seg.transcript_excerpt && (
                  <p style={{ color: 'rgba(250,249,245,0.7)', fontSize: 13, margin: '6px 0', fontStyle: 'italic' }}>
                    &ldquo;{seg.transcript_excerpt}&rdquo;
                  </p>
                )}
                <p style={{ color: 'rgba(250,249,245,0.4)', fontSize: 12, margin: 0 }}>
                  {seg.reason}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
