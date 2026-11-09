/*
 * Lecteur TeX pour NumWorks (firmware officiel, API EADK).
 * Le texte vient de doc.h, genere par tex2h.py.
 *
 * Touches :
 *   Haut / Bas      : defiler d'une ligne (maintenir = repetition)
 *   Gauche / Droite : page precedente / suivante
 *   OK              : sommaire (titres du document)
 *   + / -           : grande / petite police
 *   0 / EXE         : debut / fin du document
 *   Retour          : quitter
 */
#include "eadk.h"
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include "doc.h"

const char eadk_app_name[] __attribute__((section(".rodata.eadk_app_name"))) = "Lecteur TeX";
const uint32_t eadk_api_level __attribute__((section(".rodata.eadk_api_level"))) = 0;

#define RGB(r, g, b) ((eadk_color_t)((((r) & 0xF8) << 8) | (((g) & 0xFC) << 3) | ((b) >> 3)))
#define C_BG    RGB(255, 255, 255)
#define C_TEXT  RGB(0, 0, 0)
#define C_H1    RGB(0, 0, 150)
#define C_H2    RGB(0, 80, 190)
#define C_H3    RGB(70, 70, 70)
#define C_MATH  RGB(0, 110, 0)
#define C_BAR   RGB(225, 225, 225)
#define C_SEL   RGB(200, 220, 255)
#define C_PROG  RGB(0, 120, 215)

#define SCREEN_W 320
#define SCREEN_H 240
#define TOP 18
#define MAX_LINES 8000
#define MAX_TOC 200

/* lines[i] = offset (24 bits) | style (bits 24-30) | 0x80000000 si 1ere ligne du paragraphe */
static uint32_t lines[MAX_LINES];
static int nlines;
static int toc[MAX_TOC];
static int ntoc;
static bool large;
static int cols, rows, ch;
static int top;
static bool truncated;

static void fill(int x, int y, int w, int h, eadk_color_t c) {
  eadk_rect_t r = {(uint16_t)x, (uint16_t)y, (uint16_t)w, (uint16_t)h};
  eadk_display_push_rect_uniform(r, c);
}

static void text(const char *s, int x, int y, bool big, eadk_color_t fg, eadk_color_t bg) {
  eadk_point_t p = {(uint16_t)x, (uint16_t)y};
  eadk_display_draw_string(s, p, big, fg, bg);
}

static int put_uint(char *p, unsigned v) {
  char t[12];
  int n = 0, i;
  do { t[n++] = (char)('0' + v % 10); v /= 10; } while (v);
  for (i = 0; i < n; i++) p[i] = t[n - 1 - i];
  return n;
}

static void set_font(bool l) {
  large = l;
  cols = l ? 32 : 45;
  ch = l ? 18 : 14;
  rows = (SCREEN_H - TOP - 2) / ch;
}

/* ---- decoupage en lignes ---- */
static void build_lines(void) {
  uint32_t i = 0;
  nlines = 0; ntoc = 0; truncated = false;
  while (i < DOC_LEN) {
    if (nlines >= MAX_LINES - 1) { truncated = true; break; }
    int style = 0;
    if (doc_text[i] >= 1 && doc_text[i] <= 4) { style = doc_text[i]; i++; }
    uint32_t pend = i;
    while (pend < DOC_LEN && doc_text[pend] != '\n') pend++;
    uint32_t first = 0x80;
    if (pend == i) {
      lines[nlines++] = i | ((uint32_t)(style | first) << 24);
    } else {
      int width = cols - (style == 4 ? 2 : 0);
      uint32_t s = i;
      bool is_first = true;
      while (s < pend && nlines < MAX_LINES - 1) {
        if (!is_first) while (s < pend && doc_text[s] == ' ') s++;
        if (s >= pend) break;
        uint32_t k = s, lastsp = 0, e;
        int col = 0;
        while (k < pend) {
          unsigned char b = doc_text[k];
          if ((b & 0xC0) != 0x80) { if (col == width) break; col++; }
          if (b == ' ' && k > s) lastsp = k;
          k++;
        }
        if (k >= pend) e = pend;
        else if (doc_text[k] == ' ') e = k;
        else if (lastsp > s) e = lastsp;
        else e = k;
        lines[nlines++] = s | ((uint32_t)(style | (is_first ? first : 0)) << 24);
        is_first = false;
        s = e;
      }
    }
    i = pend + 1;
  }
  for (int n = 0; n < nlines && ntoc < MAX_TOC; n++) {
    uint32_t st = lines[n] >> 24;
    if ((st & 0x80) && (st & 0x7F) >= 1 && (st & 0x7F) <= 3) toc[ntoc++] = n;
  }
}

