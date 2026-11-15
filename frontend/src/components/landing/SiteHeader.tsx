import { Button, GoogleMark } from "@/components/ui/Button";
import { Logo } from "@/components/ui/Logo";
import { GOOGLE_SIGN_IN_URL } from "@/config/api";

/** Top navigation of the public landing page. */
export function SiteHeader() {
  return (
    <header className="border-b border-line bg-white">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:h-[76px] sm:px-8">
        <Logo />
        <nav aria-label="Основна навігація" className="hidden gap-8 text-[15px] font-semibold text-muted md:flex">
          <a href="#problem" className="hover:text-ink">
            Для кого
          </a>
          <a href="#how-it-works" className="hover:text-ink">
            Як це працює
          </a>
        </nav>
        <Button href={GOOGLE_SIGN_IN_URL} variant="google" size="sm">
          <GoogleMark />
          <span className="sm:hidden">Увійти</span>
          <span className="hidden sm:inline">Увійти через Google</span>
        </Button>
      </div>
    </header>
  );
}
