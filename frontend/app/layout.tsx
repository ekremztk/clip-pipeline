import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { Toaster } from "sonner";

export const metadata: Metadata = {
  title: "Prognot Studio",
  description: "AI-powered viral clip extraction platform",
  icons: {
    icon: "/favicon.png",
    apple: "/favicon.png",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              background: "#1c1c1b",
              border: "1px solid rgba(250,249,245,0.08)",
              color: "#faf9f5",
              fontFamily: "Inter, sans-serif",
              fontSize: "13px",
            },
          }}
        />
      </body>
    </html>
  );
}
