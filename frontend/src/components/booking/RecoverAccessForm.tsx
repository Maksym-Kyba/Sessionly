"use client";

import { type FormEvent, useState } from "react";

import { errorStatus } from "@/api/errors";
import { requestEmailVerification } from "@/api/public";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/TextField";
import { verificationErrorMessage } from "@/utils/verificationErrors";

/**
 * Shown when a booking exists but this browser has no access token for it. The client confirms the
 * email again; the verification page then recovers access through the pending recovery record.
 */
export function RecoverAccessForm({ psychologistPublicId }: { psychologistPublicId: string }) {
  const [email, setEmail] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sending) return;
    setSending(true);
    setError(null);
    try {
      await requestEmailVerification(email.trim(), psychologistPublicId);
      setSent(true);
    } catch (requestError) {
      setError(verificationErrorMessage(errorStatus(requestError)));
    } finally {
      setSending(false);
    }
  }

  if (sent) {
    return (
      <p role="status" className="text-muted">
        Ми надіслали новий лист. Відкрийте посилання з нього в цьому браузері, щоб перейти до
        бронювання.
      </p>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex w-full flex-col gap-3 text-left">
      <TextField
        id="recover-email"
        label="Email, на який ви бронювали"
        type="email"
        required
        autoComplete="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
      />
      {error && (
        <p role="alert" className="text-danger-700">
          {error}
        </p>
      )}
      <Button type="submit" fullWidth disabled={sending}>
        {sending ? "Надсилаємо…" : "Надіслати лист ще раз"}
      </Button>
    </form>
  );
}
