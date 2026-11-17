const messages: Record<string, string> = {
  sign_in_cancelled: "Вхід скасовано.",
};

const defaultMessage = "Не вдалося увійти. Спробуйте ще раз.";

type AuthErrorNoticeProps = {
  /** Generic error code from the `auth_error` query parameter set by the backend. */
  error: string;
};

/** Banner shown on the landing page when Google sign-in did not complete. */
export function AuthErrorNotice({ error }: AuthErrorNoticeProps) {
  return (
    <div className="mx-auto max-w-7xl px-4 pt-6 sm:px-8">
      <p role="alert" className="rounded-xl bg-danger-50 px-4 py-3 font-semibold text-danger-700">
        {messages[error] ?? defaultMessage}
      </p>
    </div>
  );
}
