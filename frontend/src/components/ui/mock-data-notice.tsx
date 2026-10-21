import { FlaskConical } from "lucide-react";
export function MockDataNotice() {
  return (
    <div className="mock-notice">
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
