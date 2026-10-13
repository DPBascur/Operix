import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Operix Frontend",
  description: "Espacio operacional de análisis de video de Operix",
};

// Runs before paint; route changes never choose the user's theme.
const themeScript = `(function(){var root=document.documentElement;var media=matchMedia('(prefers-color-scheme: dark)');function apply(){var p=root.dataset.preference||'system';try{p=localStorage.getItem('operix-theme')||'system'}catch(e){}if(!['light','dark','system'].includes(p))p='system';root.dataset.preference=p;root.dataset.theme=p==='system'?(media.matches?'dark':'light'):p;}apply();media.addEventListener('change',apply);window.addEventListener('storage',apply)})();`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
