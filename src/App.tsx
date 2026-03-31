import { ChevronLeft, ChevronRight, DownloadCloud, Link2, Loader2, Search, Sparkles, Square, Trash2, UploadCloud } from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./components/ui/card";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  sources?: SourceSummary[];
};

type Citation = {
  title: string;
  url?: string | null;
  source_page_url?: string | null;
  venue?: string | null;
  year?: number | null;
  source_type: "local_paper_db" | "web_search";
};

type SourceSummary = {
  source_type: "local_paper_db" | "web_search";
  description: string;
};

type ChatResponse = {
  session_id: string;
  answer: string;
  citations: Citation[];
  sources: SourceSummary[];
};

type ImportSummary = {
  id: string;
  source_name?: string | null;
  status: "pending" | "running" | "completed" | "failed";
  stage?: string | null;
  stage_message?: string | null;
  parsed_count: number;
  processed_count: number;
  imported_count: number;
  skipped_count: number;
  failed_count: number;
  abstract_missing_count: number;
  error_message?: string | null;
};

type FetchMarkdownResponse = {
  source_url: string;
  fetched_url: string;
  markdown: string;
};

type PaperRecord = {
  id: string;
  title: string;
  url?: string | null;
  conference_id?: string | null;
  conference_name?: string | null;
  source_page_url?: string | null;
  venue?: string | null;
  year?: number | null;
  abstract?: string | null;
  ingest_status: string;
};

type ConferenceRecord = {
  id: string;
  name: string;
  normalized_name: string;
  source_page_url?: string | null;
  year?: number | null;
  paper_count: number;
};

type PaperConferenceResolution = {
  paper: PaperRecord;
  conference?: ConferenceRecord | null;
  status: "already_attached" | "reused_existing" | "created_new" | "unresolved";
  duplicate_detected: boolean;
  message: string;
};

