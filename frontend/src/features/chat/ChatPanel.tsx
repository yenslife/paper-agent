import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronRight, CircleHelp, Loader2, Plus, Search, Sparkles, Square, X } from "lucide-react";

import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { MarkdownRenderer } from "../../components/ui/markdown-renderer";
import { ChatMessage } from "../../types";

type Props = {
  messages: ChatMessage[];
  prompt: string;
  isChatLoading: boolean;
  error: string | null;
  onPromptChange: (value: string) => void;
  onSuggestionSelect: (value: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onAbort: () => void;
};

const promptSuggestions = [
  "幫我找 2025 跟 prompt injection 相關的 paper，先看本地資料庫。",
  "比較最近兩年 USENIX Security 和 IEEE S&P 關於 AI agent security 的論文方向。",
  "幫我找某篇 paper 的 abstract，不夠就去外部 lookup 或讀 PDF。",
];

export function ChatPanel({
  messages,
  prompt,
  isChatLoading,
  error,
  onPromptChange,
  onSuggestionSelect,
  onSubmit,
  onAbort,
}: Props) {
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const latestUserMessageRef = useRef<HTMLElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const previousMessageCountRef = useRef(messages.length);
  const latestUserMessageIndex = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      if (messages[index]?.role === "user") return index;
    }
    return -1;
  }, [messages]);

  useEffect(() => {
    const messageCountIncreased = messages.length > previousMessageCountRef.current;
    previousMessageCountRef.current = messages.length;

    if (!messageCountIncreased) return;
    if (latestUserMessageIndex < 0) return;
    if (messages[latestUserMessageIndex]?.role !== "user") return;

    const container = scrollContainerRef.current;
    const latestUserMessage = latestUserMessageRef.current;
    if (!container || !latestUserMessage) return;

    const topPadding = 24;
    const nextScrollTop = Math.max(0, latestUserMessage.offsetTop - topPadding);
    container.scrollTo({ top: nextScrollTop, behavior: "smooth" });
  }, [messages, latestUserMessageIndex]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = "0px";
    const maxHeight = 192;
    const nextHeight = Math.min(textarea.scrollHeight, maxHeight);
    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [prompt]);

  function handlePromptKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      const form = event.currentTarget.form;
      if (!form) return;
      form.requestSubmit();
    }
  }

  return (
    <section className="relative flex h-full w-full flex-1 flex-col overflow-hidden bg-transparent">
      <div className="pointer-events-none absolute right-8 top-6 z-20">
        <div className="pointer-events-auto relative">
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="rounded-full bg-[var(--card)] shadow-sm"
            onClick={() => setIsHelpOpen((current) => !current)}
          >
            <CircleHelp className="size-4" />
          </Button>

          {isHelpOpen ? (
            <div className="absolute right-0 top-12 w-80 rounded-3xl border border-[var(--border)] bg-[var(--card)] p-5 text-sm text-[var(--foreground)] shadow-[0_20px_50px_rgba(15,23,42,0.12)] dark:shadow-[0_20px_50px_rgba(0,0,0,0.4)]">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-semibold">與 research agent 對話</div>
                  <p className="mt-2 leading-6 text-[var(--muted-foreground)]">
                    以 Shadcn Chatbot Kit 的聊天結構為主，支援即時工具泡泡、論文 citations，與後續的 Markdown 回覆顯示。
                  </p>
                </div>
                <button
                  type="button"
                  className="rounded-full p-1 text-[var(--muted-foreground)] transition hover:bg-[var(--muted)]"
                  onClick={() => setIsHelpOpen(false)}
                >
                  <X className="size-4" />
                </button>
              </div>
              <div className="mt-4 rounded-2xl border border-black/5 bg-[var(--muted)]/80 px-4 py-3 text-xs text-[var(--muted-foreground)]">
                <div className="font-medium text-[var(--foreground)]">快捷鍵</div>
                <div className="mt-1">⌘ + Enter 送出訊息</div>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      <div
        ref={scrollContainerRef}
        className="min-h-0 flex-1 overflow-y-auto bg-[linear-gradient(180deg,color-mix(in_oklch,var(--background)_82%,white_18%),color-mix(in_oklch,var(--background)_96%,var(--card)_4%))] px-8 pb-48 pt-20 dark:bg-[var(--background)]"
      >
        {messages.length === 0 ? (
          <EmptyState onSuggestionSelect={onSuggestionSelect} />
        ) : (
          <div className="flex flex-col gap-4">
            {messages.map((message, index) => (
              <ChatMessageBlock
                key={`${message.role}-${index}`}
                message={message}
                isLatestUserMessage={message.role === "user" && index === latestUserMessageIndex}
                latestUserMessageRef={latestUserMessageRef}
              />
            ))}
          </div>
        )}

        {isChatLoading ? (
          <div className="mt-4 flex">
            <div className="mr-auto flex max-w-[72%] items-center gap-3 rounded-2xl border border-[var(--border)] bg-[var(--card)]/80 px-4 py-3 text-sm text-[var(--muted-foreground)] shadow-sm">
              <Loader2 className="size-4 animate-spin" />
              Agent 正在思考，可能會依序使用多個工具
            </div>
          </div>
        ) : null}
      </div>

      <form className="pointer-events-none absolute inset-x-8 bottom-6 z-20" onSubmit={onSubmit}>
        <div className="pointer-events-auto flex flex-col gap-4">
          <div className="rounded-[40px] border border-[var(--border)] bg-[var(--card)] px-5 py-4 shadow-[0_18px_40px_rgba(15,23,42,0.12)] dark:shadow-[0_18px_40px_rgba(0,0,0,0.38)]">
            <div className="flex items-end gap-4">
              <button
                type="button"
                className="flex size-12 shrink-0 items-center justify-center rounded-full text-[var(--foreground)] transition hover:bg-[var(--muted)]"
                aria-label="More actions"
              >
                <Plus className="size-7" />
              </button>

              <div className="relative grid min-h-12 flex-1 px-1.5 py-1">
                {!prompt ? (
                  <div className="pointer-events-none col-start-1 row-start-1 self-center px-0 py-0 text-base leading-6 text-[var(--muted-foreground)]">
                    想問就問
                  </div>
                ) : null}
                <textarea
                  ref={textareaRef}
                  rows={1}
                  className="col-start-1 row-start-1 min-h-8 w-full resize-none self-center bg-transparent py-0 text-base leading-6 text-[var(--foreground)] outline-none placeholder:text-transparent"
                  placeholder="想問就問"
                  value={prompt}
                  onChange={(event) => onPromptChange(event.target.value)}
                  onKeyDown={handlePromptKeyDown}
                />
              </div>

              <div className="flex items-center gap-3">
                <Button
                  className="size-12 rounded-full"
                  type="submit"
                  size="icon"
                  disabled={isChatLoading || !prompt.trim()}
                  aria-label="發送訊息"
                >
                  <Sparkles className="size-5" />
                </Button>
                <Button
                  className="size-12 rounded-full"
                  type="button"
                  variant="outline"
                  size="icon"
                  disabled={!isChatLoading}
                  onClick={onAbort}
                  aria-label="中斷回覆"
                >
                  <Square className="size-4" />
                </Button>
              </div>
            </div>
          </div>

          {error ? (
            <p className="rounded-2xl border border-[var(--border)] bg-[var(--muted)] px-4 py-3 text-sm text-[var(--foreground)] shadow-sm">
              {error}
            </p>
          ) : null}
        </div>
      </form>
    </section>
  );
}

function ChatMessageBlock({
  message,
  isLatestUserMessage,
  latestUserMessageRef,
}: {
  message: ChatMessage;
  isLatestUserMessage: boolean;
  latestUserMessageRef: React.MutableRefObject<HTMLElement | null>;
}) {
  if (message.role === "user") {
    return (
      <article
        ref={(element) => {
          if (isLatestUserMessage) {
            latestUserMessageRef.current = element;
          }
        }}
        className="ml-auto max-w-[80%] rounded-[28px] bg-[var(--primary)] px-5 py-4 text-[var(--primary-foreground)] shadow-sm"
      >
        <MarkdownRenderer invert>{message.content}</MarkdownRenderer>
      </article>
    );
  }

  if (message.role === "tool") {
    return (
      <article className="mr-auto max-w-[68%] rounded-2xl border border-[var(--border)] bg-[var(--card)]/85 px-4 py-3 text-sm text-[var(--foreground)] shadow-sm">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{toolLabel(message.tool_name ?? "tool")}</Badge>
          <Badge>{toolStatusLabel(message.tool_status ?? "running")}</Badge>
          {message.tool_trace?.duration_ms != null ? (
            <span className="text-xs text-[var(--muted-foreground)]">{formatDuration(message.tool_trace.duration_ms)}</span>
          ) : null}
        </div>
        <p className="mt-2 whitespace-pre-wrap leading-6 text-[var(--muted-foreground)]">{message.content}</p>
        {message.tool_trace ? <ToolTraceDetails toolTrace={message.tool_trace} /> : null}
      </article>
    );
  }

  return (
    <article className="mr-auto max-w-[78%] rounded-[28px] border border-[var(--border)] bg-[var(--muted)]/90 px-5 py-4 text-[var(--foreground)] shadow-sm">
      <MarkdownRenderer>{message.content}</MarkdownRenderer>

      {message.citations && message.citations.length > 0 ? (
        <div className="mt-5 space-y-2 border-t border-[var(--border)] pt-4">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted-foreground)]">
            <Search className="size-3.5" />
            Citations
          </div>
          {message.citations.map((citation) => (
            <a
              key={`${citation.source_type}-${citation.url ?? citation.source_page_url ?? citation.title}`}
              className="block rounded-2xl border border-[var(--border)] bg-[var(--card)] px-4 py-3 text-sm no-underline transition hover:-translate-y-0.5 hover:shadow-sm"
              href={citation.url ?? citation.source_page_url ?? "#"}
              target="_blank"
              rel="noreferrer"
            >
              <div className="font-medium text-[var(--foreground)]">{citation.title}</div>
              <div className="mt-1 flex flex-wrap gap-2 text-xs text-[var(--muted-foreground)]">
                <Badge>{citation.source_type === "local_paper_db" ? "Local paper DB" : "Web search"}</Badge>
                {citation.venue ? <span>{citation.venue}</span> : null}
                {citation.year ? <span>{citation.year}</span> : null}
              </div>
            </a>
          ))}
        </div>
      ) : null}

      {message.sources && message.sources.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {message.sources.map((source) => (
            <Badge key={source.source_type}>{source.description}</Badge>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function ToolTraceDetails({ toolTrace }: { toolTrace: ChatMessage["tool_trace"] }) {
  const [isOpen, setIsOpen] = useState(false);

  if (!toolTrace) return null;

  const detailEntries = toolTrace.details ? Object.entries(toolTrace.details) : [];
  const hasExpandableContent = detailEntries.length > 0 || toolTrace.started_at || toolTrace.ended_at;
  if (!hasExpandableContent) return null;

  return (
    <div className="mt-3 rounded-2xl border border-[var(--border)] bg-[var(--muted)]/55">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-xs text-[var(--muted-foreground)]"
        onClick={() => setIsOpen((current) => !current)}
      >
        <span className="flex items-center gap-2">
          {isOpen ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
          查看執行細節
        </span>
        {toolTrace.duration_ms != null ? <span>{formatDuration(toolTrace.duration_ms)}</span> : null}
      </button>

      {isOpen ? (
        <div className="space-y-3 border-t border-[var(--border)] px-3 py-3 text-xs text-[var(--muted-foreground)]">
          <div className="grid gap-2 sm:grid-cols-2">
            <div>
              <div className="font-medium text-[var(--foreground)]">Started</div>
              <div>{formatTimestamp(toolTrace.started_at)}</div>
            </div>
            {toolTrace.ended_at ? (
              <div>
                <div className="font-medium text-[var(--foreground)]">Ended</div>
                <div>{formatTimestamp(toolTrace.ended_at)}</div>
              </div>
            ) : null}
          </div>

          {detailEntries.length > 0 ? (
            <div>
              <div className="mb-2 font-medium text-[var(--foreground)]">Partial span data</div>
              <pre className="overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-3 text-[11px] leading-5 text-[var(--foreground)]">
                {JSON.stringify(toolTrace.details, null, 2)}
              </pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function toolLabel(toolName: string) {
  switch (toolName) {
    case "search_papers":
      return "搜尋論文";
    case "get_paper_details":
      return "讀取細節";
    case "find_paper_abstract":
      return "找摘要";
    case "lookup_paper_on_web":
      return "查外部資料";
    case "convert_pdf_url_to_markdown":
    case "convert_paper_pdf_to_markdown":
      return "讀 PDF";
    case "browser_browse_task":
      return "瀏覽器";
    case "import_markdown_papers":
      return "匯入 papers";
    case "web_search":
      return "Web search";
    default:
      return toolName;
  }
}

function toolStatusLabel(status: string) {
  switch (status) {
    case "running":
      return "執行中";
    case "ok":
      return "完成";
    case "not_found":
      return "未找到";
    case "error":
      return "失敗";
    case "unavailable":
      return "不可用";
    default:
      return status;
  }
}

function formatDuration(durationMs: number) {
  if (durationMs < 1000) return `${durationMs} ms`;
  return `${(durationMs / 1000).toFixed(2)} s`;
}

function formatTimestamp(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleTimeString("zh-TW", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function EmptyState({ onSuggestionSelect }: { onSuggestionSelect: (value: string) => void }) {
  return (
    <div className="flex h-full min-h-[520px] flex-col items-center justify-center gap-8 text-center">
      <div className="space-y-3">
        <Badge className="bg-[var(--card)] text-[var(--foreground)] shadow-sm">Chat</Badge>
        <div className="text-3xl font-semibold tracking-tight">Paper Agent 對話工作台</div>
        <p className="max-w-2xl text-sm leading-7 text-[var(--muted-foreground)]">
          你可以直接問論文摘要、比較不同會議趨勢、要求 agent 外部 lookup，或進一步讓它讀 PDF 與使用瀏覽器工具。
        </p>
      </div>
      <div className="grid w-full gap-3 md:grid-cols-3">
        {promptSuggestions.map((suggestion) => (
          <button
            key={suggestion}
            className="rounded-3xl border border-[var(--border)] bg-[var(--card)]/85 p-4 text-left text-sm leading-6 text-[var(--foreground)] shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
            type="button"
            onClick={() => onSuggestionSelect(suggestion)}
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}
