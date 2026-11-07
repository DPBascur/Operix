"use client";

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  getSession,
  sessionExpired,
  type OperixUser,
} from "@/services/browser-session";

const SessionContext = createContext<{
  user: OperixUser | null | undefined;
  expired: boolean;
  setUser: (user: OperixUser | null) => void;
} | null>(null);

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) throw new Error("Falta el proveedor de sesión");
  return context;
}

export function canOpen(path: string, role: OperixUser["role"]) {
  if (role === "administrator") return true;
  const page = path.split(/[/?]/)[1];
  if (page === "account") return true;
  if (page === "users") return false;
  if (role === "safety_lead")
    return !["analysis", "sources", "rules", "zones"].includes(page);
  return ["analysis", "sources", "rules", "zones"].includes(page);
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, updateUser] = useState<OperixUser | null>();
  const [expired, setExpired] = useState(false);
  const revision = useRef(0);
  function setUser(account: OperixUser | null) {
    revision.current++;
    updateUser(account);
    setExpired(false);
    setFailed(false);
  }
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const path = usePathname();
  const router = useRouter();
  const login = path === "/login";

  useEffect(() => {
    let current = true;
    const refresh = () => {
      const request = ++revision.current;
      getSession().then(
        (account) => {
          if (current && request === revision.current) {
            updateUser(account);
            setFailed(false);
          }
        },
        () => {
          if (current && request === revision.current) setFailed(true);
        },
      );
    };
    const expire = () => {
      revision.current++;
      updateUser(null);
      setExpired(true);
      setFailed(false);
    };
    refresh();
    window.addEventListener("focus", refresh);
    window.addEventListener(sessionExpired, expire);
    return () => {
      current = false;
      window.removeEventListener("focus", refresh);
      window.removeEventListener(sessionExpired, expire);
    };
  }, [retry]);

  useEffect(() => {
    if (!login && user === null) {
      const next = path + window.location.search;
      router.replace(`/login?next=${encodeURIComponent(next)}`);
    } else if (!login && user && !canOpen(path, user.role)) {
      router.replace(user.role === "operator" ? "/analysis" : "/");
    }
  }, [login, path, router, user]);

  return (
    <SessionContext.Provider value={{ user, setUser, expired }}>
      {login || (user && !failed && canOpen(path, user.role)) ? (
        children
      ) : (
        <main className="page-wrap" aria-live="polite">
          {failed ? (
            <>
              <p>No se pudo verificar la sesión con Operix.</p>
              <button
                className="button button-outline"
                onClick={() => setRetry(retry + 1)}
              >
                Reintentar
              </button>
            </>
          ) : (
            <p>Verificando sesión…</p>
          )}
        </main>
      )}
    </SessionContext.Provider>
  );
}
