import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Market Calibration Single App',
  description: 'Minimal single-app scaffold (UI + API + worker + DB)'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body style={{ fontFamily: 'sans-serif', margin: 24 }}>{children}</body>
    </html>
  );
}
