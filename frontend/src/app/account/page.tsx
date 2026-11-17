"use client";

import { PageTitle } from "@/components/layout/page-title";
import { useRef, useState } from "react";
import { CircleCheck, KeyRound, UserRound } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { Button } from "@/components/ui/button";
import { useSession } from "@/features/auth/session-provider";
import { changePassword, roleLabels } from "@/services/browser-session";
import { controlTransition } from "@/lib/motion/presets";

const fields = [
  {
    name: "current",
    label: "Contraseña actual",
    autocomplete: "current-password",
    max: 4096,
  },
  {
    name: "next",
    label: "Nueva contraseña",
    autocomplete: "new-password",
    max: 256,
  },
  {
    name: "confirmation",
    label: "Confirmar nueva contraseña",
    autocomplete: "new-password",
    max: 256,
  },
] as const;

export default function AccountPage() {
  const { user, setUser } = useSession();
  const reduceMotion = useReducedMotion();
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [visible, setVisible] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  return (
    <div className="page-wrap identity-page">
      <header className="identity-heading app-page-heading">
        <PageTitle>Mi cuenta</PageTitle>
        <p>Consulta tu perfil y protege el acceso a Operix.</p>
      </header>
      <div className="account-grid">
        <aside
          className="identity-panel account-profile"
          aria-label="Perfil de la cuenta"
        >
          <UserRound size={23} aria-hidden="true" />
          <h2>{user?.username}</h2>
          {user && (
            <span className="identity-role">{roleLabels[user.role]}</span>
          )}
          {user?.role_review_required && (
            <p>
              Tu cuenta anterior tiene acceso de Visualizador. Si necesitas
              volver a analizar videos, solicita al administrador que revise tu
              rol.
            </p>
          )}
        </aside>
        <section
          className="identity-panel account-security"
          aria-labelledby="account-security"
        >
          <div className="account-security-heading">
            <KeyRound size={20} aria-hidden="true" />
            <div>
              <h2 id="account-security">Seguridad</h2>
              <p>
                Al guardar una nueva contraseña, se cierran tus otras sesiones.
              </p>
            </div>
          </div>
          <form
            method="post"
            onSubmit={async (event) => {
              event.preventDefault();
              if (inFlight.current) return;
              const form = event.currentTarget;
              const data = new FormData(form);
              setError("");
              setMessage("");
              if (data.get("next") !== data.get("confirmation")) {
                setError(
                  "La confirmación debe coincidir con la nueva contraseña.",
                );
                return;
              }
              inFlight.current = true;
              setBusy(true);
              try {
                const account = await changePassword(
                  String(data.get("current")),
                  String(data.get("next")),
                  String(data.get("confirmation")),
                );
                if (account) setUser(account);
                form.reset();
                setVisible(false);
                setMessage(
                  "Contraseña actualizada. Las demás sesiones se cerrarán.",
                );
              } catch (cause) {
                setError(
                  cause instanceof Error
                    ? cause.message
                    : "No se pudo actualizar la contraseña.",
                );
              } finally {
                inFlight.current = false;
                setBusy(false);
              }
            }}
          >
            <h3>Cambiar contraseña</h3>
            {fields.map(({ name, label, autocomplete, max }) => (
              <div key={name}>
                <label htmlFor={name}>{label}</label>
                <input
                  className="input"
                  id={name}
                  name={name}
                  type={visible ? "text" : "password"}
                  autoComplete={autocomplete}
                  aria-describedby={
                    name === "next" ? "password-hint" : undefined
                  }
                  minLength={name === "current" ? undefined : 15}
                  maxLength={max}
                  required
                />
                {name === "next" && (
                  <p className="field-help" id="password-hint">
                    Usa entre 15 y 256 caracteres. Puedes elegir una frase.
                  </p>
                )}
              </div>
            ))}
            <div className="mt-4 flex flex-wrap gap-3">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setVisible(!visible)}
              >
                {visible ? "Ocultar contraseñas" : "Mostrar contraseñas"}
              </Button>
              <Button type="submit" disabled={busy}>
                {busy ? "Guardando…" : "Cambiar contraseña"}
              </Button>
            </div>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <div role="status" className="identity-feedback">
              {message && (
                <motion.p
                  className="success-message"
                  initial={reduceMotion ? false : { opacity: 0.7 }}
                  animate={{ opacity: 1 }}
                  transition={controlTransition}
                >
                  <CircleCheck size={16} aria-hidden="true" /> {message}
                </motion.p>
              )}
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
