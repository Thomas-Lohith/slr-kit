import argparse
import curses
import json
import logging
import os
import pathlib
import sys
from typing import cast, Callable, Hashable

from prompt_toolkit.document import Document
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout import Dimension, Float, Window
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.widgets import Frame

from terms import Label, TermList, Term
from utils import setup_logger, substring_index

DEBUG = False


class TermLexer(Lexer):
    def invalidation_hash(self) -> Hashable:
        return self._inv

    def __init__(self):
        self._word = ''
        self._inv = 0

    @property
    def word(self) -> str:
        return self._word

    @word.setter
    def word(self, word: str):
        self._word = word
        self._inv += 1

    def lex_document(self, document):
        lines = []
        for line in document.lines:
            fmt = []
            prev = 0
            for begin, end in substring_index(line, self.word):
                if begin > prev:
                    fmt.append(('', line[prev:begin]))

                fmt.append(('#ff0000 bold', line[begin:end]))
                prev = end

            if prev < len(line) - 1:
                fmt.append(('', line[prev:]))

            lines.append(fmt)

        return lambda lineno: lines[lineno]


class PtWin(Float):
    """
    Window that shows terms

    :type x: int
    :type y: int
    :type label: Label or None
    :type title: str
    :type show_title: bool
    :type lexer: Lexer
    :type height: Dimension
    :type width: Dimension
    :type buffer: Buffer
    :type control: BufferControl
    :type window: Window
    :type terms: list[Term] or None
    """

    def __init__(self, label, title='', rows=3, cols=30, y=0, x=0,
                 show_title=False):
        """
        Creates a window that shows terms

        :param label: label associated to the windows
        :type label: Label or None
        :param title: title of window. Default: empty string
        :type title: str
        :param rows: number of rows
        :type rows: int
        :param cols: number of columns
        :type cols: int
        :param y: y coordinate
        :type y: int
        :param x: x coordinate
        :type x: int
        :param show_title: if True the window shows its title. Default: False
        :type show_title: bool
        """
        self.x = x
        self.y = y
        self.label = label
        self.title = title
        self.show_title = show_title
        self.lexer = TermLexer()
        self.height = Dimension(min=rows, max=rows)
        self.width = Dimension(min=cols, max=cols)
        # we must re-create a text-area using the basic components
        # we must do this to have control on the lexer. Otherwise prompt-toolkit
        # will cache the output of the lexer resulting in wrong highlighting
        self.buffer = Buffer(read_only=True, document=Document('', 0))
        self.control = BufferControl(buffer=self.buffer,
                                     lexer=self.lexer)
        self.window = Window(content=self.control, height=self.height,
                             width=self.width)
        self.terms = None
        frame = Frame(cast('Container', self.window))
        super().__init__(cast('Container', frame), left=self.x, top=self.y)
        if self.show_title:
            frame.title = title

    @property
    def text(self) -> str:
        """
        Text shown in the window

        :return: the text shown in the window
        """
        return self.buffer.text

    @text.setter
    def text(self, value: str):
        """
        Sets the text to be shown

        :param value: the new text to be shown
        :type value: str
        """
        self.buffer.set_document(Document(value, 0), bypass_readonly=True)

    def assign_lines(self, terms):
        """
        Assign the terms in terms with the same label as the window

        :param terms: the terms list
        :type terms: list[Term]
        """
        self.terms = [w for w in terms if w.label == self.label]
        self.terms = sorted(self.terms, key=lambda t: t.order)

    def display_lines(self, rev=True, highlight_word='', only_the_word=False,
                      color_pair=1):
        """
        Display the terms associated to the window

        :param rev: if True, display terms in reversed order. Default: True
        :type rev: bool
        :param highlight_word: the word to highlight. Default: empty string
        :type highlight_word: str
        :param only_the_word: if True only highlight_word is highlighted.
        :type only_the_word: bool
        :param color_pair: the curses color pair to use to hightlight. Default 1
        :type color_pair: int
        """
        terms = iter(self.terms)
        if rev:
            terms = reversed(self.terms)

        self.lexer.word = highlight_word
        # Useless text change to force the lexer
        self.text = ''
        self.text = '\n'.join([w.string for w in terms])


