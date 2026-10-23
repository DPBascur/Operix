import {
  Activity,
  BarChart3,
  CalendarClock,
  Clapperboard,
  House,
  Map,
  ShieldCheck,
  Users,
  type LucideIcon,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { ThemeSelector } from "@/components/ui/theme-selector";
import { MobileNavigation } from "./mobile-navigation";
import { ApiStatus } from "@/components/ui/api-status";
import { DemoAccount } from "./demo-account";

const navigationGroups: {
  label: string;
  items: { href: string; label: string; icon: LucideIcon }[];
}[] = [
  {
    label: "Operación",
    items: [
      { href: "/", label: "Resumen", icon: House },
      { href: "/sources", label: "Fuentes", icon: Clapperboard },
      { href: "/analysis", label: "Análisis", icon: Activity },
      { href: "/events", label: "Eventos", icon: CalendarClock },
    ],
  },
  {
    label: "Gestión",
    items: [
      { href: "/rules", label: "Reglas", icon: ShieldCheck },
      { href: "/zones", label: "Zonas", icon: Map },
      { href: "/indicators", label: "Indicadores", icon: BarChart3 },
      { href: "/users", label: "Usuarios", icon: Users },
    ],
  },
];

const routeNames: Record<string, string> = {
  "/": "Centro operativo",
  "/sources": "Fuentes",
  "/analysis": "Análisis de video",
  "/events": "Eventos",
  "/rules": "Reglas",
  "/zones": "Zonas",
  "/indicators": "Indicadores",
  "/users": "Usuarios y roles",
};

function Brand({
  onDark = false,
  showDescriptor = false,
}: {
  onDark?: boolean;
  showDescriptor?: boolean;
}) {
  return (
    <Link className="brand" href="/" aria-label="Operix · Inicio">
      <span className="brand-symbol" aria-hidden="true">
        <Image
          src="/brand/operix-symbol.png"
          alt=""
          width={1536}
          height={1024}
          className="h-full w-full object-contain"
          priority
        />
      </span>
      <span className="brand-copy">
        <span
          className={`brand-name ${onDark ? "text-[var(--sidebar-foreground)]" : "text-foreground"}`}
        >
          OPERIX
        </span>
        {showDescriptor && (
          <span className="brand-descriptor">
            Análisis preventivo operacional
          </span>
        )}
      </span>
    </Link>
  );
}

function Navigation({ activePath }: { activePath: string }) {
  return (
    <nav aria-label="Navegación principal" className="navigation-groups">
      {navigationGroups.map((group) => (
        <section className="navigation-group" key={group.label}>
          <h2 className="navigation-group-label">{group.label}</h2>
          <ul className="space-y-0.5">
            {group.items.map(({ href, label, icon: Icon }) => (
              <li key={href}>
                <Link
                  aria-current={activePath === href ? "page" : undefined}
                  className="navigation-item"
                  href={href}
                >
                  <Icon
                    aria-hidden="true"
                    className="navigation-icon"
                    size={16}
                    strokeWidth={1.8}
                  />
                  <span>{label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </nav>
  );
}

export function AppShell({
  activePath,
  children,
}: {
  activePath: string;
  children: ReactNode;
}) {
  return (
    <div className="app-shell refresh-shell min-h-screen bg-background text-foreground">
      <a className="skip-link" href="#main-content">
        Saltar al contenido
      </a>
      <aside className="app-sidebar fixed inset-y-0 left-0 z-30 flex-col bg-[var(--sidebar)]">
        <div className="brand-lockup">
          <Brand onDark showDescriptor />
        </div>
        <div className="mt-7">
          <Navigation activePath={activePath} />
        </div>
        <div className="sidebar-footer">
          <DemoAccount />
          <div className="sidebar-appearance">
            <span>Apariencia</span>
            <ThemeSelector />
          </div>
        </div>
      </aside>
      <div className="app-content min-w-0">
        <header className="app-header sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-border bg-surface/95 px-4 backdrop-blur-sm sm:px-5 lg:px-6">
          <div className="mobile-header-context lg:hidden">
            <Brand />
            <span className="mobile-route-name">{routeNames[activePath]}</span>
          </div>
          <h1 className="route-title text-sm font-semibold tracking-[-0.01em]">
            {routeNames[activePath]}
          </h1>
          <div className="flex items-center gap-2">
            <ApiStatus />
            <MobileNavigation>
              <Navigation activePath={activePath} />
              <div className="sidebar-footer">
                <DemoAccount />
                <div className="sidebar-appearance">
                  <span>Apariencia</span>
                  <ThemeSelector />
                </div>
              </div>
            </MobileNavigation>
          </div>
        </header>
        <main id="main-content" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
