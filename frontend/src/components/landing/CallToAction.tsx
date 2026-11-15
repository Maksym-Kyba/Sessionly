import { Button, GoogleMark } from "@/components/ui/Button";
import { GOOGLE_SIGN_IN_URL } from "@/config/api";

/** Closing invitation to sign up with Google. */
export function CallToAction() {
  return (
    <section className="mx-auto max-w-7xl px-4 py-12 sm:px-8 sm:py-20">
      <div className="flex flex-col items-start gap-5 rounded-3xl bg-ink p-7 text-white sm:flex-row sm:items-center sm:justify-between sm:p-14">
        <div className="flex flex-col gap-2">
          <h2 className="text-2xl sm:text-[34px]">Спробуйте Sessionly</h2>
          <p className="text-white/85">Вхід через Google — налаштування займе кілька хвилин.</p>
        </div>
        <Button href={GOOGLE_SIGN_IN_URL} variant="google" className="w-full sm:w-auto">
          <GoogleMark />
          Почати з Google
        </Button>
      </div>
    </section>
  );
}
