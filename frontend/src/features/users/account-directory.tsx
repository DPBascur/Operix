"use client";

import { PageTitle } from "@/components/layout/page-title";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  ChevronRight,
  KeyRound,
  UserMinus,
  UserPlus,
  Users,
} from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import {
  controlTransition,
  enterTransition,
  sectionEntrance,
} from "@/lib/motion/presets";
import { Button } from "@/components/ui/button";
import { useSession } from "@/features/auth/session-provider";
import {
  apiFetch,
  roleLabels,
  type OperixUser,
} from "@/services/browser-session";

type Role = OperixUser["role"];
type Account = {
  id: number;
  username: string;
  display_name: string;
  role: Role | null;
  is_active: boolean;
  role_review_required: boolean;
  protected: boolean;
  retired?: boolean;
};

type AccountPage = { accounts: Account[]; next: number | null };
type Editor = { mode: "create" } | { mode: "edit"; account: Account };

async function directoryRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await apiFetch("/api/v1/users/" + path, {
    cache: "no-store",
    ...init,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok || !data) {
    throw new Error(data?.detail || "No se pudo completar la solicitud.");
  }
  return data as T;
}

function passwordInput(id: string) {
  return (
    <>
      <label htmlFor={id}>Contraseña</label>
      <input
        id={id}
        name="password"
        className="input"
        type="password"
        autoComplete="new-password"
        minLength={15}
        maxLength={256}
        aria-describedby={id + "-help"}
        required
      />
      <p className="field-help" id={id + "-help"}>
        Usa entre 15 y 256 caracteres. Entrégala de forma privada a la persona
        titular.
      </p>
    </>
  );
}

