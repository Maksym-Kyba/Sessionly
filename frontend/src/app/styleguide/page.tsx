import type { Metadata } from "next";

import { Badge } from "@/components/ui/Badge";
import { Button, GoogleMark } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Logo } from "@/components/ui/Logo";
import { TextField } from "@/components/ui/TextField";

export const metadata: Metadata = {
  title: "Стиль інтерфейсу · Sessionly",
  robots: { index: false },
};

const swatches = [
  { name: "Mint 50", className: "bg-mint-50", usage: "фон секцій" },
  { name: "Mint 100", className: "bg-mint-100", usage: "бейджі, другорядні кнопки" },
  { name: "Mint 200", className: "bg-mint-200", usage: "рамки, аватари" },
  { name: "Mint 300", className: "bg-mint-300", usage: "кнопки входу через Google, вибраний стан" },
  { name: "Ink", className: "bg-ink", usage: "текст, основні кнопки" },
  { name: "Warning 50", className: "bg-warning-50", usage: "очікує оплати, таймер" },
];

/** Internal reference page that shows the shared design tokens and UI components. */
export default function StyleguidePage() {
  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-12 px-4 py-12 sm:px-8">
      <header className="flex flex-col gap-3">
        <Logo />
        <h1 className="text-4xl sm:text-5xl">Стиль інтерфейсу</h1>
        <p className="text-muted">
          Заголовки — Pangolin, основний текст — Nunito. Кольори — мʼята, білий і графіт.
        </p>
      </header>

      <section className="flex flex-col gap-4">
        <h2 className="text-2xl">Кольори</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          {swatches.map((swatch) => (
            <div key={swatch.name} className="flex flex-col gap-2">
              <div className={`h-20 rounded-2xl border border-line ${swatch.className}`} />
              <b className="text-sm">{swatch.name}</b>
              <span className="text-[13px] text-muted">{swatch.usage}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-2xl">Типографіка</h2>
        <p className="font-display text-5xl">Записи без переписок</p>
        <p className="font-display text-3xl">Як це працює</p>
        <p>Клієнт обирає час і оплачує сесію самостійно.</p>
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-2xl">Кнопки</h2>
        <div className="flex flex-wrap gap-3">
          <Button>Основна дія</Button>
          <Button variant="google">
            <GoogleMark />
            Увійти через Google
          </Button>
          <Button variant="secondary">Другорядна</Button>
          <Button variant="ghost">Контурна</Button>
          <Button size="sm">Мала</Button>
          <Button disabled>Недоступна</Button>
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-2xl">Статуси</h2>
        <div className="flex flex-wrap gap-2">
          <Badge>Підтверджено</Badge>
          <Badge tone="warning">Очікує оплати</Badge>
          <Badge tone="neutral">Проведено</Badge>
          <Badge tone="danger">Скасовано</Badge>
          <Badge tone="ink">Клієнт · без акаунта</Badge>
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-2xl">Картка і поле вводу</h2>
        <Card className="flex max-w-md flex-col gap-4 p-6">
          <TextField id="styleguide-name" label="Імʼя та прізвище" placeholder="Марія Кравець" />
          <TextField
            id="styleguide-email"
            label="Email"
            type="email"
            placeholder="name@example.com"
            hint="Ми надішлемо посилання для підтвердження."
          />
          <Button fullWidth>Надіслати посилання</Button>
        </Card>
      </section>
    </main>
  );
}
