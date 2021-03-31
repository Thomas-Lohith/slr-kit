import argparse
import logging
import re
import sys
from itertools import repeat
from multiprocessing import Pool
from typing import Generator
from timeit import default_timer as timer

import pandas as pd
from nltk.stem.wordnet import WordNetLemmatizer
from psutil import cpu_count

from utils import (
    setup_logger,
    assert_column
)

PHYSICAL_CPUS = cpu_count(logical=False)

BARRIER_PLACEHOLDER = 'XXX'
RELEVANT_PREFIX = BARRIER_PLACEHOLDER


class AppendMultipleFilesAction(argparse.Action):
    """
    Action for argparse that collects multiple option arguments as a set

    This can be used to implement a option that can have multiple arguments.
    The option itself may be given multiple time on the command line.
    All the arguments are collected in a set of string.
    """

    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        if nargs is not None:
            if ((isinstance(nargs, str) and nargs in ['*', '?'])
                    or (isinstance(nargs, int) and nargs < 0)):
                raise ValueError(f'nargs = {nargs} is not allowed')

        super().__init__(option_strings, dest, nargs, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        files = getattr(namespace, self.dest, None)
        if files is None:
            files = set()

        if not isinstance(values, list):
            values = [values]

        for v in values:
            files.add(v)

        setattr(namespace, self.dest, files)


def init_argparser():
    """Initialize the command line parser."""
    parser = argparse.ArgumentParser()
    parser.add_argument('datafile', action='store', type=str,
                        help="input CSV data file")
    parser.add_argument('--output', '-o', metavar='FILENAME', default='-',
                        help='output file name. If omitted or %(default)s '
                             'stdout is used')
    parser.add_argument('--barrier-words', '-b',
                        action=AppendMultipleFilesAction, nargs='+',
                        metavar='FILENAME', dest='barrier_words_file',
                        help='barrier words file name')
    parser.add_argument('--relevant-term', '-r', nargs='+', metavar='FILENAME',
                        dest='relevant_terms_file',
                        action=AppendMultipleFilesAction,
                        help='relevant terms file name')
    parser.add_argument('--acronyms', '-a',
                        help='TSV files with the approved acronyms')
    return parser


def load_barrier_words(input_file):
    """
    Loads a list of barrier words from a file

    This functions skips all the lines that starts with a '#'.

    :param input_file: file to read
    :type input_file: str
    :return: the loaded words as a set of string
    :rtype: set[str]
    """
    with open(input_file, 'r', encoding='utf-8') as f:
        stop_words_list = f.read().splitlines()

    stop_words_list = {w for w in stop_words_list if w != '' and w[0] != '#'}
    # Creating a list of custom stopwords
    return stop_words_list


def replace_ngram(text, n_grams, check_subsequent):
    """
    Replace the given n-grams with a placeholder in the specified text

    The n-grams and their placeholder are taken from the generator n_grams, that
    must be a generator that yields a tuple (placeholder, n-gram). Each n-gram
    must be a tuple of strings.
    The function can also check if the toke immediately after the replaced
    n-gram is equal to the placeholder to remove it. This is useful for acronyms
    because, usually the abbreviation immediately follows the extended acronym.

    :param text: the text to search
    :type text: list[str]
    :param n_grams: generator that yields n-grams and their placeholder
    :type n_grams: Generator[tuple[str, tuple[str]], Any, None]
    :param check_subsequent: if True, check the token immediately after the
        found n-gram. If it is equal to the placeholder, this token is removed.
    :return: the transformed text
    :rtype: list[str]
    """
    text2 = list(text)
    for placeholder, ngram in n_grams:
        end = False
        index = -1
        length = len(ngram)
        while not end:
            try:
                # index + 1 to skip the previous match
                index = text2.index(ngram[0], index + 1)
                if tuple(text2[index:index + length]) == ngram:
                    # found!
                    text2[index:index + length] = [placeholder]
                    try:
                        if check_subsequent and text2[index + 1] == placeholder:
                            del text2[index + 1]
                    except IndexError:
                        # reached the end of the list: stop the loop
                        end = True
            except ValueError:
                end = True

    return text2


def preprocess_item(item, relevant_terms, barrier_words, acronyms,
                    barrier=BARRIER_PLACEHOLDER,
                    relevant_prefix=RELEVANT_PREFIX):
    """
    Preprocess the text of a document.

    It lemmatizes the text. Then it searches for the relevant terms. Each
    relevant term found is replaced with a string composed with the
    relevant_prefix, an '_' and then all the words composing the term separated
    with '_'.
    It searches for the acronyms, changing the words composing them with the
    corresponding abbreviation.
    It also filters the barrier words changing them with the barrier string as
    placeholder.

    :param item: the text to process
    :type item: str
    :param relevant_terms: the relevant words to search. Each n-gram must be a
        tuple of strings
    :type relevant_terms: set[tuple[str]]
    :param barrier_words: the barrier words to filter
    :type barrier_words: set[str]
    :param acronyms: the acronyms to replace in each document. Must have two
        columns 'Acronym' and 'Extended'
    :type acronyms: pd.DataFrame
    :param barrier: placeholder for the barrier words
    :type barrier: str
    :param relevant_prefix: prefix string used when replacing the relevant terms
    :type relevant_prefix: str
    :return: the processed text
    :rtype: list[str]
    """
    # Remove punctuations
    text = re.sub('[^a-zA-Z]', ' ', item)
    # Convert to lowercase
    text = text.lower()
    # Remove tags
    text = re.sub('&lt;/?.*?&gt;', ' &lt;&gt; ', text)
    # Remove special characters and digits
    text = re.sub('(\\d|\\W)+', ' ', text)
    # Convert to list from string
    text = text.split()
    # Lemmatisation
    lem = WordNetLemmatizer()
    # text = [lem.lemmatize(word) for word in text if not word in stop_words]
    text2 = []

    # replace acronyms
    acro_gen = ((acro['Acronym'], acro['Extended'])
                for _, acro in acronyms.iterrows())
    text = replace_ngram(text, acro_gen, True)

    for word in text:
        text2.append(lem.lemmatize(word))

    # mark relevant terms
    rel_gen = ((f'{relevant_prefix}_{"_".join(rel)}', rel)
               for rel in relevant_terms)
    text2 = replace_ngram(text2, rel_gen, False)

    for i, word in enumerate(text2):
        if word in barrier_words:
            text2[i] = barrier

    text2 = ' '.join(text2)
    return text2


def process_corpus(dataset, relevant_terms, barrier_words, acronyms,
                   barrier=BARRIER_PLACEHOLDER,
                   relevant_prefix=RELEVANT_PREFIX):
    """
    Process a corpus of documents.

    Each documents is processed using the preprocess_item function

    :param dataset: the corpus of documents
    :type dataset: pd.Sequence
    :param relevant_terms: the related terms to search in each document
    :type relevant_terms: set[tuple[str]]
    :param barrier_words: the barrier words to filter in each document
    :type barrier_words: set[str]
    :param acronyms: the acronyms to replace in each document. Must have two
        columns 'Acronym' and 'Extended'
    :type acronyms: pd.Dataframe
    :param barrier: placeholder for the barrier words
    :type barrier: str
    :param relevant_prefix: prefix used to replace the relevant terms
    :type relevant_prefix: str
    :return: the corpus processed
    :rtype: list[str]
    """
    with Pool(processes=PHYSICAL_CPUS) as pool:
        corpus = pool.starmap(preprocess_item, zip(dataset,
                                                   repeat(relevant_terms),
                                                   repeat(barrier_words),
                                                   repeat(acronyms),
                                                   repeat(barrier),
                                                   repeat(relevant_prefix)))
    return corpus


def load_relevant_terms(input_file):
    """
    Loads a list of relevant terms from a file

    This functions skips all the lines that starts with a '#'.
    Each term is split in a tuple of strings

    :param input_file: file to read
    :type input_file: str
    :return: the loaded terms as a set of tuples of strings
    :rtype: set[tuple[str]]
    """
    with open(input_file, 'r', encoding='utf-8') as f:
        rel_words_list = f.read().splitlines()

    rel_words_list = {tuple(w.split(' '))
                      for w in rel_words_list
                      if w != '' and w[0] != '#'}

    return rel_words_list


def main():
    target_column = 'abstract'
    parser = init_argparser()
    args = parser.parse_args()

    debug_logger = setup_logger('debug_logger', 'slr-kit.log',
                                level=logging.DEBUG)
    # TODO: write log string with values of the parameters used in the execution

    # load the dataset
    dataset = pd.read_csv(args.datafile, delimiter='\t', encoding='utf-8')
    dataset.fillna('', inplace=True)
    assert_column(args.datafile, dataset, target_column)
    debug_logger.debug('Dataset loaded {} items'.format(len(dataset[target_column])))

    barrier_words = set()

    if args.barrier_words_file is not None:
        for sfile in args.barrier_words_file:
            barrier_words |= load_barrier_words(sfile)

        debug_logger.debug('Barrier words loaded and updated')

    if args.acronyms is not None:
        conv = {
            'Acronym': lambda s: s.lower(),
            'Extended': lambda s: tuple(s.lower().split(' ')),
        }
        acronyms = pd.read_csv(args.acronyms, delimiter='\t', encoding='utf-8',
                               converters=conv)
        assert_column(args.acronyms, acronyms, ['Acronym', 'Extended'])
        debug_logger.debug('Acronyms loaded and updated')
    else:
        acronyms = pd.DataFrame()

    rel_terms = set()
    if args.relevant_terms_file is not None:
        for rfile in args.relevant_terms_file:
            rel_terms = load_relevant_terms(rfile)

        debug_logger.debug('Relevant words loaded and updated')

    start = timer()
    corpus = process_corpus(dataset[target_column], rel_terms, barrier_words,
                            acronyms, BARRIER_PLACEHOLDER, RELEVANT_PREFIX)
    stop = timer()
    elapsed_time = stop - start
    debug_logger.debug('Corpus processed')
    dataset['abstract_lem'] = corpus

    # write to output, either a file or stdout (default)
    if args.output == '-':
        output_file = sys.stdout
    else:
        output_file = open(args.output, 'w', encoding='utf-8')

    dataset.to_csv(output_file, index=None, header=True, sep='\t')
    print('Elapsed time:', elapsed_time, file=sys.stderr)


if __name__ == '__main__':
    main()
