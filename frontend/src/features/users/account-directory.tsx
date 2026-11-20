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
  Search,
  UserMinus,
  UserPlus,
  X,
} from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { OperixScanLoader } from "@/components/ui/operix-scan-loader";
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
import styles from "./account-directory.module.css";

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

function searchKey(value: string) {
  return value.toLocaleLowerCase("es").normalize("NFD").replace(/\p{M}/gu, "");
}

function initials(account: Account) {
  return (account.display_name.trim() || account.username)
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => Array.from(part)[0])
    .join("")
    .toLocaleUpperCase("es");
}

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
  message,
  onSaved,
  onClose,
}: {
  editor: Editor;
  message: string;
  onSaved: (account: Account, message: string) => void;
  onClose: () => void;
}) {
  const account = editor.mode === "edit" ? editor.account : null;
  const [pending, setPending] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState("");
  const [reset, setReset] = useState(false);
  const [activeState, setActiveState] = useState(
    String(account?.is_active ?? true),
  );
  const deactivating = account?.is_active && activeState === "false" && !reset;
  const reactivating = Boolean(account && !account.is_active && reset);
  const [retiring, setRetiring] = useState(false);
  const reduceMotion = useReducedMotion();
  const panel = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const dialog = panel.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  useEffect(() => heading.current?.focus(), [reset, retiring]);

  function cancel() {
    if (inFlight.current) return;
    if (retiring) {
      setRetiring(false);
      setError("");
    } else {
      onClose();
    }
  }

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
    setError("");
    try {
      const updated = await directoryRequest<Account>(account.id + "/retire/", {
        method: "POST",
        signal: AbortSignal.timeout(15000),
      });
      onSaved(updated, `Cuenta @${updated.username} dada de baja.`);
    } catch (cause) {
      setError(
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
    <dialog
      ref={panel}
      className={styles.drawer}
      aria-labelledby="directory-editor-title"
      aria-describedby={retiring ? "retirement-consequences" : undefined}
      onKeyDown={(event) => {
        if (event.key !== "Escape") return;
        event.preventDefault();
        event.stopPropagation();
        if (!event.repeat) cancel();
      }}
      onCancel={(event) => {
        event.preventDefault();
        cancel();
      }}
    >
      <motion.div
        className={styles.editor}
        initial={reduceMotion ? false : "hidden"}
        animate="visible"
        variants={sectionEntrance}
        transition={enterTransition}
      >
        <header className={styles.editorHeading}>
          <div>
            <h2 id="directory-editor-title" tabIndex={-1} ref={heading}>
              {retiring
                ? "Dar de baja"
                : reactivating
                  ? "Reactivar cuenta"
                  : reset
                    ? "Restablecer contraseña"
                    : account
                      ? "Editar cuenta"
                      : "Nueva cuenta"}
            </h2>
            {account ? (
              <p className="directory-selected">
                {account.display_name || account.username} · @{account.username}
              </p>
            ) : (
              <p>Asigna un rol y define la contraseña inicial.</p>
            )}
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label={retiring ? "Cancelar baja" : "Cerrar editor"}
            disabled={pending}
            onClick={cancel}
          >
            <X size={19} aria-hidden="true" />
          </Button>
        </header>
        {retiring ? (
          <div className={styles.retirement}>
            <p id="retirement-consequences">
              La baja revoca el acceso de forma permanente y cierra las
              sesiones. La cuenta y sus registros históricos se conservan.
            </p>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <div className="identity-actions">
              <Button variant="outline" disabled={pending} onClick={cancel}>
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
          </div>
        ) : (
          <>
            {account?.role_review_required && !reset && (
              <p className="directory-notice">
                Esta cuenta usaba el perfil Usuario. Confirma Visualizador o
                asigna un rol operativo acorde a su función.
              </p>
            )}
            <form
              method="post"
              key={String(reset)}
              onSubmit={submit}
              className={styles.form}
            >
              <fieldset disabled={pending}>
                {!account && (
                  <div className={styles.fieldPair}>
                    <div>
                      <label htmlFor="directory-username">Usuario</label>
                      <input
                        className="input"
                        id="directory-username"
                        name="username"
                        autoComplete="off"
                        maxLength={150}
                        required
                      />
                    </div>
                    <div>
                      <label htmlFor="directory-display-name">
                        Nombre visible
                      </label>
                      <input
                        className="input"
                        id="directory-display-name"
                        name="display_name"
                        autoComplete="off"
                        maxLength={150}
                        required
                      />
                    </div>
                  </div>
                )}
                {!reset && (
                  <>
                    <div className={styles.fieldPair}>
                      <div>
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
                      </div>
                      <div>
                        <label htmlFor="directory-state">Estado</label>
                        <select
                          id="directory-state"
                          name="is_active"
                          className="select-control"
                          value={activeState}
                          onChange={(event) =>
                            setActiveState(event.target.value)
                          }
                        >
                          <option
                            value="true"
                            disabled={Boolean(account && !account.is_active)}
                          >
                            Activa
                          </option>
                          <option value="false">Desactivada</option>
                        </select>
                      </div>
                    </div>
                    {deactivating && (
                      <label className={styles.confirmation}>
                        <input type="checkbox" required />
                        <span>
                          Confirmo que @{account.username} perderá el acceso a
                          Operix.
                        </span>
                      </label>
                    )}
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
              {message && (
                <p className={styles.feedback} role="status">
                  {message}
                </p>
              )}
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
                  {account.is_active
                    ? "Restablecer contraseña"
                    : "Reactivar cuenta"}
                </Button>
                <Button
                  variant="destructive"
                  disabled={pending}
                  onClick={() => {
                    setError("");
                    setRetiring(true);
                  }}
                >
                  <UserMinus size={16} aria-hidden="true" /> Dar de baja
                </Button>
              </div>
            )}
          </>
        )}
      </motion.div>
    </dialog>
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
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const query = searchKey(search.trim());
  const visibleAccounts = accounts.filter(
    (account) =>
      account.is_active !== archive &&
      (!role || account.role === role) &&
      searchKey(`${account.display_name} @${account.username}`).includes(query),
  );
  const archivedCount = accounts.filter((account) => !account.is_active).length;
  const showCounts = accounts.length > 0 || (!loading && !error);
  const create = useRef<HTMLButtonElement>(null);
  const opener = useRef<HTMLButtonElement>(null);

  function closeEditor() {
    setEditor(null);
    requestAnimationFrame(() => {
      const target = opener.current;
      (target?.isConnected ? target : create.current)?.focus();
    });
  }

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
    <section className={styles.directory}>
      <header className={styles.heading}>
        <div>
          <PageTitle>Cuentas de Operix</PageTitle>
          <p>Administra quién puede acceder y qué puede hacer en Operix.</p>
        </div>
        <Button
          ref={create}
          aria-haspopup="dialog"
          onClick={(event) => {
            opener.current = event.currentTarget;
            setMessage("");
            setEditor({ mode: "create" });
          }}
        >
          <UserPlus size={17} aria-hidden="true" /> Nueva cuenta
        </Button>
      </header>
      <p className={styles.feedback} role="status">
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
      <section
        className={styles.listPanel}
        aria-labelledby="directory-list-title"
        aria-busy={loading}
      >
        <div className={styles.listHeader}>
          <h2 id="directory-list-title">Directorio de cuentas</h2>
          <div
            className={styles.tabs}
            role="group"
            aria-label="Estado de la cuenta"
          >
            <button
              type="button"
              aria-pressed={!archive}
              onClick={() => setArchive(false)}
            >
              Activas{" "}
              {showCounts && <span>{accounts.length - archivedCount}</span>}
            </button>
            <button
              type="button"
              aria-pressed={archive}
              onClick={() => setArchive(true)}
            >
              Archivadas {showCounts && <span>{archivedCount}</span>}
            </button>
          </div>
          <div className={styles.filters}>
            <label>
              Buscar cuenta
              <span className={styles.search}>
                <Search size={16} aria-hidden="true" />
                <input
                  className="input"
                  type="search"
                  value={search}
                  placeholder="Nombre o usuario"
                  onChange={(event) => setSearch(event.target.value)}
                />
              </span>
            </label>
            <label>
              Rol
              <select
                className="select-control"
                value={role}
                onChange={(event) => setRole(event.target.value)}
              >
                <option value="">Todos los roles</option>
                {Object.entries(roleLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {next !== null && (
            <p className={styles.listNote}>
              Los filtros y recuentos se aplican a las cuentas cargadas.
            </p>
          )}
        </div>
        {loading && !accounts.length && (
          <OperixScanLoader
            className={styles.listState}
            size="small"
            message="Cargando cuentas…"
          />
        )}
        {error && (
          <div className={styles.listState}>
            <p className="form-error" role="alert">
              {error}
            </p>
            <Button
              variant="outline"
              disabled={loading}
              onClick={() => loadPage(next ?? undefined)}
            >
              Reintentar
            </Button>
          </div>
        )}
        {!loading && !error && !visibleAccounts.length && (
          <div className={styles.listState} role="status">
            <strong>
              {query || role || next !== null
                ? "No hay cuentas que coincidan"
                : archive
                  ? "No hay cuentas archivadas"
                  : "No hay cuentas activas"}
            </strong>
            {(query || role) && (
              <Button
                variant="outline"
                onClick={() => {
                  setSearch("");
                  setRole("");
                }}
              >
                Limpiar filtros
              </Button>
            )}
          </div>
        )}
        {visibleAccounts.length > 0 && (
          <>
            <div className={styles.columns} aria-hidden="true">
              <span>Usuario</span>
              <span>Rol</span>
              <span>Estado</span>
              <span>Acciones</span>
            </div>
            <ul className={styles.accounts} role="list">
              {visibleAccounts.map((account) => {
                const self = account.username === user?.username;
                return (
                  <li key={account.id} className={styles.account}>
                    <div className={styles.identity}>
                      <span className={styles.avatar} aria-hidden="true">
                        {initials(account)}
                      </span>
                      <div>
                        <strong>
                          {account.display_name || account.username}
                        </strong>
                        <small>
                          @{account.username}
                          {self ? " · Tu cuenta" : ""}
                        </small>
                      </div>
                    </div>
                    <div className={styles.role}>
                      {account.role ? roleLabels[account.role] : "Sin rol"}
                      {account.role_review_required && (
                        <small>Revisar rol anterior</small>
                      )}
                    </div>
                    <span
                      className={styles.status}
                      data-active={account.is_active}
                    >
                      {account.retired
                        ? "Dada de baja"
                        : account.is_active
                          ? "Activa"
                          : "Desactivada"}
                    </span>
                    <div className={styles.rowAction}>
                      {!self && !account.protected && !account.retired ? (
                        <Button
                          variant="outline"
                          aria-label={"Editar " + account.username}
                          aria-haspopup="dialog"
                          onClick={(event) => {
                            opener.current = event.currentTarget;
                            setMessage("");
                            setEditor({ mode: "edit", account });
                          }}
                        >
                          Editar <ChevronRight size={15} aria-hidden="true" />
                        </Button>
                      ) : (
                        account.protected && <small>Cuenta de Django</small>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </>
        )}
        {next !== null && !error && (
          <div className={styles.pagination}>
            <Button
              variant="outline"
              loading={loading}
              onClick={() => loadPage(next)}
            >
              {loading ? "Cargando…" : "Cargar más"}
            </Button>
          </div>
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
          message={message}
          onClose={closeEditor}
          onSaved={(updated, success) => {
            setAccounts((current) =>
              current.some((item) => item.id === updated.id)
                ? current.map((item) =>
                    item.id === updated.id ? updated : item,
                  )
                : [...current, updated],
            );
            setMessage(success);
            if (
              editor.mode === "create" ||
              updated.retired ||
              updated.is_active === archive
            ) {
              closeEditor();
            } else {
              setEditor({ mode: "edit", account: updated });
            }
          }}
        />
      )}
    </section>
  );
}
