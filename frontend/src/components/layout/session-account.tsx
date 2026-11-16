"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronDown, KeyRound, LogOut, UserRound } from "lucide-react";
import {
  AnimatePresence,
  motion,
  useIsPresent,
  useReducedMotion,
} from "motion/react";
import {
  roleLabels,
  signOut,
  type OperixUser,
} from "@/services/browser-session";
import { useSession } from "@/features/auth/session-provider";
import { controlTransition, exitTransition } from "@/lib/motion/presets";
import styles from "./session-account.module.css";

export function SessionAccount() {
  const { user, setUser } = useSession();
  const pathname = usePathname();
  if (!user) return null;
  return (
    <AccountMenu key={pathname} user={user} onSignOut={() => setUser(null)} />
  );
}

function AccountMenu({
  user,
  onSignOut,
}: {
  user: OperixUser;
  onSignOut: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const panelId = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    function dismiss(event: PointerEvent) {
      if (event.target instanceof Node && !root.current?.contains(event.target))
        setOpen(false);
    }
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, [open]);

  async function logOut() {
    setBusy(true);
    setFailed(false);
    try {
      await signOut();
      onSignOut();
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className={styles.root}
      ref={root}
      onBlur={(event) => {
        if (
          event.relatedTarget &&
          !event.currentTarget.contains(event.relatedTarget)
        )
          setOpen(false);
      }}
      onKeyDown={(event) => {
        if (event.key !== "Escape" || !open) return;
        event.preventDefault();
        event.stopPropagation();
        setOpen(false);
        trigger.current?.focus();
      }}
    >
      <button
        ref={trigger}
        type="button"
        className={styles.trigger}
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={`Opciones de cuenta de ${user.username}`}
        onClick={() => setOpen((current) => !current)}
      >
        <span className={styles.avatar}>
          <UserRound size={17} aria-hidden="true" />
        </span>
        <span className={styles.identity}>
          <strong title={user.username}>{user.username}</strong>
          <small>{roleLabels[user.role]}</small>
        </span>
        <ChevronDown size={15} aria-hidden="true" className={styles.chevron} />
      </button>
      <div id={panelId} className={styles.panelPosition}>
        <AnimatePresence initial={false}>
          {open && (
            <AccountActions key="account-options">
              <Link href="/account" onClick={() => setOpen(false)}>
                <UserRound size={16} aria-hidden="true" /> Mi cuenta
              </Link>
              <Link
                href="/account#account-security"
                onClick={() => setOpen(false)}
              >
                <KeyRound size={16} aria-hidden="true" /> Seguridad
              </Link>
              <div className={styles.divider} />
              <button
                type="button"
                aria-disabled={busy}
                onClick={() => {
                  if (!busy) void logOut();
                }}
              >
                <LogOut size={16} aria-hidden="true" />{" "}
                {busy ? "Cerrando sesión…" : "Cerrar sesión"}
              </button>
            </AccountActions>
          )}
        </AnimatePresence>
      </div>
      {failed && (
        <p className={styles.error} role="alert">
          No se pudo cerrar la sesión. Vuelve a intentarlo.
        </p>
      )}
    </div>
  );
}

function AccountActions({ children }: { children: ReactNode }) {
  const present = useIsPresent();
  const reduceMotion = useReducedMotion();
  return (
    <motion.div
      className={styles.panel}
      inert={!present}
      initial={reduceMotion ? false : { opacity: 0.4, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={
        reduceMotion
          ? { transition: { duration: 0 } }
          : { opacity: 0, y: 3, transition: exitTransition }
      }
      transition={controlTransition}
    >
      {children}
    </motion.div>
  );
}
