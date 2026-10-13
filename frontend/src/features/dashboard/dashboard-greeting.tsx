"use client";

import { useSyncExternalStore } from "react";

function subscribe(callback: () => void) {
  const timer = window.setInterval(callback, 60_000);
  return () => window.clearInterval(timer);
}

function currentGreeting() {
  const hour = new Date().getHours();
  if (hour >= 6 && hour < 12) return "Buenos días";
  if (hour >= 12 && hour < 20) return "Buenas tardes";
  return "Buenas noches";
}

export function DashboardGreeting({ name }: { name: string }) {
  const greeting = useSyncExternalStore(
    subscribe,
    currentGreeting,
    () => "Hola",
  );
  return <>{`${greeting}, ${name}`}</>;
}
