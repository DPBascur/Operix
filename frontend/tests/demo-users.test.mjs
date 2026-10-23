import assert from "node:assert/strict";
import test from "node:test";
import {
  parseUsers,
  seedUsers,
  validateUser,
  resolveActiveUser,
} from "../src/services/demo/user-model.ts";
test("login elige la misma cuenta activa que muestra si el perfil anterior fue desactivado", () => {
  const users = seedUsers.map((u) =>
    u.id === "demo-safety" ? { ...u, active: false } : u,
  );
  assert.equal(resolveActiveUser(users, "demo-safety"), "demo-admin");
  assert.equal(resolveActiveUser([], "demo-safety"), "");
});
test("fixture explícita posee tres roles y se recupera sin perder campos", () => {
  assert.deepEqual(parseUsers(JSON.stringify(seedUsers)), seedUsers);
  assert.equal(new Set(seedUsers.map((u) => u.role)).size, 3);
});
test("crear normaliza nombre y correo sin credenciales", () => {
  const v = validateUser(
    {
      name: " Equipo ",
      email: "EQUIPO@example.test",
      role: "viewer",
      active: true,
    },
    seedUsers,
  );
  assert.equal(v.name, "Equipo");
  assert.equal(v.email, "equipo@example.test");
  assert.equal("password" in v, false);
});
test("rechaza correo duplicado sin distinguir mayúsculas", () => {
  assert.throws(
    () =>
      validateUser(
        {
          name: "Otro",
          email: "ADMIN@example.test",
          role: "viewer",
          active: true,
        },
        seedUsers,
      ),
    /ya está/,
  );
});
test("impide desactivar o degradar al último administrador", () => {
  assert.throws(
    () =>
      validateUser(
        { ...seedUsers[0], active: false },
        seedUsers,
        seedUsers[0].id,
      ),
    /administrador activo/,
  );
  assert.throws(
    () =>
      validateUser(
        { ...seedUsers[0], role: "viewer" },
        seedUsers,
        seedUsers[0].id,
      ),
    /administrador activo/,
  );
});
test("desactivar cuenta común conserva sus datos y permite reactivación", () => {
  const inactive = validateUser(
    { ...seedUsers[2], active: false },
    seedUsers,
    seedUsers[2].id,
  );
  assert.equal(inactive.active, false);
  assert.equal(
    validateUser({ ...inactive, active: true }, seedUsers, seedUsers[2].id)
      .active,
    true,
  );
});
test("rechaza almacenamiento corrupto, roles inventados e identidades duplicadas", () => {
  assert.throws(() => parseUsers("bad"));
  assert.throws(() =>
    parseUsers(JSON.stringify([{ ...seedUsers[0], role: "owner" }])),
  );
  assert.throws(() => parseUsers(JSON.stringify([seedUsers[0], seedUsers[0]])));
});
