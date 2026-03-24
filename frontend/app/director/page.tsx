"use client";

import { useState, useRef, useEffect } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCallItem[];
  isStreaming?: boolean;
}

interface ToolCallItem {
  tool: string;
  args: Record<string, unknown>;
  summary?: string;
}

function generateId() {
  return Math.random().toString(36).slice(2);
}

function ToolCallBadge({ item }: { item: ToolCallItem }) {
  const toolIcons: Record<string, string> = {
    read_file: "📄",
    list_files: "📁",
    search_codebase: "🔍",
    edit_file: "✏️",
    query_database: "🗄️",
    get_pipeline_stats: "📊",
    get_clip_analysis: "🎬",
    get_channel_dna: "🧬",
    get_recent_events: "📡",
    save_memory: "💾",
    query_memory: "🧠",
    list_memories: "📚",
    get_langfuse_data: "🔬",
    get_sentry_issues: "🚨",
    get_posthog_events: "📈",
  };

  const icon = toolIcons[item.tool] || "🔧";
  const argSummary = Object.entries(item.args)
    .map(([k, v]) => `${k}: ${String(v).slice(0, 40)}`)
    .join(", ");

  return (
    <div className="flex items-start gap-2 text-xs text-gray-400 bg-gray-900 rounded px-3 py-2 my-1">
      <span className="shrink-0">{icon}</span>
      <div>
        <span className="text-gray-300 font-mono">{item.tool}</span>
        {argSummary && <span className="text-gray-500 ml-2">({argSummary})</span>}
        {item.summary && <div className="text-gray-500 mt-0.5">→ {item.summary}</div>}
      </div>
    </div>
  );
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div className={`max-w-[80%] ${isUser ? "order-2" : "order-1"}`}>
        {!isUser && msg.toolCalls && msg.toolCalls.length > 0 && (
          <div className="mb-2">
            {msg.toolCalls.map((tc, i) => (
              <ToolCallBadge key={i} item={tc} />
            ))}
          </div>
        )}
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
            isUser
              ? "bg-blue-600 text-white rounded-tr-sm"
              : "bg-gray-800 text-gray-100 rounded-tl-sm"
          }`}
        >
          {msg.content}
          {msg.isStreaming && (
            <span className="inline-block w-1.5 h-4 bg-gray-400 animate-pulse ml-1 align-middle" />
          )}
        </div>
      </div>
    </div>
  );
}

export default function DirectorPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Merhaba. Ben Director — sistemin AI CEO'su.\n\nPipeline performansını, klip kalitesini, Gemini kararlarını analiz edebilirim. Kod okuyabilir, veritabanını sorgulayabilirim. Ne öğrenmek istiyorsun?",
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId] = useState(() => generateId());
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendMessage() {
    const text = input.trim();
    if (!text || isLoading) return;

    const userMsg: Message = { id: generateId(), role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    const assistantId = generateId();
    const assistantMsg: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      toolCalls: [],
      isStreaming: true,
    };
    setMessages((prev) => [...prev, assistantMsg]);

    try {
      const res = await fetch(`${API_URL}/director/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });

      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));

            if (event.type === "tool_call") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? {
                        ...m,
                        toolCalls: [
                          ...(m.toolCalls || []),
                          { tool: event.tool, args: event.args },
                        ],
                      }
                    : m
                )
              );
            } else if (event.type === "tool_result") {
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== assistantId) return m;
                  const toolCalls = [...(m.toolCalls || [])];
                  // Update last tool call with summary
                  const lastIdx = toolCalls.length - 1;
                  if (lastIdx >= 0 && toolCalls[lastIdx].tool === event.tool) {
                    toolCalls[lastIdx] = { ...toolCalls[lastIdx], summary: event.summary };
                  }
                  return { ...m, toolCalls };
                })
              );
            } else if (event.type === "text") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: m.content + event.text } : m
                )
              );
            } else if (event.type === "done") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, isStreaming: false } : m
                )
              );
            } else if (event.type === "error") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: `Hata: ${event.message}`, isStreaming: false }
                    : m
                )
              );
            }
          } catch {
            // Skip malformed SSE lines
          }
        }
      }
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: `Bağlantı hatası: ${String(err)}`, isStreaming: false }
            : m
        )
      );
    } finally {
      setIsLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  const suggestedPrompts = [
    "Pipeline son 7 günde nasıl performans gösterdi?",
    "S05 neden yavaş?",
    "Klip kalitesi analizi yap",
    "Son hataları göster",
  ];

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-white">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-800">
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-sm font-bold">
          D
        </div>
        <div>
          <h1 className="font-semibold text-sm">Director</h1>
          <p className="text-xs text-gray-500">AI sistem yöneticisi</p>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-2">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}

        {/* Suggested prompts when empty */}
        {messages.length === 1 && (
          <div className="flex flex-wrap gap-2 mt-4">
            {suggestedPrompts.map((prompt) => (
              <button
                key={prompt}
                onClick={() => {
                  setInput(prompt);
                  inputRef.current?.focus();
                }}
                className="text-xs text-gray-400 border border-gray-700 rounded-full px-3 py-1.5 hover:border-gray-500 hover:text-gray-300 transition-colors"
              >
                {prompt}
              </button>
            ))}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-4 pb-4">
        <div className="flex gap-2 bg-gray-900 rounded-2xl border border-gray-800 p-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Director'a sor..."
            rows={1}
            className="flex-1 bg-transparent text-sm text-white placeholder-gray-500 resize-none outline-none px-2 py-1.5 max-h-32"
            style={{ minHeight: "36px" }}
            disabled={isLoading}
          />
          <button
            onClick={sendMessage}
            disabled={isLoading || !input.trim()}
            className="w-9 h-9 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-colors shrink-0"
          >
            {isLoading ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M2 21L23 12 2 3V10L17 12 2 14Z" />
              </svg>
            )}
          </button>
        </div>
        <p className="text-center text-xs text-gray-600 mt-2">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}
