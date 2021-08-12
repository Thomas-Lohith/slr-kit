import sys

import pandas as pd
from RISparser import readris

from slrkit_utils.argument_parser import ArgParse


def to_record(config):
    """
    Returns the list of files to record with git
    :param config: content of the script config file
    :type config: dict[str, Any]
    :return: the list of files
    :rtype: list[str]
    :raise ValueError: if the config file does not contains the right values
    """
    file = config['input_file']
    if file is None or file == '':
        raise ValueError("'input_file' is not specified")
    return [str(file)]


def show_columns(df):
    print('Valid columns:')
    for c in df.columns:
        print('   {}'.format(c))


def ris2csv(args):
    try:
        with open(args.input_file, 'r', encoding='utf-8') as bibliography_file:
            entries = readris(bibliography_file)
            risdf = pd.DataFrame(entries)
    except FileNotFoundError:
        msg = 'Error: input file {!r} not found'
        sys.exit(msg.format(args.input_file))

    # The number of citations lies in 'notes' column as element of a list
    # These 3 lines extract that information
    citation = pd.DataFrame(risdf['notes'].tolist(), index=risdf.index)[0]
    citation_number = citation.str.extract(r'((?<=:)\d+)').astype(float)
    risdf['citations'] = citation_number.astype(float).fillna(0)

    cols = args.columns.split(',')
    # checks if help was requested
    if len(cols) == 1 and cols[0] == '?':
        show_columns(risdf)
        sys.exit(1)
    # checks that the requested items exist in the RIS file
    for c in cols:
        if c not in risdf:
            sys.exit('Error: invalid column: {!r}.'.format(c))

    if args.output is not None:
        output_file = open(args.output, 'w', encoding='utf-8')
    else:
        output_file = sys.stdout

    risdf.to_csv(output_file, columns=cols, index_label='id', sep='\t')


IMPORTERS = {
    'RIS': ris2csv
}
DEFAULT_IMPORTER = 'RIS'


def init_argparser():
    """Initialize the command line parser."""
    parser = ArgParse()
    parser.add_argument('input_file', action='store', type=str,
                        help='input bibliography file', input=True)
    parser.add_argument('--type', '-t', action='store', type=str,
                        default=DEFAULT_IMPORTER, choices=list(IMPORTERS.keys()),
                        help='Type of the bibliography file. Supported types: '
                             '%(choices)s. If absent %(default)r is used.')
    parser.add_argument('--output', '-o', metavar='FILENAME',
                        help='output CSV file name',
                        suggest_suffix='_abstracts.csv', output=True)
    parser.add_argument('--columns', '-c', metavar='col1,..,coln',
                        default='title,abstract,year',
                        help='list of comma-separated columns to export. If '
                             'absent %(default)r is used. Use \'?\' for the '
                             'list of available columns. '
                             'A column with the number of citations, is always '
                             'exported.')
    return parser


def import_data(args):
    IMPORTERS[args.type](args)


def main():
    parser = init_argparser()
    args = parser.parse_args()
    import_data(args)


if __name__ == '__main__':
    main()
