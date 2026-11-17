import { Button } from "@/components/ui/Button";

type PaymentActionProps = {
  /** Formatted amount shown on the button. */
  amountLabel: string;
  /** Starts the payment. When omitted, the button is disabled and payment is shown as unavailable. */
  onPay?: () => void;
  pending?: boolean;
};

/** Payment call to action for a held booking. */
export function PaymentAction({ amountLabel, onPay, pending = false }: PaymentActionProps) {
  const available = onPay !== undefined;

  return (
    <div className="flex flex-col gap-2">
      <Button fullWidth disabled={!available || pending} onClick={onPay}>
        {pending ? "Оплата…" : `Оплатити ${amountLabel}`}
      </Button>
      {!available && (
        <p className="text-center text-[13px] text-muted">
          Онлайн-оплата незабаром стане доступною.
        </p>
      )}
    </div>
  );
}
