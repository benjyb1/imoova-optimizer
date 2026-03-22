import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";

const geist = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Imoova Holiday Optimizer",
  description:
    "Find the cheapest campervan road trips across Europe. Free Imoova relocations matched with budget flights.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${geist.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col font-[family-name:var(--font-geist-sans)]">
        {/* Header */}
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="text-2xl" role="img" aria-label="campervan">
                &#x1F690;
              </span>
              <span className="text-lg font-bold text-text">
                Imoova <span className="text-accent">Holiday Optimizer</span>
              </span>
            </div>
            <a
              href="https://www.imoova.com/en/relocations/table/europe"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-text-muted hover:text-primary transition-colors"
            >
              View Imoova Deals &rarr;
            </a>
          </div>
        </header>

        {/* Main content */}
        <main className="flex-1 px-4 py-8">{children}</main>

        {/* Footer */}
        <footer className="border-t border-slate-200 bg-white py-4 text-center text-xs text-text-muted">
          Not affiliated with Imoova. Prices are estimates and may vary.
        </footer>
      </body>
    </html>
  );
}
