import "./globals.css";
import "rrweb/dist/style.css";
import type { Metadata } from "next";
import { Outfit } from "next/font/google";
import { AuthProvider } from "@/components/providers/AuthProvider";
import { AppShell } from "@/components/layout/AppShell";
import { RecordingNotice, SessionRecordingProvider } from "@/components/session/SessionRecordingProvider";

const display = Outfit({ subsets: ["latin"], weight: ["500", "600", "700", "800"], variable: "--font-display" });

export const metadata: Metadata = {
  title: "PayTrace | AI-Powered PayPal Payment Investigation & Observability",
  description: "Cross-signal PayPal payment lifecycle observability and AI investigator platform.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${display.variable} min-h-screen bg-slate-950 text-slate-100 antialiased`}>
        <AuthProvider>
          <SessionRecordingProvider>
            <AppShell>{children}</AppShell>
            <RecordingNotice />
          </SessionRecordingProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
