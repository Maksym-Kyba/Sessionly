import { Card } from "@/components/ui/Card";

const steps = [
  {
    title: "Налаштуйте години",
    text: "Вкажіть вільний час на місяць, тривалість і ціну сесії.",
  },
  {
    title: "Поділіться посиланням",
    text: "Надішліть клієнтам персональне посилання на бронювання.",
  },
  {
    title: "Отримуйте оплачені записи",
    text: "Після оплати запис підтверджується автоматично й зʼявляється у вашому кабінеті.",
  },
];

/** Three-step explanation of the booking flow for psychologists and clients. */
export function HowItWorksSection() {
  return (
    <section id="how-it-works" className="scroll-mt-20 bg-mint-50">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-12 sm:gap-9 sm:px-8 sm:py-20">
        <h2 className="text-[26px] sm:text-[38px]">Як це працює</h2>
        <ol className="grid gap-3 sm:gap-5 lg:grid-cols-3">
          {steps.map((step, index) => (
            <li key={step.title}>
              <Card className="flex h-full flex-col gap-3 p-6">
                <span className="flex size-10 items-center justify-center rounded-full bg-ink font-display text-white">
                  {index + 1}
                </span>
                <h3 className="text-lg">{step.title}</h3>
                <p className="text-muted">{step.text}</p>
              </Card>
            </li>
          ))}
        </ol>
        <p className="flex items-start gap-3.5 rounded-2xl bg-white p-5 sm:items-center sm:px-6">
          <span
            aria-hidden="true"
            className="flex size-[18px] shrink-0 items-center justify-center rounded-full bg-mint-300 text-[11px] font-extrabold"
          >
            ✓
          </span>
          <span>
            <b>Для клієнта:</b> підтверджує email, обирає час і оплачує. Слот резервується на 15
            хвилин, поки триває оплата.
          </span>
        </p>
      </div>
    </section>
  );
}
