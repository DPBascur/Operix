import { AppShell } from "@/components/layout/app-shell";
import { ObservationStory } from "@/features/experience/observation-story";

export default function ExperiencePage() {
  return (
    <AppShell activePath="/experience">
      <ObservationStory />
    </AppShell>
  );
}
