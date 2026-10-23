"use client";
import { useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import {
  Plus,
  Search,
  UserRound,
  ShieldCheck,
  Pencil,
  Check,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  roles,
  validateUser,
  type DemoUser,
  type Role,
} from "@/services/demo/user-model";
import {
  useDemoUsers,
  useDemoSession,
  saveUsers,
} from "@/services/demo/users-store";
import { enterTransition } from "@/lib/motion/presets";

const empty = { name: "", email: "", role: "viewer" as Role, active: true };
export function UserManagement() {
  const { users, error: storageError } = useDemoUsers();
  const session = useDemoSession();
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("");
  const [selected, setSelected] = useState<string | null | undefined>(
    undefined,
  );
  const [form, setForm] = useState(empty);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const nameInput = useRef<HTMLInputElement>(null);
  const createButton = useRef<HTMLButtonElement>(null);
  const canEdit = session?.role === "administrator";
  const reduceMotion = useReducedMotion();
  const visible = users.filter(
    (u) =>
      `${u.name} ${u.email}`.toLowerCase().includes(query.toLowerCase()) &&
      (!role || u.role === role),
  );
  function edit(user?: DemoUser) {
    if (selected !== undefined) return;
    setSelected(user?.id ?? null);
    setForm(
      user
        ? {
            name: user.name,
            email: user.email,
            role: user.role,
            active: user.active,
          }
        : empty,
    );
    setError(null);
    setNotice("");
    requestAnimationFrame(() => nameInput.current?.focus());
  }
  function cancel() {
    setSelected(undefined);
    setError(null);
    requestAnimationFrame(() => createButton.current?.focus());
  }
  return (
    <div className="users-page">
      <header className="insights-heading">
        <div>
          <h2>Un equipo, distintos alcances.</h2>
          <p>
            Organice cuentas y roles en un espacio de demostración
            independiente.
          </p>
        </div>
        <Button
          ref={createButton}
          disabled={!canEdit || selected !== undefined}
          onClick={() => edit()}
        >
          <Plus size={17} />
          Crear usuario
        </Button>
      </header>
      <div className="provenance-note">
        <ShieldCheck size={19} />
        <p>
          Demo local · Los cambios se guardan solo en este navegador. Use
          nombres y correos ficticios. Los roles no son permisos reales del
          Backend.
        </p>
      </div>
      {!canEdit && (
        <div className="access-note">
          <p>
            {session
              ? `${roles[session.role]}: puede consultar esta demostración. Para editar, seleccione el perfil Administrador.`
              : "Abra una sesión demo de Administrador para crear o editar cuentas."}
          </p>
          <Link href="/login" className="button button-outline">
            Elegir perfil demo
          </Link>
        </div>
      )}
      <div className="users-toolbar">
        <label className="search-field">
          <Search size={17} aria-hidden="true" />
          <input
            aria-label="Buscar usuarios"
            placeholder="Buscar por nombre o correo"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <label>
          Rol
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="">Todos los roles</option>
            {Object.entries(roles).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <span>
          {visible.length} de {users.length} cuentas
        </span>
      </div>
      {storageError && (
        <p className="form-error" role="alert">
          {storageError}
        </p>
      )}
      {notice && (
        <p className="success-message" role="status">
          <Check size={16} />
          {notice}
        </p>
      )}
      <div
        className={`users-layout ${selected !== undefined ? "has-editor" : ""}`}
      >
        <section className="users-list" aria-label="Directorio de usuarios">
          <div className="table-scroll">
            <table className="users-table">
              <thead>
                <tr>
                  <th>Usuario</th>
                  <th>Rol</th>
                  <th>Estado</th>
                  <th>
                    <span className="sr-only">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {visible.map((u) => (
                  <motion.tr
                    key={u.id}
                    className={selected === u.id ? "is-selected" : ""}
                    initial={reduceMotion ? false : { opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={
                      reduceMotion ? { duration: 0 } : enterTransition
                    }
                  >
                    <td>
                      <div className="user-identity">
                        <span className="user-avatar" aria-hidden="true">
                          <UserRound size={19} />
                        </span>
                        <div>
                          <strong>{u.name}</strong>
                          <small>{u.email}</small>
                        </div>
                      </div>
                    </td>
                    <td>{roles[u.role]}</td>
                    <td>
                      <span
                        className={`account-state ${u.active ? "is-active" : ""}`}
                      >
                        {u.active ? "Activa" : "Desactivada"}
                      </span>
                    </td>
                    <td>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Editar ${u.name}`}
                        disabled={!canEdit || selected !== undefined}
                        onClick={() => edit(u)}
                      >
                        <Pencil size={16} />
                      </Button>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
          {!visible.length && (
            <div className="feedback-panel">
              <h3>No hay coincidencias</h3>
              <p>Pruebe otro nombre, correo o rol.</p>
              <Button
                variant="outline"
                onClick={() => {
                  setQuery("");
                  setRole("");
                }}
              >
                Limpiar búsqueda
              </Button>
            </div>
          )}
        </section>
        {selected !== undefined && canEdit && (
          <motion.section
            key="user-editor"
            className="user-editor"
            aria-labelledby="user-editor-title"
            initial={reduceMotion ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={reduceMotion ? { duration: 0 } : enterTransition}
          >
            <h3 id="user-editor-title">
              {selected ? "Editar usuario" : "Nueva cuenta demo"}
            </h3>
            <p>
              Sin contraseñas, invitaciones ni correos enviados. Guarde o
              cancele esta edición antes de abrir otra cuenta.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setError(null);
                try {
                  const value = validateUser(
                    form,
                    users,
                    selected ?? undefined,
                  );
                  const next = selected
                    ? users.map((u) =>
                        u.id === selected ? { ...value, id: u.id } : u,
                      )
                    : [...users, { ...value, id: crypto.randomUUID() }];
                  saveUsers(next);
                  setNotice(
                    selected
                      ? "Cambios guardados en este navegador."
                      : "Cuenta de ejemplo creada en este navegador.",
                  );
                  cancel();
                } catch (cause) {
                  setError(
                    cause instanceof Error
                      ? cause.message
                      : "No fue posible guardar. Revise el almacenamiento del navegador.",
                  );
                }
              }}
              onKeyDown={(e) => {
                if (e.key === "Escape") cancel();
              }}
            >
              <label htmlFor="user-name">Nombre visible</label>
              <input
                ref={nameInput}
                id="user-name"
                className="input"
                required
                maxLength={80}
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                autoComplete="off"
              />
              <label htmlFor="user-email">Correo de ejemplo</label>
              <input
                id="user-email"
                type="email"
                className="input"
                required
                maxLength={160}
                value={form.email}
                placeholder="equipo@example.test"
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                autoComplete="off"
              />
              <label htmlFor="user-role">Rol</label>
              <select
                id="user-role"
                className="input"
                value={form.role}
                onChange={(e) =>
                  setForm({ ...form, role: e.target.value as Role })
                }
              >
                {Object.entries(roles).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
              <p className="field-help">
                {form.role === "viewer"
                  ? "Consulta demostrativa de fuentes y cámaras; no hay cámaras reales integradas."
                  : form.role === "safety_lead"
                    ? "Representa supervisión y revisión preventiva. No otorga permisos de servidor."
                    : "Habilita la edición de cuentas de esta demo local."}
              </p>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={form.active}
                  onChange={(e) =>
                    setForm({ ...form, active: e.target.checked })
                  }
                />
                Cuenta activa
              </label>
              <p className="field-help">
                Desactivar conserva la cuenta y permite reactivarla. No se
                elimina información.
              </p>
              {error && (
                <p className="form-error" role="alert">
                  {error}
                </p>
              )}
              <div className="form-actions">
                <Button type="submit">Guardar cambios</Button>
                <Button variant="outline" onClick={cancel}>
                  Cancelar
                </Button>
              </div>
            </form>
          </motion.section>
        )}
      </div>
      <section className="role-guide">
        <h3>Roles de referencia</h3>
        <dl>
          {Object.entries(roles).map(([key, label]) => (
            <div key={key}>
              <dt>{label}</dt>
              <dd>
                {key === "viewer"
                  ? "Consulta limitada como intención de producto."
                  : key === "safety_lead"
                    ? "Revisión general y supervisión preventiva."
                    : "Gestión de cuentas y configuración de acceso."}
              </dd>
            </div>
          ))}
        </dl>
        <p>
          La autorización real deberá implementarse y verificarse en el Backend
          antes de un despliegue protegido.
        </p>
      </section>
    </div>
  );
}
