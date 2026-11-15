import Link from "next/link";

/** Sessionly wordmark that links to the home page. */
export function Logo() {
  return (
    <Link href="/" className="inline-flex items-center gap-2.5 font-display text-xl text-ink">
      <span
        aria-hidden="true"
        className="flex size-[34px] items-center justify-center rounded-[10px] bg-mint-300 text-lg"
      >
        S
      </span>
      Sessionly
    </Link>
  );
}
