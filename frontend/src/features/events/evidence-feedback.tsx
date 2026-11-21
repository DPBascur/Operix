import { OperixScanLoader } from "@/components/ui/operix-scan-loader";
import { evidenceSummary, type EventEvidence } from "./event-detail-model";

export function EvidenceFeedback({
  evidence,
  checking,
  refreshFailed,
}: {
  evidence: EventEvidence;
  checking?: boolean;
  refreshFailed?: boolean;
}) {
  const message = evidenceSummary(evidence, checking);
  return (
    <div role="status" className="text-sm text-text-secondary">
      {checking ? (
        <OperixScanLoader size="small" message={message} announce={false} />
      ) : (
        message
      )}
      {refreshFailed && (
        <p>
          No se pudo actualizar el estado. Vuelve a abrir el evento para
          consultar de nuevo.
        </p>
      )}
    </div>
  );
}
