import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "ABW Connect",
  description: "Source-backed answers for All Builders Welcome grant recipients and alumni advisors.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="bg-ink text-white">
          <div className="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3">
            <Link href="/" className="font-semibold tracking-tight">
              ABW Connect
            </Link>
            <p className="hidden text-sm text-white/70 sm:block">
              Answers for All Builders Welcome grant recipients and alumni advisors
            </p>
            <nav className="ml-auto flex gap-4 text-sm">
              <Link className="text-white/90 hover:text-white" href="/">
                Chat
              </Link>
              <Link className="text-white/90 hover:text-white" href="/advisor">
                Advisor
              </Link>
            </nav>
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}
