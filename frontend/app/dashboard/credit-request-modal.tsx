'use client';

import { useState } from "react";
import { X, CreditCard } from "lucide-react";
import { authFetch } from "@/lib/api";

interface CreditRequestModalProps {
    isOpen: boolean;
    onClose: () => void;
    currentBalance?: number;
}

export function CreditRequestModal({ isOpen, onClose, currentBalance }: CreditRequestModalProps) {
    const [amount, setAmount] = useState<string>("100");
    const [submitting, setSubmitting] = useState(false);
    const [success, setSuccess] = useState(false);
    const [error, setError] = useState("");

    if (!isOpen) return null;

    const handleSubmit = async () => {
        const num = parseInt(amount, 10);
        if (isNaN(num) || num < 10 || num > 5000) {
            setError("Amount must be between 10 and 5000");
            return;
        }

        setSubmitting(true);
        setError("");
        try {
            const res = await authFetch('/credits/request', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ amount: num }),
            });
            if (res.ok) {
                setSuccess(true);
            } else {
                const data = await res.json().catch(() => ({}));
                setError(data.detail || "Failed to submit request");
            }
        } catch {
            setError("Network error. Please try again.");
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center">
            <div className="absolute inset-0 bg-black/60" onClick={onClose} />
            <div
                className="relative w-full max-w-sm rounded-2xl p-6"
                style={{ background: "#1c1c1b", border: "1px solid rgba(250,249,245,0.08)" }}
            >
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 w-8 h-8 rounded-full flex items-center justify-center transition-colors hover:bg-white/10"
                    style={{ color: "#ababab" }}
                >
                    <X size={16} />
                </button>

                <div className="flex items-center gap-3 mb-5">
                    <div
                        className="w-10 h-10 rounded-xl flex items-center justify-center"
                        style={{ background: "rgba(250,249,245,0.05)" }}
                    >
                        <CreditCard size={18} style={{ color: "#faf9f5" }} />
                    </div>
                    <div>
                        <h3 className="text-base font-semibold" style={{ color: "#faf9f5" }}>
                            Request Credits
                        </h3>
                        {currentBalance !== undefined && (
                            <p className="text-xs mt-0.5" style={{ color: "#ababab" }}>
                                Current balance: {currentBalance} credits
                            </p>
                        )}
                    </div>
                </div>

                {success ? (
                    <div className="text-center py-4">
                        <p className="text-sm font-medium" style={{ color: "#faf9f5" }}>
                            Request submitted successfully!
                        </p>
                        <p className="text-xs mt-2" style={{ color: "#ababab" }}>
                            You will be notified when your request is approved.
                        </p>
                        <button
                            onClick={onClose}
                            className="mt-4 px-4 py-2 rounded-xl text-sm font-medium bg-white text-black hover:bg-[#e5e5e5] transition-colors"
                        >
                            Close
                        </button>
                    </div>
                ) : (
                    <>
                        <div className="mb-4">
                            <label className="text-xs font-medium mb-1.5 block" style={{ color: "#ababab" }}>
                                Number of credits (10 - 5000)
                            </label>
                            <input
                                type="number"
                                min={10}
                                max={5000}
                                value={amount}
                                onChange={(e) => setAmount(e.target.value)}
                                className="w-full px-4 py-2.5 rounded-xl text-sm outline-none transition-colors"
                                style={{
                                    background: "#000",
                                    border: "1px solid #262626",
                                    color: "#faf9f5",
                                }}
                                onFocus={(e) => (e.target.style.borderColor = "#404040")}
                                onBlur={(e) => (e.target.style.borderColor = "#262626")}
                            />
                        </div>

                        {error && (
                            <p className="text-xs mb-3" style={{ color: "#ef4444" }}>{error}</p>
                        )}

                        <button
                            onClick={handleSubmit}
                            disabled={submitting}
                            className="w-full py-2.5 rounded-xl text-sm font-medium transition-colors disabled:opacity-50"
                            style={{ background: "#faf9f5", color: "#141413" }}
                        >
                            {submitting ? "Submitting..." : "Submit Request"}
                        </button>
                    </>
                )}
            </div>
        </div>
    );
}

interface InsufficientCreditsProps {
    balance: number;
    needed: number;
    onRequestCredits: () => void;
}

export function InsufficientCreditsWarning({ balance, needed, onRequestCredits }: InsufficientCreditsProps) {
    return (
        <div
            className="rounded-xl p-4 flex items-start gap-3"
            style={{ background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.2)" }}
        >
            <CreditCard size={18} className="flex-shrink-0 mt-0.5" style={{ color: "#f59e0b" }} />
            <div className="flex-1">
                <p className="text-sm font-medium" style={{ color: "#faf9f5" }}>
                    Insufficient credits
                </p>
                <p className="text-xs mt-1" style={{ color: "#ababab" }}>
                    This job requires {needed} credits but you only have {balance}.
                </p>
                <button
                    onClick={onRequestCredits}
                    className="mt-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors hover:bg-[#e5e5e5]"
                    style={{ background: "#faf9f5", color: "#141413" }}
                >
                    Request Credits
                </button>
            </div>
        </div>
    );
}
