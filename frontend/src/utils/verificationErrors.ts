/** Ukrainian message for a failed `POST /api/v1/email-verifications` request. */
export function verificationErrorMessage(status: number | null): string {
  switch (status) {
    case 422:
      return "Перевірте, чи правильно введено адресу електронної пошти.";
    case 429:
      return "Забагато запитів. Зачекайте хвилину й спробуйте ще раз.";
    case 503:
      return "Надсилання листів тимчасово недоступне. Спробуйте пізніше.";
    default:
      return "Не вдалося надіслати лист. Спробуйте ще раз.";
  }
}
