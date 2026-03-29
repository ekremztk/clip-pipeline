import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import { S3Client, PutObjectCommand, DeleteObjectCommand } from "@aws-sdk/client-s3";

function getR2Client() {
	return new S3Client({
		region: "auto",
		endpoint: `https://${process.env.CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com`,
		credentials: {
			accessKeyId: process.env.R2_ACCESS_KEY_ID!,
			secretAccessKey: process.env.R2_SECRET_ACCESS_KEY!,
		},
	});
}

// GET /api/media?project_id=xxx — list media assets for a project
export async function GET(request: Request) {
	try {
		const { searchParams } = new URL(request.url);
		const project_id = searchParams.get("project_id");
		if (!project_id) return NextResponse.json({ error: "Missing project_id" }, { status: 400 });

		const supabase = await createClient();
		const { data: { user } } = await supabase.auth.getUser();
		if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

		const { data, error } = await supabase
			.from("editor_media_assets")
			.select("*")
			.eq("project_id", project_id)
			.eq("user_id", user.id);

		if (error) throw error;

		// Attach public URL to each asset
		const r2BaseUrl = process.env.NEXT_PUBLIC_R2_PUBLIC_URL ?? "";
		const assetsWithUrl = (data ?? []).map((asset) => ({
			...asset,
			public_url: `${r2BaseUrl}/${asset.r2_key}`,
		}));

		return NextResponse.json(assetsWithUrl);
	} catch (err) {
		console.error("[API /media] GET error:", err);
		return NextResponse.json({ error: "Internal server error" }, { status: 500 });
	}
}

// POST /api/media — upload file to R2 server-side, create DB record
// Accepts multipart/form-data: file + metadata fields
export async function POST(request: Request) {
	try {
		const supabase = await createClient();
		const { data: { user } } = await supabase.auth.getUser();
		if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

		const contentType = request.headers.get("content-type") ?? "";
		let project_id: string, name: string, type: string, size: number,
			width: number | undefined, height: number | undefined,
			duration: number | undefined, fps: number | undefined,
			content_type: string, fileBuffer: Buffer | null = null;

		if (contentType.includes("multipart/form-data")) {
			// File upload path
			const form = await request.formData();
			const file = form.get("file") as File | null;
			if (!file) return NextResponse.json({ error: "Missing file" }, { status: 400 });

			project_id = form.get("project_id") as string;
			name = form.get("name") as string ?? file.name;
			type = form.get("type") as string;
			content_type = file.type || "application/octet-stream";
			size = file.size;
			width = form.get("width") ? Number(form.get("width")) : undefined;
			height = form.get("height") ? Number(form.get("height")) : undefined;
			duration = form.get("duration") ? Number(form.get("duration")) : undefined;
			fps = form.get("fps") ? Number(form.get("fps")) : undefined;
			fileBuffer = Buffer.from(await file.arrayBuffer());
		} else {
			// JSON metadata-only path (legacy — returns upload_url)
			const body = await request.json();
			({ project_id, name, type, size, width, height, duration, fps, content_type } = body);
		}

		if (!project_id || !name || !type) {
			return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
		}

		// Verify project belongs to user
		const { data: project } = await supabase
			.from("editor_projects")
			.select("id")
			.eq("id", project_id)
			.eq("user_id", user.id)
			.single();

		if (!project) return NextResponse.json({ error: "Project not found" }, { status: 404 });

		// Generate R2 key
		const ext = name.split(".").pop() ?? "bin";
		const r2_key = `editor/${user.id}/${project_id}/${crypto.randomUUID()}.${ext}`;

		// Create DB record
		const { data: asset, error: dbError } = await supabase
			.from("editor_media_assets")
			.insert({ user_id: user.id, project_id, name, type, size, width, height, duration, fps, r2_key })
			.select()
			.single();

		if (dbError) throw dbError;

		const r2 = getR2Client();
		const public_url = `${process.env.NEXT_PUBLIC_R2_PUBLIC_URL}/${r2_key}`;

		if (fileBuffer) {
			// Server-side upload — no client CORS needed
			await r2.send(new PutObjectCommand({
				Bucket: process.env.R2_BUCKET_NAME!,
				Key: r2_key,
				Body: fileBuffer,
				ContentType: content_type!,
			}));
			return NextResponse.json({ asset, public_url }, { status: 201 });
		} else {
			// Legacy: return presigned URL for client upload
			const { getSignedUrl } = await import("@aws-sdk/s3-request-presigner");
			const cmd = new PutObjectCommand({
				Bucket: process.env.R2_BUCKET_NAME!,
				Key: r2_key,
				ContentType: content_type!,
			});
			const upload_url = await getSignedUrl(r2, cmd, { expiresIn: 900 });
			return NextResponse.json({ asset, upload_url, public_url }, { status: 201 });
		}
	} catch (err) {
		console.error("[API /media] POST error:", err);
		return NextResponse.json({ error: "Internal server error" }, { status: 500 });
	}
}

// DELETE /api/media?id=xxx — delete media asset + R2 file
export async function DELETE(request: Request) {
	try {
		const { searchParams } = new URL(request.url);
		const id = searchParams.get("id");
		if (!id) return NextResponse.json({ error: "Missing id" }, { status: 400 });

		const supabase = await createClient();
		const { data: { user } } = await supabase.auth.getUser();
		if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

		// Get asset to find r2_key
		const { data: asset } = await supabase
			.from("editor_media_assets")
			.select("r2_key")
			.eq("id", id)
			.eq("user_id", user.id)
			.single();

		if (!asset) return NextResponse.json({ error: "Not found" }, { status: 404 });

		// Delete from R2
		const r2 = getR2Client();
		await r2.send(new DeleteObjectCommand({
			Bucket: process.env.R2_BUCKET_NAME!,
			Key: asset.r2_key,
		}));

		// Delete from DB
		await supabase.from("editor_media_assets").delete().eq("id", id).eq("user_id", user.id);

		return NextResponse.json({ deleted: true });
	} catch (err) {
		console.error("[API /media] DELETE error:", err);
		return NextResponse.json({ error: "Internal server error" }, { status: 500 });
	}
}
