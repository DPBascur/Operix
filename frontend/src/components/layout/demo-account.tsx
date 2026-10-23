"use client";
import Link from "next/link";
import { LogOut, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDemoSession, signOutDemo } from "@/services/demo/users-store";
import { roles } from "@/services/demo/user-model";
export function DemoAccount() {
  const user = useDemoSession();
  return (
    <div className="demo-account">
      {user ? (
        <>
          <Link
            href="/login"
            className="account-link"
            title={`${user.name} · ${roles[user.role]}`}
          >
            <UserRound size={17} />
            <span>
              <strong>{user.name}</strong>
              <small>{roles[user.role]}</small>
            </span>
          </Link>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Cerrar sesión"
            onClick={signOutDemo}
          >
            <LogOut size={16} />
          </Button>
        </>
      ) : (
        <Link className="button button-outline" href="/login">
          <UserRound size={16} />
          Iniciar sesión
        </Link>
      )}
    </div>
  );
}
