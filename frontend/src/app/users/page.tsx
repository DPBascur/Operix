import { AppShell } from "@/components/layout/app-shell";
import { UserManagement } from "@/features/users/user-management";
export default function UsersPage() {
  return (
    <AppShell activePath="/users">
      <UserManagement />
    </AppShell>
  );
}
