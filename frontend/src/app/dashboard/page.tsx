"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { signOut } from "@/api/auth";
import { BookingsCard } from "@/components/dashboard/BookingsCard";
import { ProfileCard } from "@/components/dashboard/ProfileCard";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Logo } from "@/components/ui/Logo";
import { useCurrentPsychologist } from "@/hooks/useCurrentPsychologist";

type DashboardSection = { title: string; description: string; href?: string };

const sections: DashboardSection[] = [
  {
    title: "Доступність",
    description: "Робочі години, тривалість і вартість сесії.",
    href: "/dashboard/availability",
  },
];

/** Psychologist dashboard: bookings, links to settings pages and sign-out. */
export default function DashboardPage() {
  const router = useRouter();
  const state = useCurrentPsychologist();
  const [signingOut, setSigningOut] = useState(false);
  const [signOutFailed, setSignOutFailed] = useState(false);

  useEffect(() => {
    if (state.status === "signed-out") {
      router.replace("/");
    }
  }, [state.status, router]);

  async function handleSignOut(csrfToken: string) {
    setSigningOut(true);
    setSignOutFailed(false);
    try {
      await signOut(csrfToken);
      router.replace("/");
    } catch {
      setSignOutFailed(true);
      setSigningOut(false);
    }
  }

  return (
    <>
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:h-[76px] sm:px-8">
          <Logo />
          {state.status === "signed-in" && (
            <Button
              variant="ghost"
              size="sm"
              disabled={signingOut}
              onClick={() => handleSignOut(state.psychologist.csrf_token)}
            >
              {signingOut ? "Вихід…" : "Вийти"}
            </Button>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-10 sm:px-8 sm:py-14">
        {state.status === "error" && (
          <p role="alert" className="rounded-xl bg-danger-50 px-4 py-3 text-danger-700">
            Не вдалося завантажити кабінет. Оновіть сторінку або спробуйте пізніше.
          </p>
        )}

        {(state.status === "loading" || state.status === "signed-out") && (
          <p className="text-muted">Завантаження…</p>
        )}

        {state.status === "signed-in" && (
          <>
            <h1 className="text-3xl text-ink sm:text-4xl">
              Вітаємо, {state.psychologist.display_name}!
            </h1>
            {state.psychologist.email && (
              <p className="mt-2 text-muted">Ви увійшли як {state.psychologist.email}</p>
            )}

            {signOutFailed && (
              <p role="alert" className="mt-6 rounded-xl bg-danger-50 px-4 py-3 text-danger-700">
                Не вдалося вийти. Спробуйте ще раз.
              </p>
            )}

            <BookingsCard timeZone={state.psychologist.time_zone} />

            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              {sections.map((section) => (
                <Card key={section.title} className="flex flex-col p-6">
                  <div className="flex items-start justify-between gap-3">
                    <h2 className="text-xl text-ink">{section.title}</h2>
                    {!section.href && <Badge tone="neutral">Незабаром</Badge>}
                  </div>
                  <p className="mt-3 text-muted">{section.description}</p>
                  {section.href && (
                    <Button
                      href={section.href}
                      variant="secondary"
                      size="sm"
                      className="mt-5 self-start"
                    >
                      Налаштувати
                    </Button>
                  )}
                </Card>
              ))}
              <ProfileCard psychologist={state.psychologist} />
            </div>
          </>
        )}
      </main>
    </>
  );
}
