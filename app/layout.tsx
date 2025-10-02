// app/layout.tsx
import '../styles/globals.css';

export const metadata = {
  title: 'Daily Market Dashboard',
  description: 'Schnelles, mobilfreundliches Markt-Dashboard'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de">
      <body>{children}</body>
    </html>
  );
}