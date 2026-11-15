import type { ComponentProps } from "react";

import { cn } from "@/utils/cn";

/** White surface with a light mint border and rounded corners. */
export function Card({ className, ...props }: ComponentProps<"div">) {
  return <div {...props} className={cn("rounded-2xl border border-line bg-white", className)} />;
}
