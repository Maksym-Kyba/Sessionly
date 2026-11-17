import type { ReactNode } from "react";

import { Logo } from "@/components/ui/Logo";
import { cn } from "@/utils/cn";

type BookingPageShellProps = {
  className?: string;
  children: ReactNode;
};

/** Minimal page frame for the public client booking flow. */
export function BookingPageShell({ className, children }: BookingPageShellProps) {
  return (
    <div className="flex min-h-screen flex-col bg-mint-50">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex h-16 max-w-5xl items-center px-4 sm:px-8">
          <Logo />
        </div>
      </header>
      <main className={cn("mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-8 sm:py-12", className)}>
        {children}
      </main>
    </div>
  );
}

type NoticeProps = {
  tone?: "info" | "danger" | "warning";
  children: ReactNode;
};

const noticeTones = {
  info: "bg-mint-100 text-ink",
  warning: "bg-warning-50 text-warning-700",
  danger: "bg-danger-50 text-danger-700",
};

/** Inline message block used for errors and status hints. */
export function Notice({ tone = "info", children }: NoticeProps) {
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn("rounded-xl px-4 py-3 text-[15px] font-semibold", noticeTones[tone])}
    >
      {children}
    </div>
  );
}
