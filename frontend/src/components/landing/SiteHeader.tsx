import { HeaderAccountButton } from "@/components/landing/HeaderAccountButton";
import { Logo } from "@/components/ui/Logo";

/** Top navigation of the public landing page. */
export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-white">
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
        <HeaderAccountButton />
      </div>
    </header>
  );
}
