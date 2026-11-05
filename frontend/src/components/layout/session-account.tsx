"use client";

import { useState } from "react";
import { LogOut, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { roleLabels, signOut } from "@/services/browser-session";
import { useSession } from "@/features/auth/session-provider";

export function SessionAccount() {
  const { user, setUser } = useSession();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  if (!user) return null;
  return (
    <div>
      <div className="demo-account">
        <div className="account-link" title={user.username}>
          <UserRound size={17} aria-hidden="true" />
          <span>
            <strong>{user.username}</strong>
            <small>{roleLabels[user.role]}</small>
          </span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Cerrar sesión"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setFailed(false);
            try {
              await signOut();
              setUser(null);
            } catch {
              setFailed(true);
            } finally {
              setBusy(false);
            }
          }}
        >
          <LogOut size={16} aria-hidden="true" />
        </Button>
      </div>
      {failed && (
        <p className="form-error" role="alert">
          No se pudo cerrar la sesión. Vuelva a intentar.
        </p>
      )}
    </div>
  );
}
