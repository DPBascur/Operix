"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { useSession } from "@/features/auth/session-provider";
import { changePassword } from "@/services/browser-session";

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
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [visible, setVisible] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  return (
    <main className="page-wrap">
      <h1>Mi cuenta</h1>
      <p>{user?.username}</p>
      <section aria-labelledby="account-security">
        <h2 id="account-security">Seguridad</h2>
        <form
          className="login-form-content !py-6"
          method="post"
          onSubmit={async (event) => {
            event.preventDefault();
            if (inFlight.current) return;
            const form = event.currentTarget;
            const data = new FormData(form);
            setError("");
            setMessage("");
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
          <p id="password-hint">
            Usa entre 15 y 256 caracteres. Puedes usar una frase.
          </p>
          {fields.map(({ name, label, autocomplete, max }) => (
            <div key={name}>
              <label htmlFor={name}>{label}</label>
              <input
                className="input"
                id={name}
                name={name}
                type={visible ? "text" : "password"}
                autoComplete={autocomplete}
                aria-describedby={name === "next" ? "password-hint" : undefined}
                maxLength={max}
                required
              />
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
          <p role="status">{message}</p>
        </form>
      </section>
    </main>
  );
}
