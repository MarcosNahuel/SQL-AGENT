import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SQL Agent - Business Analytics",
  description: "AI-powered business analytics dashboard with natural language queries",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body className="min-h-screen bg-gray-950 text-white antialiased">
        {children}
      </body>
    </html>
  );
}
