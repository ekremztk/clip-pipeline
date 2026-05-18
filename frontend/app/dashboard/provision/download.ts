"use client";

import { authFetch } from "@/lib/api";

export async function downloadProvisionVariant(variantId: string): Promise<void> {
    const res = await authFetch(`/provision/variants/${variantId}/download`);
    if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(body || `Download failed (${res.status})`);
    }
    const data = await res.json();
    const downloadUrl = data?.download_url;
    const filename = data?.filename || "provision-variant.mp4";
    if (!downloadUrl) {
        throw new Error("Download URL was not returned");
    }

    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = filename;
    link.rel = "noreferrer";
    document.body.appendChild(link);
    link.click();
    link.remove();
}
