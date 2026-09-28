import type { InputHTMLAttributes, TextareaHTMLAttributes } from "react";
import { forwardRef } from "react";

type FieldProps = {
  label: string;
  error?: string;
  hint?: string;
};

export function TextField({
  label,
  error,
  hint,
  id,
  ...props
}: FieldProps & InputHTMLAttributes<HTMLInputElement>) {
  const fieldId = id ?? props.name;
  return (
    <label className="block space-y-2" htmlFor={fieldId}>
      <span className="text-sm font-semibold text-ink">{label}</span>
      <input
        id={fieldId}
        {...props}
        className="h-12 w-full rounded-xl border border-hairline bg-canvas px-4 text-base text-ink placeholder:text-muted-soft focus:border-primary"
      />
      {hint ? <span className="block text-sm text-muted">{hint}</span> : null}
      {error ? <span className="block text-sm text-danger">{error}</span> : null}
    </label>
  );
}

export const TextArea = forwardRef<
  HTMLTextAreaElement,
  FieldProps & TextareaHTMLAttributes<HTMLTextAreaElement>
>(function TextArea({ label, error, hint, id, ...props }, ref) {
  const fieldId = id ?? props.name;
  return (
    <label className="block space-y-2" htmlFor={fieldId}>
      <span className="text-sm font-semibold text-ink">{label}</span>
      <textarea
        id={fieldId}
        ref={ref}
        {...props}
        className="min-h-36 w-full rounded-xl border border-hairline bg-canvas px-4 py-3 text-base text-ink"
      />
      {hint ? <span className="block text-sm text-muted">{hint}</span> : null}
      {error ? <span className="block text-sm text-danger">{error}</span> : null}
    </label>
  );
});
