'use client'

import { useState } from 'react'
import { createBrowserClient } from '@supabase/ssr'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const supabase = createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')

    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) {
      setError(error.message)
      setLoading(false)
    } else {
      window.location.href = '/dashboard'
    }
  }

  async function handleGoogleLogin() {
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/dashboard` }
    })
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#fafafa]">
      <div className="w-full max-w-sm bg-white border border-[#e5e5e5] rounded-lg p-8">
        <h1 className="text-xl font-bold text-[#171717] mb-1">Lern</h1>
        <p className="text-sm text-[#737373] mb-6">German language companion</p>

        <form onSubmit={handleLogin} className="space-y-4">
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            className="w-full h-9 px-3 text-sm border border-[#e5e5e5] rounded-md focus:outline-none focus:border-[#171717] transition-colors"
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            className="w-full h-9 px-3 text-sm border border-[#e5e5e5] rounded-md focus:outline-none focus:border-[#171717] transition-colors"
          />
          {error && <p className="text-xs text-red-500">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full h-9 bg-[#171717] text-white text-sm font-medium rounded-md hover:bg-[#2a2a2a] disabled:opacity-50 transition-colors"
          >
            {loading ? 'Logging in...' : 'Log in'}
          </button>
        </form>

        <div className="relative my-4">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-[#e5e5e5]" />
          </div>
          <div className="relative flex justify-center text-xs">
            <span className="bg-white px-2 text-[#a3a3a3]">or</span>
          </div>
        </div>

        <button
          onClick={handleGoogleLogin}
          className="w-full h-9 border border-[#e5e5e5] text-sm text-[#171717] rounded-md hover:bg-[#f5f5f5] transition-colors"
        >
          Continue with Google
        </button>
      </div>
    </div>
  )
}