type PaperListResponse = {
  items: PaperRecord[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
};

type ConferenceListResponse = {
  items: ConferenceRecord[];
};

type BatchConferenceBindingResult = {
  total_candidates: number;
  bound_count: number;
  reused_existing_count: number;
  created_new_count: number;
  unresolved_count: number;
  message: string;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const defaultPaperPageSize = 10;

export default function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [sourceUrlInput, setSourceUrlInput] = useState("");
  const [markdown, setMarkdown] = useState(
    "## ICLR 2025 accepted papers\n\n- [Example Paper](https://arxiv.org/abs/2501.00001)\n- Another Example Paper: https://openreview.net/forum?id=demo",
  );
  const [importSummary, setImportSummary] = useState<ImportSummary | null>(null);
  const [papers, setPapers] = useState<PaperRecord[]>([]);
  const [conferences, setConferences] = useState<ConferenceRecord[]>([]);
  const [editingPaper, setEditingPaper] = useState<PaperRecord | null>(null);
  const [paperSearchQuery, setPaperSearchQuery] = useState("");
  const [paperConferenceFilter, setPaperConferenceFilter] = useState("");
  const [paperYearFromFilter, setPaperYearFromFilter] = useState("");
  const [paperYearToFilter, setPaperYearToFilter] = useState("");
  const [paperPage, setPaperPage] = useState(1);
  const [paperPageInput, setPaperPageInput] = useState("1");
  const [paperPageSize] = useState(defaultPaperPageSize);
  const [paperTotalItems, setPaperTotalItems] = useState(0);
  const [paperTotalPages, setPaperTotalPages] = useState(1);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [isImportSubmitting, setIsImportSubmitting] = useState(false);
  const [isFetchingMarkdown, setIsFetchingMarkdown] = useState(false);
  const [isPaperSaving, setIsPaperSaving] = useState(false);
  const [deletingPaperId, setDeletingPaperId] = useState<string | null>(null);
  const [resolvingConferencePaperId, setResolvingConferencePaperId] = useState<string | null>(null);
  const [isBulkBindingConferences, setIsBulkBindingConferences] = useState(false);
  const [bulkBindingSummary, setBulkBindingSummary] = useState<BatchConferenceBindingResult | null>(null);
  const [conferenceResolutionByPaperId, setConferenceResolutionByPaperId] = useState<Record<string, PaperConferenceResolution>>({});
  const [error, setError] = useState<string | null>(null);
  const chatAbortControllerRef = useRef<AbortController | null>(null);
  const isImportLoading = isImportSubmitting || ["pending", "running"].includes(importSummary?.status ?? "");

  const conversationHistory = useMemo(
    () =>
      messages.map((message) => ({
        role: message.role,
        content: message.content,
      })),
    [messages],
  );

  useEffect(() => {
    void loadConferences();
  }, []);

  useEffect(() => {
    void loadPapers(paperPage);
  }, [paperPage, paperSearchQuery, paperConferenceFilter, paperYearFromFilter, paperYearToFilter]);

  useEffect(() => {
    setPaperPageInput(String(paperPage));
  }, [paperPage]);

  useEffect(() => {
    return () => {
      chatAbortControllerRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!importSummary || !["pending", "running"].includes(importSummary.status)) {
      if (importSummary?.status === "completed") {
        void loadPapers();
      }
      return;
    }

    const interval = window.setInterval(async () => {
      try {
        const response = await fetch(`${apiBaseUrl}/papers/import-jobs/${importSummary.id}`);
        if (!response.ok) {
          throw new Error("無法取得匯入工作狀態。");
        }
        const payload: ImportSummary = await response.json();
        setImportSummary(payload);
        void loadPapers(paperPage);
        if (payload.status === "failed" && payload.error_message) {
          setError(payload.error_message);
        }
        if (payload.status === "completed") {
          setPaperPage(1);
          void loadPapers(1);
        }
      } catch (caughtError) {
        const messageText = caughtError instanceof Error ? caughtError.message : "發生未知錯誤。";
        setError(messageText);
      }
    }, 1500);

    return () => window.clearInterval(interval);
  }, [importSummary, paperPage, paperSearchQuery]);

  async function loadPapers(targetPage = paperPage) {
    try {
      const params = new URLSearchParams({
        page: String(targetPage),
        page_size: String(paperPageSize),
      });
      if (paperSearchQuery.trim()) {
        params.set("q", paperSearchQuery.trim());
      }
      if (paperConferenceFilter) {
        params.set("conference_id", paperConferenceFilter);
      }
      if (paperYearFromFilter.trim()) {
        params.set("year_from", paperYearFromFilter.trim());
      }
      if (paperYearToFilter.trim()) {
        params.set("year_to", paperYearToFilter.trim());
      }
      const response = await fetch(`${apiBaseUrl}/papers?${params.toString()}`);
      if (!response.ok) {
        throw new Error("無法取得 paper 清單。");
      }
      const payload: PaperListResponse = await response.json();
      setPapers(payload.items);
      setPaperPage(payload.page);
      setPaperPageInput(String(payload.page));
      setPaperTotalItems(payload.total_items);
      setPaperTotalPages(payload.total_pages);
    } catch (caughtError) {
      const messageText = caughtError instanceof Error ? caughtError.message : "發生未知錯誤。";
      setError(messageText);
    }
  }

  async function loadConferences() {
    try {
      const response = await fetch(`${apiBaseUrl}/conferences`);
      if (!response.ok) {
        throw new Error("無法取得 conference 清單。");
      }
      const payload: ConferenceListResponse = await response.json();
      setConferences(payload.items);
    } catch (caughtError) {
      const messageText = caughtError instanceof Error ? caughtError.message : "發生未知錯誤。";
      setError(messageText);
    }
  }

  async function handleChatSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = prompt.trim();
    if (!message) return;

    const nextMessages = [...messages, { role: "user" as const, content: message }];
    setMessages(nextMessages);
    setPrompt("");
    setError(null);
    setIsChatLoading(true);
    const abortController = new AbortController();
    chatAbortControllerRef.current = abortController;

    try {
      const response = await fetch(`${apiBaseUrl}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortController.signal,
        body: JSON.stringify({
          message,
          session_id: chatSessionId,
          history: conversationHistory,
        }),
      });
      if (!response.ok) {
        throw new Error("聊天請求失敗。");
      }
      const payload: ChatResponse = await response.json();
      setChatSessionId(payload.session_id);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: payload.answer,
          citations: payload.citations,
          sources: payload.sources,
        },
      ]);
    } catch (caughtError) {
      if (caughtError instanceof DOMException && caughtError.name === "AbortError") {
        return;
      }
      const messageText = caughtError instanceof Error ? caughtError.message : "發生未知錯誤。";
      setError(messageText);
    } finally {
      if (chatAbortControllerRef.current === abortController) {
        chatAbortControllerRef.current = null;
      }
      setIsChatLoading(false);
    }
  }

  function handleChatAbort() {
    chatAbortControllerRef.current?.abort();
    chatAbortControllerRef.current = null;
    setIsChatLoading(false);
    setError(null);
  }

  async function handleImportSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = markdown.trim();
    if (!content) return;

    setError(null);
    setIsImportSubmitting(true);
    try {
      const response = await fetch(`${apiBaseUrl}/papers/import-markdown`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, source_name: "frontend-manual-import" }),
      });
      if (!response.ok) {
        throw new Error("匯入失敗，請確認後端與資料庫設定。");
      }
      const payload: ImportSummary = await response.json();
      setImportSummary(payload);
    } catch (caughtError) {
      const messageText = caughtError instanceof Error ? caughtError.message : "發生未知錯誤。";
      setError(messageText);
    } finally {
      setIsImportSubmitting(false);
    }
  }

  async function handleFetchMarkdownFromUrl() {
    const sourceUrl = sourceUrlInput.trim();
    if (!sourceUrl) return;

    setError(null);
    setIsFetchingMarkdown(true);
    try {
      const params = new URLSearchParams({ url: sourceUrl });
      const response = await fetch(`${apiBaseUrl}/papers/fetch-markdown?${params.toString()}`);
      if (!response.ok) {
        throw new Error("無法從 Jina 取得 Markdown。");
      }
      const payload: FetchMarkdownResponse = await response.json();
      setMarkdown(payload.markdown);
    } catch (caughtError) {
      const messageText = caughtError instanceof Error ? caughtError.message : "發生未知錯誤。";
      setError(messageText);
    } finally {
      setIsFetchingMarkdown(false);
    }
  }

  async function handlePaperSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingPaper) return;

    setError(null);
    setIsPaperSaving(true);
    try {
      const response = await fetch(`${apiBaseUrl}/papers/${editingPaper.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: editingPaper.title,
          conference_id: editingPaper.conference_id || null,
          url: editingPaper.url || null,
          source_page_url: editingPaper.source_page_url || null,
          venue: editingPaper.venue || null,
          year: editingPaper.year || null,
          abstract: editingPaper.abstract || null,
        }),
      });
      if (!response.ok) {
        throw new Error("更新 paper 失敗。");
      }
      const payload: PaperRecord = await response.json();
      setPapers((current) => current.map((paper) => (paper.id === payload.id ? payload : paper)));
      setEditingPaper(null);
    } catch (caughtError) {
      const messageText = caughtError instanceof Error ? caughtError.message : "發生未知錯誤。";
      setError(messageText);
    } finally {
      setIsPaperSaving(false);
    }
  }

  async function handlePaperDelete(paperId: string) {
    setError(null);
    setDeletingPaperId(paperId);
    try {
      const response = await fetch(`${apiBaseUrl}/papers/${paperId}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error("刪除 paper 失敗。");
      }
      if (editingPaper?.id === paperId) {
        setEditingPaper(null);
      }
      const nextTotalItems = Math.max(0, paperTotalItems - 1);
      const nextTotalPages = Math.max(1, Math.ceil(nextTotalItems / paperPageSize));
      const nextPage = Math.min(paperPage, nextTotalPages);
      await loadPapers(nextPage);
    } catch (caughtError) {
      const messageText = caughtError instanceof Error ? caughtError.message : "發生未知錯誤。";
      setError(messageText);
    } finally {
      setDeletingPaperId(null);
    }
  }

  async function handleResolveConference(paperId: string) {
    setError(null);
    setResolvingConferencePaperId(paperId);
    try {
      const response = await fetch(`${apiBaseUrl}/papers/${paperId}/resolve-conference`, {
        method: "POST",
      });
      if (!response.ok) {
        throw new Error("無法建立或綁定 conference 實體。");
      }
      const payload: PaperConferenceResolution = await response.json();
      setConferenceResolutionByPaperId((current) => ({
        ...current,
        [paperId]: payload,
      }));
      setPapers((current) => current.map((paper) => (paper.id === payload.paper.id ? payload.paper : paper)));
      if (editingPaper?.id === payload.paper.id) {
        setEditingPaper(payload.paper);
      }
    } catch (caughtError) {
      const messageText = caughtError instanceof Error ? caughtError.message : "發生未知錯誤。";
      setError(messageText);
    } finally {
      setResolvingConferencePaperId(null);
    }
  }

  async function handleBulkBindConferences() {
    setError(null);
    setBulkBindingSummary(null);
    setIsBulkBindingConferences(true);
    try {
      const response = await fetch(`${apiBaseUrl}/conferences/bind-unlinked-papers`, {
        method: "POST",
      });
      if (!response.ok) {
        throw new Error("無法批次綁定未綁定的 papers。");
      }
      const payload: BatchConferenceBindingResult = await response.json();
      setBulkBindingSummary(payload);
      await Promise.all([loadConferences(), loadPapers(1)]);
      setPaperPage(1);
    } catch (caughtError) {
      const messageText = caughtError instanceof Error ? caughtError.message : "發生未知錯誤。";
      setError(messageText);
    } finally {
      setIsBulkBindingConferences(false);
    }
  }

  const visiblePageNumbers = buildVisiblePageNumbers(paperPage, paperTotalPages);

  return (
    <main className="mx-auto flex min-h-screen max-w-7xl flex-col gap-6 px-4 py-8 md:px-8">
      <section className="grid gap-6 lg:min-h-[720px] lg:grid-cols-[1fr_2fr]">
        <Card className="flex min-h-[720px] flex-col overflow-hidden lg:h-[720px] lg:min-h-0">
          <CardHeader>
            <Badge className="w-fit bg-[var(--accent)] text-[var(--accent-foreground)]">Paper ingestion</Badge>
            <CardTitle className="flex items-center gap-3">
              <UploadCloud className="h-5 w-5" />
              匯入 accepted papers
            </CardTitle>
            <CardDescription>
              貼上你整理好的 Markdown 清單。系統會先用 LLM 解析 paper，再以規則 parser 當 fallback，接著抓摘要並建立
              embedding。
            </CardDescription>
          </CardHeader>
          <CardContent className="min-h-0 flex-1 overflow-y-auto">
            <form className="space-y-4" onSubmit={handleImportSubmit}>
              <div className="space-y-3 rounded-2xl border border-[var(--border)] bg-white/70 p-4">
                <div className="text-sm text-[var(--muted-foreground)]">
                  貼上 conference accepted paper list URL，系統會先去抓 `https://r.jina.ai/&lt;url&gt;` 的 Markdown，填進下面輸入框。
                </div>
                <div className="flex flex-col gap-3 sm:flex-row">
                  <input
                    className="flex-1 rounded-2xl border border-[var(--border)] bg-white/90 px-4 py-3 text-sm outline-none transition focus:border-[var(--primary)]"
                    value={sourceUrlInput}
                    onChange={(event) => setSourceUrlInput(event.target.value)}
                    placeholder="https://www.usenix.org/conference/usenixsecurity24/fall-accepted-papers"
                  />
                  <Button type="button" variant="outline" disabled={isFetchingMarkdown} onClick={() => void handleFetchMarkdownFromUrl()}>
                    {isFetchingMarkdown ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <DownloadCloud className="mr-2 h-4 w-4" />}
                    抓取 Markdown
                  </Button>
                </div>
              </div>
              <textarea
                className="min-h-72 w-full rounded-2xl border border-[var(--border)] bg-white/85 p-4 text-sm outline-none transition focus:border-[var(--primary)]"
                value={markdown}
                onChange={(event) => setMarkdown(event.target.value)}
                placeholder={
                  "可以是 heading + 清單，也可以是比較自由的 markdown。\n只要每篇 paper 的 title 與 url 足夠明確，LLM 會先幫你解析。"
                }
              />
              <div className="rounded-2xl border border-[var(--border)] bg-white/70 px-4 py-3 text-sm text-[var(--muted-foreground)]">
                建議仍盡量保留清楚的 paper title、連結，以及 venue/year heading，這樣解析會更穩。
              </div>
              <Button className="w-full" type="submit" disabled={isImportLoading}>
                {isImportLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <UploadCloud className="mr-2 h-4 w-4" />}
                {isImportLoading ? "匯入工作進行中" : "建立匯入工作"}
              </Button>
            </form>

            {importSummary ? (
              <div className="mt-4 space-y-4">
                <div className="rounded-2xl border border-[var(--border)] bg-[var(--muted)] px-4 py-3 text-sm text-[var(--muted-foreground)]">
                  狀態：<span className="font-semibold text-[var(--foreground)]">{formatImportStatus(importSummary.status)}</span>
                  {importSummary.parsed_count > 0 ? (
                    <span>
                      {" "}
                      · 進度 {importSummary.processed_count}/{importSummary.parsed_count}
                    </span>
                  ) : null}
                </div>
                {importSummary.stage_message ? (
                  <div className="rounded-2xl border border-[var(--border)] bg-white/70 px-4 py-3 text-sm text-[var(--muted-foreground)]">
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
          </CardContent>
        </Card>

        <Card className="flex min-h-[720px] flex-col lg:h-[720px] lg:min-h-0">
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

            <form className="space-y-3" onSubmit={handleChatSubmit}>
              <textarea
                className="min-h-28 w-full rounded-2xl border border-[var(--border)] bg-white/90 p-4 text-sm outline-none transition focus:border-[var(--primary)]"
                placeholder="例如：幫我找 2024-2025 跟 agent security 相關的論文，先從本地資料庫找，不夠再補最新背景。"
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
              />
              <div className="flex gap-3">
                <Button className="flex-1" type="submit" disabled={isChatLoading}>
                  <Sparkles className="mr-2 h-4 w-4" />
                  發送訊息
                </Button>
                <Button className="min-w-32" type="button" variant="outline" disabled={!isChatLoading} onClick={handleChatAbort}>
                  <Square className="mr-2 h-4 w-4" />
                  中斷回覆
                </Button>
              </div>
            </form>

            {error ? <p className="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-600">{error}</p> : null}
          </CardContent>
        </Card>
      </section>

      <section>
        <Card>
          <CardHeader>
            <Badge className="w-fit">Paper records</Badge>
            <CardTitle>編輯資料庫內容</CardTitle>
            <CardDescription>支援只有 title 與 conference source URL 的 paper，並可直接在前端補齊欄位。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-col gap-3 rounded-2xl border border-[var(--border)] bg-white/70 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-sm text-[var(--muted-foreground)]">
                一鍵把目前 `conference_id` 還是空的 papers 依既有規則補綁到 conference 實體。
              </div>
              <Button type="button" onClick={() => void handleBulkBindConferences()} disabled={isBulkBindingConferences}>
                {isBulkBindingConferences ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Link2 className="mr-2 h-4 w-4" />}
                綁定所有未綁定 papers
              </Button>
            </div>

            {bulkBindingSummary ? (
              <div className="rounded-2xl border border-[var(--border)] bg-[var(--muted)] px-4 py-3 text-sm text-[var(--muted-foreground)]">
                <div>{bulkBindingSummary.message}</div>
                <div className="mt-2 flex flex-wrap gap-3 text-xs">
                  <span>候選 {bulkBindingSummary.total_candidates}</span>
                  <span>成功綁定 {bulkBindingSummary.bound_count}</span>
                  <span>重用既有 {bulkBindingSummary.reused_existing_count}</span>
                  <span>新建 {bulkBindingSummary.created_new_count}</span>
                  <span>無法判定 {bulkBindingSummary.unresolved_count}</span>
                </div>
              </div>
            ) : null}

            {editingPaper ? (
              <form className="space-y-3 rounded-3xl border border-[var(--border)] bg-white/75 p-4" onSubmit={handlePaperSave}>
                <label className="block text-sm">
                  <div className="mb-1 text-[var(--muted-foreground)]">Title</div>
                  <input
                    className="w-full rounded-xl border border-[var(--border)] bg-white px-3 py-2"
                    value={editingPaper.title}
                    onChange={(event) => setEditingPaper({ ...editingPaper, title: event.target.value })}
                  />
                </label>
                <label className="block text-sm">
                  <div className="mb-1 text-[var(--muted-foreground)]">Conference Entity</div>
                  <select
                    className="w-full rounded-xl border border-[var(--border)] bg-white px-3 py-2"
                    value={editingPaper.conference_id ?? ""}
                    onChange={(event) => {
                      const selectedConferenceId = event.target.value || null;
                      const selectedConference = conferences.find((conference) => conference.id === selectedConferenceId) ?? null;
                      setEditingPaper({
                        ...editingPaper,
                        conference_id: selectedConference?.id ?? null,
                        conference_name: selectedConference?.name ?? null,
                        venue: selectedConference?.name ?? editingPaper.venue,
                        year: selectedConference?.year ?? editingPaper.year,
                        source_page_url: selectedConference?.source_page_url ?? editingPaper.source_page_url,
                      });
                    }}
                  >
                    <option value="">不綁定，手動編輯 venue/year</option>
                    {conferences.map((conference) => (
                      <option key={conference.id} value={conference.id}>
                        {conference.name}
                        {conference.year ? ` · ${conference.year}` : ""}
                        {` · ${conference.paper_count} papers`}
                      </option>
                    ))}
                  </select>
                  <div className="mt-1 text-xs text-[var(--muted-foreground)]">
                    若選了 conference entity，儲存時會以該 entity 的名稱與年份為準。
                  </div>
                </label>
                <label className="block text-sm">
                  <div className="mb-1 text-[var(--muted-foreground)]">Paper URL</div>
                  <input
                    className="w-full rounded-xl border border-[var(--border)] bg-white px-3 py-2"
                    value={editingPaper.url ?? ""}
                    onChange={(event) => setEditingPaper({ ...editingPaper, url: event.target.value })}
                  />
                </label>
                <label className="block text-sm">
                  <div className="mb-1 text-[var(--muted-foreground)]">Conference Source URL</div>
                  <input
                    className="w-full rounded-xl border border-[var(--border)] bg-white px-3 py-2"
                    value={editingPaper.source_page_url ?? ""}
                    disabled={Boolean(editingPaper.conference_id)}
                    onChange={(event) => setEditingPaper({ ...editingPaper, source_page_url: event.target.value })}
                  />
                </label>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="block text-sm">
                    <div className="mb-1 text-[var(--muted-foreground)]">Venue</div>
                    <input
                      className="w-full rounded-xl border border-[var(--border)] bg-white px-3 py-2"
                      value={editingPaper.venue ?? ""}
                      disabled={Boolean(editingPaper.conference_id)}
                      onChange={(event) => setEditingPaper({ ...editingPaper, venue: event.target.value })}
                    />
                  </label>
                  <label className="block text-sm">
                    <div className="mb-1 text-[var(--muted-foreground)]">Year</div>
                    <input
                      className="w-full rounded-xl border border-[var(--border)] bg-white px-3 py-2"
                      type="number"
                      value={editingPaper.year ?? ""}
                      disabled={Boolean(editingPaper.conference_id)}
                      onChange={(event) =>
                        setEditingPaper({ ...editingPaper, year: event.target.value ? Number(event.target.value) : null })
                      }
                    />
                  </label>
                </div>
                <label className="block text-sm">
                  <div className="mb-1 text-[var(--muted-foreground)]">Abstract</div>
                  <textarea
                    className="min-h-28 w-full rounded-xl border border-[var(--border)] bg-white px-3 py-2"
                    value={editingPaper.abstract ?? ""}
                    onChange={(event) => setEditingPaper({ ...editingPaper, abstract: event.target.value })}
                  />
                </label>
                {editingPaper.conference_name ? (
                  <div className="rounded-2xl border border-[var(--border)] bg-[var(--muted)] px-4 py-3 text-sm text-[var(--muted-foreground)]">
                    目前綁定的 conference 實體：
                    <span className="ml-2 font-semibold text-[var(--foreground)]">{editingPaper.conference_name}</span>
                  </div>
                ) : null}
                {editingPaper ? (
                  <Button
                    type="button"
                    variant="outline"
                    disabled={resolvingConferencePaperId === editingPaper.id}
                    onClick={() => void handleResolveConference(editingPaper.id)}
                  >
                    {resolvingConferencePaperId === editingPaper.id ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Link2 className="mr-2 h-4 w-4" />
                    )}
                    取出並綁定 conference 實體
                  </Button>
                ) : null}
                {editingPaper && conferenceResolutionByPaperId[editingPaper.id] ? (
                  <div className="rounded-2xl border border-[var(--border)] bg-white/70 px-4 py-3 text-sm text-[var(--muted-foreground)]">
                    {conferenceResolutionByPaperId[editingPaper.id].message}
                  </div>
                ) : null}
                <div className="flex gap-3">
                  <Button type="submit" disabled={isPaperSaving}>
                    {isPaperSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    儲存修改
                  </Button>
                  <Button type="button" variant="outline" onClick={() => setEditingPaper(null)}>
                    取消
                  </Button>
                </div>
              </form>
            ) : null}

            <div className="flex flex-col gap-3 rounded-2xl border border-[var(--border)] bg-[var(--muted)] px-4 py-3 text-sm text-[var(--muted-foreground)] sm:flex-row sm:items-center sm:justify-between">
              <div>
                共 <span className="font-semibold text-[var(--foreground)]">{paperTotalItems}</span> 筆
                {" · "}
                第 <span className="font-semibold text-[var(--foreground)]">{paperPage}</span> / {paperTotalPages} 頁
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button type="button" variant="outline" size="sm" disabled={paperPage <= 1} onClick={() => setPaperPage((current) => current - 1)}>
                  <ChevronLeft className="mr-1 h-4 w-4" />
                  上一頁
                </Button>
                {visiblePageNumbers.map((pageNumber) => (
                  <Button
                    key={pageNumber}
                    type="button"
                    size="sm"
                    variant={pageNumber === paperPage ? "default" : "outline"}
                    onClick={() => setPaperPage(pageNumber)}
                  >
                    {pageNumber}
                  </Button>
                ))}
                <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={paperPage >= paperTotalPages}
                    onClick={() => setPaperPage((current) => current + 1)}
                  >
                    下一頁
                    <ChevronRight className="ml-1 h-4 w-4" />
                  </Button>
                <form
                  className="flex items-center gap-2"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const nextPage = Number(paperPageInput);
                    if (!Number.isFinite(nextPage)) return;
                    const normalizedPage = Math.min(Math.max(1, nextPage), paperTotalPages);
                    setPaperPage(normalizedPage);
                  }}
                >
                  <input
                    className="w-20 rounded-xl border border-[var(--border)] bg-white px-3 py-2 text-sm"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    value={paperPageInput}
                    onChange={(event) => setPaperPageInput(event.target.value)}
                    placeholder="頁碼"
                  />
                  <Button type="submit" variant="outline" size="sm">
                    跳轉
                  </Button>
                </form>
              </div>
            </div>

            <form
              className="grid gap-3 rounded-2xl border border-[var(--border)] bg-white/70 p-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(180px,1fr)_120px_120px_auto_auto]"
              onSubmit={(event) => {
                event.preventDefault();
                setPaperPage(1);
                void loadPapers(1);
              }}
            >
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--muted-foreground)]" />
                <input
                  className="w-full rounded-xl border border-[var(--border)] bg-white px-10 py-2 text-sm"
                  value={paperSearchQuery}
                  onChange={(event) => setPaperSearchQuery(event.target.value)}
                  placeholder="用關鍵字搜尋 title、venue、abstract 或 source URL"
                />
              </div>
              <select
                className="rounded-xl border border-[var(--border)] bg-white px-3 py-2 text-sm"
                value={paperConferenceFilter}
                onChange={(event) => {
                  setPaperConferenceFilter(event.target.value);
                  setPaperPage(1);
                }}
              >
                <option value="">全部 conference</option>
                {conferences.map((conference) => (
                  <option key={conference.id} value={conference.id}>
                    {conference.name}
                    {conference.year ? ` (${conference.year})` : ""}
                    {` · ${conference.paper_count} papers`}
                  </option>
                ))}
              </select>
              <input
                className="rounded-xl border border-[var(--border)] bg-white px-3 py-2 text-sm"
                inputMode="numeric"
                pattern="[0-9]*"
                value={paperYearFromFilter}
                onChange={(event) => {
                  setPaperYearFromFilter(event.target.value);
                  setPaperPage(1);
                }}
                placeholder="起始年份"
              />
              <input
                className="rounded-xl border border-[var(--border)] bg-white px-3 py-2 text-sm"
                inputMode="numeric"
                pattern="[0-9]*"
                value={paperYearToFilter}
                onChange={(event) => {
                  setPaperYearToFilter(event.target.value);
                  setPaperPage(1);
                }}
                placeholder="結束年份"
              />
              <Button type="submit">搜尋</Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setPaperSearchQuery("");
                  setPaperConferenceFilter("");
                  setPaperYearFromFilter("");
                  setPaperYearToFilter("");
                  setPaperPage(1);
                }}
              >
                清除
              </Button>
            </form>

            <div className="space-y-3">
              {papers.map((paper) => (
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
                      {conferenceResolutionByPaperId[paper.id] ? (
                        <div className="rounded-2xl border border-[var(--border)] bg-[var(--muted)] px-4 py-3 text-sm text-[var(--muted-foreground)]">
                          <div>{conferenceResolutionByPaperId[paper.id].message}</div>
                          {conferenceResolutionByPaperId[paper.id].duplicate_detected ? (
                            <div className="mt-1 text-xs">已偵測到重複 conference，沒有重複建立新實體。</div>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                    <div className="flex flex-col gap-2">
                      <Button variant="outline" onClick={() => setEditingPaper({ ...paper })}>
                        編輯
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => void handleResolveConference(paper.id)}
                        disabled={resolvingConferencePaperId === paper.id}
                      >
                        {resolvingConferencePaperId === paper.id ? (
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : (
                          <Link2 className="mr-2 h-4 w-4" />
                        )}
                        綁定 conference 實體
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => void handlePaperDelete(paper.id)}
                        disabled={deletingPaperId === paper.id}
                      >
                        {deletingPaperId === paper.id ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Trash2 className="mr-2 h-4 w-4" />}
                        刪除
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
              {papers.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-[var(--border)] bg-white/60 px-4 py-8 text-center text-sm text-[var(--muted-foreground)]">
                  目前這一頁沒有 paper。
                </div>
              ) : null}
            </div>
          </CardContent>
        </Card>
      </section>
    </main>
  );
}

function formatImportStatus(status: ImportSummary["status"]) {
  if (status === "pending") return "等待執行";
  if (status === "running") return "匯入中";
  if (status === "completed") return "已完成";
  return "失敗";
}

function formatImportStage(stage: string | null | undefined) {
  if (stage === "queued") return "排隊中";
  if (stage === "preparing") return "準備中";
  if (stage === "parsing_markdown") return "解析 Markdown";
  if (stage === "merging_results") return "統整結果";
  if (stage === "saving_papers") return "寫入 papers";
  if (stage === "fetching_abstracts") return "抓取摘要";
  if (stage === "generating_embeddings") return "建立 embedding";
  if (stage === "completed") return "已完成";
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

function buildVisiblePageNumbers(currentPage: number, totalPages: number) {
  const start = Math.max(1, currentPage - 2);
  const end = Math.min(totalPages, currentPage + 2);
  const pages: number[] = [];
  for (let page = start; page <= end; page += 1) {
    pages.push(page);
  }
  return pages;
}