class Win(object):
    """
    Contains the list of lines to display.

    :type label: Label or None
    :type title: str
    :type rows: int
    :type cols: int
    :type y: int
    :type x: int
    :type win_title: _curses.window or None
    :type win_handler: _curses.window
    :type lines: list[str]
    """

    def __init__(self, label, title='', rows=3, cols=30, y=0, x=0,
                 show_title=False):
        """
        Creates a window

        :param label: label associated to the windows
        :type label: Label or None
        :param title: title of window. Default: empty string
        :type title: str
        :param rows: number of rows
        :type rows: int
        :param cols: number of columns
        :type cols: int
        :param y: y coordinate
        :type y: int
        :param x: x coordinate
        :type x: int
        :param show_title: if True the window must show its title. Default: False
        :type show_title: bool
        """
        self.label = label
        self.title = title
        self.rows = rows
        self.cols = cols
        self.x = x
        if show_title:
            self.y = y + 1
            self.win_title = curses.newwin(1, self.cols, y, self.x)
            self.win_title.addstr(' {}'.format(self.title))
        else:
            self.y = y
            self.win_title = None

        self.win_handler = curses.newwin(self.rows, self.cols, self.y, self.x)
        self.win_handler.border()
        self.win_handler.refresh()
        self.lines = []

    def display_lines(self, rev=True, highlight_word='', only_the_word=False,
                      color_pair=1):
        """
        Display the lines associated to the window

        :param rev: if True, display lines in reversed order. Default: True
        :type rev: bool
        :param highlight_word: the word to highlight. Default: empty string
        :type highlight_word: str
        :param only_the_word: if True only highlight_word is highlighted.
        :type only_the_word: bool
        :param color_pair: the curses color pair to use to hightlight. Default 1
        :type color_pair: int
        """
        if rev:
            word_list = reversed(self.lines)
        else:
            word_list = self.lines

        i = 0
        for w in word_list:
            if i >= self.rows - 2:
                break

            self._display_line(w, highlight_word, only_the_word, i, color_pair)
            i += 1

        while i < self.rows - 2:
            self.win_handler.addstr(i + 1, 1, ' ' * (self.cols - 2))
            i += 1

        self.win_handler.border()
        self.win_handler.refresh()
        if self.win_title is not None:
            self.win_title.refresh()

    def _display_line(self, line, highlight_word, only_word, line_index,
                      color_pair):
        """
        Display a single line in a window taking care of the word highlighting

        :param line: the line to display
        :type line: str
        :param highlight_word: the word to highlight
        :type highlight_word: str
        :param only_word: if True, highlight only highlight_word
        :type only_word: bool
        :param line_index: index of the line to display
        :type line_index: int
        :param color_pair: color pair for highlight
        :type color_pair: int
        """
        trunc_w = line[:self.cols - 2]
        l_trunc_w = len(trunc_w)
        pad = ' ' * (self.cols - 2 - l_trunc_w)
        flag = line != highlight_word and only_word
        if highlight_word == '' or flag:
            self.win_handler.addstr(line_index + 1, 1, trunc_w + pad)
        elif line == highlight_word:
            self.win_handler.addstr(line_index + 1, 1, trunc_w + pad,
                                    curses.color_pair(color_pair))
        else:
            tok = line.split(highlight_word)
            tok_len = len(tok)
            if tok_len == 1:
                # no highlight_word found
                self.win_handler.addstr(line_index + 1, 1, trunc_w + pad)
            else:
                self.win_handler.addstr(line_index + 1, 1, '')
                for i, t in enumerate(tok):
                    self.win_handler.addstr(t)
                    if i < tok_len - 1:
                        self.win_handler.addstr(highlight_word,
                                                curses.color_pair(color_pair))

                self.win_handler.addstr(line_index + 1, l_trunc_w + 1, pad)

    def assign_lines(self, terms):
        """
        Assign the terms in terms with the same label as the window
        :param terms: the terms list
        :type terms: list[Term]
        """
        terms = sorted(terms, key=lambda t: t.order)
        self.lines = [w.string for w in terms if w.label == self.label]


