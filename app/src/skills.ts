// Display data for skill ids (model/skill-graph.md): the keys drilled and a
// few plain words. The model's graph (model/skill-graph.json) is the source of truth
// for tiers and prereqs; this table is only used for labels, and as a fallback graph
// when model/skill-graph.json is not served (see graph.ts).

export interface SkillInfo {
  id: string;
  tier: number;
  keys: string; // short key form for the header / footer, e.g. ci"
  name: string; // plain words
  prereqs: string[];
}

// prettier-ignore
const ROWS: [string, number, string, string, string][] = [
  // id, tier, keys, name, prereqs (space separated)
  ["f.modes", 0, "i a o", "insert modes", ""],
  ["f.hjkl", 0, "hjkl", "basic movement", ""],
  ["f.undo", 0, "u", "undo / redo", ""],
  ["f.xdd", 0, "x dd p", "delete / paste", ""],
  ["f.save", 0, ":w", "write / quit", ""],
  ["m.word", 1, "w b e", "word motions", "f.hjkl"],
  ["m.WORD", 1, "W B E", "WORD motions", "m.word"],
  ["m.line", 1, "0 ^ $", "line start / end", "f.hjkl"],
  ["m.find", 1, "f t", "find on line", "m.line"],
  ["m.repeatfind", 1, "; ,", "repeat find", "m.find"],
  ["m.count", 1, "3w", "counts", "m.word"],
  ["m.file", 2, "gg G", "file motions", "f.hjkl"],
  ["m.para", 2, "{ }", "paragraphs", "f.hjkl"],
  ["m.rel", 2, "5j", "relative jumps", "m.count"],
  ["m.screen", 2, "<C-d>", "scrolling", "f.hjkl"],
  ["m.screenpos", 2, "H M L", "screen position", "m.screen"],
  ["m.match", 2, "%", "matching bracket", "f.hjkl"],
  ["m.search", 2, "/ n", "search", "f.hjkl"],
  ["m.star", 2, "*", "word search", "m.search"],
  ["m.sentence", 2, "( )", "sentences", "m.para"],
  ["o.delete", 3, "d", "delete", "m.word m.line"],
  ["o.change", 3, "c", "change", "o.delete"],
  ["o.yank", 3, "y", "yank", "o.delete"],
  ["o.put", 3, "p P", "put", "o.yank"],
  ["o.dot", 3, ".", "repeat change", "o.change"],
  ["o.indent", 3, ">>", "indent", "o.delete"],
  ["o.case", 3, "gU", "case", "o.delete"],
  ["o.join", 3, "J", "join lines", "o.delete"],
  ["o.replace", 3, "r R", "replace", "f.modes"],
  ["o.number", 3, "<C-a>", "increment", "m.count"],
  ["o.filter", 3, "!", "filter", "o.delete"],
  ["t.word", 4, "ciw", "words", "o.change"],
  ["t.quote", 4, "ci\"", "strings", "o.change"],
  ["t.paren", 4, "ci(", "parentheses", "m.match"],
  ["t.bracket", 4, "ci[", "brackets", "t.paren"],
  ["t.brace", 4, "ci{", "braces", "t.paren"],
  ["t.angle", 4, "ci<", "angle brackets", "t.paren"],
  ["t.tag", 4, "cit", "tags", "t.brace"],
  ["t.para", 4, "dap", "paragraph objects", "m.para"],
  ["t.sentence", 4, "das", "sentence objects", "m.sentence"],
  ["t.compose", 4, "da(", "text objects", "t.word t.quote t.paren t.bracket t.brace t.angle t.tag t.para t.sentence"],
  ["v.char", 5, "v", "visual", "o.delete"],
  ["v.line", 5, "V", "visual line", "v.char"],
  ["v.block", 5, "<C-v>", "visual block", "v.line"],
  ["v.blockedit", 5, "<C-v>I", "block insert", "v.block"],
  ["v.objects", 5, "vi(", "select object", "t.compose"],
  ["v.reselect", 5, "gv", "reselect", "v.char"],
  ["v.ops", 5, "v>", "visual operators", "v.char"],
  ["r.named", 6, "\"a", "named registers", "o.yank"],
  ["r.yank0", 6, "\"0p", "yank register", "r.named"],
  ["r.numbered", 6, "\"1p", "numbered registers", "r.named"],
  ["r.blackhole", 6, "\"_d", "black hole", "r.named"],
  ["r.system", 6, "\"+y", "clipboard", "r.named"],
  ["r.insert", 6, "<C-r>a", "insert register", "r.named"],
  ["r.view", 6, ":reg", "view registers", "r.named"],
  ["x.subst", 7, ":s", "substitute", "m.search"],
  ["x.substrange", 7, ":5,9s", "ranges", "x.subst"],
  ["x.regex", 7, "\\<\\>", "regex", "x.subst"],
  ["x.lastsearch", 7, "cgn", "reuse search", "x.subst o.dot"],
  ["x.global", 7, ":g", "global", "x.subst"],
  ["x.normal", 7, ":norm", "normal over range", "x.global"],
  ["x.copymove", 7, ":m :t", "copy / move lines", "x.substrange"],
  ["x.cmdline", 7, "<C-r><C-w>", "command line", "x.subst"],
  ["a.dot", 8, "n.", "dot patterns", "o.dot"],
  ["a.macro", 8, "qa @a", "macros", "r.named"],
  ["a.macrorange", 8, ":norm @a", "macro over range", "a.macro x.normal"],
  ["a.macroedit", 8, "\"ap", "edit a macro", "a.macro"],
  ["a.recursive", 8, "@a in qa", "recursive macro", "a.macro"],
  ["n.marks", 9, "ma 'a", "marks", "m.file"],
  ["n.autmarks", 9, "''", "automatic marks", "n.marks"],
  ["n.jumplist", 9, "<C-o>", "jump list", "m.search"],
  ["n.changelist", 9, "g;", "change list", "n.jumplist"],
  ["n.lastinsert", 9, "gi", "last insert", "n.autmarks"],
  ["n.unmatched", 9, "]}", "enclosing bracket", "m.match"],
  ["n.section", 9, "]]", "sections", "m.para"],
  ["n.folds", 9, "za", "folds", "m.file"],
  ["i.delete", 10, "<C-w>", "insert delete", "f.modes"],
  ["i.oneshot", 10, "<C-o>", "one normal command", "f.modes"],
  ["i.register", 10, "<C-r>\"", "insert register", "r.named"],
  ["i.indent", 10, "<C-t>", "insert indent", "f.modes"],
  ["i.complete", 10, "<C-n>", "completion", "f.modes"],
  ["i.escape", 10, "<C-[>", "escape", "f.modes"],
  ["i.last", 10, "<C-a>", "last insert text", "f.modes"],
  ["w.split", 11, ":sp", "splits", "f.save"],
  ["w.move", 11, "<C-w>w", "windows", "w.split"],
  ["w.buffers", 11, ":b", "buffers", "f.save"],
  ["w.tabs", 11, "gt", "tabs", "w.split"],
  ["w.args", 11, ":argdo", "arg list", "x.global"],
  ["w.quickfix", 11, ":cdo", "quickfix", "x.global"],
  ["nv.lsp", 12, "grn", "LSP maps", "w.quickfix"],
  ["nv.diag", 12, "]d", "diagnostics", "nv.lsp"],
  ["nv.comment", 12, "gcc", "commenting", "o.delete"],
  ["nv.treesitter", 12, "af", "syntax objects", "t.compose"],
];

export const SKILLS: SkillInfo[] = ROWS.map(([id, tier, keys, name, pre]) => ({
  id,
  tier,
  keys,
  name,
  prereqs: pre ? pre.split(" ") : [],
}));

const BY_ID = new Map(SKILLS.map((s) => [s.id, s]));

export function skillInfo(id: string): SkillInfo {
  return BY_ID.get(id) ?? { id, tier: 99, keys: id, name: id, prereqs: [] };
}

/** One-line "try in your editor today" tips, used when the model gives none. */
export const EDITOR_TIPS: Record<string, string> = {
  "t.quote": 'ci" changes a string from anywhere on its line, even before the quotes.',
  "t.paren": "ci( rewrites a call's arguments from anywhere inside the parentheses.",
  "m.rel": "with relative numbers on, {n}j reaches any visible line in two or three keys.",
  "m.find": "f, and ; walk through a call's arguments without touching l.",
  "x.global": ":g/print/d removes every debug print in one command.",
  "r.blackhole": '"_d deletes without clobbering your yank.',
  "o.dot": "make the first edit with c, then repeat it with . instead of retyping.",
};
