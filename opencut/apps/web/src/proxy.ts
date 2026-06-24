import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login", "/api/health", "/api/auth"];

export async function proxy(request: NextRequest) {
	const { pathname } = request.nextUrl;

	// Allow public paths through without auth check
	if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
		return NextResponse.next();
	}

	let response = NextResponse.next({ request });

	const supabase = createServerClient(
		process.env.NEXT_PUBLIC_SUPABASE_URL!,
		process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
		{
			cookies: {
				getAll() {
					return request.cookies.getAll();
				},
				setAll(cookiesToSet) {
					for (const { name, value } of cookiesToSet) {
						request.cookies.set(name, value);
					}
					response = NextResponse.next({ request });
					for (const { name, value, options } of cookiesToSet) {
						response.cookies.set(name, value, options);
					}
				},
			},
		},
	);

	const {
		data: { user },
	} = await supabase.auth.getUser();

	if (!user) {
		const loginUrl = new URL("/login", request.url);
		loginUrl.searchParams.set("next", pathname);
		return NextResponse.redirect(loginUrl);
	}

	// Block client accounts from accessing the editor
	const { data } = await supabase
		.from("client_accounts")
		.select("user_id")
		.eq("user_id", user.id)
		.limit(1);
	if (data && data.length > 0) {
		return new NextResponse(
			'<html><body style="background:#000;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif"><div style="text-align:center"><h1 style="font-size:1.5rem;margin-bottom:0.5rem">Access Denied</h1><p style="color:#888">You do not have permission to access the editor. Please contact your administrator.</p></div></body></html>',
			{ status: 403, headers: { "Content-Type": "text/html" } },
		);
	}

	return response;
}

export const config = {
	matcher: [
		"/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
	],
};
