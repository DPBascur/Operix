import { AppShell } from "@/components/layout/app-shell";
export default function UsersPage() {
  return (
    <AppShell activePath="/users">
      <section className="page-wrap">
        <h2 className="compact-page-title">Cuentas de Operix</h2>
        <p className="compact-page-copy">
          Las cuentas y sus roles se gestionan en la administración de Django.
        </p>
      </section>
    </AppShell>
  );
}
