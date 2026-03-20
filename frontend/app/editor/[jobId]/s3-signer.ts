// EDITOR MODULE — Isolated module, no dependencies on other app files

export async function generateR2PresignedUrl(
    key: string,
    expiresIn = 86400
): Promise<string> {
    const accountId = process.env.R2_ACCOUNT_ID;
    const accessKeyId = process.env.R2_ACCESS_KEY_ID;
    const secretAccessKey = process.env.R2_SECRET_ACCESS_KEY;
    const bucketName = process.env.R2_BUCKET_NAME;

    if (!accountId || !accessKeyId || !secretAccessKey || !bucketName) {
        console.warn('Missing R2 credentials for presigned URL, falling back to public URL');
        return `${process.env.R2_PUBLIC_URL}/${key}`;
    }

    const host = `${accountId}.r2.cloudflarestorage.com`;
    const endpoint = `https://${host}/${bucketName}/${key}`;

    const url = new URL(endpoint);
    const date = new Date();

    // AWS Signature V4 requires specific date formats
    const amzDate = date.toISOString().replace(/[:-]|\.\d{3}/g, '');
    const dateStamp = amzDate.substring(0, 8);
    const region = 'auto';
    const service = 's3';

    url.searchParams.set('X-Amz-Algorithm', 'AWS4-HMAC-SHA256');
    url.searchParams.set('X-Amz-Credential', `${accessKeyId}/${dateStamp}/${region}/${service}/aws4_request`);
    url.searchParams.set('X-Amz-Date', amzDate);
    url.searchParams.set('X-Amz-Expires', expiresIn.toString());
    url.searchParams.set('X-Amz-SignedHeaders', 'host');

    // Canonical Request
    const canonicalUri = `/${bucketName}/${key}`;
    const canonicalQueryString = Array.from(url.searchParams.entries())
        .sort(([k1], [k2]) => k1.localeCompare(k2))
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
        .join('&');

    const canonicalHeaders = `host:${host}\n`;
    const signedHeaders = 'host';
    const payloadHash = 'UNSIGNED-PAYLOAD';

    const canonicalRequest = `GET\n${canonicalUri}\n${canonicalQueryString}\n${canonicalHeaders}\n${signedHeaders}\n${payloadHash}`;

    // String to Sign
    const algorithm = 'AWS4-HMAC-SHA256';
    const credentialScope = `${dateStamp}/${region}/${service}/aws4_request`;

    const hashBuffer = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonicalRequest));
    const canonicalRequestHash = Array.from(new Uint8Array(hashBuffer)).map(b => b.toString(16).padStart(2, '0')).join('');

    const stringToSign = `${algorithm}\n${amzDate}\n${credentialScope}\n${canonicalRequestHash}`;

    // Calculate Signature
    const getSignatureKey = async (key: string, dateStamp: string, regionName: string, serviceName: string) => {
        const kDate = await hmac('AWS4' + key, dateStamp);
        const kRegion = await hmac(kDate, regionName);
        const kService = await hmac(kRegion, serviceName);
        const kSigning = await hmac(kService, 'aws4_request');
        return kSigning;
    };

    const hmac = async (key: string | ArrayBuffer, data: string) => {
        const cryptoKey = await crypto.subtle.importKey(
            'raw',
            typeof key === 'string' ? new TextEncoder().encode(key) : key,
            { name: 'HMAC', hash: 'SHA-256' },
            false,
            ['sign']
        );
        const signature = await crypto.subtle.sign('HMAC', cryptoKey, new TextEncoder().encode(data));
        return signature;
    };

    const signingKey = await getSignatureKey(secretAccessKey, dateStamp, region, service);
    const signatureBuffer = await hmac(signingKey, stringToSign);
    const signature = Array.from(new Uint8Array(signatureBuffer)).map(b => b.toString(16).padStart(2, '0')).join('');

    url.searchParams.set('X-Amz-Signature', signature);

    return url.toString();
}
