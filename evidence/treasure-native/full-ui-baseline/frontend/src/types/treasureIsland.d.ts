// Browser adapter contract; kept compatible with the child repository display contract.
/** Non-sensitive view data only. Authentication, networking and state belong to Vue. */
export interface TreasureIslandProps {
  context: { projectId: string | null; projectName: string; locale: 'zh' | 'en'; theme: 'light' | 'dark' };
  messages: readonly { id: string; role: 'user' | 'assistant'; content: string }[];
  mode?: 'welcome' | 'composer' | 'pet';
  modelOptions: readonly string[];
  selectedModel: string;
  draft: string;
  streaming: boolean;
  disabled: boolean;
  onDraftChange: (draft: string) => void;
  onSubmit: (text: string) => void;
  onPickExample: (text: string) => void;
  onCancel: () => void;
  onSelectModel: (model: string) => void;
  onOpenDataset: (accession: string) => void;
}
export interface TreasureIslandHandle {
  update: (props: TreasureIslandProps) => void;
  unmount: () => void;
}
