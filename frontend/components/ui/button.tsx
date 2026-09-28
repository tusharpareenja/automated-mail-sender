import type { ButtonHTMLAttributes } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  loading?: boolean;
};

const variants = {
  primary: "bg-primary text-white hover:bg-primary-active disabled:bg-primary-disabled",
  secondary: "bg-surface-strong text-ink hover:bg-hairline",
  danger: "bg-danger text-white hover:opacity-90",
  ghost: "bg-transparent text-primary hover:bg-surface-soft",
};

export function Button({
  variant = "primary",
  loading,
  className = "",
  children,
  disabled,
  ...props
}: Props) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={`inline-flex h-11 cursor-pointer items-center justify-center rounded-full px-5 text-base font-semibold transition disabled:cursor-not-allowed ${variants[variant]} ${className}`}
    >
      {loading ? (
        <span className="inline-flex items-center gap-2">
          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          Working…
        </span>
      ) : (
        children
      )}
    </button>
  );
}
