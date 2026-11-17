"use client";

import { useEffect, useState } from "react";

import { type CurrentPsychologist, getCurrentPsychologist } from "@/api/auth";

export type CurrentPsychologistState =
  | { status: "loading" }
  | { status: "signed-out" }
  | { status: "signed-in"; psychologist: CurrentPsychologist }
  | { status: "error" };

/** Loads the signed-in psychologist once when the component mounts. */
export function useCurrentPsychologist(): CurrentPsychologistState {
  const [state, setState] = useState<CurrentPsychologistState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    getCurrentPsychologist()
      .then((psychologist) => {
        if (cancelled) return;
        setState(
          psychologist ? { status: "signed-in", psychologist } : { status: "signed-out" },
        );
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
