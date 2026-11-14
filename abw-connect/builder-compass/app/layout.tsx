import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import StoreHydrator from "@/components/StoreHydrator";
import UndoToast from "@/components/UndoToast";

// Self-hosted at build time by next/font: no runtime request to Google, no
// render-blocking stylesheet, and no layout shift from font swapping.
const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
    ],
    apple: "/apple-touch-icon.png",
  },
  title: "Builder Compass — AWS re:Invent planner",
  description:
    "An independent, unofficial AWS re:Invent session planner. Browse the catalog, build a conflict-free schedule across venues, and export a trip report.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Apply saved/system theme before paint to avoid a light flash. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem("bc-theme");if(t==="dark"||(!t&&window.matchMedia("(prefers-color-scheme: dark)").matches)){document.documentElement.classList.add("dark")}}catch(e){}`,
          }}
        />
      </head>
      <body className={`${sans.variable} ${mono.variable} min-h-screen bg-surface font-sans text-ink`}>
        <StoreHydrator />
        <Sidebar />
        <div className="md:pl-60">
          <main className="mx-auto max-w-6xl px-4 py-6 md:px-8 md:py-8">
            {children}
          </main>
          <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-muted md:px-8">
            Builder Compass is an independent, unofficial planner. Not
            affiliated with or endorsed by Amazon Web Services.
          </footer>
        </div>
        <UndoToast />
      </body>
    </html>
  );
}
