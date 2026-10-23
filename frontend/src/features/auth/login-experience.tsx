"use client";
import { useState } from "react";
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
import { useDemoUsers, signInDemo } from "@/services/demo/users-store";
import { roles, resolveActiveUser } from "@/services/demo/user-model";

export function LoginExperience() {
  const { users, error: storageError } = useDemoUsers();
  const [account, setAccount] = useState("demo-safety");
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const chosenAccount = resolveActiveUser(users, account);
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
        <div className="login-form-content">
          <span className="source-indicator">Acceso demostrativo local</span>
          <h1>
            La prevención empieza
            <br />
            con una mejor mirada.
          </h1>
          <p>
            Explore el espacio de trabajo de Operix con una cuenta de ejemplo.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              try {
                signInDemo(chosenAccount);
                router.push("/");
              } catch (cause) {
                setError(
                  cause instanceof Error
                    ? cause.message
                    : "No se pudo abrir la sesión demo.",
                );
              }
            }}
          >
            <label htmlFor="demo-account">Perfil de acceso</label>
            <select
              id="demo-account"
              value={chosenAccount}
              onChange={(e) => setAccount(e.target.value)}
              className="input"
            >
              {users
                .filter((u) => u.active)
                .map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name} · {roles[u.role]}
                  </option>
                ))}
            </select>
            <p className="field-help">
              No introduzca contraseñas ni credenciales reales.
            </p>
            {(error || storageError) && (
              <p className="form-error" role="alert">
                {error || storageError}
              </p>
            )}
            <Button
              type="submit"
              className="login-submit"
              disabled={!chosenAccount}
            >
              Entrar a la demostración <ArrowRight size={18} />
            </Button>
          </form>
          <div className="login-disclosure">
            <ShieldCheck size={19} />
            <p>
              Esta sesión solo cambia la experiencia visual en este navegador.
              No autentica contra el servidor ni protege las rutas o la API.
            </p>
          </div>
          <Link className="text-link" href="/sources">
            Continuar al análisis sin sesión <ArrowRight size={15} />
          </Link>
        </div>
        <footer>
          Proyecto académico · Visión artificial aplicada a la prevención
          operacional
        </footer>
      </section>
      <section
        className="login-preview-side"
        aria-label="Vista animada ilustrativa de Operix"
      >
        <div className="preview-intro">
          <h2>
            Del video al contexto.
            <br />
            Del contexto a la revisión.
          </h2>
          <p>Una misma plataforma para observar, analizar y comprender.</p>
        </div>
        <div className="live-preview">
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
        </div>
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
