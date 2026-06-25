import type { Metadata, Viewport } from "next";
import { Barlow_Condensed, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const brandDisplay = Barlow_Condensed({
  variable: "--font-brand-display",
  subsets: ["latin"],
  weight: ["600", "700"],
});

const mono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "MK Jewels Live Dashboard",
  description: "Live sales floor transcript monitoring for MK Jewels",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    title: "MK Jewels Manager",
  },
};

export const viewport: Viewport = {
  themeColor: "#C9A96E",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${brandDisplay.variable} ${mono.variable} dark h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-zinc-950">{children}</body>
    </html>
  );
}
