import { forwardRef, InputHTMLAttributes, TextareaHTMLAttributes } from "react";

const FIELD_BASE =
  "w-full rounded-sm border border-line-strong bg-surface px-4 py-3 text-base text-ink placeholder:text-ink-faint transition-colors duration-150 focus:border-2 focus:border-accent outline-none disabled:cursor-not-allowed disabled:bg-black/[0.03] disabled:text-ink-faint";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className = "", ...props }, ref) => <input ref={ref} className={`${FIELD_BASE} ${className}`} {...props} />
);
Input.displayName = "Input";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className = "", ...props }, ref) => <textarea ref={ref} className={`${FIELD_BASE} ${className}`} {...props} />
);
Textarea.displayName = "Textarea";

export function Label({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <span className={`text-sm font-medium text-ink ${className}`}>{children}</span>;
}
