"use client";

import {
  Activity,
  BarChart3,
  CalendarClock,
  Clapperboard,
  House,
  LayoutGrid,
  Map,
  PanelLeftClose,
  PanelLeftOpen,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  type LucideIcon,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutGroup, motion, useReducedMotion } from "motion/react";
import {
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { ThemeSelector } from "@/components/ui/theme-selector";
import { MobileNavigation } from "./mobile-navigation";
import { ApiStatus } from "@/components/ui/api-status";
import { SessionAccount } from "./session-account";
import { canOpen, useSession } from "@/features/auth/session-provider";
import { calmSpring, enterTransition, sectionTransition } from "@/lib/motion/presets";

import styles from "./desktop-sidebar.module.css";

const sidebarKey = "operix-sidebar";
const sidebarPreferenceEvent = "operix:sidebar-preference";
let temporaryPreference: boolean | undefined;

function getSidebarPreference() {
  try {
    return localStorage.getItem(sidebarKey) === "compact";
  } catch {
    return temporaryPreference ?? false;
  }
}

function subscribeToSidebarPreference(update: () => void) {
  window.addEventListener(sidebarPreferenceEvent, update);
  window.addEventListener("storage", update);
  return () => {
    window.removeEventListener(sidebarPreferenceEvent, update);
    window.removeEventListener("storage", update);
  };
}

function changeSidebarPreference(compact: boolean) {
  temporaryPreference = compact;
  try {
    localStorage.setItem(sidebarKey, compact ? "compact" : "expanded");
  } catch {
    // The current session still supports collapsing when storage is unavailable.
  }
  window.dispatchEvent(new Event(sidebarPreferenceEvent));
}

const navigationGroups: {
  label: string;
  items: { href: string; label: string; icon: LucideIcon }[];
}[] = [
  {
    label: "Operación",
    items: [
      { href: "/", label: "Resumen", icon: House },
      { href: "/sources", label: "Fuentes", icon: Clapperboard },
      { href: "/monitoring", label: "Monitoreo", icon: LayoutGrid },
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
      {
        href: "/admin/camera-lab",
        label: "Control de cámaras",
        icon: SlidersHorizontal,
      },
    ],
  },
];

const routeNames: Record<string, string> = {
  "/": "Centro operativo",
  "/sources": "Fuentes",
  "/monitoring": "Centro de monitoreo",
  "/analysis": "Análisis de video",
  "/events": "Eventos",
  "/rules": "Reglas",
  "/zones": "Zonas",
  "/indicators": "Indicadores",
  "/users": "Usuarios y roles",
  "/admin/camera-lab": "Control del laboratorio",
  "/account": "Mi cuenta",
  "/experience": "Cómo funciona Operix",
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

type NavigationHint = { label: string; target: HTMLElement };

function SidebarTooltip({ label, target }: NavigationHint) {
  const tooltip = useRef<HTMLSpanElement>(null);

  useLayoutEffect(() => {
    const element = tooltip.current;
    if (!element) return;
    const place = () => {
      const bounds = target.getBoundingClientRect();
      element.style.left = `${bounds.right + 12}px`;
      element.style.top = `${bounds.top + bounds.height / 2}px`;
    };
    place();

    const sidebar = target.closest("aside");
    const observer = new ResizeObserver(place);
    observer.observe(target);
    if (sidebar) observer.observe(sidebar);
    window.addEventListener("scroll", place, true);
    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", place, true);
    };
  }, [target]);

  return createPortal(
    <span
      ref={tooltip}
      className={styles.tooltip}
      role="tooltip"
      aria-hidden="true"
    >
      {label}
    </span>,
    document.body,
  );
}

function Navigation({
  activePath,
  scope,
  compact = false,
}: {
  activePath: string;
  scope: string;
  compact?: boolean;
}) {
  const { user } = useSession();
  const reduceMotion = useReducedMotion();
  const [hint, setHint] = useState<NavigationHint | null>(null);
  function trackHint(target: HTMLElement, label: string) {
    if (scope === "desktop-nav") setHint({ label, target });
  }
  const groups = navigationGroups
    .map((group) => ({
      ...group,
      items: group.items.filter(({ href }) => user && canOpen(href, user.role)),
    }))
    .filter((group) => group.items.length);
  return (
    <LayoutGroup id={scope}>
      <nav
        aria-label="Navegación principal"
        className="navigation-groups"
        onKeyDown={(event) => {
          if (event.key === "Escape") setHint(null);
        }}
      >
        {groups.map((group) => (
          <section className="navigation-group" key={group.label}>
            <h2 className="navigation-group-label">{group.label}</h2>
            <ul className="space-y-0.5">
              {group.items.map(({ href, label, icon: Icon }) => (
                <li key={href}>
                  <Link
                    aria-current={activePath === href ? "page" : undefined}
                    className="navigation-item"
                    href={href}
                    onMouseEnter={(event) => trackHint(event.currentTarget, label)}
                    onFocus={(event) => trackHint(event.currentTarget, label)}
                    onMouseLeave={(event) => { if (document.activeElement !== event.currentTarget) setHint(null); }}
                    onBlur={(event) => { if (!event.currentTarget.matches(":hover")) setHint(null); }}
                    onClick={() => setHint(null)}
                  >
                    {activePath === href && (
                      <motion.span
                        aria-hidden="true"
                        className="navigation-highlight"
                        layoutId={reduceMotion ? undefined : "active-route"}
                        transition={calmSpring}
                        initial={false}
                      />
                    )}
                    <span aria-hidden="true" className="navigation-glyph">
                      <Icon
                        className="navigation-icon"
                        size={16}
                        strokeWidth={1.8}
                      />
                    </span>
                    <span className="navigation-label">{label}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </nav>
      {compact && hint && <SidebarTooltip {...hint} />}
    </LayoutGroup>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const reduceMotion = useReducedMotion();
  const compact = useSyncExternalStore(subscribeToSidebarPreference, getSidebarPreference, () => null);
  if (pathname === "/login") return children;
  const activePath =
    pathname === "/dashboard"
      ? "/"
      : pathname.startsWith("/admin/")
        ? pathname
        : "/" + (pathname.split("/")[1] || "");
  const routeTitle = routeNames[activePath] ?? "Operix";
  const width =
    activePath === "/account"
      ? "compact"
      : ["/analysis", "/events", "/indicators", "/experience", "/"].includes(
            activePath,
          )
        ? "wide"
        : "standard";

  return (
    <motion.div
      className={`app-shell refresh-shell min-h-screen bg-background text-foreground ${styles.shell}`}
      data-sidebar={compact == null ? undefined : compact ? "compact" : "expanded"}
      initial={false}
      animate={compact == null ? undefined : { "--live-sidebar-width": compact ? "4.625rem" : "15rem" }}
      transition={reduceMotion ? { duration: 0 } : sectionTransition}
    >
      <a className="skip-link" href="#main-content">
        Saltar al contenido
      </a>
      <aside id="operix-sidebar" className={`app-sidebar fixed inset-y-0 left-0 z-30 flex-col bg-[var(--sidebar)] ${styles.sidebar}`}>
        <div className={styles.brandHeader}>
          <Brand onDark showDescriptor />
          <button
            type="button"
            aria-label={
              compact ? "Expandir barra lateral" : "Contraer barra lateral"
            }
            aria-expanded={compact == null ? undefined : !compact}
            aria-controls="operix-sidebar"
            className={styles.collapse}
            onClick={() => changeSidebarPreference(!compact)}
          >
            {compact ? (
              <PanelLeftOpen size={17} aria-hidden="true" />
            ) : (
              <PanelLeftClose size={17} aria-hidden="true" />
            )}
          </button>
        </div>
        <div className={styles.navigationViewport}>
          <Navigation activePath={activePath} scope="desktop-nav" compact={compact ?? false} />
        </div>
        <div className="sidebar-footer">
          <SessionAccount />
        </div>
      </aside>
      <div className="app-content min-w-0">
        <header className="app-header sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-border bg-surface/95 px-4 backdrop-blur-sm sm:px-5 lg:px-6">
          <div className="mobile-header-context lg:hidden">
            <Brand />
            <span className="mobile-route-name">{routeTitle}</span>
          </div>
          <span className="route-title text-sm font-semibold tracking-[-0.01em]">
            {routeTitle}
          </span>
          <div className="flex items-center gap-2">
            <ApiStatus />
            <ThemeSelector />
            <MobileNavigation>
              <Navigation activePath={activePath} scope="mobile-nav" />
              <div className="sidebar-footer">
                <SessionAccount />
              </div>
            </MobileNavigation>
          </div>
        </header>
        <main
          id="main-content"
          className="app-page"
          data-width={width}
          tabIndex={-1}
        >
          <motion.div
            key={pathname}
            className="app-page-body"
            initial={
              reduceMotion ||
              activePath === "/analysis" ||
              activePath === "/experience"
                ? false
                : { opacity: 0.84, y: 4 }
            }
            animate={{ opacity: 1, y: 0 }}
            transition={enterTransition}
          >
            {children}
          </motion.div>
        </main>
      </div>
    </motion.div>
  );
}
