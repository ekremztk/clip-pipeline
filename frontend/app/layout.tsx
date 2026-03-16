import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Prognot Studio",
  description: "AI-powered viral clip extraction platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
