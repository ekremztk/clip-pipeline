"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

export default function LoginPage() {
    const router = useRouter();
    const [activeTab, setActiveTab] = useState<"signin" | "signup">("signin");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);

    const validateForm = () => {
        setError(null);
        setMessage(null);
        if (!email.includes("@")) {
            setError("Please enter a valid email address.");
            return false;
        }
        if (password.length < 8) {
            setError("Password must be at least 8 characters long.");
            return false;
        }
        return true;
    };

    const handleSignIn = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!validateForm()) return;
        setLoading(true);

        const { error } = await supabase.auth.signInWithPassword({
            email,
            password,
        });

        if (error) {
            setError(error.message);
            setLoading(false);
        } else {
            router.push("/dashboard");
        }
    };

    const handleSignUp = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!validateForm()) return;
        setLoading(true);

        const { error } = await supabase.auth.signUp({
            email,
            password,
        });

        if (error) {
            setError(error.message);
        } else {
            setMessage("Check your email to confirm your account");
        }
        setLoading(false);
    };

    const handleGoogleSignIn = async () => {
        setLoading(true);
        setError(null);
        const { error } = await supabase.auth.signInWithOAuth({
            provider: "google",
            options: { redirectTo: `${window.location.origin}/dashboard` },
        });

        if (error) {
            setError(error.message);
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-[#000000] flex items-center justify-center p-4">
            <div className="w-full max-w-[400px] bg-[#0d0d0d] border border-white/[0.06] rounded-xl p-8 shadow-2xl">
                {/* Logo & Tagline */}
                <div className="text-center mb-8">
                    <div className="flex items-center justify-center gap-1.5 font-bold tracking-tight mb-2">
                        <span className="text-white text-2xl">PROGNOT</span>
                        <span className="text-[#7c3aed] text-2xl">STUDIO</span>
                    </div>
                    <p className="text-[#6b7280] text-sm">AI-powered viral clip extraction</p>
                </div>

                {/* Tabs */}
                <div className="flex mb-6 border-b border-white/[0.06]">
                    <button
                        onClick={() => {
                            setActiveTab("signin");
                            setError(null);
                            setMessage(null);
                        }}
                        className={`flex-1 pb-3 text-sm font-medium transition-colors ${activeTab === "signin"
                                ? "text-white border-b-2 border-[#7c3aed]"
                                : "text-[#6b7280] hover:text-[#e5e5e5]"
                            }`}
                    >
                        Sign In
                    </button>
                    <button
                        onClick={() => {
                            setActiveTab("signup");
                            setError(null);
                            setMessage(null);
                        }}
                        className={`flex-1 pb-3 text-sm font-medium transition-colors ${activeTab === "signup"
                                ? "text-white border-b-2 border-[#7c3aed]"
                                : "text-[#6b7280] hover:text-[#e5e5e5]"
                            }`}
                    >
                        Sign Up
                    </button>
                </div>

                {/* Form */}
                <form onSubmit={activeTab === "signin" ? handleSignIn : handleSignUp} className="space-y-4">
                    <div>
                        <label className="block text-xs font-medium text-[#6b7280] mb-1.5">Email</label>
                        <input
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            className="w-full bg-[#141414] border border-white/[0.08] rounded-lg px-4 py-2.5 text-sm text-[#e5e5e5] placeholder-[#6b7280] focus:outline-none focus:border-[#7c3aed] transition-colors"
                            placeholder="you@example.com"
                            required
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-[#6b7280] mb-1.5">Password</label>
                        <input
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            className="w-full bg-[#141414] border border-white/[0.08] rounded-lg px-4 py-2.5 text-sm text-[#e5e5e5] placeholder-[#6b7280] focus:outline-none focus:border-[#7c3aed] transition-colors"
                            placeholder="••••••••"
                            required
                            minLength={8}
                        />
                    </div>

                    {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
                    {message && <p className="text-green-400 text-xs mt-2">{message}</p>}

                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full h-[44px] bg-[#7c3aed] hover:bg-[#6d28d9] text-white rounded-lg text-sm font-semibold transition-colors mt-6 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
                    >
                        {loading ? (
                            <div className="w-5 h-5 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                        ) : activeTab === "signin" ? (
                            "Sign In"
                        ) : (
                            "Sign Up"
                        )}
                    </button>
                </form>

                {/* Divider */}
                <div className="flex items-center gap-3 my-6">
                    <div className="flex-1 h-px bg-white/[0.06]"></div>
                    <span className="text-xs text-[#6b7280]">or continue with</span>
                    <div className="flex-1 h-px bg-white/[0.06]"></div>
                </div>

                {/* Google OAuth */}
                <button
                    onClick={handleGoogleSignIn}
                    disabled={loading}
                    className="w-full h-[44px] bg-[#141414] border border-white/[0.1] hover:bg-white/[0.02] text-[#e5e5e5] rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    <svg className="w-4 h-4" viewBox="0 0 24 24">
                        <path
                            d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                            fill="#4285F4"
                        />
                        <path
                            d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                            fill="#34A853"
                        />
                        <path
                            d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                            fill="#FBBC05"
                        />
                        <path
                            d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                            fill="#EA4335"
                        />
                    </svg>
                    Google
                </button>
            </div>
        </div>
    );
}
