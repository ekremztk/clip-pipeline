import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import { S3Client, PutObjectCommand, DeleteObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

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

export async function POST(request: Request) {
  try {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const body = await request.json();
    const { filename, content_type } = body;

    if (!filename || !content_type) {
      return NextResponse.json({ error: "Missing filename or content_type" }, { status: 400 });
    }

    const ext = filename.split(".").pop() ?? "jpg";
    const r2_key = `sell/${user.id}/${crypto.randomUUID()}.${ext}`;

    const r2 = getR2Client();
    const cmd = new PutObjectCommand({
      Bucket: process.env.R2_BUCKET_NAME!,
      Key: r2_key,
      ContentType: content_type,
    });
    const upload_url = await getSignedUrl(r2, cmd, { expiresIn: 900 });
    const public_url = `${process.env.NEXT_PUBLIC_R2_PUBLIC_URL}/${r2_key}`;

    return NextResponse.json({ upload_url, public_url }, { status: 201 });
  } catch (err) {
    console.error("[API /media] POST error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}

export async function DELETE(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const key = searchParams.get("key");
    if (!key) return NextResponse.json({ error: "Missing key" }, { status: 400 });

    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    if (!key.startsWith(`sell/${user.id}/`)) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }

    const r2 = getR2Client();
    await r2.send(new DeleteObjectCommand({
      Bucket: process.env.R2_BUCKET_NAME!,
      Key: key,
    }));

    return NextResponse.json({ deleted: true });
  } catch (err) {
    console.error("[API /media] DELETE error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
