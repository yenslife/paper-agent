import { ChevronLeft, ChevronRight, Link2, Loader2, Search, Trash2 } from "lucide-react";

import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";
import { BatchConferenceBindingResult, ConferenceRecord, PaperConferenceResolution, PaperRecord } from "../../types";

type Props = {
  papers: PaperRecord[];
  conferences: ConferenceRecord[];
  editingPaper: PaperRecord | null;
  paperSearchQuery: string;
  paperConferenceFilter: string;
  paperYearFromFilter: string;
  paperYearToFilter: string;
  paperPage: number;
  paperPageInput: string;
  paperTotalItems: number;
  paperTotalPages: number;
  isPaperSaving: boolean;
  deletingPaperId: string | null;
  resolvingConferencePaperId: string | null;
  isBulkBindingConferences: boolean;
  bulkBindingSummary: BatchConferenceBindingResult | null;
  conferenceResolutionByPaperId: Record<string, PaperConferenceResolution>;
  onEditPaperChange: (paper: PaperRecord | null) => void;
  onPaperSearchQueryChange: (value: string) => void;
  onPaperConferenceFilterChange: (value: string) => void;
  onPaperYearFromFilterChange: (value: string) => void;
  onPaperYearToFilterChange: (value: string) => void;
  onPaperPageChange: (page: number | ((current: number) => number)) => void;
  onPaperPageInputChange: (value: string) => void;
  onPaperSave: (event: React.FormEvent<HTMLFormElement>) => void;
  onPaperDelete: (paperId: string) => void;
  onResolveConference: (paperId: string) => void;
  onBulkBindConferences: () => void;
  onSearchSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onClearFilters: () => void;
};

