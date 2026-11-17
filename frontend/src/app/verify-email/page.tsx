"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { errorStatus } from "@/api/errors";
import { consumeEmailVerification } from "@/api/public";
import { BookingPageShell } from "@/components/booking/BookingPageShell";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { loadPendingSelection, saveGrant } from "@/utils/clientBookingStorage";
import { holdSlot } from "@/utils/holdSlot";

type VerifyState =
  | { status: "working" }
  | { status: "invalid-link"; psychologistPublicId: string | null }
  | { status: "rate-limited" }
  | { status: "slot-taken"; psychologistPublicId: string }
  | { status: "no-access" }
  | { status: "error"; psychologistPublicId: string | null };

/** Reads the verification token from the URL fragment and removes it from browser history. */
function takeTokenFromFragment(): string | null {
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  const token = fragment.get("token");
  if (window.location.hash) {
    window.history.replaceState(
      window.history.state,
      "",
      window.location.pathname + window.location.search,
    );
  }
  return token;
}

/**
 * Landing page of the email verification link (`CLIENT_VERIFICATION_LINK_BASE_URL`).
 * Consumes the one-time token and then holds the slot the client selected before verifying.
 */
export default function VerifyEmailPage() {
  const router = useRouter();
  const [state, setState] = useState<VerifyState>({ status: "working" });
  // The token is single-use, so the flow must run exactly once, including in React strict mode.
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const token = takeTokenFromFragment();
    const selection = loadPendingSelection();

    async function run() {
      if (!token) {
        setState({ status: "invalid-link", psychologistPublicId: selection?.psychologistPublicId ?? null });
        return;
      }

      let grant;
      try {
        const verified = await consumeEmailVerification(token);
        grant = {
          token: verified.booking_verification_token,
          expiresAt: verified.expires_at,
          psychologistPublicId: verified.psychologist_public_id,
        };
      } catch (error) {
        const status = errorStatus(error);
        if (status === 429) {
          setState({ status: "rate-limited" });
        } else if (status === 400 || status === 422) {
          setState({ status: "invalid-link", psychologistPublicId: selection?.psychologistPublicId ?? null });
        } else {
          setState({ status: "error", psychologistPublicId: selection?.psychologistPublicId ?? null });
        }
        return;
      }

      // Keep the grant for this tab so the client can pick another slot if needed.
      saveGrant(grant);

      if (!selection || selection.psychologistPublicId !== grant.psychologistPublicId) {
        // The selected slot did not survive (another browser or device): let the client choose again.
        router.replace(`/p/${encodeURIComponent(grant.psychologistPublicId)}`);
        return;
      }

      const result = await holdSlot(selection, grant);
      switch (result.kind) {
        case "held":
          router.replace(`/bookings/${result.bookingId}`);
          return;
        case "slot-taken":
          setState({ status: "slot-taken", psychologistPublicId: grant.psychologistPublicId });
          return;
        case "verification-invalid":
          setState({ status: "invalid-link", psychologistPublicId: grant.psychologistPublicId });
          return;
        case "no-access":
          setState({ status: "no-access" });
          return;
        default:
          setState({ status: "error", psychologistPublicId: grant.psychologistPublicId });
      }
    }

    void run();
  }, [router]);

  return (
    <BookingPageShell>
      <Card className="mx-auto flex max-w-xl flex-col items-center gap-4 p-8 text-center">
        <VerifyContent state={state} />
      </Card>
    </BookingPageShell>
  );
}

function backToPsychologist(publicId: string | null, label: string) {
  if (!publicId) return null;
  return <Button href={`/p/${encodeURIComponent(publicId)}`}>{label}</Button>;
}

function VerifyContent({ state }: { state: VerifyState }) {
  switch (state.status) {
    case "working":
      return (
        <>
          <h1 className="text-3xl">Підтверджуємо пошту…</h1>
          <p className="text-muted">Зачекайте кілька секунд, ми бронюємо обраний час.</p>
        </>
      );
    case "invalid-link":
      return (
        <>
          <h1 className="text-3xl">Посилання недійсне</h1>
          <p className="text-muted">
            Посилання для підтвердження застаріло або вже було використане. Поверніться на сторінку
            психолога та запросіть новий лист.
          </p>
          {backToPsychologist(state.psychologistPublicId, "Повернутися до розкладу")}
        </>
      );
    case "rate-limited":
      return (
        <>
          <h1 className="text-3xl">Забагато спроб</h1>
          <p className="text-muted">Зачекайте хвилину та відкрийте посилання з листа ще раз.</p>
        </>
      );
    case "slot-taken":
      return (
        <>
          <h1 className="text-3xl">Цей час уже зайнятий</h1>
          <p className="text-muted">
            Вашу пошту підтверджено, але обраний час щойно забронював хтось інший. Оберіть, будь
            ласка, інший час — повторно підтверджувати пошту не потрібно.
          </p>
          {backToPsychologist(state.psychologistPublicId, "Обрати інший час")}
        </>
      );
    case "no-access":
      return (
        <>
          <h1 className="text-3xl">Бронювання вже створено</h1>
          <p className="text-muted">
            Це бронювання вже було створено раніше. Відкрийте його в тому браузері, у якому ви
            бронювали час.
          </p>
        </>
      );
    case "error":
      return (
        <>
          <h1 className="text-3xl">Щось пішло не так</h1>
          <p className="text-muted">
            Не вдалося завершити бронювання. Перевірте з’єднання з інтернетом і спробуйте ще раз.
          </p>
          {backToPsychologist(state.psychologistPublicId, "Повернутися до розкладу")}
        </>
      );
  }
}
