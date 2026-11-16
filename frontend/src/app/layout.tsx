import type { Metadata } from "next";
import { OperixMotionProvider } from "@/components/motion/motion-provider";
import { AppShell } from "@/components/layout/app-shell";
import { SessionProvider } from "@/features/auth/session-provider";
import { GuideLauncher } from "@/features/experience/guide-launcher";
import "./globals.css";
import "./identity.css";
import "@/features/experience/experience.css";
import "./app-design.css";

export const metadata: Metadata = {
  title: { default: "Operix", template: "%s · Operix" },
  description: "Espacio operacional de análisis de video de Operix",
};

// Runs before paint; route changes never choose the user's theme.
const themeScript = `(function(){var root=document.documentElement;var media=matchMedia('(prefers-color-scheme: dark)');function apply(){var p=root.dataset.preference||'system';try{p=localStorage.getItem('operix-theme')||'system'}catch(e){}if(!['light','dark','system'].includes(p))p='system';root.dataset.preference=p;root.dataset.theme=p==='system'?(media.matches?'dark':'light'):p;}apply();media.addEventListener('change',apply);window.addEventListener('storage',apply)})();`;
const sidebarScript = `try{if(localStorage.getItem('operix-sidebar')==='compact')document.documentElement.dataset.sidebarPreference='compact'}catch(e){}`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        <script dangerouslySetInnerHTML={{ __html: sidebarScript }} />
      </head>
      <body>
        <OperixMotionProvider>
          <SessionProvider>
            <AppShell>{children}</AppShell>
            <GuideLauncher />
          </SessionProvider>
        </OperixMotionProvider>
      </body>
    </html>
  );
}
