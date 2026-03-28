"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

export default function LoginPage() {
    const router = useRouter();

    // Screen state
    const [showOtpScreen, setShowOtpScreen] = useState(false);
    const [signupEmail, setSignupEmail] = useState("");

    // Form state
    const [activeTab, setActiveTab] = useState<"signin" | "signup">("signin");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [fullName, setFullName] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [termsAccepted, setTermsAccepted] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // OTP state
    const [otpCode, setOtpCode] = useState("");
    const [otpLoading, setOtpLoading] = useState(false);
    const [otpError, setOtpError] = useState<string | null>(null);
    const [otpSuccess, setOtpSuccess] = useState<string | null>(null);
    const [resendCooldown, setResendCooldown] = useState(0);
    const cooldownRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // Password strength
    const getStrength = (pw: string) => {
        if (pw.length === 0) return 0;
        const hasUpper = /[A-Z]/.test(pw);
        const hasSpecial = /[^a-zA-Z0-9]/.test(pw);
        const hasSpecialOrUpper = hasUpper || hasSpecial;
        if (hasSpecialOrUpper && pw.length >= 6) return 4;
        if (hasSpecialOrUpper && pw.length >= 4) return 3;
        if (pw.length >= 8) return 4;
        if (pw.length >= 6) return 3;
        if (pw.length >= 3) return 2;
        return 1;
    };
    const strength = getStrength(password);
    const getStrengthColor = (i: number) => {
        if (strength === 0) return "bg-[#262626]";
        if (strength === 1) return i === 0 ? "bg-red-500" : "bg-[#262626]";
        if (strength === 2) return i < 2 ? "bg-orange-500" : "bg-[#262626]";
        if (strength === 3) return i < 3 ? "bg-yellow-500" : "bg-[#262626]";
        return "bg-green-500";
    };

    useEffect(() => {
        return () => { if (cooldownRef.current) clearInterval(cooldownRef.current); };
    }, []);

    const startCooldown = () => {
        setResendCooldown(60);
        cooldownRef.current = setInterval(() => {
            setResendCooldown(prev => {
                if (prev <= 1) {
                    if (cooldownRef.current) clearInterval(cooldownRef.current);
                    return 0;
                }
                return prev - 1;
            });
        }, 1000);
    };

    const validateForm = () => {
        setError(null);
        if (!email.includes("@")) { setError("Please enter a valid email address."); return false; }
        if (password.length < 8) { setError("Password must be at least 8 characters long."); return false; }
        if (activeTab === "signup") {
            if (!fullName.trim()) { setError("Please enter your full name."); return false; }
            if (password !== confirmPassword) { setError("Passwords do not match."); return false; }
            if (!termsAccepted) { setError("You must agree to the Terms of Service and Privacy Policy."); return false; }
        }
        return true;
    };

    const handleSignIn = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!validateForm()) return;
        setLoading(true);
        const { error } = await supabase.auth.signInWithPassword({ email, password });
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
        const { data, error } = await supabase.auth.signUp({
            email,
            password,
            options: { data: { full_name: fullName } },
        });
        if (error) {
            setError(error.message);
            setLoading(false);
            return;
        }
        if (data.session) {
            // Email confirmation disabled — immediate login
            router.push("/dashboard");
            return;
        }
        if (data.user && !data.session) {
            // Email confirmation enabled — show OTP screen
            setSignupEmail(email);
            setShowOtpScreen(true);
            startCooldown();
        }
        setLoading(false);
    };

    const handleVerifyOtp = async (e: React.FormEvent) => {
        e.preventDefault();
        if (otpCode.length !== 6) { setOtpError("Please enter the 6-digit code."); return; }
        setOtpLoading(true);
        setOtpError(null);
        const { data, error } = await supabase.auth.verifyOtp({
            email: signupEmail,
            token: otpCode,
            type: "signup",
        });
        if (error) {
            setOtpError("Invalid or expired code. Please try again.");
            setOtpLoading(false);
            return;
        }
        if (data.session) {
            router.push("/dashboard");
        } else {
            setOtpError("Verification failed. Please try again.");
            setOtpLoading(false);
        }
    };

    const handleResend = async () => {
        if (resendCooldown > 0) return;
        setOtpError(null);
        setOtpSuccess(null);
        const { error } = await supabase.auth.resend({
            type: "signup",
            email: signupEmail,
        });
        if (error) {
            setOtpError(error.message);
        } else {
            setOtpSuccess("New code sent.");
            startCooldown();
        }
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
        setEmail("");
        setPassword("");
        setFullName("");
        setConfirmPassword("");
        setTermsAccepted(false);
    };

    // ── OTP Screen ────────────────────────────────────────────────────────────
    if (showOtpScreen) {
        return (
            <div className="min-h-screen bg-black flex items-center justify-center p-4">
                <div className="w-full max-w-[400px]">
                    <div className="text-center mb-8">
                        <span className="text-white text-xl font-bold tracking-tight">PROGNOT</span>
                        <p className="text-[#525252] text-sm mt-1">AI-powered viral clip extraction</p>
                    </div>

                    <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-2xl p-6">
                        <div className="mb-6">
                            <h2 className="text-base font-semibold text-white mb-1">Check your email</h2>
                            <p className="text-sm text-[#737373]">
                                We sent a 6-digit code to
                            </p>
                            <p className="text-sm text-[#a3a3a3] font-medium mt-0.5">{signupEmail}</p>
                        </div>

                        <form onSubmit={handleVerifyOtp} className="space-y-4">
                            <div>
                                <label className="block text-xs text-[#737373] mb-1.5">Verification code</label>
                                <input
                                    type="text"
                                    inputMode="numeric"
                                    pattern="[0-9]*"
                                    maxLength={6}
                                    value={otpCode}
                                    onChange={(e) => {
                                        const val = e.target.value.replace(/\D/g, "");
                                        setOtpCode(val);
                                        setOtpError(null);
                                    }}
                                    disabled={otpLoading}
                                    autoFocus
                                    placeholder="000000"
                                    className="w-full bg-black border border-[#262626] rounded-lg px-3 py-3 text-lg text-white text-center tracking-[0.5em] placeholder-[#525252] focus:outline-none focus:border-[#404040] transition-colors disabled:opacity-50 font-mono"
                                />
                            </div>

                            {otpError && <p className="text-red-400 text-xs">{otpError}</p>}
                            {otpSuccess && <p className="text-green-400 text-xs">{otpSuccess}</p>}

                            <button
                                type="submit"
                                disabled={otpLoading || otpCode.length !== 6}
                                className="w-full bg-white hover:bg-[#e5e5e5] text-black font-medium py-2.5 rounded-xl text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                            >
                                {otpLoading ? (
                                    <>
                                        <div className="w-4 h-4 border-2 border-black/20 border-t-black rounded-full animate-spin" />
                                        Verifying...
                                    </>
                                ) : "Verify"}
                            </button>
                        </form>

                        <div className="flex items-center justify-between mt-5 pt-4 border-t border-[#1a1a1a]">
                            <button
                                onClick={() => { setShowOtpScreen(false); setOtpCode(""); setOtpError(null); setOtpSuccess(null); }}
                                className="text-xs text-[#525252] hover:text-[#a3a3a3] transition-colors"
                            >
                                ← Back
                            </button>
                            <button
                                onClick={handleResend}
                                disabled={resendCooldown > 0}
                                className="text-xs text-[#a3a3a3] hover:text-white transition-colors disabled:text-[#525252] disabled:cursor-not-allowed"
                            >
                                {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend code"}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    // ── Login/Signup Screen ───────────────────────────────────────────────────
    return (
        <div className="min-h-screen bg-black flex items-center justify-center p-4">
            <div className="w-full max-w-[400px]">
                <div className="text-center mb-8">
                    <span className="text-white text-xl font-bold tracking-tight">PROGNOT</span>
                    <p className="text-[#525252] text-sm mt-1">AI-powered viral clip extraction</p>
                </div>

                <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-2xl p-6">
                    {/* Tabs */}
                    <div className="flex mb-6 border-b border-[#1a1a1a]">
                        <button
                            onClick={() => { if (activeTab !== "signin") { setActiveTab("signin"); resetState(); } }}
                            className={`flex-1 pb-3 text-sm font-medium transition-colors relative ${
                                activeTab === "signin" ? "text-white" : "text-[#525252] hover:text-[#a3a3a3]"
                            }`}
                        >
                            Sign In
                            {activeTab === "signin" && (
                                <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-white rounded-full" />
                            )}
                        </button>
                        <button
                            onClick={() => { if (activeTab !== "signup") { setActiveTab("signup"); resetState(); } }}
                            className={`flex-1 pb-3 text-sm font-medium transition-colors relative ${
                                activeTab === "signup" ? "text-white" : "text-[#525252] hover:text-[#a3a3a3]"
                            }`}
                        >
                            Create Account
                            {activeTab === "signup" && (
                                <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-white rounded-full" />
                            )}
                        </button>
                    </div>

                    {activeTab === "signin" ? (
                        <form onSubmit={handleSignIn} className="space-y-4">
                            <div>
                                <label className="block text-xs text-[#737373] mb-1.5">Email</label>
                                <input
                                    type="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    disabled={loading}
                                    className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2.5 text-sm text-white placeholder-[#525252] focus:outline-none focus:border-[#404040] transition-colors disabled:opacity-50"
                                    placeholder="you@example.com"
                                    required
                                />
                            </div>
                            <div>
                                <div className="flex justify-between items-center mb-1.5">
                                    <label className="block text-xs text-[#737373]">Password</label>
                                    <a href="#" className="text-xs text-[#a3a3a3] hover:text-white transition-colors">Forgot password?</a>
                                </div>
                                <input
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    disabled={loading}
                                    className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2.5 text-sm text-white placeholder-[#525252] focus:outline-none focus:border-[#404040] transition-colors disabled:opacity-50"
                                    placeholder="••••••••"
                                    required
                                />
                            </div>

                            {error && <p className="text-red-400 text-xs">{error}</p>}

                            <button
                                type="submit"
                                disabled={loading}
                                className="w-full bg-white hover:bg-[#e5e5e5] text-black font-medium py-2.5 rounded-xl text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 mt-2"
                            >
                                {loading ? (
                                    <>
                                        <div className="w-4 h-4 border-2 border-black/20 border-t-black rounded-full animate-spin" />
                                        Signing in...
                                    </>
                                ) : "Sign In"}
                            </button>
                        </form>
                    ) : (
                        <form onSubmit={handleSignUp} className="space-y-4">
                            <div>
                                <label className="block text-xs text-[#737373] mb-1.5">Full Name</label>
                                <input
                                    type="text"
                                    value={fullName}
                                    onChange={(e) => setFullName(e.target.value)}
                                    disabled={loading}
                                    className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2.5 text-sm text-white placeholder-[#525252] focus:outline-none focus:border-[#404040] transition-colors disabled:opacity-50"
                                    placeholder="John Doe"
                                    required
                                />
                            </div>
                            <div>
                                <label className="block text-xs text-[#737373] mb-1.5">Email</label>
                                <input
                                    type="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    disabled={loading}
                                    className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2.5 text-sm text-white placeholder-[#525252] focus:outline-none focus:border-[#404040] transition-colors disabled:opacity-50"
                                    placeholder="you@example.com"
                                    required
                                />
                            </div>
                            <div>
                                <label className="block text-xs text-[#737373] mb-1.5">Password</label>
                                <input
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    disabled={loading}
                                    className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2.5 text-sm text-white placeholder-[#525252] focus:outline-none focus:border-[#404040] transition-colors disabled:opacity-50"
                                    placeholder="••••••••"
                                    required
                                    minLength={8}
                                />
                                <div className="flex gap-1 mt-2">
                                    {[0, 1, 2, 3].map((i) => (
                                        <div key={i} className={`h-1 flex-1 rounded-full transition-colors duration-300 ${getStrengthColor(i)}`} />
                                    ))}
                                </div>
                            </div>
                            <div>
                                <label className="block text-xs text-[#737373] mb-1.5">Confirm Password</label>
                                <input
                                    type="password"
                                    value={confirmPassword}
                                    onChange={(e) => setConfirmPassword(e.target.value)}
                                    disabled={loading}
                                    className="w-full bg-black border border-[#262626] rounded-lg px-3 py-2.5 text-sm text-white placeholder-[#525252] focus:outline-none focus:border-[#404040] transition-colors disabled:opacity-50"
                                    placeholder="••••••••"
                                    required
                                />
                            </div>

                            <div className="flex items-start gap-2">
                                <input
                                    type="checkbox"
                                    id="terms"
                                    checked={termsAccepted}
                                    onChange={(e) => setTermsAccepted(e.target.checked)}
                                    disabled={loading}
                                    className="mt-0.5 w-4 h-4 rounded border-[#262626] bg-black accent-white cursor-pointer"
                                />
                                <label htmlFor="terms" className="text-xs text-[#737373] leading-snug cursor-pointer">
                                    I agree to the Terms of Service and Privacy Policy
                                </label>
                            </div>

                            {error && <p className="text-red-400 text-xs">{error}</p>}

                            <button
                                type="submit"
                                disabled={loading}
                                className="w-full bg-white hover:bg-[#e5e5e5] text-black font-medium py-2.5 rounded-xl text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 mt-2"
                            >
                                {loading ? (
                                    <>
                                        <div className="w-4 h-4 border-2 border-black/20 border-t-black rounded-full animate-spin" />
                                        Creating account...
                                    </>
                                ) : "Create Account"}
                            </button>
                        </form>
                    )}

                    {/* Divider */}
                    <div className="flex items-center gap-3 my-5">
                        <div className="flex-1 h-px bg-[#1a1a1a]" />
                        <span className="text-xs text-[#525252]">or</span>
                        <div className="flex-1 h-px bg-[#1a1a1a]" />
                    </div>

                    {/* Google OAuth */}
                    <button
                        onClick={handleGoogleSignIn}
                        disabled={loading}
                        className="w-full bg-black border border-[#262626] hover:border-[#404040] text-white rounded-xl text-sm font-medium py-2.5 transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <svg className="w-4 h-4" viewBox="0 0 24 24">
                            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
                            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                        </svg>
                        Continue with Google
                    </button>
                </div>
            </div>
        </div>
    );
}
