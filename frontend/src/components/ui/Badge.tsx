import type { ReactNode } from "react";

import { cn } from "@/utils/cn";

export type BadgeTone = "mint" | "warning" | "neutral" | "danger" | "ink";

const toneClasses: Record<BadgeTone, string> = {
  mint: "bg-mint-100 text-ink",
  warning: "bg-warning-50 text-warning-700",
  neutral: "bg-surface-muted text-muted",
  danger: "bg-danger-50 text-danger-700",
  ink: "bg-ink text-white",
};

type BadgeProps = {
  tone?: BadgeTone;
  className?: string;
  children: ReactNode;
};

/** Compact pill used for statuses and short labels. */
export function Badge({ tone = "mint", className, children }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex h-[30px] shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-3 text-[13px] font-bold",
        toneClasses[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
