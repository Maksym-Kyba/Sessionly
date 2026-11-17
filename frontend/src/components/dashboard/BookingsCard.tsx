"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { BookingsUnauthorizedError, listMyBookings, type PsychologistBooking } from "@/api/bookings";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

type BookingsState =
  | { status: "loading" }
  | { status: "error" }
  | {
      status: "loaded";
      upcoming: PsychologistBooking[];
      upcomingTotal: number;
      /** Most recent past bookings, newest first. */
      past: PsychologistBooking[];
      pastTotal: number;
    };

const UPCOMING_LIMIT = 100;
const PAST_LIMIT = 20;

/**
 * Loads upcoming bookings with `from=now` and the most recent past bookings. The list is ordered by
 * `starts_at` ascending, so past bookings occupy the first `pastTotal` positions of the unfiltered
 * list, where `pastTotal` is the unfiltered total minus the filtered one.
 */
async function loadBookings(): Promise<Extract<BookingsState, { status: "loaded" }>> {
  const now = new Date();
  const [upcomingPage, allPage] = await Promise.all([
    listMyBookings({ limit: UPCOMING_LIMIT, from: now }),
    listMyBookings({ limit: 1 }),
  ]);
  const pastTotal = Math.max(0, allPage.total - upcomingPage.total);
  let past: PsychologistBooking[] = [];
  if (pastTotal > 0) {
    const pastPage = await listMyBookings({
      limit: Math.min(PAST_LIMIT, pastTotal),
      offset: Math.max(0, pastTotal - PAST_LIMIT),
    });
    // Guards against a booking created between the requests shifting the page.
    past = pastPage.items
      .filter((booking) => new Date(booking.starts_at).getTime() < now.getTime())
      .reverse();
  }
  return {
    status: "loaded",
    upcoming: upcomingPage.items,
    upcomingTotal: upcomingPage.total,
    past,
    pastTotal,
  };
}

const statusLabels: Record<string, { label: string; tone: BadgeTone }> = {
  HELD: { label: "Очікує оплати", tone: "warning" },
  CONFIRMED: { label: "Підтверджено", tone: "mint" },
  EXPIRED: { label: "Час вийшов", tone: "neutral" },
};

function statusBadge(status: string) {
  const known = statusLabels[status];
  return <Badge tone={known?.tone ?? "neutral"}>{known?.label ?? status}</Badge>;
}

function formatSlot(booking: PsychologistBooking, timeZone: string): string {
  const date = new Intl.DateTimeFormat("uk-UA", {
    timeZone,
    weekday: "short",
    day: "numeric",
    month: "long",
  }).format(new Date(booking.starts_at));
  const time = new Intl.DateTimeFormat("uk-UA", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${date}, ${time.format(new Date(booking.starts_at))}–${time.format(new Date(booking.ends_at))}`;
}

function formatPrice(booking: PsychologistBooking): string {
  return new Intl.NumberFormat("uk-UA", {
    style: "currency",
    currency: booking.currency,
    maximumFractionDigits: booking.price_minor % 100 === 0 ? 0 : 2,
  }).format(booking.price_minor / 100);
}

function BookingRow({ booking, timeZone }: { booking: PsychologistBooking; timeZone: string }) {
  return (
    <li className="flex flex-col gap-2 py-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="font-bold text-ink">{formatSlot(booking, timeZone)}</p>
        <p className="mt-1 truncate text-sm text-muted">
          {booking.client_email ?? "Email не вказано"} · {booking.session_duration_minutes} хв ·{" "}
          {formatPrice(booking)}
        </p>
      </div>
      {statusBadge(booking.status)}
    </li>
  );
}

function BookingList({
  title,
  bookings,
  timeZone,
}: {
  title: string;
  bookings: PsychologistBooking[];
  timeZone: string;
}) {
  if (bookings.length === 0) return null;
  return (
    <section className="mt-6">
      <h3 className="text-sm font-bold uppercase tracking-wide text-muted">{title}</h3>
      <ul className="divide-y divide-line">
        {bookings.map((booking) => (
          <BookingRow key={booking.id} booking={booking} timeZone={timeZone} />
        ))}
      </ul>
    </section>
  );
}

/** Lists the signed-in psychologist's bookings, split into upcoming and past sessions. */
export function BookingsCard({ timeZone }: { timeZone: string }) {
  const router = useRouter();
  const [state, setState] = useState<BookingsState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    loadBookings()
      .then((loaded) => {
        if (!cancelled) setState(loaded);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof BookingsUnauthorizedError) {
          router.replace("/");
          return;
        }
        setState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  const total = state.status === "loaded" ? state.upcomingTotal + state.pastTotal : 0;

  return (
    <Card className="mt-10 p-6">
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-xl text-ink">Записи</h2>
        {total > 0 && <Badge tone="neutral">Усього: {total}</Badge>}
      </div>

      {state.status === "loading" && <p className="mt-3 text-muted">Завантаження записів…</p>}

      {state.status === "error" && (
        <p role="alert" className="mt-3 rounded-xl bg-danger-50 px-4 py-3 text-danger-700">
          Не вдалося завантажити записи. Оновіть сторінку або спробуйте пізніше.
        </p>
      )}

      {state.status === "loaded" && total === 0 && (
        <p className="mt-3 text-muted">
          Записів поки немає. Щойно клієнт забронює сесію, вона з&apos;явиться тут.
        </p>
      )}

      {state.status === "loaded" && total > 0 && (
        <>
          {state.upcoming.length === 0 && (
            <p className="mt-3 text-muted">Найближчих сесій немає.</p>
          )}
          <BookingList title="Найближчі" bookings={state.upcoming} timeZone={timeZone} />
          {state.upcomingTotal > state.upcoming.length && (
            <p className="mt-2 text-sm text-muted">
              Показано {state.upcoming.length} найближчих із {state.upcomingTotal}.
            </p>
          )}
          <BookingList title="Минулі" bookings={state.past} timeZone={timeZone} />
          {state.pastTotal > state.past.length && state.past.length > 0 && (
            <p className="mt-2 text-sm text-muted">
              Показано останні {state.past.length} із {state.pastTotal}.
            </p>
          )}
        </>
      )}
    </Card>
  );
}
