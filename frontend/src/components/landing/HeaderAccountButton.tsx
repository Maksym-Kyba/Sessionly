"use client";

import { Button, GoogleMark } from "@/components/ui/Button";
import { GOOGLE_SIGN_IN_URL } from "@/config/api";
import { useCurrentPsychologist } from "@/hooks/useCurrentPsychologist";

/** Shows a link to the dashboard for a signed-in psychologist, or the Google sign-in button. */
export function HeaderAccountButton() {
  const state = useCurrentPsychologist();

  if (state.status === "signed-in") {
    return (
      <Button href="/dashboard" variant="primary" size="sm">
        Кабінет
      </Button>
    );
  }

  return (
    <Button href={GOOGLE_SIGN_IN_URL} variant="google" size="sm">
      <GoogleMark />
      <span className="sm:hidden">Увійти</span>
      <span className="hidden sm:inline">Увійти через Google</span>
    </Button>
  );
}
