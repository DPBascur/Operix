import { FlaskConical } from "lucide-react";
export function MockDataNotice() {
  return (
    <div className="flex items-start gap-3 rounded-control border border-info/25 bg-info/5 px-4 py-3 text-sm text-text-secondary">
      <FlaskConical
        aria-hidden="true"
        className="mt-0.5 shrink-0 text-info"
        size={18}
      />
      <p>
        Vista demostrativa con datos mock del frontend. No representa resultados
        del Motor ni información persistida.
      </p>
    </div>
  );
}