export function PaperRecordsSection(props: Props) {
  const visiblePageNumbers = buildVisiblePageNumbers(props.paperPage, props.paperTotalPages);

  return (
    <section>
      <Card className="overflow-x-hidden">
        <CardHeader>
          <Badge className="w-fit">Paper records</Badge>
          <CardTitle>編輯資料庫內容</CardTitle>
          <CardDescription>支援只有 title 與 conference source URL 的 paper，並可直接在前端補齊欄位。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-3 rounded-2xl border border-[var(--border)] bg-white/70 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-sm text-[var(--muted-foreground)]">一鍵把目前 `conference_id` 還是空的 papers 依既有規則補綁到 conference 實體。</div>
            <Button type="button" onClick={props.onBulkBindConferences} disabled={props.isBulkBindingConferences}>
              {props.isBulkBindingConferences ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Link2 className="mr-2 h-4 w-4" />}
              綁定所有未綁定 papers
            </Button>
          </div>

          {props.bulkBindingSummary ? (
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--muted)] px-4 py-3 text-sm text-[var(--muted-foreground)]">
              <div>{props.bulkBindingSummary.message}</div>
              <div className="mt-2 flex flex-wrap gap-3 text-xs">
                <span>候選 {props.bulkBindingSummary.total_candidates}</span>
                <span>成功綁定 {props.bulkBindingSummary.bound_count}</span>
                <span>重用既有 {props.bulkBindingSummary.reused_existing_count}</span>
                <span>新建 {props.bulkBindingSummary.created_new_count}</span>
                <span>無法判定 {props.bulkBindingSummary.unresolved_count}</span>
              </div>
            </div>
          ) : null}

          {props.editingPaper ? (
            <form className="space-y-3 rounded-3xl border border-[var(--border)] bg-white/75 p-4" onSubmit={props.onPaperSave}>
              <label className="block text-sm">
                <div className="mb-1 text-[var(--muted-foreground)]">Title</div>
                <input
                  className="w-full rounded-xl border border-[var(--border)] bg-white px-3 py-2"
                  value={props.editingPaper.title}
                  onChange={(event) => props.onEditPaperChange({ ...props.editingPaper!, title: event.target.value })}
                />
              </label>
              <label className="block text-sm">
                <div className="mb-1 text-[var(--muted-foreground)]">Conference Entity</div>
                <select
                  className="w-full rounded-xl border border-[var(--border)] bg-white px-3 py-2"
                  value={props.editingPaper.conference_id ?? ""}
                  onChange={(event) => {
                    const selectedConferenceId = event.target.value || null;
                    const selectedConference = props.conferences.find((conference) => conference.id === selectedConferenceId) ?? null;
                    props.onEditPaperChange({
                      ...props.editingPaper!,
                      conference_id: selectedConference?.id ?? null,
                      conference_name: selectedConference?.name ?? null,
                      venue: selectedConference?.name ?? props.editingPaper!.venue,
                      year: selectedConference?.year ?? props.editingPaper!.year,
                      source_page_url: selectedConference?.source_page_url ?? props.editingPaper!.source_page_url,
                    });
                  }}
                >
                  <option value="">不綁定，手動編輯 venue/year</option>
                  {props.conferences.map((conference) => (
                    <option key={conference.id} value={conference.id}>
                      {conference.name}
                      {conference.year ? ` · ${conference.year}` : ""}
                      {` · ${conference.paper_count} papers`}
                    </option>
                  ))}
                </select>
                <div className="mt-1 text-xs text-[var(--muted-foreground)]">若選了 conference entity，儲存時會以該 entity 的名稱與年份為準。</div>
              </label>
              <label className="block text-sm">
                <div className="mb-1 text-[var(--muted-foreground)]">Paper URL</div>
                <input
                  className="w-full rounded-xl border border-[var(--border)] bg-white px-3 py-2"
                  value={props.editingPaper.url ?? ""}
                  onChange={(event) => props.onEditPaperChange({ ...props.editingPaper!, url: event.target.value })}
                />
              </label>
              <label className="block text-sm">
                <div className="mb-1 text-[var(--muted-foreground)]">Conference Source URL</div>
                <input
                  className="w-full rounded-xl border border-[var(--border)] bg-white px-3 py-2"
                  value={props.editingPaper.source_page_url ?? ""}
                  disabled={Boolean(props.editingPaper.conference_id)}
                  onChange={(event) => props.onEditPaperChange({ ...props.editingPaper!, source_page_url: event.target.value })}
                />
              </label>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block text-sm">
                  <div className="mb-1 text-[var(--muted-foreground)]">Venue</div>
                  <input
                    className="w-full rounded-xl border border-[var(--border)] bg-white px-3 py-2"
                    value={props.editingPaper.venue ?? ""}
                    disabled={Boolean(props.editingPaper.conference_id)}
                    onChange={(event) => props.onEditPaperChange({ ...props.editingPaper!, venue: event.target.value })}
                  />
                </label>
                <label className="block text-sm">
                  <div className="mb-1 text-[var(--muted-foreground)]">Year</div>
                  <input
                    className="w-full rounded-xl border border-[var(--border)] bg-white px-3 py-2"
                    type="number"
                    value={props.editingPaper.year ?? ""}
                    disabled={Boolean(props.editingPaper.conference_id)}
                    onChange={(event) =>
                      props.onEditPaperChange({ ...props.editingPaper!, year: event.target.value ? Number(event.target.value) : null })
                    }
                  />
                </label>
              </div>
              <label className="block text-sm">
                <div className="mb-1 text-[var(--muted-foreground)]">Abstract</div>
                <textarea
                  className="min-h-28 w-full rounded-xl border border-[var(--border)] bg-white px-3 py-2"
                  value={props.editingPaper.abstract ?? ""}
                  onChange={(event) => props.onEditPaperChange({ ...props.editingPaper!, abstract: event.target.value })}
                />
              </label>
              {props.editingPaper.conference_name ? (
                <div className="rounded-2xl border border-[var(--border)] bg-[var(--muted)] px-4 py-3 text-sm text-[var(--muted-foreground)]">
                  目前綁定的 conference 實體：
                  <span className="ml-2 font-semibold text-[var(--foreground)]">{props.editingPaper.conference_name}</span>
                </div>
              ) : null}
              <Button
                type="button"
                variant="outline"
                disabled={props.resolvingConferencePaperId === props.editingPaper.id}
                onClick={() => props.onResolveConference(props.editingPaper!.id)}
              >
                {props.resolvingConferencePaperId === props.editingPaper.id ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Link2 className="mr-2 h-4 w-4" />
                )}
                取出並綁定 conference 實體
              </Button>
              {props.conferenceResolutionByPaperId[props.editingPaper.id] ? (
                <div className="rounded-2xl border border-[var(--border)] bg-white/70 px-4 py-3 text-sm text-[var(--muted-foreground)]">
                  {props.conferenceResolutionByPaperId[props.editingPaper.id].message}
                </div>
              ) : null}
              <div className="flex gap-3">
                <Button type="submit" disabled={props.isPaperSaving}>
                  {props.isPaperSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  儲存修改
                </Button>
                <Button type="button" variant="outline" onClick={() => props.onEditPaperChange(null)}>
                  取消
                </Button>
              </div>
            </form>
          ) : null}

          <div className="flex flex-col gap-3 rounded-2xl border border-[var(--border)] bg-[var(--muted)] px-4 py-3 text-sm text-[var(--muted-foreground)] sm:flex-row sm:items-center sm:justify-between">
            <div>
              共 <span className="font-semibold text-[var(--foreground)]">{props.paperTotalItems}</span> 筆 · 第{" "}
              <span className="font-semibold text-[var(--foreground)]">{props.paperPage}</span> / {props.paperTotalPages} 頁
            </div>
            <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={props.paperPage <= 1}
                  onClick={() => props.onPaperPageChange((current) => current - 1)}
                >
                <ChevronLeft className="mr-1 h-4 w-4" />
                上一頁
                </Button>
                {visiblePageNumbers.map((pageNumber) => (
                  <Button
                    key={pageNumber}
                    type="button"
                    size="sm"
                    variant={pageNumber === props.paperPage ? "default" : "outline"}
                    onClick={() => props.onPaperPageChange(pageNumber)}
                  >
                    {pageNumber}
                  </Button>
                ))}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={props.paperPage >= props.paperTotalPages}
                  onClick={() => props.onPaperPageChange((current) => current + 1)}
                >
                  下一頁
                  <ChevronRight className="ml-1 h-4 w-4" />
                </Button>
              </div>
              <form
                className="flex min-w-0 items-center gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  const nextPage = Number(props.paperPageInput);
                  if (!Number.isFinite(nextPage)) return;
                  const normalizedPage = Math.min(Math.max(1, nextPage), props.paperTotalPages);
                  props.onPaperPageChange(normalizedPage);
                }}
              >
                <input
                  className="min-w-0 flex-1 rounded-xl border border-[var(--border)] bg-white px-3 py-2 text-sm sm:w-20 sm:flex-none"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  value={props.paperPageInput}
                  onChange={(event) => props.onPaperPageInputChange(event.target.value)}
                  placeholder="頁碼"
                />
                <Button type="submit" variant="outline" size="sm">
                  跳轉
                </Button>
              </form>
            </div>
          </div>

          <form
            className="grid min-w-0 gap-3 rounded-2xl border border-[var(--border)] bg-white/70 p-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(180px,1fr)_120px_120px_auto_auto]"
            onSubmit={props.onSearchSubmit}
          >
            <div className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--muted-foreground)]" />
              <input
                className="w-full min-w-0 rounded-xl border border-[var(--border)] bg-white px-10 py-2 text-sm"
                value={props.paperSearchQuery}
                onChange={(event) => props.onPaperSearchQueryChange(event.target.value)}
                placeholder="用關鍵字搜尋 title、venue、abstract 或 source URL"
              />
            </div>
            <select
              className="min-w-0 rounded-xl border border-[var(--border)] bg-white px-3 py-2 text-sm"
              value={props.paperConferenceFilter}
              onChange={(event) => props.onPaperConferenceFilterChange(event.target.value)}
            >
              <option value="">全部 conference</option>
              {props.conferences.map((conference) => (
                <option key={conference.id} value={conference.id}>
                  {conference.name}
                  {conference.year ? ` (${conference.year})` : ""}
                  {` · ${conference.paper_count} papers`}
                </option>
              ))}
            </select>
            <input
              className="min-w-0 rounded-xl border border-[var(--border)] bg-white px-3 py-2 text-sm"
              inputMode="numeric"
              pattern="[0-9]*"
              value={props.paperYearFromFilter}
              onChange={(event) => props.onPaperYearFromFilterChange(event.target.value)}
              placeholder="起始年份"
            />
            <input
              className="min-w-0 rounded-xl border border-[var(--border)] bg-white px-3 py-2 text-sm"
              inputMode="numeric"
              pattern="[0-9]*"
              value={props.paperYearToFilter}
              onChange={(event) => props.onPaperYearToFilterChange(event.target.value)}
              placeholder="結束年份"
            />
            <Button className="w-full lg:w-auto" type="submit">搜尋</Button>
            <Button className="w-full lg:w-auto" type="button" variant="outline" onClick={props.onClearFilters}>
              清除
            </Button>
          </form>

          <div className="space-y-3">
            {props.papers.map((paper) => (
              <div key={paper.id} className="rounded-2xl border border-[var(--border)] bg-white/70 p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="space-y-2">
                    <div className="font-semibold">{paper.title}</div>
                    <div className="flex flex-wrap gap-2 text-xs text-[var(--muted-foreground)]">
                      <Badge>{paper.ingest_status}</Badge>
                      {paper.venue ? <span>{paper.venue}</span> : null}
                      {paper.year ? <span>{paper.year}</span> : null}
                      {paper.conference_name ? (
                        <Badge className="border border-[var(--border)] bg-white text-[var(--foreground)]">
                          Conference entity: {paper.conference_name}
                        </Badge>
                      ) : null}
                    </div>
                    <div className="space-y-1 text-sm text-[var(--muted-foreground)]">
                      <div>Paper URL: {paper.url || "未設定"}</div>
                      <div>Conference Source: {paper.source_page_url || "未設定"}</div>
                    </div>
                    {props.conferenceResolutionByPaperId[paper.id] ? (
                      <div className="rounded-2xl border border-[var(--border)] bg-[var(--muted)] px-4 py-3 text-sm text-[var(--muted-foreground)]">
                        <div>{props.conferenceResolutionByPaperId[paper.id].message}</div>
                        {props.conferenceResolutionByPaperId[paper.id].duplicate_detected ? (
                          <div className="mt-1 text-xs">已偵測到重複 conference，沒有重複建立新實體。</div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                  <div className="flex w-full flex-col gap-2 sm:w-auto sm:min-w-[11rem]">
                    <Button className="w-full whitespace-normal text-center leading-snug" variant="outline" onClick={() => props.onEditPaperChange({ ...paper })}>
                      編輯
                    </Button>
                    <Button
                      className="w-full whitespace-normal text-center leading-snug"
                      variant="outline"
                      onClick={() => props.onResolveConference(paper.id)}
                      disabled={props.resolvingConferencePaperId === paper.id}
                    >
                      {props.resolvingConferencePaperId === paper.id ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <Link2 className="mr-2 h-4 w-4" />
                      )}
                      綁定 conference 實體
                    </Button>
                    <Button
                      className="w-full whitespace-normal text-center leading-snug"
                      variant="outline"
                      onClick={() => props.onPaperDelete(paper.id)}
                      disabled={props.deletingPaperId === paper.id}
                    >
                      {props.deletingPaperId === paper.id ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Trash2 className="mr-2 h-4 w-4" />}
                      刪除
                    </Button>
                  </div>
                </div>
              </div>
            ))}
            {props.papers.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-[var(--border)] bg-white/60 px-4 py-8 text-center text-sm text-[var(--muted-foreground)]">
                目前這一頁沒有 paper。
              </div>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </section>
  );
}

function buildVisiblePageNumbers(currentPage: number, totalPages: number) {
  const start = Math.max(1, currentPage - 2);
  const end = Math.min(totalPages, currentPage + 2);
  const pages: number[] = [];
  for (let page = start; page <= end; page += 1) {
    pages.push(page);
  }
  return pages;
}
