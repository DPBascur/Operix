import { AppShell } from "@/components/layout/app-shell";
import { AccountDirectory } from "@/features/users/account-directory";

export default function UsersPage() {
  return (
    <AppShell activePath="/users">
      <AccountDirectory />
    </AppShell>
  );
}
