"use client";
import { useMemo, useSyncExternalStore } from "react";
import { parseUsers, seedUsers, type DemoUser } from "./user-model";
const KEY = "operix-demo-users-v1";
const SESSION = "operix-demo-session-v1";
const fallback = JSON.stringify(seedUsers);
function subscribe(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener("operix-demo-change", callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener("operix-demo-change", callback);
  };
}
function snapshot() {
  try {
    return localStorage.getItem(KEY) ?? fallback;
  } catch {
    return fallback;
  }
}
function sessionSnapshot() {
  try {
    return sessionStorage.getItem(SESSION) ?? "";
  } catch {
    return "";
  }
}
function changed() {
  window.dispatchEvent(new Event("operix-demo-change"));
}
export function saveUsers(users: DemoUser[]) {
  parseUsers(JSON.stringify(users));
  localStorage.setItem(KEY, JSON.stringify(users));
  changed();
}
export function signInDemo(id: string) {
  const user = parseUsers(snapshot()).find((u) => u.id === id && u.active);
  if (!user) throw new Error("Seleccione una cuenta activa de demostración.");
  sessionStorage.setItem(SESSION, id);
  changed();
}
export function signOutDemo() {
  sessionStorage.removeItem(SESSION);
  changed();
}
export function useDemoUsers() {
  const raw = useSyncExternalStore(subscribe, snapshot, () => fallback);
  return useMemo(() => {
    try {
      return { users: parseUsers(raw), error: null };
    } catch {
      return {
        users: seedUsers,
        error:
          "Los datos guardados no son válidos. Se muestra la base de demostración sin sobrescribirlos.",
      };
    }
  }, [raw]);
}
export function useDemoSession() {
  const id = useSyncExternalStore(subscribe, sessionSnapshot, () => "");
  const { users } = useDemoUsers();
  return users.find((u) => u.id === id && u.active) ?? null;
}
