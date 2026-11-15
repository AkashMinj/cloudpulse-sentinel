import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CloudPulse Sentinel | Cloud Operations Dashboard",
  description: "Cloud health, incident intelligence, anomaly detection and resource utilization monitoring.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
