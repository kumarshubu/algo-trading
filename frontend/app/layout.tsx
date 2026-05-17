import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "Algo Trading - Paper Only",
  description: "Paper trading platform for learning algo trading. NOT for real trading.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body suppressHydrationWarning>
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 ml-56 p-6 overflow-auto">{children}</main>
        </div>
      </body>
    </html>
  );
}
