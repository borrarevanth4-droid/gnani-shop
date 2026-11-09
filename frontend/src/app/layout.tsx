import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import AuthProvider from "@/components/AuthProvider";
import AppShell from "@/components/AppShell";
import { LanguageProvider } from "@/lib/i18n";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Gnani Shop",
  description: "A voice-first grocery store in 10 Indian languages, powered by Gnani Vachana speech AI. Built by Revanth.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <AuthProvider>
          <LanguageProvider>
            <AppShell>{children}</AppShell>
          </LanguageProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
