-- oracle.lua: replay Vim keystrokes on an exercise buffer in headless Neovim.
-- Script:  nvim --headless --clean -u NONE -l oracle.lua JOBS.json   (or ORACLE_JOBS=path)
--   JOBS.json is an exercise object or a list of {"exercise": {...}, "keys": "..."};
--   one "@@ORACLE <json>" line per job is printed to stdout.
-- Module:  Oracle = dofile("oracle.lua"); Oracle.run(exercise, keys) -> result table
-- Cursor is [line 1-based, byte column 0-based] (nvim_win_get_cursor convention).
local M = { MARKER = '@@ORACLE ' }
package.loaded.oracle_self = M
-- Documented par option set, applied after the filetype plugin so every language
-- gets the same tab/indent behaviour. indentexpr from the filetype is kept.
M.OPTIONS = { number = true, relativenumber = true, expandtab = true, shiftwidth = 4,
  tabstop = 4, softtabstop = 0, autoindent = true, wrap = false }
local FILETYPE = { tsx = 'typescriptreact' }
for _, p in ipairs({ 'python3', 'node', 'perl', 'ruby' }) do vim.g['loaded_' .. p .. '_provider'] = 0 end
vim.o.showmode, vim.o.more, vim.o.swapfile = false, false, false
local final_mode, used_ex
vim.keymap.set({ 'n', 'i', 'v', 'x', 's', 'o', 'c', 't' }, '<Plug>(oracle-done)',
  function() final_mode = vim.api.nvim_get_mode().mode end)
vim.api.nvim_create_autocmd('CmdlineEnter', { pattern = ':', callback = function() used_ex = true end })
local function tc(s) return vim.api.nvim_replace_termcodes(s, true, false, true) end

local function reset(ex)
  vim.cmd('enew!')
  vim.bo.bufhidden = 'wipe'
  vim.bo.filetype = FILETYPE[ex.lang] or ex.lang or ''
  for k, v in pairs(vim.tbl_extend('force', M.OPTIONS, ex.options or {})) do vim.opt_local[k] = v end
  for r in ('"abcdefghijklmnopqrstuvwxyz0123456789-/'):gmatch('.') do vim.fn.setreg(r, {}) end
  vim.fn.setcharsearch({ char = '', forward = 1, ['until'] = 0 })
  vim.cmd('silent! delmarks A-Z0-9 | clearjumps | nohlsearch')
  local ul = vim.bo.undolevels
  vim.bo.undolevels = -1
  vim.api.nvim_buf_set_lines(0, 0, -1, false, ex.start.lines)
  vim.bo.undolevels = ul
  vim.api.nvim_win_set_cursor(0, ex.start.cursor)
  final_mode, used_ex, vim.v.errmsg = nil, false, ''
end

function M.run(ex, keys)
  reset(ex)
  keys = keys or ex.par.keys
  local t0 = vim.uv.hrtime()
  -- silent! keeps errors off the (absent) screen: Neovim otherwise sleeps ~1 s before
  -- redrawing over a displayed error. v:errmsg is still set.
  M.pending = tc(keys .. '<Plug>(oracle-done)')
  local ok, err = pcall(vim.cmd, "silent! lua vim.api.nvim_feedkeys(require'oracle_self'.pending, 'mtx', false)")
  local res = { keys = keys, mode = final_mode or vim.api.nvim_get_mode().mode, used_ex = used_ex,
    recording = vim.fn.reg_recording() ~= '', errmsg = ok and vim.v.errmsg or tostring(err),
    ms = (vim.uv.hrtime() - t0) / 1e6 }
  if res.recording then vim.cmd('normal! q') end
  vim.api.nvim_feedkeys(tc('<C-\\><C-n>'), 'nx', false)
  res.lines = vim.api.nvim_buf_get_lines(0, 0, -1, false)
  res.cursor = vim.api.nvim_win_get_cursor(0)
  return res
end

-- Cursor probes: replay many short motions from the start cursor on one buffer and
-- report where each lands. Returns one [line, col] per probe, or vim.NIL when the probe
-- did not end in Normal mode or changed the buffer (the buffer is then reset).
function M.probe(ex, probes)
  reset(ex)
  local tick = vim.b.changedtick
  local out = {}
  for i, keys in ipairs(probes) do
    vim.api.nvim_win_set_cursor(0, ex.start.cursor)
    vim.fn.setcharsearch({ char = '', forward = 1, ['until'] = 0 })
    final_mode = nil
    M.pending = tc(keys .. '<Plug>(oracle-done)')
    pcall(vim.cmd, "silent! lua vim.api.nvim_feedkeys(require'oracle_self'.pending, 'mtx', false)")
    local mode = final_mode or vim.api.nvim_get_mode().mode
    if vim.fn.reg_recording() ~= '' then vim.cmd('normal! q') end
    vim.api.nvim_feedkeys(tc('<C-\\><C-n>'), 'nx', false)
    if vim.b.changedtick ~= tick then
      out[i] = vim.NIL
      reset(ex)
      tick = vim.b.changedtick
    else
      out[i] = mode == 'n' and vim.api.nvim_win_get_cursor(0) or vim.NIL
    end
  end
  return out
end

if _G.arg and _G.arg[0] and _G.arg[0]:match('oracle%.lua$') then
  local path = _G.arg[1] or os.getenv('ORACLE_JOBS')
  local jobs = vim.json.decode(table.concat(vim.fn.readfile(path), '\n'))
  if not vim.islist(jobs) then jobs = { { exercise = jobs, keys = _G.arg[2] } } end
  for _, job in ipairs(jobs) do
    local res = job.probes and { probes = M.probe(job.exercise, job.probes) } or M.run(job.exercise, job.keys)
    io.stdout:write('\n' .. M.MARKER .. vim.json.encode(res) .. '\n')
  end
end
return M
