import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Clip Studio",
  description: "Tạo video Shorts và TikTok từ kịch bản tiếng Việt.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi">
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(()=>{const external=(value)=>{const text=String(value?.stack||value?.message||value||'');return text.includes('chrome-extension://')||text.includes("reading 'M_ID'")||text.includes('reading \\"M_ID\\"')};window.addEventListener('unhandledrejection',(event)=>{if(external(event.reason)){event.preventDefault();event.stopImmediatePropagation()}},true);window.addEventListener('error',(event)=>{if(String(event.filename||'').startsWith('chrome-extension://')||external(event.error)){event.preventDefault();event.stopImmediatePropagation()}},true)})();`,
          }}
        />
      </head>
      <body className="antialiased">{children}</body>
    </html>
  );
}
