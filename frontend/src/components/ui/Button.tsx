import { ButtonHTMLAttributes, forwardRef } from "react";

// Every button is a fully-rounded pill. Blue = primary action, orange =
// commerce only (Add / Buy / Pay), outline = secondary.
export type ButtonVariant = "primary" | "commerce" | "secondary" | "ghost" | "destructive" | "night";
export type ButtonSize = "sm" | "md" | "lg";

const BASE =
  "inline-flex items-center justify-center gap-1.5 rounded-full font-bold tracking-[0.3px] transition-colors duration-150 active:shadow-[0_4px_12px_rgba(0,0,0,0.16)] disabled:cursor-not-allowed disabled:bg-surface-soft disabled:text-line-strong disabled:border-transparent";

const VARIANT_STYLES: Record<ButtonVariant, string> = {
  primary: "bg-accent text-white hover:bg-accent-hover active:bg-accent-active",
  commerce: "bg-commerce text-white hover:bg-commerce-hover",
  secondary: "border border-line-strong bg-transparent text-ink hover:border-ink",
  ghost: "text-ink-soft hover:bg-black/[0.05] hover:text-ink",
  destructive: "border border-danger/40 bg-transparent text-danger hover:bg-danger-soft",
  night: "border border-night-line bg-transparent text-on-night hover:border-on-night",
};

const SIZE_STYLES: Record<ButtonSize, string> = {
  sm: "h-9 px-4 text-[13px]",
  md: "h-11 px-6 text-sm",
  lg: "h-12 px-7 text-base",
};

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const Button = forwardRef<HTMLButtonElement, Props>(
  ({ variant = "secondary", size = "md", className = "", ...props }, ref) => (
    <button ref={ref} className={`${BASE} ${VARIANT_STYLES[variant]} ${SIZE_STYLES[size]} ${className}`} {...props} />
  )
);
Button.displayName = "Button";

export default Button;