static int line_len(int idx) {
  uint32_t s = lines[idx] & 0xFFFFFF;
  uint32_t nx = (idx + 1 < nlines) ? (lines[idx + 1] & 0xFFFFFF) : DOC_LEN;
  uint32_t l = nx - s;
  while (l > 0) {
    unsigned char c = doc_text[s + l - 1];
    if (c == ' ' || c == '\n' || (c >= 1 && c <= 4)) l--; else break;
  }
  return (int)l;
}

static int find_line(uint32_t off) {
  int r = 0;
  for (int i = 0; i < nlines; i++) { if ((lines[i] & 0xFFFFFF) <= off) r = i; else break; }
  return r;
}

static int max_top(void) { return nlines > rows ? nlines - rows : 0; }
static void clamp_top(void) { if (top > max_top()) top = max_top(); if (top < 0) top = 0; }

/* ---- affichage ---- */
static void draw_line(int idx, int y, bool big, int maxcols) {
  uint32_t v = lines[idx];
  int style = (v >> 24) & 0x7F;
  uint32_t s = v & 0xFFFFFF;
  int len = line_len(idx);
  char buf[210];
  int n = 0;
  if (style == 4) { buf[n++] = ' '; buf[n++] = ' '; }
  if (len > 200 - n) len = 200 - n;
  memcpy(buf + n, doc_text + s, (size_t)len);
  n += len;
  buf[n] = 0;
  (void)maxcols;
  eadk_color_t fg = style == 1 ? C_H1 : style == 2 ? C_H2 : style == 3 ? C_H3 : style == 4 ? C_MATH : C_TEXT;
  text(buf, 0, y, big, fg, C_BG);
}

static void draw_header(void) {
  char buf[40];
  int n = 0;
  fill(0, 0, SCREEN_W, TOP - 2, C_BAR);
  int l = (int)strlen(doc_title);
  if (l > 24) l = 24;
  memcpy(buf, doc_title, (size_t)l); buf[l] = 0;
  text(buf, 2, 1, false, C_TEXT, C_BAR);
  int pages = (nlines + rows - 1) / rows; if (pages < 1) pages = 1;
  int page = top / rows + 1; if (top >= max_top()) page = pages;
  n += put_uint(buf + n, (unsigned)page);
  buf[n++] = '/';
  n += put_uint(buf + n, (unsigned)pages);
  buf[n++] = ' ';
  int pct = max_top() == 0 ? 100 : (int)((long)top * 100 / max_top());
  n += put_uint(buf + n, (unsigned)pct);
  buf[n++] = '%'; buf[n] = 0;
  text(buf, SCREEN_W - 7 * n - 2, 1, false, C_TEXT, C_BAR);
}

static void draw_screen(void) {
  fill(0, TOP - 2, SCREEN_W, SCREEN_H - TOP + 2, C_BG);
  for (int r = 0; r < rows && top + r < nlines; r++)
    draw_line(top + r, TOP + r * ch, large, cols);
  draw_header();
  int pct = max_top() == 0 ? SCREEN_W : (int)((long)SCREEN_W * top / max_top());
  fill(0, SCREEN_H - 2, SCREEN_W, 2, C_BAR);
  fill(0, SCREEN_H - 2, pct < 2 ? 2 : pct, 2, C_PROG);
  if (truncated) text("(tronque)", 120, 1, false, RGB(200, 0, 0), C_BAR);
}

/* ---- clavier ---- */
static int hold[12];
static bool trig(eadk_keyboard_state_t st, eadk_key_t k, int slot, bool repeat) {
  if (!eadk_keyboard_key_down(st, k)) { hold[slot] = 0; return false; }
  hold[slot]++;
  if (hold[slot] == 1) return true;
  return repeat && hold[slot] > 15 && (hold[slot] % 3) == 0;
}

