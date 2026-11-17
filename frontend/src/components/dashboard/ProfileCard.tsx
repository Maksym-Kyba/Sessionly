"use client";

import { useEffect, useState } from "react";

import type { CurrentPsychologist } from "@/api/auth";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

/** Absolute URL of the psychologist's public booking page, which they share with clients. */
export function publicBookingUrl(publicId: string): string {
  return `${window.location.origin}/p/${encodeURIComponent(publicId)}`;
}

/** Shows the public booking link with a copy button, and links to the profile settings. */
export function ProfileCard({ psychologist }: { psychologist: CurrentPsychologist }) {
  const [url, setUrl] = useState("");
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  // `window` is only available in the browser, so the absolute URL is built after mounting.
  useEffect(() => {
    setUrl(publicBookingUrl(psychologist.public_id));
  }, [psychologist.public_id]);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(url);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  }

  return (
    <Card className="flex flex-col p-6">
      <h2 className="text-xl text-ink">Профіль</h2>
      <p className="mt-3 text-muted">
        Надішліть клієнтам це посилання, щоб вони могли обрати час і забронювати сесію.
      </p>
      <p className="mt-4 break-all rounded-xl bg-mint-50 px-4 py-3 text-[15px] font-semibold text-ink">
        {url || "…"}
      </p>
      {copyState === "copied" && (
        <p role="status" className="mt-2 text-[13px] text-muted">
          Посилання скопійовано.
        </p>
      )}
      {copyState === "failed" && (
        <p role="alert" className="mt-2 text-[13px] text-danger-700">
          Не вдалося скопіювати. Виділіть посилання й скопіюйте його вручну.
        </p>
      )}
      <div className="mt-5 flex flex-wrap gap-2">
        <Button size="sm" onClick={copyLink} disabled={!url}>
          Копіювати посилання
        </Button>
        <Button href={`/p/${encodeURIComponent(psychologist.public_id)}`} variant="ghost" size="sm">
          Відкрити
        </Button>
        <Button href="/dashboard/profile" variant="secondary" size="sm">
          Редагувати профіль
        </Button>
      </div>
    </Card>
  );
}
