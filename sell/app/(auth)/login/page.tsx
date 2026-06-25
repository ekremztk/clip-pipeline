"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    const { error } = await supabase.auth.signInWithPassword({ email, password });

    if (error) {
      setError(error.message);
      setLoading(false);
      return;
    }

    router.push("/dashboard");
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#fafafa]">
      <div className="w-full max-w-sm rounded-lg border border-[#e5e5e5] bg-white p-8">
        <h1 className="mb-6 text-center text-xl font-semibold text-[#171717]">Sell - Login</h1>
        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm text-[#525252]">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-[#e5e5e5] px-3 py-2 text-sm outline-none focus:border-[#171717]"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-[#525252]">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-[#e5e5e5] px-3 py-2 text-sm outline-none focus:border-[#171717]"
              required
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md bg-[#171717] py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#333] disabled:opacity-50"
          >
            {loading ? "Loading..." : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
