"use client";

import { useParams, useRouter } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { errorStatus } from "@/api/errors";
import {
  type AvailabilitySlot,
  getPublicAvailability,
  getPublicPsychologist,
  type PublicPsychologist,
  requestEmailVerification,
} from "@/api/public";
import { BookingPageShell, Notice } from "@/components/booking/BookingPageShell";
import { RecoverAccessForm } from "@/components/booking/RecoverAccessForm";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { TextField } from "@/components/ui/TextField";
import {
  clearPendingRecovery,
  loadGrant,
  newIdempotencyKey,
  savePendingSelection,
  type StoredGrant,
} from "@/utils/clientBookingStorage";
import { verificationErrorMessage } from "@/utils/verificationErrors";
import { cn } from "@/utils/cn";
import { browserTimeZone, dayKey, formatDay, formatPrice, formatSlot, formatTime } from "@/utils/format";
import { holdSlot } from "@/utils/holdSlot";

/** The backend accepts availability queries of at most 30 days; stay just inside that bound. */
const AVAILABILITY_WINDOW_MS = 30 * 24 * 60 * 60 * 1000 - 60 * 1000;

type LoadState =
  | { status: "loading" }
  | { status: "not-found" }
  | { status: "error" }
  | { status: "ready"; psychologist: PublicPsychologist; timeZone: string; slots: AvailabilitySlot[] };

type DayGroup = { key: string; label: string; slots: AvailabilitySlot[] };

function groupByDay(slots: AvailabilitySlot[], timeZone: string): DayGroup[] {
  const groups = new Map<string, DayGroup>();
  for (const slot of [...slots].sort((a, b) => a.starts_at.localeCompare(b.starts_at))) {
    const key = dayKey(slot.starts_at, timeZone);
    const group = groups.get(key);
    if (group) {
      group.slots.push(slot);
    } else {
      groups.set(key, { key, label: formatDay(slot.starts_at, timeZone), slots: [slot] });
    }
  }
  return [...groups.values()];
}

