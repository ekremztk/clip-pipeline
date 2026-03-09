import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Clip Pipeline",
  description: "YouTube → Viral Klipler",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body>{children}</body>
    </html>
  );
}