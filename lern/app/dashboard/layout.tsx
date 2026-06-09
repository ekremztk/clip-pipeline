import { Sidebar } from '@/components/sidebar'
import { Header } from '@/components/header'
import { LanguageProvider } from '@/lib/language-context'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <LanguageProvider>
      <div className="min-h-screen bg-white">
        <Sidebar />
        <div className="ml-[260px]">
          <Header />
          <main className="p-6">
            {children}
          </main>
        </div>
      </div>
    </LanguageProvider>
  )
}
