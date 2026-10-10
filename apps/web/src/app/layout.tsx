import "./globals.css";
import { Navigation } from "@/components/Navigation";
import { KiteHeader } from "@/components/KiteHeader";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Algo Lab — Zerodha Kite Quant OS",
  description: "Disciplined systematic research and execution platform for Indian markets — Reviewed by Nithin Kamath",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-background text-slate-100 flex min-h-screen">
        <Navigation />
        <div className="flex-1 flex flex-col min-w-0">
          <KiteHeader />
          <main className="flex-1 p-6 md:p-8 overflow-y-auto">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
