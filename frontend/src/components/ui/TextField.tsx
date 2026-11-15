import type { ComponentProps } from "react";

import { cn } from "@/utils/cn";

type TextFieldProps = Omit<ComponentProps<"input">, "id"> & {
  /** Required so the label is always associated with its input. */
  id: string;
  label: string;
  hint?: string;
};

/** Labelled single-line text input. */
export function TextField({ id, label, hint, className, ...inputProps }: TextFieldProps) {
  const hintId = hint ? `${id}-hint` : undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-bold text-ink">
        {label}
      </label>
      <input
        id={id}
        aria-describedby={hintId}
        {...inputProps}
        className={cn(
          "h-12 rounded-xl border border-line bg-white px-4 text-[15px] text-ink",
          "placeholder:text-muted focus:border-mint-300 focus:outline-2 focus:outline-mint-200",
          className,
        )}
      />
      {hint && (
        <p id={hintId} className="text-[13px] text-muted">
          {hint}
        </p>
      )}
    </div>
  );
}
