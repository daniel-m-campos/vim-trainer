// App-side types: exercises and the content index,
// settings and persisted app state. Model types live in ./model (via modelApi.ts).

/** [line 1-based, column 0-based], the nvim_win_get_cursor convention used by the oracle. */
export type Pos = [number, number];

export interface ExerciseHint {
  /** Regex matched against the user's normalised key string, e.g. ^f" */
  trigger?: string | null;
  text: string;
}

/** Highlight span, both ends inclusive (build/ exercise JSON). */
export interface TargetSpan {
  start: Pos;
  end: Pos;
}

export interface Exercise {
  id: string;
  skill: string;
  lang: string;
  kind: "edit" | "cursor" | "ex";
  task: string;
  start: { lines: string[]; cursor: Pos };
  expect: { lines?: string[]; cursor?: Pos };
  par: { keys: string; count: number; verified?: string };
  alternates?: string[];
  /** Plain strings (no trigger) or {trigger, text}. */
  hints?: (string | ExerciseHint)[];
  tags?: string[];
  source?: { repo: string; path: string; commit: string | null; license: string; lines?: [number, number] };
  emulator?: Record<string, string>;
  params?: Record<string, unknown>;
  /**
   * Ranges to highlight in the start buffer. The content pipeline emits a list of
   * {start, end} with both ends inclusive ([line 1-based, col 0-based]); the older
   * single {from, to} form (end exclusive) is still accepted. When absent the app
   * derives the range (diff of start vs expect, or expect.cursor).
   */
  target?: TargetSpan[] | { from: Pos; to: Pos };
  /** Pipeline extras the app does not use for grading. */
  template?: string;
  naive?: number;
  reviewed?: boolean;
  options?: Record<string, unknown>;
}

export interface IndexSkill {
  ids: string[];
  count: number;
  parMedian: number;
  thin?: boolean;
}

export interface ContentIndex {
  langs: Record<string, { skills: Record<string, IndexSkill> }>;
}

export type EditorProfile = "neovim" | "vscodevim" | "ideavim";
export type EscapePref = "esc" | "ctrl-[" | "jk";

export interface Settings {
  lang: string;
  profile: EditorProfile;
  relativeNumbers: boolean;
  escape: EscapePref;
}

export interface SessionRecord {
  start: number; // epoch ms
  end: number; // epoch ms
  exercises: number;
  improved: string[];
}