/** Public booking page of one psychologist. */
export default function PsychologistPublicPage() {
  const { publicId } = useParams<{ publicId: string }>();
  const router = useRouter();

  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [reloadCounter, setReloadCounter] = useState(0);
  const [selectedSlotId, setSelectedSlotId] = useState<string | null>(null);
  const [grant, setGrant] = useState<StoredGrant | null>(null);
  const [email, setEmail] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [booking, setBooking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Set when a booking exists but this browser received no access token for it.
  const [needsRecovery, setNeedsRecovery] = useState(false);
  // One Idempotency-Key per selected slot, reused across retries so that a booking created before
  // a lost response is replayed instead of failing. A new key is made only for a different slot.
  const attemptKey = useRef<{ slotId: string; key: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    const now = new Date();
    Promise.all([
      getPublicPsychologist(publicId),
      getPublicAvailability(publicId, now, new Date(now.getTime() + AVAILABILITY_WINDOW_MS)).catch(
        (loadError: unknown) => {
          if (errorStatus(loadError) === 404) return null;
          throw loadError;
        },
      ),
    ])
      .then(([psychologist, availability]) => {
        if (cancelled) return;
        if (!psychologist || !availability) {
          setState({ status: "not-found" });
          return;
        }
        setState({
          status: "ready",
          psychologist,
          timeZone: availability.time_zone || psychologist.time_zone,
          slots: availability.slots,
        });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [publicId, reloadCounter]);

  useEffect(() => {
    setGrant(loadGrant(publicId));
  }, [publicId]);

  const days = useMemo(
    () => (state.status === "ready" ? groupByDay(state.slots, state.timeZone) : []),
    [state],
  );

  const selectedSlot =
    state.status === "ready" ? state.slots.find((slot) => slot.id === selectedSlotId) ?? null : null;

  const selectSlot = useCallback((slotId: string) => {
    setSelectedSlotId(slotId);
    setSent(false);
    setError(null);
  }, []);

  if (state.status === "loading") {
    return (
      <BookingPageShell>
        <p className="text-muted">Завантаження…</p>
      </BookingPageShell>
    );
  }

  if (state.status === "not-found") {
    return (
      <BookingPageShell>
        <Card className="mx-auto max-w-xl p-8 text-center">
          <h1 className="text-3xl">Сторінку не знайдено</h1>
          <p className="mt-3 text-muted">
            Перевірте посилання, яке надав вам психолог.
          </p>
        </Card>
      </BookingPageShell>
    );
  }

  if (state.status === "error") {
    return (
      <BookingPageShell>
        <Card className="mx-auto flex max-w-xl flex-col items-center gap-4 p-8 text-center">
          <h1 className="text-3xl">Не вдалося завантажити сторінку</h1>
          <p className="text-muted">Перевірте з’єднання з інтернетом і спробуйте ще раз.</p>
          <Button variant="ghost" onClick={() => setReloadCounter((value) => value + 1)}>
            Спробувати ще раз
          </Button>
        </Card>
      </BookingPageShell>
    );
  }

  const { psychologist, timeZone } = state;
  const clientTimeZone = browserTimeZone();

  function keyForSlot(slotId: string): string {
    if (attemptKey.current?.slotId !== slotId) {
      attemptKey.current = { slotId, key: newIdempotencyKey() };
    }
    return attemptKey.current.key;
  }

  const selectionFor = (slot: AvailabilitySlot) => ({
    psychologistPublicId: psychologist.public_id,
    psychologistName: psychologist.display_name,
    timeZone,
    slotId: slot.id,
    startsAt: slot.starts_at,
    endsAt: slot.ends_at,
    priceMinor: slot.price_minor,
    currency: slot.currency,
    idempotencyKey: keyForSlot(slot.id),
  });

  async function handleRequestEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedSlot || sending) return;
    setSending(true);
    setError(null);
    // A new slot request replaces any unfinished access recovery from an earlier booking.
    clearPendingRecovery();
    savePendingSelection(selectionFor(selectedSlot));
    try {
      await requestEmailVerification(email.trim(), psychologist.public_id);
      setSent(true);
    } catch (requestError) {
      setError(verificationErrorMessage(errorStatus(requestError)));
    } finally {
      setSending(false);
    }
  }

  async function handleBookWithGrant() {
    if (!selectedSlot || !grant || booking) return;
    setBooking(true);
    setError(null);
    const result = await holdSlot(selectionFor(selectedSlot), grant);
    // Keep the key only when the outcome is unknown (network error), so that a retry replays it.
    if (result.kind !== "error") attemptKey.current = null;
    switch (result.kind) {
      case "held":
        router.push(`/bookings/${result.bookingId}`);
        return;
      case "slot-taken":
        setError("Цей час щойно забронювали. Оберіть, будь ласка, інший.");
        setSelectedSlotId(null);
        setReloadCounter((value) => value + 1);
        break;
      case "verification-invalid":
        setGrant(null);
        setError("Підтвердження пошти більше не дійсне. Введіть email, щоб отримати нове посилання.");
        break;
      case "no-access":
        setGrant(null);
        setNeedsRecovery(true);
        break;
      default:
        setError("Не вдалося забронювати час. Спробуйте ще раз.");
    }
    setBooking(false);
  }

  return (
    <BookingPageShell>
      <div className="grid gap-6 lg:grid-cols-[1fr_380px] lg:items-start">
        <div className="flex flex-col gap-6">
          <Card className="p-6 sm:p-8">
            <p className="text-[13px] font-bold uppercase tracking-wide text-muted">Запис на консультацію</p>
            <h1 className="mt-2 text-4xl">{psychologist.display_name}</h1>
            <div className="mt-4 flex flex-wrap gap-2">
              {psychologist.session_duration_minutes !== null && (
                <Badge tone="mint">{psychologist.session_duration_minutes} хв</Badge>
              )}
              {psychologist.price_minor !== null && psychologist.currency !== null && (
                <Badge tone="neutral">{formatPrice(psychologist.price_minor, psychologist.currency)}</Badge>
              )}
            </div>
          </Card>

          <Card className="p-6 sm:p-8">
            <h2 className="text-2xl">Оберіть зручний час</h2>
            <p className="mt-1 text-[14px] text-muted">
              Час указано за часовим поясом психолога: {timeZone}.
              {clientTimeZone && clientTimeZone !== timeZone && ` Ваш часовий пояс: ${clientTimeZone}.`}
            </p>

            {days.length === 0 ? (
              <p className="mt-6 rounded-xl bg-surface-muted px-4 py-3 text-muted">
                Наразі немає вільного часу на найближчі 30 днів. Зверніться до психолога напряму або
                загляньте пізніше.
              </p>
            ) : (
              <div className="mt-6 flex flex-col gap-6">
                {days.map((day) => (
                  <section key={day.key} aria-label={day.label}>
                    <h3 className="font-sans text-[15px] font-bold first-letter:uppercase">{day.label}</h3>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {day.slots.map((slot) => {
                        const selected = slot.id === selectedSlotId;
                        return (
                          <button
                            key={slot.id}
                            type="button"
                            aria-pressed={selected}
                            onClick={() => selectSlot(slot.id)}
                            className={cn(
                              "h-11 rounded-[10px] border px-4 text-[15px] font-bold transition-colors",
                              "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink",
                              selected
                                ? "border-ink bg-ink text-white"
                                : "border-line bg-white text-ink hover:bg-mint-50",
                            )}
                          >
                            {formatTime(slot.starts_at, timeZone)}
                          </button>
                        );
                      })}
                    </div>
                  </section>
                ))}
              </div>
            )}
          </Card>
        </div>

        <Card className="flex flex-col gap-4 p-6 sm:p-8 lg:sticky lg:top-24">
          <h2 className="text-2xl">Ваше бронювання</h2>
          {!selectedSlot ? (
            <p className="text-muted">Оберіть час у розкладі, щоб продовжити.</p>
          ) : (
            <>
              <div className="rounded-xl bg-mint-50 px-4 py-3">
                <p className="font-bold first-letter:uppercase">
                  {formatSlot(selectedSlot.starts_at, selectedSlot.ends_at, timeZone)}
                </p>
                <p className="mt-1 text-muted">{formatPrice(selectedSlot.price_minor, selectedSlot.currency)}</p>
              </div>

              {grant ? (
                <>
                  <Notice>Вашу пошту вже підтверджено.</Notice>
                  <Button fullWidth disabled={booking} onClick={handleBookWithGrant}>
                    {booking ? "Бронюємо…" : "Забронювати"}
                  </Button>
                </>
              ) : sent ? (
                <div className="flex flex-col gap-3">
                  <Notice>
                    Перевірте пошту. Ми надіслали лист із посиланням для підтвердження. Посилання
                    дійсне 30 хвилин.
                  </Notice>
                  <p className="text-[14px] text-muted">
                    Після переходу за посиланням ми забронюємо обраний час на 15 хвилин, щоб ви
                    встигли оплатити консультацію.
                  </p>
                  <Button variant="ghost" onClick={() => setSent(false)}>
                    Надіслати ще раз
                  </Button>
                </div>
              ) : (
                <form className="flex flex-col gap-4" onSubmit={handleRequestEmail}>
                  <TextField
                    id="client-email"
                    label="Електронна пошта"
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    hint="Обліковий запис не потрібен — лише підтвердьте пошту."
                    placeholder="name@example.com"
                  />
                  <Button type="submit" fullWidth disabled={sending}>
                    {sending ? "Надсилаємо…" : "Підтвердити пошту"}
                  </Button>
                </form>
              )}
            </>
          )}
          {error && <Notice tone="danger">{error}</Notice>}
          {needsRecovery && (
            <div className="flex flex-col gap-3">
              <Notice tone="warning">
                Ваше бронювання створено, але цей браузер не отримав доступу до нього. Підтвердіть
                пошту ще раз, щоб відкрити бронювання й оплатити його.
              </Notice>
              <RecoverAccessForm psychologistPublicId={psychologist.public_id} />
            </div>
          )}
          <p className="text-[13px] text-muted">
            Скасування чи перенесення консультації узгоджуйте напряму з психологом.
          </p>
        </Card>
      </div>
    </BookingPageShell>
  );
}
