'use client';

import { useState, useEffect } from "react";
import { authFetch } from "@/lib/api";
import AccessDenied from "./access-denied";

export function ClientRestricted({ children }: { children: React.ReactNode }) {
    const [isClient, setIsClient] = useState<boolean | null>(null);

    useEffect(() => {
        authFetch('/credits/balance')
            .then((res) => {
                setIsClient(res.ok);
            })
            .catch(() => {
                setIsClient(false);
            });
    }, []);

    if (isClient === null) return null;
    if (isClient) return <AccessDenied />;
    return <>{children}</>;
}
