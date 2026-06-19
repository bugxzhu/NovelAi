import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { ThemeScript } from "./ThemeScript";
import { ThemeApplier } from "./ThemeApplier";

export const metadata: Metadata = {
  title: "NovelAI",
  description: "本地优先的 AI 辅助小说写作工具",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <ThemeScript />
      </head>
      <body>
        <Providers>
          <ThemeApplier />
          {children}
        </Providers>
      </body>
    </html>
  );
}
