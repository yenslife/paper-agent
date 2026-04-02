export type ChatMessage = {
  role: "user" | "assistant" | "tool";
  content: string;
  citations?: Citation[];
  sources?: SourceSummary[];
  tool_traces?: ToolTrace[];
  tool_name?: string;
  tool_status?: "running" | "ok" | "not_found" | "error" | "unavailable";
  tool_phase?: "started" | "finished" | "failed";
};

export type Citation = {
  title: string;
  url?: string | null;
  source_page_url?: string | null;
  venue?: string | null;
  year?: number | null;
  source_type: "local_paper_db" | "web_search";
};

export type SourceSummary = {
  source_type: "local_paper_db" | "web_search";
  description: string;
};

export type ToolTrace = {
  tool_name: string;
  status: "ok" | "not_found" | "error" | "unavailable";
  summary: string;
};

export type ChatResponse = {
  session_id: string;
  answer: string;
  citations: Citation[];
  sources: SourceSummary[];
  tool_traces: ToolTrace[];
};

export type ChatStreamEvent =
  | { type: "session_started"; session_id: string }
  | { type: "tool_started"; tool_name: string; summary: string }
  | { type: "tool_finished"; tool_name: string; status: "ok" | "not_found" | "error" | "unavailable"; summary: string }
  | { type: "tool_failed"; tool_name: string; status: "ok" | "not_found" | "error" | "unavailable"; summary: string }
  | { type: "final_answer"; session_id: string; answer: string; citations: Citation[]; sources: SourceSummary[]; tool_traces: ToolTrace[] }
  | { type: "error"; message: string }
  | { type: "completed" };

export type ImportSummary = {
  id: string;
  source_name?: string | null;
  status: "pending" | "running" | "cancelled" | "completed" | "failed";
  cancel_requested: boolean;
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

export type FetchMarkdownResponse = {
  source_url: string;
  fetched_url: string;
  markdown: string;
};

export type PaperRecord = {
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

export type ConferenceRecord = {
  id: string;
  name: string;
  normalized_name: string;
  source_page_url?: string | null;
  year?: number | null;
  paper_count: number;
};

export type PaperConferenceResolution = {
  paper: PaperRecord;
  conference?: ConferenceRecord | null;
  status: "already_attached" | "reused_existing" | "created_new" | "unresolved";
  duplicate_detected: boolean;
  message: string;
};

export type PaperListResponse = {
  items: PaperRecord[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
};

export type ConferenceListResponse = {
  items: ConferenceRecord[];
};

export type BatchConferenceBindingResult = {
  total_candidates: number;
  bound_count: number;
  reused_existing_count: number;
  created_new_count: number;
  unresolved_count: number;
  message: string;
};
