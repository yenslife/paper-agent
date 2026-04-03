import * as React from "react";

import { cn } from "../../lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "flex h-11 w-full rounded-xl border border-[var(--border)] bg-[var(--card)]/85 px-4 py-2 text-sm text-[var(--foreground)] outline-none transition focus:border-[var(--primary)]",
        className,
      )}
      {...props}
    />
  ),
);

Input.displayName = "Input";
