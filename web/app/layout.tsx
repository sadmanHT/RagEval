import type { Metadata } from "next";
import "./globals.css";
import "./light-theme.css";

export const metadata: Metadata = {
  title: "RAG-Eval Console",
  description: "Grounded retrieval, citations, evaluation, and system status.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
