import { Loader2, Search, Sparkles, Square } from "lucide-react";

import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";
import { ChatMessage } from "../../types";

type Props = {
  messages: ChatMessage[];
  prompt: string;
  isChatLoading: boolean;
  error: string | null;
  onPromptChange: (value: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onAbort: () => void;
};

export function ChatPanel({ messages, prompt, isChatLoading, error, onPromptChange, onSubmit, onAbort }: Props) {
  function handlePromptKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      const form = event.currentTarget.form;
      if (!form) return;
      form.requestSubmit();
    }
  }

  return (
    <Card className="flex w-full min-h-[720px] flex-col lg:h-[720px] lg:min-h-0">
      <CardHeader>
        <Badge className="w-fit bg-[var(--primary)] text-[var(--primary-foreground)]">Chat agent</Badge>
        <CardTitle className="flex items-center gap-3">
          <Sparkles className="h-5 w-5" />
          與 paper agent 對話
        </CardTitle>
        <CardDescription>Agent 會優先查本地 paper 資料庫，資料不足時才使用網路搜尋補充背景。</CardDescription>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col gap-4">
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto rounded-3xl bg-white/60 p-4">
          {messages.length === 0 ? (
            <EmptyState />
          ) : (
            messages.map((message, index) => (
              <article
                key={`${message.role}-${index}`}
                className={[
                  "rounded-3xl p-4",
                  message.role === "user"
                    ? "ml-auto max-w-[85%] bg-[var(--primary)] text-[var(--primary-foreground)]"
                    : "mr-auto max-w-[90%] bg-[var(--muted)] text-[var(--foreground)]",
                ].join(" ")}
              >
                <p className="whitespace-pre-wrap text-sm leading-7">{message.content}</p>

                {message.citations && message.citations.length > 0 ? (
                  <div className="mt-4 space-y-2 border-t border-black/5 pt-4">
                    <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted-foreground)]">
                      <Search className="h-3.5 w-3.5" />
                      Citations
                    </div>
                    {message.citations.map((citation) => (
                      <a
                        key={`${citation.source_type}-${citation.url ?? citation.source_page_url ?? citation.title}`}
                        className="block rounded-2xl border border-black/5 bg-white/70 px-4 py-3 text-sm no-underline transition hover:-translate-y-0.5 hover:shadow-sm"
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
                  <div className="mt-3 flex flex-wrap gap-2">
                    {message.sources.map((source) => (
                      <Badge key={source.source_type}>{source.description}</Badge>
                    ))}
                  </div>
                ) : null}
              </article>
            ))
          )}

          {isChatLoading ? (
            <div className="mr-auto flex max-w-[90%] items-center gap-3 rounded-3xl bg-[var(--muted)] px-4 py-3 text-sm text-[var(--muted-foreground)]">
              <Loader2 className="h-4 w-4 animate-spin" />
              Agent 正在檢索 papers 與整理答案
            </div>
          ) : null}
        </div>

        <form className="space-y-3" onSubmit={onSubmit}>
          <textarea
            className="min-h-28 w-full rounded-2xl border border-[var(--border)] bg-white/90 p-4 text-sm outline-none transition focus:border-[var(--primary)]"
            placeholder="例如：幫我找 2024-2025 跟 agent security 相關的論文，先從本地資料庫找，不夠再補最新背景。"
            value={prompt}
            onChange={(event) => onPromptChange(event.target.value)}
            onKeyDown={handlePromptKeyDown}
          />
          <div className="flex gap-3">
            <Button className="flex-1" type="submit" disabled={isChatLoading}>
              <Sparkles className="mr-2 h-4 w-4" />
              發送訊息
            </Button>
            <Button className="min-w-32" type="button" variant="outline" disabled={!isChatLoading} onClick={onAbort}>
              <Square className="mr-2 h-4 w-4" />
              中斷回覆
            </Button>
          </div>
        </form>

        {error ? <p className="rounded-2xl border border-[var(--border)] bg-[var(--muted)] px-4 py-3 text-sm text-[var(--foreground)]">{error}</p> : null}
      </CardContent>
    </Card>
  );
}

function EmptyState() {
  return (
    <div className="flex h-full min-h-64 flex-col items-center justify-center gap-4 rounded-3xl border border-dashed border-[var(--border)] bg-[var(--muted)]/70 px-6 text-center">
      <Sparkles className="h-8 w-8 text-[var(--primary)]" />
      <div>
        <div className="text-lg font-semibold">先匯入 paper 清單，再開始提問</div>
        <p className="mt-2 text-sm text-[var(--muted-foreground)]">
          你可以問特定主題、指定 venue/year，或要求 Agent 在本地資料不足時補充外部背景。
        </p>
      </div>
    </div>
  );
}
