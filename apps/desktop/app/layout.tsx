import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "倪师数字人",
  description: "基于倪海厦体系资料与 MiMo 的桌面数字人对话示例"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
