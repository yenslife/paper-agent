import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { buildApiUrl } from "./lib/api";
import { ChatPanel } from "./features/chat/ChatPanel";
import { IngestionPanel } from "./features/ingestion/IngestionPanel";
import { AppSidebar, AppView, getViewTitle } from "./features/navigation/AppSidebar";
import { PaperRecordsSection } from "./features/papers/PaperRecordsSection";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "./components/ui/sidebar";
import {
  BatchConferenceBindingResult,
  ChatMessage,
  ChatResponse,
  ConferenceListResponse,
  ConferenceRecord,
  FetchMarkdownResponse,
  ImportSummary,
  PaperConferenceResolution,
  PaperListResponse,
  PaperRecord,
} from "./types";

const defaultPaperPageSize = 10;

export default function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [currentView, setCurrentView] = useState<AppView>("chat");
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
  const [paperTotalItems, setPaperTotalItems] = useState(0);
  const [paperTotalPages, setPaperTotalPages] = useState(1);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [isImportSubmitting, setIsImportSubmitting] = useState(false);
  const [isFetchingMarkdown, setIsFetchingMarkdown] = useState(false);
  const [isCancellingImport, setIsCancellingImport] = useState(false);
  const [isPaperSaving, setIsPaperSaving] = useState(false);
  const [deletingPaperId, setDeletingPaperId] = useState<string | null>(null);
  const [resolvingConferencePaperId, setResolvingConferencePaperId] = useState<string | null>(null);
  const [isBulkBindingConferences, setIsBulkBindingConferences] = useState(false);
  const [bulkBindingSummary, setBulkBindingSummary] = useState<BatchConferenceBindingResult | null>(null);
  const [conferenceResolutionByPaperId, setConferenceResolutionByPaperId] = useState<Record<string, PaperConferenceResolution>>({});
  const [error, setError] = useState<string | null>(null);
  const chatAbortControllerRef = useRef<AbortController | null>(null);
  const isImportLoading = isImportSubmitting || ["pending", "running"].includes(importSummary?.status ?? "");
  const currentViewTitle = getViewTitle(currentView);

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
        const response = await fetch(buildApiUrl(`/papers/import-jobs/${importSummary.id}`));
        if (!response.ok) {
          throw new Error("無法取得匯入工作狀態。");
        }
        const payload: ImportSummary = await response.json();
        setImportSummary(payload);
        void loadPapers(paperPage);
        if (payload.status === "failed" && payload.error_message) {
          setError(payload.error_message);
        }
        if (payload.status === "completed" || payload.status === "cancelled") {
          setPaperPage(1);
          void loadPapers(1);
        }
      } catch (caughtError) {
        setError(caughtError instanceof Error ? caughtError.message : "發生未知錯誤。");
      }
    }, 1500);

    return () => window.clearInterval(interval);
  }, [importSummary, paperPage]);

  async function loadPapers(targetPage = paperPage) {
    try {
      const params = new URLSearchParams({
        page: String(targetPage),
        page_size: String(defaultPaperPageSize),
      });
      if (paperSearchQuery.trim()) params.set("q", paperSearchQuery.trim());
      if (paperConferenceFilter) params.set("conference_id", paperConferenceFilter);
      if (paperYearFromFilter.trim()) params.set("year_from", paperYearFromFilter.trim());
      if (paperYearToFilter.trim()) params.set("year_to", paperYearToFilter.trim());

      const response = await fetch(buildApiUrl("/papers", params));
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
      setError(caughtError instanceof Error ? caughtError.message : "發生未知錯誤。");
    }
  }

  async function loadConferences() {
    try {
      const response = await fetch(buildApiUrl("/conferences"));
      if (!response.ok) {
        throw new Error("無法取得 conference 清單。");
      }
      const payload: ConferenceListResponse = await response.json();
      setConferences(payload.items);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "發生未知錯誤。");
    }
  }

  async function handleChatSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = prompt.trim();
    if (!message) return;

    setMessages((current) => [...current, { role: "user", content: message }]);
    setPrompt("");
    setError(null);
    setIsChatLoading(true);
    const abortController = new AbortController();
    chatAbortControllerRef.current = abortController;

    try {
      const response = await fetch(buildApiUrl("/chat"), {
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
      setError(caughtError instanceof Error ? caughtError.message : "發生未知錯誤。");
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
      const response = await fetch(buildApiUrl("/papers/import-markdown"), {
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
      setError(caughtError instanceof Error ? caughtError.message : "發生未知錯誤。");
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
      const response = await fetch(buildApiUrl("/papers/fetch-markdown", params));
      if (!response.ok) {
        throw new Error("無法從 Jina 取得 Markdown。");
      }
      const payload: FetchMarkdownResponse = await response.json();
      setMarkdown(payload.markdown);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "發生未知錯誤。");
    } finally {
      setIsFetchingMarkdown(false);
    }
  }

  async function handleCancelImport() {
    if (!importSummary) return;

    setError(null);
    setIsCancellingImport(true);
    try {
      const response = await fetch(buildApiUrl(`/papers/import-jobs/${importSummary.id}/cancel`), {
        method: "POST",
      });
      if (!response.ok) {
        throw new Error("無法中斷這個匯入工作。");
      }
      const payload: ImportSummary = await response.json();
      setImportSummary(payload);
      if (payload.status === "cancelled") {
        await loadPapers(1);
        setPaperPage(1);
      }
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "發生未知錯誤。");
    } finally {
      setIsCancellingImport(false);
    }
  }

  async function handlePaperSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingPaper) return;

    setError(null);
    setIsPaperSaving(true);
    try {
      const response = await fetch(buildApiUrl(`/papers/${editingPaper.id}`), {
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
      setError(caughtError instanceof Error ? caughtError.message : "發生未知錯誤。");
    } finally {
      setIsPaperSaving(false);
    }
  }

  async function handlePaperDelete(paperId: string) {
    setError(null);
    setDeletingPaperId(paperId);
    try {
      const response = await fetch(buildApiUrl(`/papers/${paperId}`), { method: "DELETE" });
      if (!response.ok) {
        throw new Error("刪除 paper 失敗。");
      }
      if (editingPaper?.id === paperId) {
        setEditingPaper(null);
      }
      const nextTotalItems = Math.max(0, paperTotalItems - 1);
      const nextTotalPages = Math.max(1, Math.ceil(nextTotalItems / defaultPaperPageSize));
      await loadPapers(Math.min(paperPage, nextTotalPages));
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "發生未知錯誤。");
    } finally {
      setDeletingPaperId(null);
    }
  }

  async function handleResolveConference(paperId: string) {
    setError(null);
    setResolvingConferencePaperId(paperId);
    try {
      const response = await fetch(buildApiUrl(`/papers/${paperId}/resolve-conference`), { method: "POST" });
      if (!response.ok) {
        throw new Error("無法建立或綁定 conference 實體。");
      }
      const payload: PaperConferenceResolution = await response.json();
      setConferenceResolutionByPaperId((current) => ({ ...current, [paperId]: payload }));
      setPapers((current) => current.map((paper) => (paper.id === payload.paper.id ? payload.paper : paper)));
      if (editingPaper?.id === payload.paper.id) {
        setEditingPaper(payload.paper);
      }
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "發生未知錯誤。");
    } finally {
      setResolvingConferencePaperId(null);
    }
  }

  async function handleBulkBindConferences() {
    setError(null);
    setBulkBindingSummary(null);
    setIsBulkBindingConferences(true);
    try {
      const response = await fetch(buildApiUrl("/conferences/bind-unlinked-papers"), { method: "POST" });
      if (!response.ok) {
        throw new Error("無法批次綁定未綁定的 papers。");
      }
      const payload: BatchConferenceBindingResult = await response.json();
      setBulkBindingSummary(payload);
      await Promise.all([loadConferences(), loadPapers(1)]);
      setPaperPage(1);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "發生未知錯誤。");
    } finally {
      setIsBulkBindingConferences(false);
    }
  }

  return (
    <SidebarProvider defaultOpen>
      <div className="min-h-screen w-full bg-[var(--background)]">
        <div className="flex min-h-screen w-full">
          <AppSidebar currentView={currentView} onViewChange={setCurrentView} />

          <SidebarInset className="min-w-0 bg-transparent">
            <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-[var(--border)] bg-[color:rgba(255,255,255,0.9)] px-4 backdrop-blur md:px-8">
              <SidebarTrigger className="md:hidden" />
              <div className="min-w-0">
                <div className="text-xs font-medium uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
                  Paper Agent
                </div>
                <div className="truncate text-lg font-semibold tracking-tight text-[var(--foreground)]">
                  {currentViewTitle}
                </div>
              </div>
            </header>

            <div className="flex min-h-[calc(100vh-4rem)] min-w-0 flex-col px-4 py-4 md:px-8 md:py-8">
              {error ? (
                <div className="mb-4 rounded-xl border border-[var(--border)] bg-[var(--muted)] px-4 py-3 text-sm text-[var(--foreground)]">
                  {error}
                </div>
              ) : null}

              {currentView === "chat" ? (
                <div className="flex min-h-0 flex-1 w-full">
                  <div className="mx-auto flex w-full max-w-6xl">
                    <ChatPanel
                      messages={messages}
                      prompt={prompt}
                      isChatLoading={isChatLoading}
                      error={null}
                      onPromptChange={setPrompt}
                      onSubmit={handleChatSubmit}
                      onAbort={handleChatAbort}
                    />
                  </div>
                </div>
              ) : null}

              {currentView === "ingestion" ? (
                <div className="flex min-h-0 flex-1 w-full">
                  <div className="mx-auto flex w-full max-w-6xl">
                    <IngestionPanel
                      markdown={markdown}
                      sourceUrlInput={sourceUrlInput}
                      importSummary={importSummary}
                      isFetchingMarkdown={isFetchingMarkdown}
                      isImportLoading={isImportLoading}
                      isCancellingImport={isCancellingImport}
                      onSourceUrlChange={setSourceUrlInput}
                      onMarkdownChange={setMarkdown}
                      onFetchMarkdown={() => void handleFetchMarkdownFromUrl()}
                      onImportSubmit={handleImportSubmit}
                      onCancelImport={() => void handleCancelImport()}
                    />
                  </div>
                </div>
              ) : null}

              {currentView === "papers" ? (
                <div className="min-w-0 flex-1">
                  <PaperRecordsSection
                    papers={papers}
                    conferences={conferences}
                    editingPaper={editingPaper}
                    paperSearchQuery={paperSearchQuery}
                    paperConferenceFilter={paperConferenceFilter}
                    paperYearFromFilter={paperYearFromFilter}
                    paperYearToFilter={paperYearToFilter}
                    paperPage={paperPage}
                    paperPageInput={paperPageInput}
                    paperTotalItems={paperTotalItems}
                    paperTotalPages={paperTotalPages}
                    isPaperSaving={isPaperSaving}
                    deletingPaperId={deletingPaperId}
                    resolvingConferencePaperId={resolvingConferencePaperId}
                    isBulkBindingConferences={isBulkBindingConferences}
                    bulkBindingSummary={bulkBindingSummary}
                    conferenceResolutionByPaperId={conferenceResolutionByPaperId}
                    onEditPaperChange={setEditingPaper}
                    onPaperSearchQueryChange={setPaperSearchQuery}
                    onPaperConferenceFilterChange={(value) => {
                      setPaperConferenceFilter(value);
                      setPaperPage(1);
                    }}
                    onPaperYearFromFilterChange={(value) => {
                      setPaperYearFromFilter(value);
                      setPaperPage(1);
                    }}
                    onPaperYearToFilterChange={(value) => {
                      setPaperYearToFilter(value);
                      setPaperPage(1);
                    }}
                    onPaperPageChange={setPaperPage}
                    onPaperPageInputChange={setPaperPageInput}
                    onPaperSave={handlePaperSave}
                    onPaperDelete={(paperId) => void handlePaperDelete(paperId)}
                    onResolveConference={(paperId) => void handleResolveConference(paperId)}
                    onBulkBindConferences={() => void handleBulkBindConferences()}
                    onSearchSubmit={(event) => {
                      event.preventDefault();
                      setPaperPage(1);
                      void loadPapers(1);
                    }}
                    onClearFilters={() => {
                      setPaperSearchQuery("");
                      setPaperConferenceFilter("");
                      setPaperYearFromFilter("");
                      setPaperYearToFilter("");
                      setPaperPage(1);
                    }}
                  />
                </div>
              ) : null}
            </div>
          </SidebarInset>
        </div>
      </div>
    </SidebarProvider>
  );
}
