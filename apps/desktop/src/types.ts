export type Domain = "auto" | "renji" | "tianji" | "diji";

export type AssistantStatus = "idle" | "listening" | "transcribing" | "thinking" | "speaking";

export interface Citation {
  source_id?: string;
  chunk_id?: string;
  title: string;
  course?: string;
  chapter?: string;
  timestamp?: string;
  page?: string;
  source_url?: string;
  score?: number;
}

export interface RetrievalHit extends Citation {
  snippet?: string;
  rights_status?: string;
  match_source?: "fts" | "vector" | "hybrid" | string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  time: string;
  status?: "transcribing";
  domain?: Domain | string;
  citations?: Citation[];
  retrievalHits?: RetrievalHit[];
  retrievalInfo?: Record<string, unknown>;
  safetyNotes?: string[];
}
