import { Logo } from "@/components/ui/Logo";

/** Temporary home page; it is replaced by the landing page in a follow-up change. */
export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-mint-50 px-4 text-center">
      <Logo />
      <h1 className="text-4xl sm:text-5xl">Записи, оплати та розклад — в одному місці</h1>
      <p className="max-w-xl text-muted">Сайт для незалежних психологів і їхніх клієнтів. Скоро тут буде більше.</p>
    </main>
  );
}
