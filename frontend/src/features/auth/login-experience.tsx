"use client";
import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { ArrowRight, Eye, EyeOff } from "lucide-react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ThemeSelector } from "@/components/ui/theme-selector";
import { signIn } from "@/services/browser-session";
import { canOpen, useSession } from "./session-provider";

import { ObservationStory } from "@/features/experience/observation-story";
import styles from "./login-form.module.css";

export function LoginExperience() {
  const { setUser, expired } = useSession();
  const [busy, setBusy] = useState(false);
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  return (
    <main className="login-page">
      <section className={`login-form-side ${styles.panel}`}>
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
        <div className={`login-form-content ${styles.content}`}>
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
              setPasswordVisible(false);
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
                    ? URL.parse(nextValue, window.location.origin)
                    : null;
                const fallback =
                  account.role === "viewer" ? "/indicators" : "/";
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
            <div className="login-password-field">
              <input
                className="input"
                id="login-password"
                name="password"
                type={passwordVisible ? "text" : "password"}
                autoComplete="current-password"
                maxLength={4096}
                required
              />
              <button
                type="button"
                className="login-password-toggle"
                aria-label={
                  passwordVisible ? "Ocultar contraseña" : "Mostrar contraseña"
                }
                aria-controls="login-password"
                onClick={() => setPasswordVisible((visible) => !visible)}
              >
                {passwordVisible ? (
                  <EyeOff size={19} aria-hidden="true" />
                ) : (
                  <Eye size={19} aria-hidden="true" />
                )}
              </button>
            </div>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <Button type="submit" className="login-submit" loading={busy}>
              {busy ? "Ingresando…" : "Ingresar"}
              {!busy && <ArrowRight size={18} aria-hidden="true" />}
            </Button>
          </form>
          <details className="login-recovery">
            <summary>Recuperar contraseña</summary>
            <p>
              Solicita el restablecimiento de tu contraseña al administrador de
              Operix.
            </p>
          </details>
          <footer>
            Proyecto académico · Visión artificial aplicada a la prevención
            operacional
          </footer>
        </div>
      </section>
      <section className="login-preview-side" aria-label="Cómo funciona Operix">
        <ObservationStory login />
      </section>
    </main>
  );
}
