export const roles = {
  viewer: "Usuario común",
  safety_lead: "Jefe de seguridad",
  administrator: "Administrador",
} as const;
export type Role = keyof typeof roles;
export interface DemoUser {
  id: string;
  name: string;
  email: string;
  role: Role;
  active: boolean;
}
export const seedUsers: DemoUser[] = [
  {
    id: "demo-admin",
    name: "Administración demo",
    email: "admin@example.test",
    role: "administrator",
    active: true,
  },
  {
    id: "demo-safety",
    name: "Equipo de prevención",
    email: "seguridad@example.test",
    role: "safety_lead",
    active: true,
  },
  {
    id: "demo-viewer",
    name: "Operación demo",
    email: "operacion@example.test",
    role: "viewer",
    active: true,
  },
];
export function resolveActiveUser(
  users: DemoUser[],
  preferred: string,
): string {
  return (
    users.find((u) => u.id === preferred && u.active)?.id ??
    users.find((u) => u.active)?.id ??
    ""
  );
}
export function validateUser(
  input: Omit<DemoUser, "id">,
  users: DemoUser[],
  id?: string,
) {
  if (!input.name.trim() || input.name.trim().length > 80)
    throw new Error("Escriba un nombre de 1 a 80 caracteres.");
  if (
    !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(input.email) ||
    input.email.length > 160
  )
    throw new Error("Escriba un correo válido, preferentemente de ejemplo.");
  if (!Object.hasOwn(roles, input.role))
    throw new Error("Seleccione un rol válido.");
  if (
    users.some(
      (u) => u.id !== id && u.email.toLowerCase() === input.email.toLowerCase(),
    )
  )
    throw new Error("Ese correo ya está en la lista.");
  if (
    id &&
    users.some((u) => u.id === id && u.active && u.role === "administrator") &&
    (!input.active || input.role !== "administrator") &&
    !users.some((u) => u.id !== id && u.active && u.role === "administrator")
  )
    throw new Error("Conserve al menos un administrador activo en la demo.");
  return {
    ...input,
    name: input.name.trim(),
    email: input.email.trim().toLowerCase(),
  };
}
export function parseUsers(raw: string): DemoUser[] {
  const value: unknown = JSON.parse(raw);
  if (
    !Array.isArray(value) ||
    !value.length ||
    value.length > 200 ||
    !value.every(
      (u) =>
        u &&
        typeof u.id === "string" &&
        typeof u.name === "string" &&
        typeof u.email === "string" &&
        Object.hasOwn(roles, u.role) &&
        typeof u.active === "boolean",
    )
  )
    throw new Error("Los datos locales no son válidos.");
  if (new Set(value.map((u) => u.id)).size !== value.length)
    throw new Error("Identidades locales duplicadas.");
  value.forEach((u) => validateUser(u, value, u.id));
  if (!value.some((u) => u.active && u.role === "administrator"))
    throw new Error("Falta un administrador activo.");
  return value;
}
