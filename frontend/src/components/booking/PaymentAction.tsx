import { Button } from "@/components/ui/Button";

type PaymentActionProps = {
  /** Formatted amount shown on the button. */
  amountLabel: string;
  /**
   * Starts the payment. The backend exposes no payment endpoint yet, so callers omit it and the
   * button stays disabled. Wire it up once the `payments` module provides a public route.
   */
  onPay?: () => void;
  pending?: boolean;
};

/** Payment call to action for a held booking. */
export function PaymentAction({ amountLabel, onPay, pending = false }: PaymentActionProps) {
  const available = onPay !== undefined;

  return (
    <div className="flex flex-col gap-2">
      <Button fullWidth disabled={!available || pending} onClick={onPay}>
        Оплатити {amountLabel}
      </Button>
      {!available && (
        <p className="text-center text-[13px] text-muted">
          Онлайн-оплата незабаром стане доступною.
        </p>
      )}
    </div>
  );
}
