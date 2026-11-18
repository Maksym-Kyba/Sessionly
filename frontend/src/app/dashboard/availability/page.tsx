"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import {
  ApiError,
  type AvailabilityRule,
  type AvailabilityRuleInput,
  createAvailabilityRule,
  deleteAvailabilityRule,
  listAvailabilityRules,
  updateAvailabilityRule,
} from "@/api/availability";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Logo } from "@/components/ui/Logo";
import { TextField } from "@/components/ui/TextField";
import { useCurrentPsychologist } from "@/hooks/useCurrentPsychologist";

/** Weekday names indexed as the backend expects: Monday is 0 and Sunday is 6. */
const WEEKDAYS = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"];

/** Ukrainian labels for rule fields, used to explain backend validation errors. */
const FIELD_LABELS: Record<string, string> = {
  weekday: "День тижня",
  local_start: "Початок",
  local_end: "Кінець",
  session_duration_minutes: "Тривалість сесії",
  price_minor: "Вартість",
  currency: "Валюта",
  valid_from: "Діє з",
  valid_until: "Діє до",
};

/** Ukrainian translations of known backend error messages, matched by substring. */
const KNOWN_MESSAGES: [string, string][] = [
  ["local_end must be later than local_start", "Кінець має бути пізніше за початок того ж дня."],
  [
    "session_duration_minutes must fit inside",
    "Тривалість сесії має вміщатися в проміжок між початком і кінцем.",
  ],
  ["valid_until must not precede valid_from", "Дата завершення не може бути раніше за дату початку."],
  [
    "contains no occurrence of the selected weekday",
    "У вибраному діапазоні дат немає жодного такого дня тижня.",
  ],
  ["minute precision", "Час має бути вказано з точністю до хвилини."],
  ["Only UAH is supported", "Наразі підтримується лише гривня."],
  [
    "overlap with different times, duration, or price",
    "Правило перетинається з іншим правилом цього дня, що має інший час, тривалість або ціну.",
  ],
  [
    "different prices for one slot",
    "Правила, що перетинаються, задають різну ціну для того самого часу.",
  ],
  [
    "generate overlapping appointment slots",
    "Правила створюють сесії, що накладаються одна на одну.",
  ],
];

type FormValues = {
  weekday: string;
  localStart: string;
  localEnd: string;
  durationMinutes: string;
  priceUah: string;
  validFrom: string;
  validUntil: string;
};

type RulesState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "loaded"; rules: AvailabilityRule[] };

/** Today's date (`YYYY-MM-DD`) in the given IANA timezone. */
function todayIn(timeZone: string): string {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone }).format(new Date());
  } catch {
    return new Date().toISOString().slice(0, 10);
  }
}

function emptyForm(timeZone: string): FormValues {
  return {
    weekday: "0",
    localStart: "09:00",
    localEnd: "17:00",
    durationMinutes: "50",
    priceUah: "",
    validFrom: todayIn(timeZone),
    validUntil: "",
  };
}

/** Backend times are serialised as `HH:MM:SS`; the form and the list use `HH:MM`. */
function shortTime(value: string): string {
  return value.slice(0, 5);
}

function formFromRule(rule: AvailabilityRule): FormValues {
  return {
    weekday: String(rule.weekday),
    localStart: shortTime(rule.local_start),
    localEnd: shortTime(rule.local_end),
    durationMinutes: String(rule.session_duration_minutes),
    priceUah: minorToPriceInput(rule.price_minor),
    validFrom: rule.valid_from,
    validUntil: rule.valid_until ?? "",
  };
}

const priceFormatter = new Intl.NumberFormat("uk-UA", { style: "currency", currency: "UAH" });

function formatPrice(priceMinor: number): string {
  return priceFormatter.format(priceMinor / 100);
}

/** Hryvnias with an optional fraction of at most two digits, separated by a dot or a comma. */
const PRICE_PATTERN = /^(\d{1,7})(?:[.,](\d{1,2}))?$/;

/**
 * Parses a price entered in hryvnias into kopiykas using string arithmetic only, so that
 * floating-point errors cannot change the amount. Returns `null` for any other format.
 */
function parsePriceMinor(input: string): number | null {
  const match = PRICE_PATTERN.exec(input.trim());
  if (!match) return null;
  const [, hryvnias, kopiykas = ""] = match;
  return Number(hryvnias) * 100 + Number(kopiykas.padEnd(2, "0"));
}

