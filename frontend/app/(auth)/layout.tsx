export default async function AuthLayout({ children }: { children: React.ReactNode }) {
    // Server component — just render children
    // Client-side redirect handled in page.tsx/middleware
    return <>{children}</>;
}
