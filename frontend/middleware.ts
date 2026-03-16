import { createMiddlewareClient } from '@supabase/auth-helpers-nextjs'
import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export async function middleware(req: NextRequest) {
    const res = NextResponse.next()
    const supabase = createMiddlewareClient({ req, res })
    const { data: { session } } = await supabase.auth.getSession()

    const isAuthPage = req.nextUrl.pathname.startsWith('/login')
    const isDashboard = req.nextUrl.pathname.startsWith('/dashboard') ||
        req.nextUrl.pathname === '/'

    if (!session && isDashboard) {
        return NextResponse.redirect(new URL('/login', req.url))
    }

    if (session && isAuthPage) {
        return NextResponse.redirect(new URL('/dashboard', req.url))
    }

    // If user hits root and has session, redirect to dashboard.
    if (session && req.nextUrl.pathname === '/') {
        return NextResponse.redirect(new URL('/dashboard', req.url))
    }

    return res
}

export const config = {
    matcher: ['/((?!_next/static|_next/image|favicon.ico|api).*)']
}
