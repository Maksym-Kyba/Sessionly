import { Badge } from "@/components/ui/Badge";
import { Button, GoogleMark } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { GOOGLE_SIGN_IN_URL } from "@/config/api";

/** Illustrative sessions for the dashboard preview; not real client data. */
const previewSessions = [
  { time: "10:00", initials: "МК", name: "Марія К.", paid: true },
  { time: "13:00", initials: "АП", name: "Андрій П.", paid: true },
  { time: "17:00", initials: "ОС", name: "Ольга С.", paid: false },
];

/** Opening section with the value proposition and the main call to action. */
export function Hero() {
  return (
    <section className="bg-linear-to-b from-mint-50 to-white">
      <div className="mx-auto flex max-w-7xl flex-col gap-10 px-4 py-12 sm:px-8 lg:flex-row lg:items-center lg:gap-16 lg:py-24">
        <div className="flex flex-1 flex-col items-start gap-6">
          <Badge>Для незалежних психологів</Badge>
          <h1 className="text-[34px] leading-tight sm:text-5xl lg:text-[56px]">
            Записи, оплати та розклад — в одному місці
          </h1>
          <p className="max-w-xl text-base text-muted sm:text-[19px] sm:leading-relaxed">
            Клієнти самі обирають вільний час і оплачують сесію. Ви отримуєте підтверджений запис —
            без переписок у месенджерах.
          </p>
          <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
            <Button href={GOOGLE_SIGN_IN_URL} variant="google">
              <GoogleMark />
              Почати з Google
            </Button>
            <Button href="#how-it-works" variant="ghost">
              Як це працює
            </Button>
          </div>
        </div>

        <Card
          className="flex w-full flex-col gap-3.5 p-4 shadow-[0_24px_60px_rgba(34,48,46,0.10)] sm:p-6 lg:w-[520px]"
        >
          <div className="flex items-center justify-between">
            <h2 className="text-lg">Найближчі сесії</h2>
            <Badge>Сьогодні · 3</Badge>
          </div>
          {previewSessions.map((session) => (
            <div key={session.time} className="flex items-center gap-3.5 rounded-xl bg-mint-50 p-3.5">
              <span className="w-14 font-display text-[15px]">{session.time}</span>
              <span className="hidden size-9 shrink-0 items-center justify-center rounded-full bg-mint-200 text-[13px] font-extrabold sm:flex">
                {session.initials}
              </span>
              <div className="flex min-w-0 flex-1 flex-col">
                <b className="truncate">{session.name}</b>
                <span className="text-[13px] text-muted">50 хв · онлайн</span>
              </div>
              <Badge tone={session.paid ? "mint" : "warning"}>
                {session.paid ? "Оплачено" : "Очікує оплати"}
              </Badge>
            </div>
          ))}
        </Card>
      </div>
    </section>
  );
}