def init_argparser():
    """
    Initialize the command line parser.

    :return: the command line parser
    :rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('datafile', action="store", type=str,
                        help="input CSV data file")
    parser.add_argument('--input', '-i', metavar='LABEL',
                        help='input only the terms classified with the specified label')
    parser.add_argument('--dry-run', action='store_true', dest='dry_run',
                        help='do not write the results on exit')
    parser.add_argument('--no-auto-save', action='store_true', dest='no_auto_save',
                        help='disable auto-saving; save changes at the end of the session')
    parser.add_argument('--no-profile', action='store_true', dest='no_profile',
                        help='disable profiling logging')
    return parser


def avg_or_zero(num, den):
    """
    Safely calculates an average, returning 0 if no elements are present.

    :param num: numerator
    :type num: int
    :param den: denominator
    :type den: int
    """
    if den > 0:
        avg = 100 * num / den
    else:
        avg = 0

    return avg


def get_stats_strings(terms, related_items_count=0):
    """
    Calculates the statistics and formats them into strings

    :param terms: the list of terms
    :type terms: TermList
    :param related_items_count: the current number of related term
    :type related_items_count: int
    :return: the statistics about words formatted as strings
    :rtype: list[str]
    """
    stats_strings = []
    n_completed = terms.count_classified()
    n_keywords = terms.count_by_label(Label.KEYWORD)
    n_noise = terms.count_by_label(Label.NOISE)
    n_not_relevant = terms.count_by_label(Label.NOT_RELEVANT)
    n_later = terms.count_by_label(Label.POSTPONED)
    stats_strings.append('Total words:  {:7}'.format(len(terms.items)))
    avg = avg_or_zero(n_completed, len(terms.items))
    stats_strings.append('Completed:    {:7} ({:6.2f}%)'.format(n_completed,
                                                                avg))
    avg = avg_or_zero(n_keywords, n_completed)
    stats_strings.append('Keywords:     {:7} ({:6.2f}%)'.format(n_keywords,
                                                                avg))
    avg = avg_or_zero(n_noise, n_completed)
    stats_strings.append('Noise:        {:7} ({:6.2f}%)'.format(n_noise, avg))
    avg = avg_or_zero(n_not_relevant, n_completed)
    stats_strings.append('Not relevant: {:7} ({:6.2f}%)'.format(n_not_relevant,
                                                                avg))
    avg = avg_or_zero(n_later, n_completed)
    stats_strings.append('Postponed:    {:7} ({:6.2f}%)'.format(n_later,
                                                                avg))
    s = 'Related:      {:7}'
    if related_items_count >= 0:
        s = s.format(related_items_count)
    else:
        s = s.format(0)

    stats_strings.append(s)
    return stats_strings


def init_curses():
    """
    Initialize curses

    :return: the screen object
    :rtype: _curses.window
    """
    # create stdscr
    stdscr = curses.initscr()
    stdscr.clear()

    # allow echo, set colors
    curses.noecho()
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)

    return stdscr


def classify(label, terms, review, evaluated_term, sort_word_key,
             related_items_count):
    """
    Handle the term classification process of the evaluated_term

    :param label: label to be assigned to the evaluated_term
    :type label: Label
    :param terms: the list of terms
    :type terms: TermList
    :param review: label under review
    :type review: Label
    :param evaluated_term: term to classify
    :type evaluated_term: Term
    :param sort_word_key: actual term used for the related terms
    :type sort_word_key: str
    :param related_items_count: actual number of related terms
    :type related_items_count: int
    :return: the remaining terms to classify, the new related_item_count and sort_word_key
    :rtype: (TermList, int, str)
    """
    # windows[label.label_name].lines.append(evaluated_term.string)
    # refresh_label_windows(evaluated_term.string, label, windows)

    terms.classify_term(evaluated_term.string, label,
                        terms.get_last_classified_order() + 1, sort_word_key)

    if related_items_count <= 0:
        sort_word_key = evaluated_term.string

    containing, not_containing = terms.return_related_items(sort_word_key,
                                                            label=review)

    if related_items_count <= 0:
        related_items_count = len(containing) + 1

    to_classify = containing + not_containing

    # windows['__WORDS'].lines = to_classify.get_strings()
    # windows['__WORDS'].display_lines(rev=False, highlight_word=sort_word_key)
    related_items_count -= 1
    # next_evaluated = to_classify.items[0]
    return to_classify, related_items_count, sort_word_key


def refresh_label_windows(term_to_highlight, label, windows):
    """
    Refresh the windows associated with a label

    :param term_to_highlight: the term to highlight
    :type term_to_highlight: str
    :param label: label of the window that has to highlight the term
    :type label: Label
    :param windows: dict of the windows
    :type windows: dict[str, Win]
    """
    for win in windows:
        if win in ['__WORDS', '__STATS']:
            continue
        if win == label.label_name:
            windows[win].display_lines(rev=True,
                                       highlight_word=term_to_highlight,
                                       only_the_word=True,
                                       color_pair=2)
        else:
            windows[win].display_lines(rev=True)


def undo(terms, to_classify, review, sort_word_key, related_items_count, logger,
         profiler):
    """
    Handle the undo of a term

    :param terms: the list of terms
    :type terms: TermList
    :param to_classify: terms not classified
    :type to_classify: TermList
    :param review: label under review
    :type review: Label
    :param sort_word_key: actual term used for the related terms
    :type sort_word_key: str
    :param related_items_count: actual number of related terms
    :type related_items_count: int
    :param logger: debug logger
    :type logger: logging.Logger
    :param profiler: profiling logger
    :type profiler: logging.Logger
    :return: the remaining terms to classify, the new number of related terms and the new sort_word_key
    :rtype: (TermList, int, str)
    """
    last_word = terms.get_last_classified_term()
    if last_word is None:
        return to_classify, related_items_count, sort_word_key

    label = last_word.label
    related = last_word.related
    logger.debug("Undo: {} group {} order {}".format(last_word.string,
                                                     label,
                                                     last_word.order))
    # un-mark last_word
    terms.classify_term(last_word.string, review, -1)
    # remove last_word from the window that actually contains it
    # try:
    #     classified = terms.get_from_label(label)
    #     win = windows[label.label_name]
    #     win.lines = classified.get_strings()
    #     prev_last_word = terms.get_last_classified_term()
    #     if prev_last_word is not None:
    #         refresh_label_windows(prev_last_word.string, prev_last_word.label,
    #                               windows)
    #     else:
    #         refresh_label_windows('', Label.NONE, windows)
    # except KeyError:
    #     pass  # if here the word is not in a window so nothing to do

    # handle related word
    if related == sort_word_key:
        related_items_count += 1
        to_classify.items.insert(0, last_word)
        # windows['__WORDS'].lines = to_classify.get_strings()
    else:
        sort_word_key = related
        containing, not_containing = terms.return_related_items(sort_word_key,
                                                                label=review)
        related_items_count = len(containing)
        to_classify = containing + not_containing
        # windows['__WORDS'].lines = lines.get_strings()
        # windows['__WORDS'].display_lines(rev=False,
        #                                  highlight_word=sort_word_key)

    if sort_word_key == '':
        # if sort_word_key is empty there's no related item: fix the
        # related_items_count to the correct value of 0
        related_items_count = 0

    profiler.info("WORD '{}' UNDONE".format(last_word.string))

    return to_classify, related_items_count, sort_word_key


def create_windows(win_width, rows, review):
    """
    Creates all the windows

    :param win_width: number of columns of each windows
    :type win_width: int
    :param rows: number of row of each windows
    :type rows: int
    :param review: label to review
    :type review: Label
    :return: the dict of the windows
    :rtype: dict[str, _curses.window]
    """
    windows = dict()
    win_classes = [Label.KEYWORD, Label.RELEVANT, Label.NOISE,
                   Label.NOT_RELEVANT, Label.POSTPONED]
    for i, cls in enumerate(win_classes):
        windows[cls.label_name] = Win(cls, title=cls.label_name.capitalize(),
                                      rows=rows, cols=win_width,
                                      y=(rows + 1) * i, x=0, show_title=True)

    title = 'Input label: {}'
    if review == Label.NONE:
        title = title.format('None')
    else:
        title = title.format(review.label_name.capitalize())

    windows['__WORDS'] = Win(None, title=title, rows=27, cols=win_width, y=9,
                             x=win_width, show_title=True)
    windows['__STATS'] = Win(None, rows=9, cols=win_width, y=0, x=win_width)
    return windows


def curses_main(scr, terms, args, review, last_reviews, logger=None,
                profiler=None):
    """
    Main loop

    :param scr: main window (the entire screen). It is passed by curses
    :type scr: _curses.window
    :param terms: list of terms
    :type terms: TermList
    :param args: command line arguments
    :type args: argparse.Namespace
    :param review: label to review if any
    :type review: Label
    :param last_reviews: last reviews performed. key: abs path of the csv; value: reviewed label name
    :type last_reviews: dict[str, str]
    :param logger: debug logger. Default: None
    :type logger: logging.Logger or None
    :param profiler: profiler logger. Default None
    :type profiler: logging.Logger or None
    """
    datafile = args.datafile
    confirmed = []
    reset = False
    if review != Label.NONE:
        # review mode: check last_reviews
        if review.label_name != last_reviews.get(datafile, ''):
            reset = True

        if reset:
            for w in terms.items:
                w.order = -1
                w.related = ''

    stdscr = init_curses()
    win_width = 40
    rows = 8

    # define windows
    windows = create_windows(win_width, rows, review)

    curses.ungetch(' ')
    _ = stdscr.getch()

    setup_term_windows(terms, windows, review)

    last_word = terms.get_last_classified_term()

    if last_word is None:
        refresh_label_windows('', Label.NONE, windows)
        related_items_count = 0
        sort_word_key = ''
        if review != Label.NONE:
            # review mode
            to_classify = terms.get_from_label(review, order_set=True)
            to_classify.remove(confirmed)
        else:
            to_classify = terms.get_not_classified()
    else:
        refresh_label_windows(last_word.string, last_word.label, windows)
        sort_word_key = last_word.related
        if sort_word_key == '':
            sort_word_key = last_word.string

        containing, not_containing = terms.return_related_items(sort_word_key,
                                                                label=review)
        related_items_count = len(containing)
        to_classify = containing + not_containing

    update_words_window(windows['__WORDS'], to_classify, sort_word_key)
    update_stats_window(windows['__STATS'], terms, related_items_count)
    classifing_keys = [Label.KEYWORD.key,
                       Label.NOT_RELEVANT.key,
                       Label.NOISE.key,
                       Label.RELEVANT.key]
    while True:
        if len(to_classify) <= 0:
            evaluated_word = None
        else:
            evaluated_word = to_classify.items[0]

        if related_items_count <= 0:
            sort_word_key = ''

        c = chr(stdscr.getch())
        c = c.lower()
        if c not in ['w', 'q', 'u'] and evaluated_word == '':
            # no terms to classify. the only working keys are write, undo and
            # quit the others will do nothing
            continue

        try:
            label = Label.get_from_key(c)
        except ValueError:
            # the user did not press a key associated with a label
            label = None

        if c in classifing_keys:
            ret_val = do_classify(terms, evaluated_word, label, review,
                                  sort_word_key, related_items_count, profiler)
            last_word, related_items_count, sort_word_key, to_classify = ret_val

        elif c == 'p':
            ret_val = do_postpone(terms, evaluated_word, review,
                                  sort_word_key, related_items_count, profiler)
            last_word, related_items_count, to_classify = ret_val
        elif c == 'w':
            # write to file
            terms.to_tsv(datafile)
        elif c == 'u':
            # undo last operation
            ret_val = undo(terms, to_classify, review, sort_word_key,
                           related_items_count, logger, profiler)
            to_classify, related_items_count, sort_word_key = ret_val
            last_word = terms.get_last_classified_term()
            if last_word is None:
                label = Label.NONE
            else:
                label = last_word.label
        elif c == 'q':
            # quit
            break
        else:
            # no recognized key: doing nothing (and avoiding useless autosave)
            continue

        if label is not None:
            # update windows
            update_windows(windows, terms, to_classify, last_word,
                           related_items_count, sort_word_key)

        if not args.dry_run and not args.no_auto_save:
            # auto-save
            terms.to_tsv(datafile)


def update_stats_window(window, terms, related_count):
    window.lines = get_stats_strings(terms, related_count)
    window.display_lines(rev=False)


def update_words_window(window, to_classify, sort_key):
    window.lines = to_classify.get_strings()
    window.display_lines(rev=False, highlight_word=sort_key)


def setup_term_windows(terms, windows, review):
    for win in windows:
        if win in ['__WORDS', '__STATS']:
            continue

        if win == review.label_name:
            # in review mode we must add to the window associated with the label
            # review only the items in confirmed (if any)
            conf_word = terms.get_from_label(review, order_set=True)
            windows[win].assign_lines(conf_word.items)
        else:
            windows[win].assign_lines(terms.items)


def do_postpone(terms, word, review, sort_key, related_count, profiler):
    profiler.info("WORD '{}' POSTPONED".format(word))
    # classification: POSTPONED
    terms.classify_term(word.string, Label.POSTPONED,
                        terms.get_last_classified_order() + 1,
                        sort_key)

    related_count -= 1
    if related_count > 0:
        cont, not_cont = terms.return_related_items(sort_key, review)
        to_classify = cont + not_cont
    else:
        to_classify = terms.get_from_label(review)

    return word, related_count, to_classify


def do_classify(terms, word, label, review, sort_key, related_count, profiler):
    profiler.info("WORD '{}' AS '{}'".format(word.string, label.label_name))

    ret_val = classify(label, terms, review, word, sort_key, related_count)
    to_classify, related_count, sort_key = ret_val

    return word, related_count, sort_key, to_classify


def update_windows(windows, terms, to_classify, term_to_highlight,
                   related_items_count, sort_word_key):
    """
    Handle the update of all the windows

    :param windows: dict of the windows
    :type windows: dict[str, Win]
    :param terms: list of the Term
    :type terms: TermList
    :param to_classify: terms not yet classified
    :type to_classify: TermList
    :param term_to_highlight: term to hightlight as the last classified term
    :type term_to_highlight: Term
    :param related_items_count: number of related items
    :type related_items_count: int
    :param sort_word_key: words used for the related item highlighting
    :type sort_word_key: str
    """
    update_words_window(windows['__WORDS'], to_classify, sort_word_key)

    for win in windows:
        if win in ['__WORDS', '__STATS']:
            continue

        cls = terms.get_from_label(Label.get_from_name(win))
        windows[win].lines = cls.get_strings()

    if term_to_highlight is not None:
        refresh_label_windows(term_to_highlight.string, term_to_highlight.label,
                              windows)
    else:
        refresh_label_windows('', Label.NONE, windows)

    update_stats_window(windows['__STATS'], terms, related_items_count)


def main():
    """
    Main function
    """
    parser = init_argparser()
    args = parser.parse_args()

    if args.no_profile:
        profile_log_level = logging.CRITICAL
    else:
        profile_log_level = logging.INFO

    profiler_logger = setup_logger('profiler_logger', 'profiler.log',
                                   level=profile_log_level)
    debug_logger = setup_logger('debug_logger', 'slr-kit.log',
                                level=logging.DEBUG)

    if args.input is not None:
        try:
            review = Label.get_from_name(args.input)
        except ValueError:
            debug_logger.error('{} is not a valid label'.format(args.input))
            sys.exit('Error: {} is not a valid label'.format(args.input))
    else:
        review = Label.NONE

    profiler_logger.info("*** PROGRAM STARTED ***")
    datafile_path = str(pathlib.Path(args.datafile).absolute())
    profiler_logger.info("DATAFILE: '{}'".format(datafile_path))
    # use the absolute path
    args.datafile = datafile_path
    terms = TermList()
    _, _ = terms.from_tsv(args.datafile)
    profiler_logger.info("CLASSIFIED: {}".format(terms.count_classified()))
    # check the last_review file
    try:
        with open('last_review.json') as file:
            last_reviews = json.load(file)
    except FileNotFoundError:
        # no file to care about
        last_reviews = dict()

    if review != Label.NONE:
        label = review.label_name
    else:
        label = 'NONE'
        if datafile_path in last_reviews:
            # remove the last review on the same csv
            del last_reviews[datafile_path]
            if len(last_reviews) <= 0:
                try:
                    os.unlink('last_review.json')
                except FileNotFoundError:
                    pass
            # also reset order and related
            for t in terms.items:
                t.order = -1
                t.related = ''

    profiler_logger.info("INPUT LABEL: {}".format(label))

    curses.wrapper(curses_main, terms, args, review, last_reviews,
                   logger=debug_logger, profiler=profiler_logger)

    profiler_logger.info("CLASSIFIED: {}".format(terms.count_classified()))
    profiler_logger.info("DATAFILE '{}'".format(datafile_path))
    profiler_logger.info("*** PROGRAM TERMINATED ***")
    curses.endwin()

    if review != Label.NONE:
        # ending review mode we must save some info
        last_reviews[datafile_path] = review.label_name

    if len(last_reviews) > 0:
        with open('last_review.json', 'w') as fout:
            json.dump(last_reviews, fout)

    if not args.dry_run:
        terms.to_tsv(args.datafile)


if __name__ == "__main__":
    if DEBUG:
        input('Wait for debug...')
    main()
