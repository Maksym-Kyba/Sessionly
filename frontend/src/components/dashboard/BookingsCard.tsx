"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { BookingsUnauthorizedError, listMyBookings, type PsychologistBooking } from "@/api/bookings";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

type BookingsState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "loaded"; bookings: PsychologistBooking[]; total: number };

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
    listMyBookings()
      .then((page) => {
        if (!cancelled) setState({ status: "loaded", bookings: page.items, total: page.total });
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

  const now = Date.now();
  const upcoming =
    state.status === "loaded"
      ? state.bookings.filter((booking) => new Date(booking.ends_at).getTime() >= now)
      : [];
  // The backend orders bookings by start time ascending; show the most recent past sessions first.
  const past =
    state.status === "loaded"
      ? state.bookings.filter((booking) => new Date(booking.ends_at).getTime() < now).reverse()
      : [];

  return (
    <Card className="mt-10 p-6">
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-xl text-ink">Записи</h2>
        {state.status === "loaded" && state.total > 0 && (
          <Badge tone="neutral">Усього: {state.total}</Badge>
        )}
      </div>

      {state.status === "loading" && <p className="mt-3 text-muted">Завантаження записів…</p>}

      {state.status === "error" && (
        <p role="alert" className="mt-3 rounded-xl bg-danger-50 px-4 py-3 text-danger-700">
          Не вдалося завантажити записи. Оновіть сторінку або спробуйте пізніше.
        </p>
      )}

      {state.status === "loaded" && state.bookings.length === 0 && (
        <p className="mt-3 text-muted">
          Записів поки немає. Щойно клієнт забронює сесію, вона з&apos;явиться тут.
        </p>
      )}

      {state.status === "loaded" && state.bookings.length > 0 && (
        <>
          {upcoming.length === 0 && <p className="mt-3 text-muted">Найближчих сесій немає.</p>}
          <BookingList title="Найближчі" bookings={upcoming} timeZone={timeZone} />
          <BookingList title="Минулі" bookings={past} timeZone={timeZone} />
          {state.total > state.bookings.length && (
            <p className="mt-4 text-sm text-muted">
              Показано {state.bookings.length} із {state.total} записів.
            </p>
          )}
        </>
      )}
    </Card>
  );
}
