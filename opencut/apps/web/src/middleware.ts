import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function middleware(request: NextRequest) {
	let supabaseResponse = NextResponse.next({ request });

	const supabase = createServerClient(
		process.env.NEXT_PUBLIC_SUPABASE_URL!,
		process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
		{
			cookies: {
				getAll() {
					return request.cookies.getAll();
				},
				setAll(
					cookiesToSet: { name: string; value: string; options?: any }[],
				) {
					cookiesToSet.forEach(({ name, value }) =>
						request.cookies.set(name, value),
					);
					supabaseResponse = NextResponse.next({ request });
					cookiesToSet.forEach(({ name, value, options }) =>
						supabaseResponse.cookies.set(name, value, options),
					);
				},
			},
		},
	);

	const {
		data: { user },
	} = await supabase.auth.getUser();

	const isEditorRoute =
		request.nextUrl.pathname.startsWith("/editor") ||
		request.nextUrl.pathname === "/";

	// Block client accounts from accessing the editor
	if (user && isEditorRoute) {
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
	}

	return supabaseResponse;
}

export const config = {
	matcher: ["/((?!_next/static|_next/image|favicon.ico|api).*)"],
};
