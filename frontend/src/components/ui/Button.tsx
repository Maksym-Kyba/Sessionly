import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/utils/cn";

export type ButtonVariant = "primary" | "google" | "secondary" | "ghost";
export type ButtonSize = "md" | "sm";

const baseClasses =
  "inline-flex items-center justify-center gap-2.5 whitespace-nowrap font-bold transition-colors " +
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink " +
  "disabled:cursor-not-allowed disabled:opacity-50";

const variantClasses: Record<ButtonVariant, string> = {
  primary: "bg-ink text-white hover:bg-ink/90",
  google: "bg-mint-300 text-ink hover:bg-mint-300/80",
  secondary: "bg-mint-100 text-ink hover:bg-mint-200",
  ghost: "border border-line bg-white text-ink hover:bg-mint-50",
};

const sizeClasses: Record<ButtonSize, string> = {
  md: "h-12 rounded-xl px-5 text-base",
  sm: "h-10 rounded-[10px] px-4 text-sm",
};

type StyleProps = {
  /** Visual style. Use `google` only for Google sign-in and sign-up actions. */
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  className?: string;
  children: ReactNode;
};

type ButtonAsButtonProps = StyleProps &
  Omit<ComponentProps<"button">, keyof StyleProps> & { href?: undefined };

type ButtonAsLinkProps = StyleProps &
  Omit<ComponentProps<typeof Link>, keyof StyleProps> & { href: string };

export type ButtonProps = ButtonAsButtonProps | ButtonAsLinkProps;

/** Builds the class list shared by every button style. */
export function buttonClasses({
  variant = "primary",
  size = "md",
  fullWidth = false,
  className,
}: Omit<StyleProps, "children">): string {
  return cn(
    baseClasses,
    variantClasses[variant],
    sizeClasses[size],
    fullWidth && "w-full",
    className,
  );
}

/** Renders a button, or a link styled as a button when `href` is provided. */
export function Button(props: ButtonProps) {
  const { variant, size, fullWidth, className, children, ...rest } = props;
  const classes = buttonClasses({ variant, size, fullWidth, className });

  if (rest.href !== undefined) {
    return (
      <Link {...(rest as Omit<ButtonAsLinkProps, keyof StyleProps>)} className={classes}>
        {children}
      </Link>
    );
  }

  const buttonProps = rest as Omit<ButtonAsButtonProps, keyof StyleProps>;
  return (
    <button type="button" {...buttonProps} className={classes}>
      {children}
    </button>
  );
}

/** Small round "G" mark displayed inside Google sign-in buttons. */
export function GoogleMark() {
  return (
    <span
      aria-hidden="true"
      className="flex size-[22px] shrink-0 items-center justify-center rounded-full bg-white text-[13px] font-extrabold text-ink"
    >
      G
    </span>
  );
}
