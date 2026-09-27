import type { ButtonHTMLAttributes, HTMLAttributes } from "react";

function cx(...classes: (string | false | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

export function Button({
  variant = "secondary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  const base =
    "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed";
  const variants: Record<ButtonVariant, string> = {
    primary: "bg-accent text-accent-fg hover:brightness-110",
    secondary: "bg-surface-hover text-fg border border-border hover:border-accent",
    danger: "bg-transparent text-bad border border-bad/40 hover:bg-bad/10",
    ghost: "bg-transparent text-fg-muted hover:text-fg",
  };
  return <button className={cx(base, variants[variant], className)} {...props} />;
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cx("rounded-lg border border-border bg-surface", className)}
      {...props}
    />
  );
}

const badgeTones = {
  neutral: "bg-surface-hover text-fg-muted border-border",
  warn: "bg-warn/10 text-warn border-warn/30",
  bad: "bg-bad/10 text-bad border-bad/30",
  good: "bg-good/10 text-good border-good/30",
} as const;

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: keyof typeof badgeTones;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cx(
        "inline-block rounded border px-1.5 py-0.5 text-xs font-medium",
        badgeTones[tone],
      )}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "ready" ? "good" : status === "failed" ? "bad" : status === "generating" ? "warn" : "neutral";
  return <Badge tone={tone}>{status}</Badge>;
}

// Non-rejecting flags earned in gates.py - shown as warn badges so agency/C2C/
// no-sponsorship postings are visible but not filtered out.
export function FlagBadge({ flag }: { flag: string }) {
  return <Badge tone="warn">{flag}</Badge>;
}
