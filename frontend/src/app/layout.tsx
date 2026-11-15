import type { Metadata } from "next";
import { Nunito, Pangolin } from "next/font/google";
import "./globals.css";

const nunito = Nunito({
  variable: "--font-nunito",
  subsets: ["latin", "cyrillic"],
});

const pangolin = Pangolin({
  variable: "--font-pangolin",
  subsets: ["latin", "cyrillic"],
  weight: "400",
});

export const metadata: Metadata = {
  title: "Sessionly",
  description: "Записи, оплати та розклад для незалежних психологів.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="uk" className={`${nunito.variable} ${pangolin.variable}`}>
      <body>{children}</body>
    </html>
  );
}
