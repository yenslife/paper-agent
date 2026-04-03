import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "../../lib/utils";

type Props = {
  children: string;
  className?: string;
  invert?: boolean;
};

export function MarkdownRenderer({ children, className, invert = false }: Props) {
  return (
    <div
      className={cn(
        "markdown-body text-sm leading-7",
        invert ? "text-[var(--primary-foreground)]" : "text-[var(--foreground)]",
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1 className="mb-3 text-xl font-semibold">{children}</h1>,
          h2: ({ children }) => <h2 className="mb-3 text-lg font-semibold">{children}</h2>,
          h3: ({ children }) => <h3 className="mb-3 text-base font-semibold">{children}</h3>,
          p: ({ children }) => <p className="mb-4 whitespace-pre-wrap last:mb-0">{children}</p>,
          ul: ({ children }) => <ul className="mb-4 ml-5 list-disc space-y-2">{children}</ul>,
          ol: ({ children }) => <ol className="mb-4 ml-5 list-decimal space-y-2">{children}</ol>,
          li: ({ children }) => <li>{children}</li>,
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          code: ({ children, className }) =>
            className ? (
              <code className="block overflow-x-auto rounded-2xl bg-[var(--card)] px-4 py-3 text-[0.9em] text-[var(--foreground)]">
                {children}
              </code>
            ) : (
              <code
                className={cn(
                  "rounded px-1.5 py-0.5 text-[0.9em]",
                  invert ? "bg-white/10 text-[var(--primary-foreground)]" : "bg-[var(--card)] text-[var(--foreground)]",
                )}
              >
                {children}
              </code>
            ),
          pre: ({ children }) => <pre className="mb-4 overflow-x-auto">{children}</pre>,
          a: ({ children, href }) => (
            <a
              className={cn("underline underline-offset-4", invert ? "text-[var(--primary-foreground)]" : "text-[var(--foreground)]")}
              href={href}
              target="_blank"
              rel="noreferrer"
            >
              {children}
            </a>
          ),
          blockquote: ({ children }) => (
            <blockquote className="mb-4 border-l-2 border-[var(--border)] pl-4 text-[var(--muted-foreground)]">{children}</blockquote>
          ),
          table: ({ children }) => <table className="mb-4 w-full border-collapse overflow-hidden rounded-2xl text-left">{children}</table>,
          thead: ({ children }) => <thead className="bg-[var(--card)]/80">{children}</thead>,
          tbody: ({ children }) => <tbody>{children}</tbody>,
          tr: ({ children }) => <tr className="border-b border-[var(--border)]">{children}</tr>,
          th: ({ children }) => <th className="px-3 py-2 text-sm font-semibold">{children}</th>,
          td: ({ children }) => <td className="px-3 py-2 align-top text-sm">{children}</td>,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
