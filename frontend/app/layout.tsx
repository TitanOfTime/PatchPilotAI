import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "PatchPilot AI · Engineering, with evidence",
  description:
    "Source-grounded repository intelligence and human-reviewed engineering workflows.",
};
export default function Layout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