/** Formats kopiykas as an editable price string, e.g. `120050` as `1200,50`. */
function minorToPriceInput(priceMinor: number): string {
  const hryvnias = Math.floor(priceMinor / 100);
  const kopiykas = priceMinor % 100;
  return kopiykas === 0 ? String(hryvnias) : `${hryvnias},${String(kopiykas).padStart(2, "0")}`;
}

function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-");
  return `${day}.${month}.${year}`;
}

/** Converts the form into a request body, or returns a Ukrainian error message. */
function toInput(values: FormValues): AvailabilityRuleInput | string {
  const duration = Number(values.durationMinutes);
  if (!Number.isInteger(duration) || duration <= 0) {
    return "Тривалість сесії має бути цілим додатним числом хвилин.";
  }
  const priceMinor = parsePriceMinor(values.priceUah);
  if (priceMinor === null) {
    return "Вкажіть вартість у гривнях: ціле число або не більше двох знаків після коми, наприклад 1200 або 1200,50.";
  }
  if (!values.localStart || !values.localEnd || !values.validFrom) {
    return "Заповніть усі обов'язкові поля.";
  }
  return {
    weekday: Number(values.weekday),
    local_start: values.localStart,
    local_end: values.localEnd,
    session_duration_minutes: duration,
    price_minor: priceMinor,
    currency: "UAH",
    valid_from: values.validFrom,
    valid_until: values.validUntil || null,
  };
}

function translateMessage(message: string): string | null {
  const match = KNOWN_MESSAGES.find(([needle]) => message.includes(needle));
  return match ? match[1] : null;
}

/** Turns a failed request into readable Ukrainian messages. */
function describeError(error: unknown): string[] {
  if (!(error instanceof ApiError)) {
    return ["Не вдалося зв'язатися із сервером. Перевірте з'єднання й спробуйте ще раз."];
  }
  if (error.status === 403) {
    return ["Не вдалося підтвердити запит. Оновіть сторінку й спробуйте ще раз."];
  }
  if (error.status === 404) {
    return ["Правило не знайдено. Можливо, його вже видалено. Оновіть сторінку."];
  }
  if (Array.isArray(error.detail)) {
    const messages = error.detail.map((issue) => {
      const known = translateMessage(issue.msg);
      if (known) return known;
      const field = issue.loc.find((part) => typeof part === "string" && part in FIELD_LABELS);
      return field
        ? `${FIELD_LABELS[field as string]}: некоректне значення.`
        : "Перевірте введені дані.";
    });
    return Array.from(new Set(messages));
  }
  if (typeof error.detail === "string") {
    const known = translateMessage(error.detail);
    if (known) return [known];
  }
  if (error.status === 409) {
    return ["Правило конфліктує з наявними правилами доступності."];
  }
  if (error.status === 422) {
    return ["Перевірте введені дані."];
  }
  return ["Сталася помилка на сервері. Спробуйте пізніше."];
}

function sortRules(rules: AvailabilityRule[]): AvailabilityRule[] {
  return [...rules].sort(
    (a, b) =>
      a.weekday - b.weekday ||
      a.local_start.localeCompare(b.local_start) ||
      a.valid_from.localeCompare(b.valid_from),
  );
}

