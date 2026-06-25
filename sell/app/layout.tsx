import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sell - Prognot",
  description: "Marketplace deal finder",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de">
      <body>{children}</body>
    </html>
  );
}
