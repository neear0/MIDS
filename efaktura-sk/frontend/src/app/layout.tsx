import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "eFaktúra SK",
  description: "Elektronická fakturácia pre slovenských podnikateľov – EN 16931, Peppol, DPH.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="sk" className="h-full">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
