"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { type ClientBooking, getClientBooking } from "@/api/booking";
import { BookingPageShell, Notice } from "@/components/booking/BookingPageShell";
import { PaymentAction } from "@/components/booking/PaymentAction";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { loadBookingAccess, type StoredBookingAccess } from "@/utils/clientBookingStorage";
import { browserTimeZone, formatCountdown, formatPrice, formatSlot } from "@/utils/format";

type LoadState =
  | { status: "loading" }
  | { status: "no-access" }
  | { status: "error" }
  | { status: "ready"; booking: ClientBooking; access: StoredBookingAccess };

/** Status shown to the client; a held booking past its deadline is displayed as expired. */
type DisplayStatus = "HELD" | "CONFIRMED" | "EXPIRED";

const statusLabels: Record<DisplayStatus, { label: string; tone: BadgeTone }> = {
  HELD: { label: "Очікує оплати", tone: "warning" },
  CONFIRMED: { label: "Підтверджено", tone: "mint" },
  EXPIRED: { label: "Час бронювання минув", tone: "danger" },
};

/** Ticks once per second and returns the current time in milliseconds. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  return now;
}

/** Booking status page for a client, authorised by the access token stored in this browser. */
export default function BookingStatusPage() {
  const { id } = useParams<{ id: string }>();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [reloadCounter, setReloadCounter] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const access = loadBookingAccess(id);
    if (!access) {
      setState({ status: "no-access" });
      return;
    }
    getClientBooking(id, access.token)
      .then((booking) => {
        if (cancelled) return;
        setState(booking ? { status: "ready", booking, access } : { status: "no-access" });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [id, reloadCounter]);

  const isHeld = state.status === "ready" && state.booking.status === "HELD";
  const now = useNow(isHeld);

  if (state.status === "loading") {
    return (
      <BookingPageShell>
        <p className="text-muted">Завантаження…</p>
      </BookingPageShell>
    );
  }

  if (state.status === "no-access") {
    return (
      <BookingPageShell>
        <Card className="mx-auto max-w-xl p-8 text-center">
          <h1 className="text-3xl">Бронювання недоступне</h1>
          <p className="mt-3 text-muted">
            Не вдалося відкрити це бронювання. Сторінка доступна лише в тому браузері, у якому ви
            бронювали час. Якщо потрібна допомога, зверніться до психолога напряму.
          </p>
        </Card>
      </BookingPageShell>
    );
  }

  if (state.status === "error") {
    return (
      <BookingPageShell>
        <Card className="mx-auto flex max-w-xl flex-col items-center gap-4 p-8 text-center">
          <h1 className="text-3xl">Не вдалося завантажити бронювання</h1>
          <p className="text-muted">Перевірте з’єднання з інтернетом і спробуйте ще раз.</p>
          <Button variant="ghost" onClick={() => setReloadCounter((value) => value + 1)}>
            Спробувати ще раз
          </Button>
        </Card>
      </BookingPageShell>
    );
  }

  const { booking, access } = state;
  const timeZone = access.timeZone || browserTimeZone() || "UTC";
  const remainingMs = new Date(booking.hold_expires_at).getTime() - now;
  const displayStatus: DisplayStatus =
    booking.status === "HELD" && remainingMs <= 0 ? "EXPIRED" : booking.status;
  const price = formatPrice(booking.price_minor, booking.currency);
  const statusBadge = statusLabels[displayStatus];

  return (
    <BookingPageShell>
      <Card className="mx-auto flex max-w-xl flex-col gap-6 p-6 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[13px] font-bold uppercase tracking-wide text-muted">Бронювання</p>
            <h1 className="mt-1 text-3xl">{access.psychologistName}</h1>
          </div>
          <Badge tone={statusBadge.tone}>{statusBadge.label}</Badge>
        </div>

        <dl className="grid gap-3 rounded-xl bg-mint-50 px-4 py-4 text-[15px]">
          <div>
            <dt className="text-[13px] font-bold text-muted">Дата й час</dt>
            <dd className="font-bold first-letter:uppercase">
              {formatSlot(booking.starts_at, booking.ends_at, timeZone)}
            </dd>
            <dd className="text-[13px] text-muted">Часовий пояс: {timeZone}</dd>
          </div>
          <div className="flex gap-8">
            <div>
              <dt className="text-[13px] font-bold text-muted">Тривалість</dt>
              <dd className="font-bold">{booking.session_duration_minutes} хв</dd>
            </div>
            <div>
              <dt className="text-[13px] font-bold text-muted">Вартість</dt>
              <dd className="font-bold">{price}</dd>
            </div>
          </div>
        </dl>

        {displayStatus === "HELD" && (
          <>
            <div className="text-center">
              <p className="text-muted">Час заброньовано для вас ще</p>
              <p className="font-display text-5xl" aria-live="off">
                {formatCountdown(remainingMs)}
              </p>
              <p className="mt-1 text-[13px] text-muted">
                Оплатіть консультацію до завершення відліку, інакше бронювання буде скасовано.
              </p>
            </div>
            <PaymentAction amountLabel={price} />
          </>
        )}

        {displayStatus === "EXPIRED" && (
          <div className="flex flex-col gap-4">
            <Notice tone="warning">
              15 хвилин на оплату минули, тому цей час знову доступний для запису. Ви можете обрати
              новий час.
            </Notice>
            <Button href={`/p/${encodeURIComponent(access.psychologistPublicId)}`}>Обрати новий час</Button>
          </div>
        )}

        {displayStatus === "CONFIRMED" && (
          <Notice>Консультацію підтверджено. Психолог чекає на вас у призначений час.</Notice>
        )}

        <p className="text-[13px] text-muted">
          Скасування чи перенесення консультації узгоджуйте напряму з психологом.
        </p>
      </Card>
    </BookingPageShell>
  );
}
