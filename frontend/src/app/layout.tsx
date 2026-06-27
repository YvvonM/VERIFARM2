import type { Metadata } from "next";
import { Space_Grotesk, Syne } from "next/font/google";
import "./globals.css";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["300", "400", "500", "600", "700"],
});

const syne = Syne({
  subsets: ["latin"],
  variable: "--font-heading",
  weight: ["700", "800"],
});

export const metadata: Metadata = {
  title: "VeriFarms Copilot",
  description: "GenUI agricultural trust dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body
        className={`${spaceGrotesk.variable} ${syne.variable} font-body antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
