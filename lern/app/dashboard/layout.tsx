import { Sidebar } from '@/components/sidebar'
import { Header } from '@/components/header'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-white">
      <Sidebar />
      <div className="ml-[260px]">
        <Header />
        <main className="p-6">
          {children}
        </main>
      </div>
    </div>
  )
}
