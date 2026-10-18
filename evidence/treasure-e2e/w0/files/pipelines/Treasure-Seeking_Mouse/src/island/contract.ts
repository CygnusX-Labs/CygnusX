/** Non-sensitive view data only. Authentication, networking and state belong to Vue. */
export interface TreasureCard {
  tool: string; accession: string; title: string; summary: string; meta: Record<string, string>;
}
export interface TreasureMessage {
  id: string; role: 'user' | 'assistant'; content: string;
  cards?: TreasureCard[]; toolLogs?: { name: string; label: string; ok: boolean; ms: number }[];
  liveTools?: { name: string; label: string; status: 'running' | 'done' | 'error'; ms?: number }[];
  grounding?: { unconfirmed: { id: string; status: string }[]; confirmed: string[] } | null;
  boost?: { accession: string | null } | null;
  streaming?: boolean; error?: string | null;
}
export interface TreasureIslandProps {
  context: { projectId: string | null; projectName: string; locale: 'zh' | 'en'; theme: 'light' | 'dark' };
  messages: readonly TreasureMessage[];
  mode?: 'welcome' | 'composer' | 'pet' | 'app';
  modelOptions: readonly string[]; selectedModel: string;
  draft: string; streaming: boolean; disabled: boolean;
  sessions?: { id: string; title: string; updated_at: string }[];
  activeSessionId?: string | null;
  projects?: { id: string; name: string }[];
  loading?: boolean; accessError?: string; historyError?: string; streamError?: string;
  onDraftChange: (draft: string) => void; onSubmit: (text: string) => void;
  onPickExample: (text: string) => void; onCancel: () => void;
  onSelectModel: (model: string) => void; onOpenDataset: (accession: string) => void;
  onSelectSession?: (id: string) => void; onNewSession?: () => void;
  onRenameSession?: (id: string, title: string) => void; onArchiveSession?: (id: string) => void;
  onChangeProject?: (id: string) => void; onRefresh?: () => void;
  onLocaleChange?: (lang: 'zh' | 'en') => void; onThemeChange?: () => void;
  onRegenerate?: (id: string) => void;
  loadLiterature?: (kind: string, id: string) => Promise<{
    status: 'ok' | 'not_found'; pmid?: string; title?: string; journal?: string; year?: string;
    doi?: string; outline?: { section: string; text: string }[];
    urls?: { pubmed?: string; doi?: string; full_text?: string }; suggested_queries?: string[];
  }>;
}
export interface TreasureIslandHandle { update: (props: TreasureIslandProps) => void; unmount: () => void; }