/** Lets a signed-in psychologist view, add, edit and delete weekly availability rules. */
export default function AvailabilityPage() {
  const router = useRouter();
  const state = useCurrentPsychologist();
  const [rulesState, setRulesState] = useState<RulesState>({ status: "loading" });
  const [form, setForm] = useState<FormValues | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formErrors, setFormErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [listError, setListError] = useState<string[]>([]);

  const signedIn = state.status === "signed-in";

  useEffect(() => {
    if (state.status === "signed-out") {
      router.replace("/");
    }
  }, [state.status, router]);

  useEffect(() => {
    if (!signedIn) return;
    let cancelled = false;
    listAvailabilityRules()
      .then((rules) => {
        if (!cancelled) setRulesState({ status: "loaded", rules: sortRules(rules.filter((rule) => rule.is_active)) });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof ApiError && error.status === 401) {
          router.replace("/");
          return;
        }
        setRulesState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [signedIn, router]);

  if (state.status !== "signed-in") {
    return (
      <>
        <PageHeader />
        <main className="mx-auto max-w-7xl px-4 py-10 sm:px-8 sm:py-14">
          {state.status === "error" ? (
            <p role="alert" className="rounded-xl bg-danger-50 px-4 py-3 text-danger-700">
              Не вдалося завантажити кабінет. Оновіть сторінку або спробуйте пізніше.
            </p>
          ) : (
            <p className="text-muted">Завантаження…</p>
          )}
        </main>
      </>
    );
  }

  const { psychologist } = state;
  // `valid_until` is inclusive, so a rule has ended once that date is before today.
  const today = todayIn(psychologist.time_zone);

  function startCreate() {
    setEditingId(null);
    setForm(emptyForm(psychologist.time_zone));
    setFormErrors([]);
  }

  function startEdit(rule: AvailabilityRule) {
    setEditingId(rule.id);
    setForm(formFromRule(rule));
    setFormErrors([]);
  }

  function closeForm() {
    setEditingId(null);
    setForm(null);
    setFormErrors([]);
  }

  function handleUnauthorized(error: unknown): boolean {
    if (error instanceof ApiError && error.status === 401) {
      router.replace("/");
      return true;
    }
    return false;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form) return;
    const input = toInput(form);
    if (typeof input === "string") {
      setFormErrors([input]);
      return;
    }
    setSaving(true);
    setFormErrors([]);
    try {
      const saved = editingId
        ? await updateAvailabilityRule(editingId, input, psychologist.csrf_token)
        : await createAvailabilityRule(input, psychologist.csrf_token);
      setRulesState((current) => {
        const rules = current.status === "loaded" ? current.rules : [];
        return {
          status: "loaded",
          rules: sortRules([...rules.filter((rule) => rule.id !== saved.id), saved]),
        };
      });
      closeForm();
    } catch (error) {
      if (!handleUnauthorized(error)) setFormErrors(describeError(error));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(rule: AvailabilityRule) {
    const label = `${WEEKDAYS[rule.weekday]}, ${shortTime(rule.local_start)}–${shortTime(rule.local_end)}`;
    if (!window.confirm(`Видалити правило «${label}»?`)) return;
    setDeletingId(rule.id);
    setListError([]);
    try {
      await deleteAvailabilityRule(rule.id, psychologist.csrf_token);
      setRulesState((current) =>
        current.status === "loaded"
          ? { status: "loaded", rules: current.rules.filter((item) => item.id !== rule.id) }
          : current,
      );
      if (editingId === rule.id) closeForm();
    } catch (error) {
      if (!handleUnauthorized(error)) setListError(describeError(error));
    } finally {
      setDeletingId(null);
    }
  }

  function updateField(field: keyof FormValues, value: string) {
    setForm((current) => (current ? { ...current, [field]: value } : current));
  }

  return (
    <>
      <PageHeader />
      <main className="mx-auto max-w-7xl px-4 py-10 sm:px-8 sm:py-14">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-3xl text-ink sm:text-4xl">Доступність</h1>
            <p className="mt-2 text-muted">
              Щотижневі робочі години, тривалість і вартість сесії. Час вказано за вашим
              часовим поясом: {psychologist.time_zone}.
            </p>
          </div>
          {!form && <Button onClick={startCreate}>Додати правило</Button>}
        </div>

        {form && (
          <Card className="mt-8 p-6">
            <h2 className="text-xl text-ink">
              {editingId ? "Редагування правила" : "Нове правило"}
            </h2>
            <form onSubmit={handleSubmit} className="mt-5" noValidate>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="rule-weekday" className="text-[13px] font-bold text-ink">
                    День тижня
                  </label>
                  <select
                    id="rule-weekday"
                    value={form.weekday}
                    onChange={(event) => updateField("weekday", event.target.value)}
                    className="h-12 rounded-xl border border-line bg-white px-4 text-[15px] text-ink focus:border-mint-300 focus:outline-2 focus:outline-mint-200"
                  >
                    {WEEKDAYS.map((name, index) => (
                      <option key={name} value={index}>
                        {name}
                      </option>
                    ))}
                  </select>
                </div>
                <TextField
                  id="rule-start"
                  label="Початок"
                  type="time"
                  required
                  value={form.localStart}
                  onChange={(event) => updateField("localStart", event.target.value)}
                />
                <TextField
                  id="rule-end"
                  label="Кінець"
                  type="time"
                  required
                  value={form.localEnd}
                  onChange={(event) => updateField("localEnd", event.target.value)}
                />
                <TextField
                  id="rule-duration"
                  label="Тривалість сесії, хв"
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={1440}
                  step={1}
                  required
                  value={form.durationMinutes}
                  onChange={(event) => updateField("durationMinutes", event.target.value)}
                />
                <TextField
                  id="rule-price"
                  label="Вартість сесії, грн"
                  type="text"
                  inputMode="decimal"
                  placeholder="Наприклад, 1200"
                  required
                  value={form.priceUah}
                  onChange={(event) => updateField("priceUah", event.target.value)}
                />
                <TextField
                  id="rule-valid-from"
                  label="Діє з"
                  type="date"
                  required
                  value={form.validFrom}
                  onChange={(event) => updateField("validFrom", event.target.value)}
                />
                <TextField
                  id="rule-valid-until"
                  label="Діє до"
                  type="date"
                  hint="Залиште порожнім, якщо правило діє безстроково."
                  value={form.validUntil}
                  onChange={(event) => updateField("validUntil", event.target.value)}
                />
              </div>

              {formErrors.length > 0 && (
                <div
                  role="alert"
                  className="mt-5 rounded-xl bg-danger-50 px-4 py-3 text-danger-700"
                >
                  {formErrors.length === 1 ? (
                    <p>{formErrors[0]}</p>
                  ) : (
                    <ul className="list-disc pl-5">
                      {formErrors.map((message) => (
                        <li key={message}>{message}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              <div className="mt-6 flex flex-wrap gap-3">
                <Button type="submit" disabled={saving}>
                  {saving ? "Збереження…" : "Зберегти"}
                </Button>
                <Button variant="ghost" onClick={closeForm} disabled={saving}>
                  Скасувати
                </Button>
              </div>
            </form>
          </Card>
        )}

        {listError.length > 0 && (
          <p role="alert" className="mt-8 rounded-xl bg-danger-50 px-4 py-3 text-danger-700">
            {listError.join(" ")}
          </p>
        )}

        <section className="mt-10">
          {rulesState.status === "loading" && <p className="text-muted">Завантаження правил…</p>}

          {rulesState.status === "error" && (
            <p role="alert" className="rounded-xl bg-danger-50 px-4 py-3 text-danger-700">
              Не вдалося завантажити правила доступності. Оновіть сторінку або спробуйте пізніше.
            </p>
          )}

          {rulesState.status === "loaded" && rulesState.rules.length === 0 && (
            <Card className="p-6">
              <h2 className="text-xl text-ink">Правил ще немає</h2>
              <p className="mt-3 text-muted">
                Додайте перше правило, щоб клієнти могли бронювати сесії у вибрані години.
              </p>
            </Card>
          )}

          {rulesState.status === "loaded" && rulesState.rules.length > 0 && (
            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {rulesState.rules.map((rule) => (
                <li key={rule.id}>
                  <Card className="flex h-full flex-col p-6">
                    <div className="flex items-start justify-between gap-3">
                      <h2 className="text-xl text-ink">{WEEKDAYS[rule.weekday]}</h2>
                      {editingId === rule.id ? (
                        <Badge tone="warning">Редагується</Badge>
                      ) : (
                        rule.valid_until !== null &&
                        rule.valid_until < today && (
                          <Badge tone="neutral">Термін дії завершився</Badge>
                        )
                      )}
                    </div>
                    <p className="mt-2 text-2xl font-bold text-ink">
                      {shortTime(rule.local_start)}–{shortTime(rule.local_end)}
                    </p>
                    <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[15px]">
                      <dt className="text-muted">Сесія</dt>
                      <dd className="text-ink">{rule.session_duration_minutes} хв</dd>
                      <dt className="text-muted">Вартість</dt>
                      <dd className="text-ink">{formatPrice(rule.price_minor)}</dd>
                      <dt className="text-muted">Діє</dt>
                      <dd className="text-ink">
                        {rule.valid_until
                          ? `${formatDate(rule.valid_from)} – ${formatDate(rule.valid_until)}`
                          : `з ${formatDate(rule.valid_from)}`}
                      </dd>
                    </dl>
                    <div className="mt-auto flex flex-wrap gap-2 pt-5">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => startEdit(rule)}
                        disabled={saving || deletingId === rule.id}
                      >
                        Редагувати
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(rule)}
                        disabled={deletingId === rule.id}
                      >
                        {deletingId === rule.id ? "Видалення…" : "Видалити"}
                      </Button>
                    </div>
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </>
  );
}

function PageHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-white">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:h-[76px] sm:px-8">
        <Logo />
        <Button href="/dashboard" variant="ghost" size="sm">
          До кабінету
        </Button>
      </div>
    </header>
  );
}