/* ---- sommaire ---- */
static void draw_toc(int sel, int scroll) {
  const int trows = (SCREEN_H - TOP - 2) / 14;
  fill(0, TOP - 2, SCREEN_W, SCREEN_H - TOP + 2, C_BG);
  fill(0, 0, SCREEN_W, TOP - 2, C_BAR);
  text("Sommaire", 2, 1, false, C_TEXT, C_BAR);
  if (ntoc == 0) { text("(aucun titre)", 4, TOP + 4, false, C_TEXT, C_BG); return; }
  for (int r = 0; r < trows && scroll + r < ntoc; r++) {
    int idx = toc[scroll + r];
    uint32_t v = lines[idx];
    int style = (v >> 24) & 0x7F;
    int y = TOP + r * 14;
    if (scroll + r == sel) fill(0, y, SCREEN_W, 14, C_SEL);
    char buf[210]; int n = 0;
    for (int k = 0; k < (style - 1) * 2; k++) buf[n++] = ' ';
    int len = line_len(idx);
    if (len > 60) len = 60;
    memcpy(buf + n, doc_text + (v & 0xFFFFFF), (size_t)len);
    n += len; buf[n] = 0;
    text(buf, 2, y, false, C_TEXT, scroll + r == sel ? C_SEL : C_BG);
  }
}

static void toc_screen(void) {
  const int trows = (SCREEN_H - TOP - 2) / 14;
  int sel = 0, scroll = 0;
  for (int i = 0; i < ntoc; i++) if (toc[i] <= top) sel = i;
  scroll = sel - trows / 2; if (scroll < 0) scroll = 0;
  bool dirty = true;
  for (;;) {
    eadk_keyboard_state_t st = eadk_keyboard_scan();
    if (trig(st, eadk_key_back, 6, false)) return;
    if (trig(st, eadk_key_up, 0, true) && sel > 0) { sel--; dirty = true; }
    if (trig(st, eadk_key_down, 1, true) && sel < ntoc - 1) { sel++; dirty = true; }
    if (trig(st, eadk_key_left, 2, true)) { sel -= trows; if (sel < 0) sel = 0; dirty = true; }
    if (trig(st, eadk_key_right, 3, true)) { sel += trows; if (sel > ntoc - 1) sel = ntoc - 1; dirty = true; }
    if (trig(st, eadk_key_ok, 4, false) && ntoc > 0) { top = toc[sel]; clamp_top(); return; }
    if (sel < scroll) scroll = sel;
    if (sel >= scroll + trows) scroll = sel - trows + 1;
    if (dirty) { draw_toc(sel, scroll); dirty = false; }
    eadk_timing_msleep(20);
  }
}

static void change_font(bool l) {
  if (l == large) return;
  uint32_t off = nlines ? (lines[top] & 0xFFFFFF) : 0;
  set_font(l);
  build_lines();
  top = find_line(off);
  clamp_top();
}

int main(int argc, char *argv[]) {
  (void)argc; (void)argv;
  set_font(true);
  build_lines();
  top = 0;
  bool dirty = true;
  for (;;) {
    eadk_keyboard_state_t st = eadk_keyboard_scan();
    if (trig(st, eadk_key_back, 6, false)) break;
    int old = top;
    if (trig(st, eadk_key_down, 1, true)) top++;
    if (trig(st, eadk_key_up, 0, true)) top--;
    if (trig(st, eadk_key_right, 3, true)) top += rows - 1;
    if (trig(st, eadk_key_left, 2, true)) top -= rows - 1;
    if (trig(st, eadk_key_zero, 7, false)) top = 0;
    if (trig(st, eadk_key_exe, 8, false)) top = max_top();
    clamp_top();
    if (top != old) dirty = true;
    if (trig(st, eadk_key_plus, 9, false)) { change_font(true); dirty = true; }
    if (trig(st, eadk_key_minus, 10, false)) { change_font(false); dirty = true; }
    if (trig(st, eadk_key_ok, 4, false)) { toc_screen(); dirty = true; }
    if (dirty) { draw_screen(); dirty = false; }
    eadk_timing_msleep(20);
  }
  return 0;
}