function AccountEditor({
  editor,
  onSaved,
  onClose,
}: {
  editor: Editor;
  onSaved: (account: Account, message: string) => void;
  onClose: () => void;
}) {
  const account = editor.mode === "edit" ? editor.account : null;
  const [pending, setPending] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState("");
  const [reset, setReset] = useState(false);
  const reactivating = Boolean(account && !account.is_active && reset);
  const [retireError, setRetireError] = useState("");
  const reduceMotion = useReducedMotion();
  const retirement = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const role = values.get("role");
    const is_active = values.get("is_active") === "true";
    const password = values.get("password");
    inFlight.current = true;
    setPending(true);
    setError("");
    try {
      const path = account
        ? account.id +
          (reactivating ? "/reactivate/" : reset ? "/password/" : "/")
        : "";
      const body = !account
        ? {
            username: values.get("username"),
            display_name: values.get("display_name"),
            role,
            is_active,
            password,
          }
        : reset
          ? { password }
          : { role, is_active };
      const updated = await directoryRequest<Account>(path, {
        signal: AbortSignal.timeout(15000),
        method: account && !reset ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      form.reset();
      onSaved(
        updated,
        reactivating
          ? "Cuenta reactivada. Debe ingresar con su nueva contraseña."
          : reset
            ? "Contraseña restablecida. Las sesiones anteriores quedaron invalidadas."
            : account
              ? "Cambios guardados."
              : "Cuenta creada.",
      );
      if (reset) setReset(false);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "No se pudo guardar la cuenta.",
      );
    } finally {
      setPending(false);
      inFlight.current = false;
    }
  }

  async function retire() {
    if (!account || inFlight.current) return;
    inFlight.current = true;
    setPending(true);
    setRetireError("");
    try {
      const updated = await directoryRequest<Account>(account.id + "/retire/", {
        method: "POST",
        signal: AbortSignal.timeout(15000),
      });
      retirement.current?.close();
      onSaved(updated, `Cuenta @${updated.username} dada de baja.`);
    } catch (cause) {
      setRetireError(
        cause instanceof Error
          ? cause.message
          : "No se pudo dar de baja la cuenta.",
      );
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  }

  return (
    <motion.section
      className="identity-panel directory-editor"
      aria-labelledby="directory-editor-title"
      initial={reduceMotion ? false : "hidden"}
      animate="visible"
      variants={sectionEntrance}
      transition={enterTransition}
    >
      <h2 id="directory-editor-title" tabIndex={-1} ref={heading}>
        {reactivating
          ? "Reactivar cuenta"
          : reset
            ? "Restablecer contraseña"
            : account
              ? "Editar cuenta"
              : "Nueva cuenta"}
      </h2>
      {account && (
        <p className="directory-selected">
          {account.display_name || account.username} · @{account.username}
        </p>
      )}
      {account?.role_review_required && !reset && (
        <p className="directory-notice">
          Esta cuenta usaba el perfil Usuario. Confirma Visualizador o asigna un
          rol operativo acorde a su función.
        </p>
      )}
      <form method="post" key={String(reset)} onSubmit={submit}>
        <fieldset disabled={pending}>
          {!account && (
            <>
              <label htmlFor="directory-username">Usuario</label>
              <input
                className="input"
                id="directory-username"
                name="username"
                autoComplete="off"
                maxLength={150}
                required
              />
              <label htmlFor="directory-display-name">Nombre visible</label>
              <input
                className="input"
                id="directory-display-name"
                name="display_name"
                autoComplete="off"
                maxLength={150}
                required
              />
            </>
          )}
          {!reset && (
            <>
              <label htmlFor="directory-role">Rol</label>
              <select
                id="directory-role"
                name="role"
                className="select-control"
                defaultValue={account?.role ?? "viewer"}
              >
                {Object.entries(roleLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <label htmlFor="directory-state">Estado</label>
              <select
                id="directory-state"
                name="is_active"
                className="select-control"
                defaultValue={String(account?.is_active ?? true)}
              >
                <option
                  value="true"
                  disabled={Boolean(account && !account.is_active)}
                >
                  Activa
                </option>
                <option value="false">Desactivada</option>
              </select>
              <p className="field-help">
                Una cuenta desactivada pierde acceso a Operix.
              </p>
            </>
          )}
          {(!account || reset) && passwordInput("directory-password")}
        </fieldset>
        {reset && (
          <p className="directory-notice">
            La operación cierra las sesiones anteriores de esta cuenta.
          </p>
        )}
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="identity-actions">
          <Button type="submit" disabled={pending}>
            {pending
              ? "Guardando…"
              : reset
                ? reactivating
                  ? "Confirmar reactivación"
                  : "Restablecer"
                : account
                  ? "Guardar cambios"
                  : "Crear cuenta"}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={pending}
            onClick={() => {
              if (reset) {
                setReset(false);
                setError("");
              } else onClose();
            }}
          >
            {reset ? "Volver" : "Cerrar"}
          </Button>
        </div>
      </form>
      {account && !reset && (
        <div className="directory-secondary-actions">
          <Button
            type="button"
            variant="ghost"
            disabled={pending}
            onClick={() => {
              setReset(true);
              setError("");
            }}
          >
            <KeyRound size={16} aria-hidden="true" />{" "}
            {account.is_active ? "Restablecer contraseña" : "Reactivar cuenta"}
          </Button>
          <Button
            variant="destructive"
            aria-haspopup="dialog"
            disabled={pending}
            onClick={() => {
              setRetireError("");
              retirement.current?.showModal();
            }}
          >
            <UserMinus size={16} aria-hidden="true" /> Dar de baja
          </Button>
          <dialog
            ref={retirement}
            className="directory-retirement surface-card"
            aria-labelledby="retirement-title"
            aria-describedby="retirement-consequences"
            onCancel={(event) => {
              if (inFlight.current) event.preventDefault();
            }}
          >
            <h3 id="retirement-title">Dar de baja a @{account.username}</h3>
            <p id="retirement-consequences">
              Se revocará el acceso y se cerrarán las sesiones de la cuenta. La
              baja es permanente en Operix, a diferencia de la desactivación
              temporal. La cuenta y sus registros históricos se conservan.
            </p>
            {retireError && (
              <p className="form-error" role="alert">
                {retireError}
              </p>
            )}
            <div className="identity-actions">
              <Button
                variant="outline"
                disabled={pending}
                onClick={() => retirement.current?.close()}
              >
                Cancelar
              </Button>
              <Button
                variant="destructive"
                loading={pending}
                onClick={() => void retire()}
              >
                {pending ? "Procesando…" : "Confirmar baja"}
              </Button>
            </div>
          </dialog>
        </div>
      )}
    </motion.section>
  );
}

export function AccountDirectory() {
  const reduceMotion = useReducedMotion();
  const { user } = useSession();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [next, setNext] = useState<number | null>(null);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [archive, setArchive] = useState(false);
  const visibleAccounts = accounts.filter((account) =>
    archive ? !account.is_active : account.is_active,
  );
  const archivedCount = accounts.filter((account) => !account.is_active).length;
  const create = useRef<HTMLButtonElement>(null);

  const load = useCallback(
    async (after?: number, signal = AbortSignal.timeout(10000)) => {
      try {
        const page = await directoryRequest<AccountPage>(
          after ? "?after=" + after : "",
          { signal },
        );
        setAccounts((current) =>
          after
            ? [
                ...current,
                ...page.accounts.filter(
                  (account) => !current.some((item) => item.id === account.id),
                ),
              ]
            : page.accounts,
        );
        setNext(page.next);
      } catch (cause) {
        if (!signal.aborted || signal.reason?.name !== "AbortError") {
          setError(
            cause instanceof Error
              ? cause.message
              : "No se pudieron cargar las cuentas.",
          );
        }
      } finally {
        if (!signal.aborted || signal.reason?.name !== "AbortError")
          setLoading(false);
      }
    },
    [],
  );

  function loadPage(after?: number) {
    setLoading(true);
    setError("");
    void load(after);
  }

  useEffect(() => {
    const controller = new AbortController();
    const signal = AbortSignal.any([
      controller.signal,
      AbortSignal.timeout(10000),
    ]);
    queueMicrotask(() => {
      if (!signal.aborted) void load(undefined, signal);
    });
    return () => controller.abort();
  }, [load]);

  return (
    <section className="page-wrap identity-page">
      <header className="identity-heading directory-heading app-page-heading">
        <div>
          <PageTitle>Cuentas de Operix</PageTitle>
          <p>Administra quién puede acceder y qué puede hacer en Operix.</p>
        </div>
        <Button
          ref={create}
          onClick={() => {
            setMessage("");
            setEditor({ mode: "create" });
          }}
        >
          <UserPlus size={17} aria-hidden="true" /> Nueva cuenta
        </Button>
      </header>
      <p className="identity-feedback" role="status">
        {message && (
          <motion.span
            key={message}
            initial={reduceMotion ? false : { opacity: 0.7 }}
            animate={{ opacity: 1 }}
            transition={controlTransition}
          >
            {message}
          </motion.span>
        )}
      </p>
      <div className="directory-grid">
        <section
          className="identity-panel directory-list"
          aria-label="Cuentas registradas"
          aria-busy={loading}
        >
          <h3>
            <Users size={18} aria-hidden="true" />{" "}
            {archive ? "Cuentas archivadas" : "Cuentas activas"}
          </h3>
          <div
            className="identity-actions"
            role="group"
            aria-label="Estado de cuentas cargadas"
          >
            <Button
              variant={archive ? "outline" : "primary"}
              aria-pressed={!archive}
              onClick={() => {
                setArchive(false);
                setEditor(null);
              }}
            >
              Activas ({accounts.length - archivedCount})
            </Button>
            <Button
              variant={archive ? "primary" : "outline"}
              aria-pressed={archive}
              onClick={() => {
                setArchive(true);
                setEditor(null);
              }}
            >
              Archivadas ({archivedCount})
            </Button>
          </div>
          {next && (
            <p className="field-help">
              Los recuentos corresponden a las cuentas cargadas.
            </p>
          )}
          {loading && !accounts.length && (
            <p role="status">Cargando cuentas…</p>
          )}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          {error && (
            <Button
              variant="outline"
              disabled={loading}
              onClick={() => loadPage(next ?? undefined)}
            >
              Reintentar
            </Button>
          )}
          {!loading && !error && !visibleAccounts.length && (
            <p>
              {next
                ? "No hay coincidencias en las cuentas cargadas."
                : archive
                  ? "No hay cuentas archivadas."
                  : "No hay cuentas activas."}
            </p>
          )}
          <motion.ul
            key={String(archive)}
            initial={reduceMotion ? false : { opacity: 0.8 }}
            animate={{ opacity: 1 }}
            transition={controlTransition}
          >
            {visibleAccounts.map((account) => {
              const self = account.username === user?.username;
              const selected =
                editor?.mode === "edit" && editor.account.id === account.id;
              return (
                <li key={account.id}>
                  <div className="directory-name">
                    <strong>{account.display_name || account.username}</strong>
                    {(account.display_name || self) && (
                      <small>
                        @{account.username}
                        {self ? " · Tu cuenta" : ""}
                      </small>
                    )}
                    <small>
                      {account.role ? roleLabels[account.role] : "Sin rol"} ·{" "}
                      {account.retired
                        ? "Dada de baja"
                        : account.is_active
                          ? "Activa"
                          : "Desactivada"}
                    </small>
                    {account.role_review_required && (
                      <span className="directory-review">
                        Revisar rol anterior
                      </span>
                    )}
                  </div>
                  {!self && !account.protected && !account.retired ? (
                    <Button
                      variant="outline"
                      size="small"
                      aria-label={"Editar " + account.username}
                      aria-pressed={selected}
                      onClick={() => {
                        setMessage("");
                        setEditor({ mode: "edit", account });
                      }}
                    >
                      Editar <ChevronRight size={15} aria-hidden="true" />
                    </Button>
                  ) : (
                    account.protected && (
                      <small className="directory-locked">
                        Cuenta de Django
                      </small>
                    )
                  )}
                </li>
              );
            })}
          </motion.ul>
          {next && !error && (
            <Button
              variant="outline"
              disabled={loading}
              onClick={() => loadPage(next)}
            >
              Cargar más
            </Button>
          )}
        </section>
        {editor && (
          <AccountEditor
            key={
              editor.mode === "edit"
                ? [
                    editor.account.id,
                    editor.account.role,
                    editor.account.is_active,
                  ].join(":")
                : "create"
            }
            editor={editor}
            onClose={() => {
              setEditor(null);
              create.current?.focus();
            }}
            onSaved={(updated, success) => {
              setAccounts((current) =>
                current.some((item) => item.id === updated.id)
                  ? current.map((item) =>
                      item.id === updated.id ? updated : item,
                    )
                  : [...current, updated],
              );
              setMessage(success);
              if (updated.retired) create.current?.focus();
              setEditor((current) => {
                if (
                  editor.mode === "edit" &&
                  current?.mode === "edit" &&
                  current.account.id === updated.id
                ) {
                  return updated.retired || updated.is_active === archive
                    ? null
                    : { mode: "edit", account: updated };
                }
                return current === editor ? null : current;
              });
            }}
          />
        )}
      </div>
    </section>
  );
}
