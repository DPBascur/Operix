import {
  Activity,
  BarChart3,
  CalendarClock,
  House,
  Map,
  ShieldCheck,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { ThemeSelector } from "@/components/ui/theme-selector";
import { mockCurrentUser } from "@/mocks/ui-data";
import { MobileNavigation } from "./mobile-navigation";

const navigationItems: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/", label: "Dashboard", icon: House },
  { href: "/analysis", label: "Análisis", icon: Activity },
  { href: "/events", label: "Eventos", icon: CalendarClock },
  { href: "/rules", label: "Reglas", icon: ShieldCheck },
  { href: "/zones", label: "Zonas", icon: Map },
  { href: "/indicators", label: "Indicadores", icon: BarChart3 },
];

function Brand() {
  return (
    <Link
      className="flex shrink-0 items-center gap-1.5 lg:gap-2"
      href="/"
      aria-label="Operix · Inicio"
    >
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
      <span className="text-base font-bold tracking-[0.1em] text-foreground">
        OPERIX
      </span>
    </Link>
  );
}
function Navigation({ activePath }: { activePath: string }) {
  return (
    <nav aria-label="Navegación principal">
      <ul className="space-y-1.5">
        {navigationItems.map(({ href, label, icon: Icon }) => (
          <li key={href}>
            <Link
              aria-current={activePath === href ? "page" : undefined}
              className={`navigation-item flex min-h-11 items-center gap-3 rounded-control px-3 py-2.5 text-sm font-medium ${activePath === href ? "text-accent" : "text-text-secondary hover:bg-brand-accent/5 hover:text-primary"}`}
              href={href}
            >
              <Icon aria-hidden="true" className="navigation-icon" size={19} />
              <span>{label}</span>
            </Link>
          </li>
        ))}
      </ul>
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
  const isAnalysis = activePath === "/analysis";
  const contextLabel = isAnalysis ? "Análisis local" : "Datos de desarrollo";
  return (
    <div className="app-shell min-h-screen bg-surface-muted text-foreground">
      <a className="skip-link" href="#main-content">
        Saltar al contenido
      </a>
      <aside className="app-sidebar fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-border bg-surface px-5 py-6 lg:flex">
        <Brand />
        <div className="mt-8">
          <Navigation activePath={activePath} />
        </div>
        <div className="mt-auto flex items-center gap-3 border-t border-border px-1 pt-5">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-surface-muted text-text-secondary">
            <UserRound size={19} aria-hidden="true" />
          </span>
          <span>
            <span className="block text-sm font-semibold">
              {isAnalysis ? "Sesión local" : mockCurrentUser.displayName}
            </span>
            <span className="block text-xs text-text-secondary">
              {isAnalysis
                ? "Motor de Operix"
                : `${mockCurrentUser.role} · Mock`}
            </span>
          </span>
        </div>
      </aside>
      <div className="min-w-0 lg:ml-64">
        <header className="app-header sticky top-0 z-20 flex min-h-18 items-center justify-between gap-2 border-b border-border bg-surface px-4 py-2 sm:px-6 lg:px-8">
          <div className="lg:hidden">
            <Brand />
          </div>
          <span className="hidden text-xs font-medium text-text-secondary lg:inline-flex">
            {contextLabel}
          </span>
          <div className="flex items-center gap-2 sm:gap-3">
            <ThemeSelector />
            <span className="hidden text-xs text-text-secondary sm:inline-flex lg:hidden">
              {contextLabel}
            </span>
            <MobileNavigation>
              <Navigation activePath={activePath} />
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
