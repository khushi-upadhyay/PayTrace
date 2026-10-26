import "./globals.css";
import "rrweb/dist/style.css";
import type { Metadata } from "next";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { RecordingNotice, SessionRecordingProvider } from "@/components/session/SessionRecordingProvider";

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
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 antialiased font-sans min-h-screen">
        <SessionRecordingProvider>
          <div className="flex">
            <Sidebar />
            <div className="flex-1 min-w-0 ml-64">
              <Header />
              <main className="p-8 min-h-[calc(100vh-4rem)] bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900/40 via-slate-950 to-slate-950">
                {children}
              </main>
            </div>
          </div>
          <RecordingNotice />
        </SessionRecordingProvider>
      </body>
    </html>
  );
}
