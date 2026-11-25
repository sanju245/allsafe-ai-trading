import type { Metadata } from "next";
import localFont from "next/font/local";
import { AuthProvider } from "@/components/auth/AuthProvider";
import "./globals.css";

const inter = localFont({
  src: "./fonts/inter-latin.woff2",
  weight: "400 800",
  variable: "--font-allsafe",
  display: "swap",
});

export const metadata: Metadata = {
  title: "AllSafe AI Trading",
  description:
    "Rule-based market analysis for NIFTY 50 and BANK NIFTY. Educational analysis only; no order placement.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
