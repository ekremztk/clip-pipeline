"use client";

import posthog from "posthog-js";
import { PostHogProvider } from "posthog-js/react";

const POSTHOG_KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY || "";
const POSTHOG_HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST || "https://us.i.posthog.com";

// Sentry client init is handled by sentry.client.config.ts via instrumentation hook
// PostHog init
if (typeof window !== "undefined" && POSTHOG_KEY) {
  posthog.init(POSTHOG_KEY, {
    api_host: POSTHOG_HOST,
    person_profiles: "identified_only",
    capture_pageview: true,
    capture_pageleave: true,
  });
}

export function Providers({ children }: { children: React.ReactNode }) {
  if (!POSTHOG_KEY) return <>{children}</>;
  return <PostHogProvider client={posthog}>{children}</PostHogProvider>;
}
