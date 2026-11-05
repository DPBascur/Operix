"use client";
import { useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  Activity,
  ShieldCheck,
  Check,
  BarChart3,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ThemeSelector } from "@/components/ui/theme-selector";
import { signIn } from "@/services/browser-session";
import { canOpen, useSession } from "./session-provider";
import { enterTransition, revealVariants } from "@/lib/motion/presets";

export function LoginExperience() {
  const { setUser, expired } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const reduceMotion = useReducedMotion();
  return (
    <main className="login-page">
      <section className="login-form-side">
        <header>
          <Link href="/" className="login-brand" aria-label="Operix · Inicio">
            <Image
              src="/brand/operix-symbol.png"
              width={90}
              height={60}
              alt=""
              priority
            />
            <strong>OPERIX</strong>
          </Link>
          <ThemeSelector />
        </header>
        <motion.div
          className="login-form-content"
          variants={revealVariants}
          initial={reduceMotion ? false : "hidden"}
          animate="visible"
          transition={reduceMotion ? { duration: 0 } : enterTransition}
        >
          <h1>Bienvenido a Operix.</h1>
          <p>
            {expired
              ? "Tu sesión terminó. Vuelve a ingresar para continuar."
              : "Ingresa con tu cuenta."}
          </p>
          <form
            method="post"
            onSubmit={async (event) => {
              event.preventDefault();
              if (busy) return;
              const form = new FormData(event.currentTarget);
              setError(null);
              setBusy(true);
              try {
                const account = await signIn(
                  String(form.get("username")),
                  String(form.get("password")),
                );
                if (!account)
                  throw new Error("La cuenta no tiene acceso a Operix.");
                const nextValue = new URLSearchParams(
                  window.location.search,
                ).get("next");
                const next =
                  nextValue?.startsWith("/") && !nextValue.startsWith("//")
                    ? new URL(nextValue, window.location.origin)
                    : null;
                const fallback =
                  account.role === "operator" ? "/analysis" : "/";
                setUser(account);
                router.replace(
                  next &&
                    next.origin === window.location.origin &&
                    next.pathname !== "/login" &&
                    !next.pathname.startsWith("//") &&
                    canOpen(next.pathname, account.role)
                    ? next.pathname + next.search
                    : fallback,
                );
              } catch (cause) {
                setError(
                  cause instanceof Error
                    ? cause.message
                    : "No se pudo iniciar sesión.",
                );
              } finally {
                setBusy(false);
              }
            }}
          >
            <label htmlFor="login-username">Usuario</label>
            <input
              className="input"
              id="login-username"
              name="username"
              autoComplete="username"
              maxLength={150}
              required
            />
            <label htmlFor="login-password">Contraseña</label>
            <input
              className="input"
              id="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              maxLength={4096}
              required
            />
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <Button type="submit" className="login-submit" disabled={busy}>
              {busy ? "Ingresando…" : "Ingresar"} <ArrowRight size={18} />
            </Button>
          </form>
        </motion.div>
        <footer>
          Proyecto académico · Visión artificial aplicada a la prevención
          operacional
        </footer>
      </section>
      <section
        className="login-preview-side"
        aria-label="Vista animada ilustrativa de Operix"
      >
        <motion.div
          className="preview-intro"
          variants={revealVariants}
          initial={reduceMotion ? false : "hidden"}
          animate="visible"
          transition={reduceMotion ? { duration: 0 } : enterTransition}
        >
          <h2>
            Del video al contexto.
            <br />
            Del contexto a la revisión.
          </h2>
          <p>Una misma plataforma para observar, analizar y comprender.</p>
        </motion.div>
        <motion.div
          className="live-preview"
          initial={reduceMotion ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={
            reduceMotion ? { duration: 0 } : { ...enterTransition, delay: 0.08 }
          }
        >
          <div className="mini-topbar">
            <strong>OPERIX</strong>
            <span>
              <i />
              Vista ilustrativa
            </span>
          </div>
          <div className="mini-content">
            <aside>
              <Activity size={18} />
              <BarChart3 size={18} />
              <ShieldCheck size={18} />
            </aside>
            <div className="mini-panels">
              <div className="mini-heading">
                <span>Resumen operacional</span>
                <span>Octubre</span>
              </div>
              <div className="mini-kpis">
                <div>
                  <small>Eventos demo</small>
                  <strong>64</strong>
                </div>
                <div>
                  <small>Zonas</small>
                  <strong>4</strong>
                </div>
                <div>
                  <small>En revisión</small>
                  <strong>12</strong>
                </div>
              </div>
              <div className="mini-chart" aria-hidden="true">
                {[30, 52, 43, 68, 47, 80, 56, 65, 39, 58, 35, 45].map(
                  (v, i) => (
                    <span
                      key={i}
                      style={{ height: `${v}%`, animationDelay: `${i * 70}ms` }}
                    />
                  ),
                )}
              </div>
              <div className="mini-notification">
                <span className="mini-check">
                  <Check size={17} />
                </span>
                <div>
                  <strong>Evidencia lista para revisión</strong>
                  <small>El criterio humano completa el análisis.</small>
                </div>
              </div>
            </div>
          </div>
        </motion.div>
        <div className="preview-caption">
          <span>Detección</span>
          <ArrowRight size={14} />
          <span>Contexto</span>
          <ArrowRight size={14} />
          <span>Evidencia</span>
        </div>
      </section>
    </main>
  );
}
