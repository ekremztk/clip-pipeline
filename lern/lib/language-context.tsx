'use client'

import { createContext, useContext, useState, useEffect } from 'react'

type Language = 'tr' | 'ru'

interface LanguageContextType {
  lang: Language
  setLang: (l: Language) => void
}

const LanguageContext = createContext<LanguageContextType>({
  lang: 'tr',
  setLang: () => {},
})

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Language>('tr')

  useEffect(() => {
    const saved = localStorage.getItem('lern_lang') as Language | null
    if (saved === 'tr' || saved === 'ru') setLangState(saved)
  }, [])

  function setLang(l: Language) {
    setLangState(l)
    localStorage.setItem('lern_lang', l)
  }

  return (
    <LanguageContext.Provider value={{ lang, setLang }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLang() {
  return useContext(LanguageContext)
}
