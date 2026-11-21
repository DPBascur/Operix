import { CameraLabDetail } from "@/features/sources/camera-lab";

export const metadata = { title: "Cámara de laboratorio" };

export default async function CameraPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <CameraLabDetail key={id} id={id} />;
}
