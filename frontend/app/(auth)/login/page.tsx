"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { motion, AnimatePresence } from "framer-motion";

export default function LoginPage() {
    const router = useRouter();
    const [activeTab, setActiveTab] = useState<"signin" | "signup">("signin");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [fullName, setFullName] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [termsAccepted, setTermsAccepted] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);

    // Password strength logic
    const getPasswordStrength = (pass: string) => {
        let score = 0;
        if (!pass) return 0;
        if (pass.length > 8) score += 1;
        if (/[A-Z]/.test(pass)) score += 1;
        if (/[0-9]/.test(pass)) score += 1;
        if (/[^A-Za-z0-9]/.test(pass)) score += 1;
        return score;
    };

    const strength = getPasswordStrength(password);

    const getStrengthColor = (index: number) => {
        if (strength === 0) return "bg-white/10";
        if (strength === 1) return index === 0 ? "bg-red-500" : "bg-white/10";
        if (strength === 2) return index < 2 ? "bg-orange-500" : "bg-white/10";
        if (strength === 3) return index < 3 ? "bg-yellow-500" : "bg-white/10";
        return "bg-green-500";
    };

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
        if (activeTab === "signup") {
            if (!fullName.trim()) {
                setError("Please enter your full name.");
                return false;
            }
            if (password !== confirmPassword) {
                setError("Passwords do not match.");
                return false;
            }
            if (!termsAccepted) {
                setError("You must agree to the Terms of Service and Privacy Policy.");
                return false;
            }
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
            options: {
                data: { full_name: fullName },
            },
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

    const resetState = () => {
        setError(null);
        setMessage(null);
        setEmail("");
        setPassword("");
        setFullName("");
        setConfirmPassword("");
        setTermsAccepted(false);
    };

    return (
        <div className="relative min-h-screen bg-[#000000] flex items-center justify-center p-4 overflow-hidden font-sans text-[#e5e5e5]">
            {/* CSS Animations */}
            <style dangerouslySetInnerHTML={{
                __html: `
          @keyframes drift1 {
            0% { transform: translate(0, 0) scale(1); }
            33% { transform: translate(30px, -50px) scale(1.1); }
            66% { transform: translate(-20px, 20px) scale(0.9); }
            100% { transform: translate(0, 0) scale(1); }
          }
          @keyframes drift2 {
            0% { transform: translate(0, 0) scale(1); }
            33% { transform: translate(-50px, 30px) scale(0.9); }
            66% { transform: translate(20px, -20px) scale(1.1); }
            100% { transform: translate(0, 0) scale(1); }
          }
          @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
          }
          .animate-fade-in-up {
            animation: fadeInUp 0.6s ease-out forwards;
          }
        `
            }} />

            {/* Background Orbs */}
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
                <div
                    className="absolute top-1/4 left-1/4 w-[40vw] h-[40vw] rounded-full bg-[#7c3aed] opacity-20 blur-[120px] mix-blend-screen"
                    style={{ animation: 'drift1 20s ease-in-out infinite' }}
                />
                <div
                    className="absolute bottom-1/4 right-1/4 w-[35vw] h-[35vw] rounded-full bg-[#06b6d4] opacity-15 blur-[120px] mix-blend-screen"
                    style={{ animation: 'drift2 25s ease-in-out infinite' }}
                />
                <div
                    className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[30vw] h-[30vw] rounded-full bg-[#6d28d9] opacity-10 blur-[100px] mix-blend-screen"
                    style={{ animation: 'drift1 30s ease-in-out infinite reverse' }}
                />
            </div>

            {/* Main Card */}
            <div className="relative z-10 w-full max-w-[420px] bg-[#0d0d0d]/90 backdrop-blur-xl border border-white/[0.08] rounded-2xl p-10 shadow-2xl animate-fade-in-up">

                {/* Header */}
                <div className="text-center mb-8">
                    <div className="flex items-center justify-center gap-1.5 mb-2 tracking-tight">
                        <span className="text-white text-2xl font-bold">PROGNOT</span>
                        <span className="text-[#7c3aed] text-2xl font-bold">STUDIO</span>
                    </div>
                    <p className="text-[#6b7280] text-sm">AI-powered viral clip extraction</p>
                </div>

                {/* Tabs */}
                <div className="flex mb-8 border-b border-white/[0.06]">
                    <button
                        onClick={() => {
                            if (activeTab !== "signin") {
                                setActiveTab("signin");
                                resetState();
                            }
                        }}
                        className={`flex-1 pb-3 text-sm font-medium transition-all duration-300 relative ${activeTab === "signin"
                            ? "text-white"
                            : "text-[#6b7280] hover:text-[#e5e5e5]"
                            }`}
                    >
                        Sign In
                        {activeTab === "signin" && (
                            <motion.div layoutId="tab-indicator" className="absolute bottom-0 left-0 right-0 h-[2px] bg-[#7c3aed]" />
                        )}
                    </button>
                    <button
                        onClick={() => {
                            if (activeTab !== "signup") {
                                setActiveTab("signup");
                                resetState();
                            }
                        }}
                        className={`flex-1 pb-3 text-sm font-medium transition-all duration-300 relative ${activeTab === "signup"
                            ? "text-white"
                            : "text-[#6b7280] hover:text-[#e5e5e5]"
                            }`}
                    >
                        Create Account
                        {activeTab === "signup" && (
                            <motion.div layoutId="tab-indicator" className="absolute bottom-0 left-0 right-0 h-[2px] bg-[#7c3aed]" />
                        )}
                    </button>
                </div>

                <AnimatePresence mode="wait">
                    {activeTab === "signin" ? (
                        <motion.div
                            key="signin"
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: 10 }}
                            transition={{ duration: 0.2 }}
                        >
                            <form onSubmit={handleSignIn} className="space-y-4">
                                <div>
                                    <label className="block text-xs font-medium text-[#6b7280] mb-1.5">Email</label>
                                    <input
                                        type="email"
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        disabled={loading}
                                        className="w-full bg-[#141414] border border-white/[0.08] rounded-lg px-4 py-2.5 text-sm text-[#e5e5e5] placeholder-[#6b7280] focus:outline-none focus:border-[#7c3aed] transition-colors disabled:opacity-50"
                                        placeholder="you@example.com"
                                        required
                                    />
                                </div>
                                <div>
                                    <div className="flex justify-between items-center mb-1.5">
                                        <label className="block text-xs font-medium text-[#6b7280]">Password</label>
                                        <a href="#" className="text-xs text-[#7c3aed] hover:text-[#6d28d9] transition-colors">Forgot password?</a>
                                    </div>
                                    <input
                                        type="password"
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        disabled={loading}
                                        className="w-full bg-[#141414] border border-white/[0.08] rounded-lg px-4 py-2.5 text-sm text-[#e5e5e5] placeholder-[#6b7280] focus:outline-none focus:border-[#7c3aed] transition-colors disabled:opacity-50"
                                        placeholder="••••••••"
                                        required
                                    />
                                </div>

                                {error && <p className="text-red-400 text-xs mt-2">{error}</p>}

                                <motion.button
                                    whileHover={!loading ? { scale: 1.01, filter: "brightness(1.1)" } : {}}
                                    whileTap={!loading ? { scale: 0.99 } : {}}
                                    type="submit"
                                    disabled={loading}
                                    className="w-full h-[44px] bg-gradient-to-r from-purple-700 to-purple-500 text-white rounded-lg text-sm font-semibold transition-all mt-6 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 shadow-lg shadow-purple-500/20"
                                >
                                    {loading ? (
                                        <>
                                            <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                                            Signing in...
                                        </>
                                    ) : "Sign In"}
                                </motion.button>
                            </form>
                        </motion.div>
                    ) : (
                        <motion.div
                            key="signup"
                            initial={{ opacity: 0, x: 10 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: -10 }}
                            transition={{ duration: 0.2 }}
                        >
                            <form onSubmit={handleSignUp} className="space-y-4">
                                <div>
                                    <label className="block text-xs font-medium text-[#6b7280] mb-1.5">Full Name</label>
                                    <input
                                        type="text"
                                        value={fullName}
                                        onChange={(e) => setFullName(e.target.value)}
                                        disabled={loading}
                                        className="w-full bg-[#141414] border border-white/[0.08] rounded-lg px-4 py-2.5 text-sm text-[#e5e5e5] placeholder-[#6b7280] focus:outline-none focus:border-[#7c3aed] transition-colors disabled:opacity-50"
                                        placeholder="John Doe"
                                        required
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-medium text-[#6b7280] mb-1.5">Email</label>
                                    <input
                                        type="email"
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        disabled={loading}
                                        className="w-full bg-[#141414] border border-white/[0.08] rounded-lg px-4 py-2.5 text-sm text-[#e5e5e5] placeholder-[#6b7280] focus:outline-none focus:border-[#7c3aed] transition-colors disabled:opacity-50"
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
                                        disabled={loading}
                                        className="w-full bg-[#141414] border border-white/[0.08] rounded-lg px-4 py-2.5 text-sm text-[#e5e5e5] placeholder-[#6b7280] focus:outline-none focus:border-[#7c3aed] transition-colors disabled:opacity-50"
                                        placeholder="••••••••"
                                        required
                                        minLength={8}
                                    />
                                    {/* Password Strength Indicator */}
                                    <div className="flex gap-1 mt-2">
                                        {[0, 1, 2, 3].map((i) => (
                                            <div key={i} className={`h-1 flex-1 rounded-full transition-colors duration-300 ${getStrengthColor(i)}`} />
                                        ))}
                                    </div>
                                </div>
                                <div>
                                    <label className="block text-xs font-medium text-[#6b7280] mb-1.5">Confirm Password</label>
                                    <input
                                        type="password"
                                        value={confirmPassword}
                                        onChange={(e) => setConfirmPassword(e.target.value)}
                                        disabled={loading}
                                        className="w-full bg-[#141414] border border-white/[0.08] rounded-lg px-4 py-2.5 text-sm text-[#e5e5e5] placeholder-[#6b7280] focus:outline-none focus:border-[#7c3aed] transition-colors disabled:opacity-50"
                                        placeholder="••••••••"
                                        required
                                    />
                                </div>

                                <div className="flex items-start gap-2 pt-2">
                                    <input
                                        type="checkbox"
                                        id="terms"
                                        checked={termsAccepted}
                                        onChange={(e) => setTermsAccepted(e.target.checked)}
                                        disabled={loading}
                                        className="mt-1 w-4 h-4 rounded border-white/[0.2] bg-[#141414] text-[#7c3aed] focus:ring-[#7c3aed] focus:ring-offset-0 transition-colors cursor-pointer"
                                    />
                                    <label htmlFor="terms" className="text-xs text-[#6b7280] leading-snug cursor-pointer">
                                        I agree to the Terms of Service and Privacy Policy
                                    </label>
                                </div>

                                {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
                                {message && <p className="text-green-400 text-xs mt-2">{message}</p>}

                                <motion.button
                                    whileHover={!loading ? { scale: 1.01, filter: "brightness(1.1)" } : {}}
                                    whileTap={!loading ? { scale: 0.99 } : {}}
                                    type="submit"
                                    disabled={loading}
                                    className="w-full h-[44px] bg-gradient-to-r from-purple-700 to-purple-500 text-white rounded-lg text-sm font-semibold transition-all mt-6 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 shadow-lg shadow-purple-500/20"
                                >
                                    {loading ? (
                                        <>
                                            <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                                            Creating account...
                                        </>
                                    ) : "Create Account"}
                                </motion.button>
                            </form>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* Divider */}
                <div className="flex items-center gap-3 my-6">
                    <div className="flex-1 h-px bg-white/[0.06]"></div>
                    <span className="text-xs text-[#6b7280]">or</span>
                    <div className="flex-1 h-px bg-white/[0.06]"></div>
                </div>

                {/* Google OAuth */}
                <motion.button
                    whileHover={!loading ? { scale: 1.01, backgroundColor: "rgba(255,255,255,0.02)" } : {}}
                    whileTap={!loading ? { scale: 0.99 } : {}}
                    onClick={handleGoogleSignIn}
                    disabled={loading}
                    className="w-full h-[44px] bg-[#141414] border border-white/[0.1] text-[#e5e5e5] rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
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
                    Continue with Google
                </motion.button>
            </div>
        </div>
    );
}
