import { Card } from "@/components/ui/Card";

const problems = [
  {
    title: "Години переписок",
    text: "Узгодження вільного часу в месенджерах забирає час між сесіями.",
  },
  {
    title: "Подвійні записи",
    text: "Двоє клієнтів на один час і незручні перенесення.",
  },
  {
    title: "Неоплачені сесії",
    text: "Клієнт не прийшов, а час уже був зарезервований.",
  },
  {
    title: "Ручний календар",
    text: "Кожен запис доводиться переносити в календар самостійно.",
  },
];

/** Section describing the scheduling problems psychologists face today. */
export function ProblemSection() {
  return (
    <section id="problem" className="mx-auto flex max-w-7xl scroll-mt-20 flex-col gap-6 px-4 py-12 sm:gap-9 sm:px-8 sm:py-20">
      <h2 className="text-[26px] sm:text-[38px]">Знайомо?</h2>
      <div className="grid gap-3 sm:grid-cols-2 sm:gap-5 lg:grid-cols-4">
        {problems.map((problem, index) => (
          <Card key={problem.title} className="flex flex-col gap-3 p-6">
            <span className="flex size-11 items-center justify-center rounded-xl bg-mint-100 font-display text-lg">
              {index + 1}
            </span>
            <h3 className="text-lg">{problem.title}</h3>
            <p className="text-muted">{problem.text}</p>
          </Card>
        ))}
      </div>
    </section>
  );
}
