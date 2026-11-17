"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import { type CurrentPsychologist, ProfileUpdateError, updateProfile } from "@/api/auth";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Logo } from "@/components/ui/Logo";
import { TextField } from "@/components/ui/TextField";
import { useCurrentPsychologist } from "@/hooks/useCurrentPsychologist";

const MAX_NAME_LENGTH = 200;

/**
 * IANA time zones supported by the browser, or an empty list when the browser cannot list them.
 * In that case the page falls back to a text field, and the backend validates the value.
 */
function supportedTimeZones(): string[] {
  try {
    return typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  } catch {
    return [];
  }
}

function errorMessage(error: unknown): string {
  if (error instanceof ProfileUpdateError) {
    if (error.status === 422) return "Перевірте ім'я та часовий пояс і спробуйте ще раз.";
    if (error.status === 403) return "Сесія застаріла. Оновіть сторінку й спробуйте ще раз.";
  }
  return "Не вдалося зберегти профіль. Спробуйте пізніше.";
}

/** Lets a signed-in psychologist change the display name and scheduling time zone. */
export default function ProfilePage() {
  const router = useRouter();
  const state = useCurrentPsychologist();
  const [psychologist, setPsychologist] = useState<CurrentPsychologist | null>(null);
  const [name, setName] = useState("");
  const [timeZone, setTimeZone] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);

  useEffect(() => {
    if (state.status === "signed-out") router.replace("/");
    if (state.status === "signed-in") {
      setPsychologist(state.psychologist);
      setName(state.psychologist.display_name);
      setTimeZone(state.psychologist.time_zone);
    }
  }, [state, router]);

  const supportedZones = useMemo(() => supportedTimeZones(), []);
  // Keep the saved zone selectable even if the browser's list does not include it.
  const zones =
    supportedZones.length === 0 || supportedZones.includes(timeZone)
      ? supportedZones
      : [timeZone, ...supportedZones];

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!psychologist) return;
    const trimmed = name.trim();
    if (!trimmed) {
      setMessage({ tone: "error", text: "Вкажіть ім'я." });
      return;
    }
    const update: { display_name?: string; time_zone?: string } = {};
    if (trimmed !== psychologist.display_name) update.display_name = trimmed;
    if (timeZone !== psychologist.time_zone) update.time_zone = timeZone;
    if (Object.keys(update).length === 0) {
      setMessage({ tone: "ok", text: "Змін немає." });
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const updated = await updateProfile(psychologist.csrf_token, update);
      setPsychologist(updated);
      setName(updated.display_name);
      setTimeZone(updated.time_zone);
      setMessage({ tone: "ok", text: "Профіль збережено." });
    } catch (error) {
      if (error instanceof ProfileUpdateError && error.status === 401) {
        router.replace("/");
        return;
      }
      setMessage({ tone: "error", text: errorMessage(error) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:h-[76px] sm:px-8">
          <Logo />
          <Button href="/dashboard" variant="ghost" size="sm">
            До кабінету
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-10 sm:px-8 sm:py-14">
        <h1 className="text-3xl text-ink sm:text-4xl">Профіль</h1>

        {state.status === "error" && (
          <p role="alert" className="mt-6 rounded-xl bg-danger-50 px-4 py-3 text-danger-700">
            Не вдалося завантажити профіль. Оновіть сторінку або спробуйте пізніше.
          </p>
        )}

        {!psychologist && state.status !== "error" && (
          <p className="mt-6 text-muted">Завантаження…</p>
        )}

        {psychologist && (
          <Card className="mt-8 p-6 sm:p-8">
            <form onSubmit={handleSubmit}>
              {/* Disabled while saving, so that edits cannot be overwritten by the response. */}
              <fieldset disabled={saving} className="m-0 flex min-w-0 flex-col gap-5 border-0 p-0">
                <TextField
                  id="profile-name"
                  label="Ім'я, яке бачать клієнти"
                  required
                  maxLength={MAX_NAME_LENGTH}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="profile-time-zone" className="text-[13px] font-bold text-ink">
                    Часовий пояс
                  </label>
                  {zones.length > 0 ? (
                    <select
                      id="profile-time-zone"
                      aria-describedby="profile-time-zone-hint"
                      value={timeZone}
                      onChange={(event) => setTimeZone(event.target.value)}
                      className="h-12 rounded-xl border border-line bg-white px-4 text-[15px] text-ink focus:border-mint-300 focus:outline-2 focus:outline-mint-200"
                    >
                      {zones.map((zone) => (
                        <option key={zone} value={zone}>
                          {zone}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      id="profile-time-zone"
                      aria-describedby="profile-time-zone-hint"
                      required
                      placeholder="Europe/Kyiv"
                      value={timeZone}
                      onChange={(event) => setTimeZone(event.target.value.trim())}
                      className="h-12 rounded-xl border border-line bg-white px-4 text-[15px] text-ink focus:border-mint-300 focus:outline-2 focus:outline-mint-200"
                    />
                  )}
                  <p id="profile-time-zone-hint" className="text-[13px] text-muted">
                    У цьому часовому поясі задаються робочі години. Після зміни майбутні вільні
                    слоти буде перераховано, а наявні бронювання залишаться без змін.
                  </p>
                </div>

                {message && (
                  <p
                    role={message.tone === "error" ? "alert" : "status"}
                    className={
                      message.tone === "error"
                        ? "rounded-xl bg-danger-50 px-4 py-3 text-danger-700"
                        : "rounded-xl bg-mint-100 px-4 py-3 text-ink"
                    }
                  >
                    {message.text}
                  </p>
                )}

                <div>
                  <Button type="submit" disabled={saving}>
                    {saving ? "Збереження…" : "Зберегти"}
                  </Button>
                </div>
              </fieldset>
            </form>
          </Card>
        )}
      </main>
    </>
  );
}
