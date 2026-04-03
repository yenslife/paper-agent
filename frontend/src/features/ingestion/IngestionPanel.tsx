import { DownloadCloud, Loader2, Square, UploadCloud } from "lucide-react";

import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { ImportSummary } from "../../types";

type Props = {
  markdown: string;
  sourceUrlInput: string;
  importSummary: ImportSummary | null;
  isFetchingMarkdown: boolean;
  isImportLoading: boolean;
  isCancellingImport: boolean;
  onSourceUrlChange: (value: string) => void;
  onMarkdownChange: (value: string) => void;
  onFetchMarkdown: () => void;
  onImportSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onCancelImport: () => void;
};

export function IngestionPanel({
  markdown,
  sourceUrlInput,
  importSummary,
  isFetchingMarkdown,
  isImportLoading,
  isCancellingImport,
  onSourceUrlChange,
  onMarkdownChange,
  onFetchMarkdown,
  onImportSubmit,
  onCancelImport,
}: Props) {
  const canCancelImport =
    !!importSummary && ["pending", "running"].includes(importSummary.status) && !importSummary.cancel_requested;

  return (
    <section className="flex h-full min-h-0 w-full flex-col">
      <div className="shrink-0 space-y-3 px-8 pt-8">
        <Badge className="w-fit bg-[var(--accent)] text-[var(--accent-foreground)]">Paper ingestion</Badge>
        <div className="flex items-center gap-3 text-3xl font-semibold tracking-tight">
          <UploadCloud className="h-5 w-5" />
          匯入 accepted papers
        </div>
        <p className="max-w-4xl text-base leading-7 text-[var(--muted-foreground)]">
          貼上你整理好的 Markdown 清單。系統會先用 LLM 解析 paper，再以規則 parser 當 fallback，接著抓摘要並建立 embedding。
        </p>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-8 pb-8 pt-6">
        <form className="space-y-4" onSubmit={onImportSubmit}>
          <div className="space-y-3 rounded-2xl border border-[var(--border)] bg-[var(--card)]/70 p-4">
            <div className="text-sm text-[var(--muted-foreground)]">
              貼上 conference accepted paper list URL，系統會先去抓 `https://r.jina.ai/&lt;url&gt;` 的 Markdown，填進下面輸入框。
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <input
                className="min-w-0 flex-1 rounded-2xl border border-[var(--border)] bg-[var(--card)]/90 px-4 py-3 text-sm text-[var(--foreground)] outline-none transition focus:border-[var(--primary)]"
                value={sourceUrlInput}
                onChange={(event) => onSourceUrlChange(event.target.value)}
                placeholder="https://www.usenix.org/conference/usenixsecurity24/fall-accepted-papers"
              />
              <Button
                className="w-full sm:w-auto sm:shrink-0"
                type="button"
                variant="outline"
                disabled={isFetchingMarkdown}
                onClick={onFetchMarkdown}
              >
                {isFetchingMarkdown ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <DownloadCloud className="mr-2 h-4 w-4" />}
                抓取 Markdown
              </Button>
            </div>
          </div>
          <textarea
            className="min-h-72 w-full rounded-2xl border border-[var(--border)] bg-[var(--card)]/85 p-4 text-sm text-[var(--foreground)] outline-none transition focus:border-[var(--primary)]"
            value={markdown}
            onChange={(event) => onMarkdownChange(event.target.value)}
            placeholder={"可以是 heading + 清單，也可以是比較自由的 markdown。\n只要每篇 paper 的 title 與 url 足夠明確，LLM 會先幫你解析。"}
          />
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)]/70 px-4 py-3 text-sm text-[var(--muted-foreground)]">
            建議仍盡量保留清楚的 paper title、連結，以及 venue/year heading，這樣解析會更穩。
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Button className="flex-1" type="submit" disabled={isImportLoading}>
              {isImportLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <UploadCloud className="mr-2 h-4 w-4" />}
              {isImportLoading ? "匯入工作進行中" : "建立匯入工作"}
            </Button>
            <Button
              className="border-[var(--border)] text-[var(--foreground)] hover:bg-[var(--muted)] sm:w-44"
              type="button"
              variant="outline"
              disabled={!canCancelImport || isCancellingImport}
              onClick={onCancelImport}
            >
              {isCancellingImport ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Square className="mr-2 h-4 w-4" />}
              {isCancellingImport ? "中斷中" : "中斷 job"}
            </Button>
          </div>
        </form>

        {importSummary ? (
          <div className="mt-4 space-y-4">
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--muted)] px-4 py-3 text-sm text-[var(--muted-foreground)]">
              狀態：<span className="font-semibold text-[var(--foreground)]">{formatImportStatus(importSummary.status)}</span>
              {importSummary.parsed_count > 0 ? <span> · 進度 {importSummary.processed_count}/{importSummary.parsed_count}</span> : null}
            </div>
            {importSummary.stage_message ? (
              <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)]/70 px-4 py-3 text-sm text-[var(--muted-foreground)]">
                <div>
                  階段：<span className="font-semibold text-[var(--foreground)]">{formatImportStage(importSummary.stage)}</span>
                </div>
                <div className="mt-1">{importSummary.stage_message}</div>
              </div>
            ) : null}
            <div className="grid gap-3 sm:grid-cols-2">
              <SummaryTile label="Parsed" value={importSummary.parsed_count} />
              <SummaryTile label="Processed" value={importSummary.processed_count} />
              <SummaryTile label="Imported" value={importSummary.imported_count} />
              <SummaryTile label="Skipped" value={importSummary.skipped_count} />
              <SummaryTile label="Failed" value={importSummary.failed_count} />
              <SummaryTile label="Abstract missing" value={importSummary.abstract_missing_count} />
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function formatImportStatus(status: ImportSummary["status"]) {
  if (status === "pending") return "等待執行";
  if (status === "running") return "匯入中";
  if (status === "cancelled") return "已取消";
  if (status === "completed") return "已完成";
  return "失敗";
}

function formatImportStage(stage: string | null | undefined) {
  if (stage === "queued") return "排隊中";
  if (stage === "preparing") return "準備中";
  if (stage === "cancelling") return "取消中";
  if (stage === "parsing_markdown") return "解析 Markdown";
  if (stage === "merging_results") return "統整結果";
  if (stage === "saving_papers") return "寫入 papers";
  if (stage === "fetching_abstracts") return "抓取摘要";
  if (stage === "generating_embeddings") return "建立 embedding";
  if (stage === "completed") return "已完成";
  if (stage === "cancelled") return "已取消";
  if (stage === "failed") return "失敗";
  return "進行中";
}

function SummaryTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--muted)] px-4 py-3">
      <div className="text-xs uppercase tracking-[0.2em] text-[var(--muted-foreground)]">{label}</div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
    </div>
  );
}
