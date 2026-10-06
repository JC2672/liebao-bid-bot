import { forwardRef } from "react";
import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";

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
    "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-[background-color,color,transform] active:scale-[0.97] disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100";
  const variants: Record<ButtonVariant, string> = {
    primary: "bg-accent text-accent-fg hover:bg-accent-hover",
    secondary: "bg-surface text-fg border border-border hover:bg-surface-hover",
    danger: "bg-surface text-bad border border-bad/30 hover:bg-bad-wash",
    ghost: "bg-transparent text-fg-muted hover:text-fg hover:bg-surface-hover",
  };
  return <button className={cx(base, variants[variant], className)} {...props} />;
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx("rounded-md border border-border bg-surface", className)} {...props} />;
}

type IconButtonTone = "default" | "danger" | "primary";

const iconButtonTones: Record<IconButtonTone, string> = {
  default: "text-fg-muted hover:text-fg hover:bg-surface-hover",
  danger: "text-bad hover:bg-bad-wash",
  primary: "text-accent hover:bg-accent-wash",
};

// A small square icon-only action button - used wherever a row/card needs
// compact actions (Queue's per-row actions, Profiles' Edit/Delete) rather
// than full text buttons competing for space.
export function IconButton({
  title,
  onClick,
  disabled,
  tone = "default",
  badge,
  children,
}: {
  title: string;
  onClick: () => void;
  disabled?: boolean;
  tone?: IconButtonTone;
  badge?: number;
  children: React.ReactNode;
}) {
  return (
    <button
      title={title}
      aria-label={title}
      disabled={disabled}
      onClick={onClick}
      className={cx(
        "relative inline-flex h-7 w-7 items-center justify-center rounded-md transition-[background-color,color,transform] active:scale-90 disabled:opacity-30 disabled:cursor-not-allowed disabled:active:scale-100",
        iconButtonTones[tone],
      )}
    >
      {children}
      {!!badge && (
        <span className="absolute -right-1 -top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-bad px-0.5 font-mono text-[9px] leading-none text-accent-fg">
          {badge}
        </span>
      )}
    </button>
  );
}

const badgeTones = {
  neutral: "bg-surface-hover text-fg-muted",
  warn: "bg-warn-wash text-warn",
  bad: "bg-bad-wash text-bad",
  good: "bg-good-wash text-good",
} as const;

export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: keyof typeof badgeTones;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cx(
        "inline-block rounded px-1.5 py-0.5 font-mono text-[11px] leading-none",
        badgeTones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "ready" ? "good" : status === "failed" ? "bad" : status === "generating" ? "warn" : "neutral";
  return (
    <Badge tone={tone} className={status === "generating" ? "animate-pulse" : undefined}>
      {status}
    </Badge>
  );
}

// Non-rejecting flags earned in gates.py - shown as warn badges so agency/C2C/
// no-sponsorship postings are visible but not filtered out.
const FLAG_LABELS: Record<string, string> = {
  "no-sponsorship": "No Sponsorship",
  c2c: "C2C",
  "w2-only": "W2 Only",
  agency: "Staffing Agency",
  hybrid: "Hybrid",
  "remote-unscoped": "Remote (Country Unspecified)",
};

function titleCase(slug: string) {
  return slug
    .split("-")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function flagLabel(flag: string) {
  return FLAG_LABELS[flag] ?? titleCase(flag);
}

export function FlagBadge({ flag }: { flag: string }) {
  return <Badge tone="warn">{flagLabel(flag)}</Badge>;
}

// reject_reason values come straight from gates.py's apply_gates(): either a
// fixed string or one with a field id / day count spliced in - matched here
// before falling back to a generic title-case so new reasons don't show raw.
export function prettifyReason(reason: string) {
  if (reason === "not-in-country-or-remote") return "Not in country or remote";
  const relevance = reason.match(/^not-(.+)-relevant$/);
  if (relevance) return `Not relevant to ${titleCase(relevance[1])}`;
  const age = reason.match(/^older-than-(\d+)-days$/);
  if (age) return `Older than ${age[1]} days`;
  return titleCase(reason);
}

export const Checkbox = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Checkbox({ className, ...props }, ref) {
    return (
      <input
        ref={ref}
        type="checkbox"
        className={cx(
          "h-4 w-4 rounded-sm border-border text-accent accent-[var(--color-accent)] cursor-pointer",
          className,
        )}
        {...props}
      />
    );
  },
);

// --- Table primitives -----------------------------------------------------
// One shared set so every data table in the app (Fetch results, Queue) reads
// as one system: a real header row, hairline row dividers, a hover state,
// and consistent cell padding - instead of each page hand-rolling its own.

export function Table({ className, ...props }: HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="overflow-x-auto">
      <table className={cx("w-full border-collapse text-left text-sm", className)} {...props} />
    </div>
  );
}

export function THead({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cx("border-b border-border", className)} {...props} />;
}

export function TBody(props: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody {...props} />;
}

export function Tr({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cx("border-b border-border/70 last:border-0 hover:bg-surface-hover", className)} {...props} />;
}

export function Th({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cx("px-3 py-2 text-xs font-medium text-fg-muted whitespace-nowrap", className)}
      {...props}
    />
  );
}

export function Td({ className, mono, ...props }: TdHTMLAttributes<HTMLTableCellElement> & { mono?: boolean }) {
  return <td className={cx("px-3 py-2 align-middle", mono && "font-mono text-[13px]", className)} {...props} />;
}
