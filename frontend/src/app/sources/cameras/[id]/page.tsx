import { CameraLabDetail } from "@/features/sources/camera-lab";
import { CameraRecordingConfiguration } from "@/features/sources/camera-recording-configuration";

export const metadata = { title: "Cámara de laboratorio" };

export default async function CameraPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ recording?: string | string[] }>;
}) {
  const [{ id }, { recording }] = await Promise.all([params, searchParams]);
  if (typeof recording === "string" && /^[a-z0-9_-]{1,64}$/.test(recording)) {
    return <CameraRecordingConfiguration key={`${id}:${recording}`} id={id} media={recording} />;
  }
  return <CameraLabDetail key={id} id={id} />;
}
