'use client'

import { createBrowserClient } from '@supabase/ssr'
import { LogOut } from 'lucide-react'

export function Header() {
  const supabase = createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )

  async function handleLogout() {
    await supabase.auth.signOut()
    window.location.href = '/login'
  }

  return (
    <header className="h-16 border-b border-[#e5e5e5] bg-white/90 backdrop-blur flex items-center justify-between px-6">
      <div />
      <button
        onClick={handleLogout}
        className="flex items-center gap-2 text-sm text-[#737373] hover:text-[#171717] transition-colors"
      >
        <LogOut size={14} />
        Logout
      </button>
    </header>
  )
}
