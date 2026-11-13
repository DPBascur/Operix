"use client";

import dynamic from "next/dynamic";
import { CircleHelp } from "lucide-react";
import { useSession } from "@/features/auth/session-provider";
import { useState } from "react";
import type { OperixUser } from "@/services/browser-session";

const ExperienceGuide = dynamic(
  () => import("./experience-guide").then((module) => module.ExperienceGuide),
  { ssr: false },
);

export function GuideLauncher() {
  const { user } = useSession();
  return user ? <UserGuide key={user.username} user={user} /> : null;
}

function UserGuide({ user }: { user: OperixUser }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        id="operix-guide-launcher"
        type="button"
        className="experience-help"
        aria-label="Ayuda de Operix"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <CircleHelp size={19} aria-hidden="true" />
      </button>
      <ExperienceGuide user={user} open={open} onOpenChange={setOpen} />
    </>
  );
}
