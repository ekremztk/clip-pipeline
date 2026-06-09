'use client'

import { createBrowserClient } from '@supabase/ssr'
import { LogOut } from 'lucide-react'
import { useLang } from '@/lib/language-context'

export function Header() {
  const supabase = createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )
  const { lang, setLang } = useLang()

  async function handleLogout() {
    await supabase.auth.signOut()
    window.location.href = '/login'
  }

  return (
    <header className="h-16 border-b border-[#e5e5e5] bg-white/90 backdrop-blur flex items-center justify-between px-6">
      <div />
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1 border border-[#e5e5e5] rounded-md p-0.5">
          <button
            onClick={() => setLang('tr')}
            title="Türkçe çeviri"
            className={`px-2.5 py-1 rounded text-sm transition-colors ${
              lang === 'tr'
                ? 'bg-[#171717] text-white'
                : 'text-[#737373] hover:text-[#171717]'
            }`}
          >
            🇹🇷
          </button>
          <button
            onClick={() => setLang('ru')}
            title="Русский перевод"
            className={`px-2.5 py-1 rounded text-sm transition-colors ${
              lang === 'ru'
                ? 'bg-[#171717] text-white'
                : 'text-[#737373] hover:text-[#171717]'
            }`}
          >
            🇷🇺
          </button>
        </div>
        <button
          onClick={handleLogout}
          className="flex items-center gap-2 text-sm text-[#737373] hover:text-[#171717] transition-colors"
        >
          <LogOut size={14} />
          Abmelden
        </button>
      </div>
    </header>
  )
}
