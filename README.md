# Support material for the FAST SLR workflow

The workflow is based on the following stages:

- selection of bibliographic data set (manual)
- extraction of n-grams (automatic)
- classification of n-grams (manual)
- clustering of documents (automatic)
- validation of the topics associated with the clusters (manual)
- derivation of statistics (automatic)

# FA.WO.C. comments

## TODO and possible features

- NEW FEATURE: the program should be able to open a list of strings coming from the source abstracts that contain the word under exaxmination, to help understanding its relevance; this could be done only upon user request - if too computational heavy - or always in real-time - if not so heavy.
- Allow the user to configure the keys associated to the different actions/class; a simple JSON file may contain the association "key <-> action".

# Possible efficient workflow to use FA.WO.C.

## Manual workflow

- stage 1: mark words either being NOISE or postponed (look for trivial noise words, such as "however, thus, require, ...")
- stage 2: classify the postponed words as either NOISE or RELEVANT
- stage 3: classify the relevant words as keywords or not

In all the stages, mark NOT-RELEVANT words if needed.

## Possible automatic stages

- probably stage 1 could be made automatic

# Available scripts and programs

The following scripts and programs are currently available. They are listed in the order that they are expected to be used in the SLR workflow.
All the scripts expect utf-8 files as input.

## `ris2csv.py`

- ACTION: Converts a file from the RIS to the CSV format.
- INPUT: RIS bibliographic file.
- OUTPUT: CSV file format with the desired columns.

The output is sent to stdout unless an output file name is explicitly specified.

The advice is to always start from the RIS format (instead of CSV or BIB) since it allows a better, easier and clearer separation among the different elements of a bibliographic item.
The command line parameters allow to select the fields to export fro the RIS file.

During the conversion, an unique progressive number is added to each paper, which acts as unique identifier in the rest of the processing (within a column named `id`).
Therefore, be careful to not mix different versions of the source RIS that may generate a different numbering of the papers.

TODO: add an option to append the output to an existing CSV file?

### Example of usage

The standard slr-kit workflow needs a CSV file with two columns: `title` and `abstract`. Such CSV file can be obtained with the command:

```
ris2csv --columns title,abstract dataset.ris > dataset_abstracts.csv
```

## `acronyms.py`

- ACTION: Extracts a list of acronyms from the abstracts.
- INPUT: CSV file with the list of abstracts generated by `ris2csv.py`.
- OUTPUT: CSV file containing the short and extended acronyms.

Uses the algorithm presented in A. Schwartz and M. Hearst, "A Simple Algorithm for Identifying Abbreviations Definitions in Biomedical Text", Biocomputing, 2003.

The script assumes that the abstracts are contained in a column named `abstract`. Therefore, if the input CSV comes from other sources (e.g., the direct export from online services), make sure that the `abstract` column is present in the CSV. It also requires a column named `id`.

## `preprocess.py`

- ACTION: Performs the preprocessing of the documents to prepare it for further processing.
- INPUT: The CSV file produced by `ris2csv.py`.
- OUTPUT: A CSV file containing the same columns of the input file, plus a new column containing the preprocessed text.

The preprocessing includes:

- Remove punctuations
- Convert to lowercase
- Remove stop words (also called as barrier word)
- Mark selected n-grams as relevant
- Acronyms substitution
- Remove special characters and digits
- Lemmatisation

The barrier words are read from one or more optional files.
These words are replaced, in the output, with a placeholder (called barrier placeholder) that is recognized in the term extraction phase.
The default barrier placeholder is the '@' character.

The user can also specify files containing lists of relevant n-grams.
For each specified file, the user can specify a particular placeholder that will be used as replacement text for each term in that list.
That text will be surrounded with the barrier placeholder.
If the user specify a '-' or the empty string as the placeholder for a list of terms, then a different approach is used.
Each term will be replaced with a placeholder composed by, the barrier placeholder, the words composing the term separated with '_' and finally another barrier placeholder.
This kind of placeholders can be used by the subsequent phases to recognize the term without losing the meaning of the n-gram.

Examples (assuming that '@' is the barrier placeholder):
1. if the user specifies a list of relevant n-grams with the specific placeholder 'TASK_PARAM', all the n-grams in that list will be replaced with '@TASK_PARAM@'.
2. if the user specifies a list of relevant n-grams without a specific placeholder, then each n-gram will be replaced with a specific string. The n-gram 'edf' will be replaced with '@edf@', the n-gram 'earliest deadline first' will be replaced with '@earliest_deadline_first@'.

This program also handles the acronyms.
A TSV file containing the approved acronyms can be specified.
This file must have a column 'Acronym' with the abbreviation of each acronym and a column 'Extended' with the extended version of the acronym.
For each row in the TSV file, the program searches for:
1. the abbreviation of the acronym;
2. the extended acronym;
3. the extended acronym with all the spaces substituted with '-'.
The program replaces each recognized acronym with `<barrier placeholder><acronym><barrier placeholder>`.

Positional arguments:
- `datafile` input CSV data file

optional arguments:

* `--output | -o FILENAME` output file name. If omitted or '-' stdout is used
* `--placeholder | -p PLACEHOLDER` Placeholder for barrier word. Also used as a prefix for the relevant words. Default: '@'
* `--barrier-words | -b FILENAME [FILENAME ...]` barrier words file name
* `--relevant-term | -r FILENAME PLACEHOLDER` relevant terms file name and the placeholder to use with those terms. The placeholder must not contains any space. If the placeholder is a "-" or the empty string, each relevant term from this file, is replaced with the barrier placeholder, followed by the term itself with each space changed with the "-" character and then another barrier placeholder.
* `--acronyms | -a ACRONYMS` TSV files with the approved acronyms
* `--target-column | -t TARGET_COLUMN` Column in datafile to process. If omitted 'abstract' is used.
* `--output-column OUTPUT_COLUMN` name of the column to saveIf omitted 'abstract_lem' is used.
* `--input-delimiter INPUT_DELIMITER` Delimiter used in datafile. Default '\t'
* `--output-delimiter OUTPUT_DELIMITER` Delimiter used in output file. Default '\t'
* `--rows | -R INPUT_ROWS` Select maximum number of samples
* `--language | -l LANGUAGE` language of text. Must be a ISO 639-1 two-letter code. Default: 'en'

### Example of usage

The following example processes the `dataset_abstracts.csv` file, filtering the stop words in `stop_words.txt` and produces `dataset_preproc.csv`, which contains the same columns of the input file plus the `abstract_lem` column:

```
preprocess.py --barrier-words stop_words.txt dataset_abstracts.csv > dataset_preproc.csv
```
The following example processes the `dataset_abstracts.csv` file, replacing the terms `relevant_terms.txt` with placeholder created from the terms themselves, replacing the terms in `other_relevant.txt` with '@PLACEHOLDER@' and produces `dataset_preproc.csv`, which contains the same columns of the input file plus the `abstract_lem` column:

```
preprocess.py --relevant-term relevant_terms.txt - -r other_relevant.txt PLACEHOLDER dataset_abstracts.csv > dataset_preproc.csv
```
## `gen-terms.py`

- ACTION: Extracts the terms ({1,2,3,4}-grams) from the abstracts.
- INPUT: The TSV file produced by `preprocess.py` (it works on the column `abstract_lem`).
- OUTPUT: A TSV file containing the list of terms, and a TSV with their frequency.

### Arguments:

- `inputfile`: name of the TSV produced by `preprocess.py`;
- `outputfile`: name of the output file. This name is also used to create the name of the file with the term frequencies.
  For instance, if `outputfile` is `filename.tsv`, the frequencies file will be named `filename_fawoc_data.tsv`.
  This file is create in the same directory of `outputfile`;
- `--stdout|-s`: also print on stdout the output file;
- `--n-grams|-n N`: maximum size of n-grams. The script will output all the 1-grams, ... N-grams;
- `--min-frequency|-m N`: minimum frequency of the n-grams. All the n-grams with a frequency lower than `N` are not output.

### Example of usage

Extracts terms from `dataset_preproc.csv` and store them in `dataset_terms.csv` and `dataset_terms_fawoc_data.tsv`:

```
gen-n-grams.py dataset_preproc.csv dataset_terms.csv
```

## `cumulative-frequency.py`

- ACTION: Extracts the terms ({1,2,3,4}-grams) from the abstracts, and produces a lineplot of most N frequent terms over the number of papers.
- INPUT: The CSV file produced by `preprocess.py` (it works on the column `abstract_lem`).
- OUTPUT: A png file showing the plot and/or the dataset used to build that png

### Example of usage

Extracts terms from `dataset_preproc.csv` and prints the chart on `./n-grams_frequency/dataset_preproc_N-gram.png`:

```
cumulative-frequency.py --datafile dataset_preproc.csv --top 5 --savefig
```

## `fawoc.py`, the FAst WOrd Classifier

- ACTION: GUI program for the fast classification of terms.
- INPUT: The CSV file with the terms produced by `gen-n-grams.py`.
- OUTPUT: The same input CSV with the labels assigned to the terms.

NOTE: the program changes the content of the input file.

The program uses also two files to save its state and retrieve some information about terms.
Assuming that the input file is called `dataset_terms.tsv`, FAWOC uses `dataset_terms_fawoc_data.json` and `dataset_terms_fawoc_data.tsv`.
This two files are searched and saved in the same directory of the input file.
The json file is used to save the state of FAWOC, and it is saved every time the input file is updated.
The tsv file is used to load some additional data about the terms (currently only the terms count).
This file is not modified by FAWOC.
If these two file are not present, they are created by FAWOC, the json file with the current state.
The tsv file is created with data eventually loaded from the input file.
If no count field was present in the input file a default value of -1 is used for all terms.

FAWOC saves data every 10 classsifications.
To save data more often, use the 'w' key.

The program also writes profiling information into the file `profiler.log` with the relevant operations that are carried out.


## `occurrences.py`

- ACTION: Determines the occurrences of the terms in the abstracts.
- INPUT: Two files: 1) the list of abstracts generated by `preprocess.py` and 2) the list of terms generated by `fawoc.py`
- OUTPUT: A JSON data structure with the position of every term in each abstract; the output is written to stdout by default.

### Example of usage

Extracts the occurrences of the terms listed in `dataset_terms.csv` in the abstracts contained in `dataset_preproc.csv`, storing the results in `dataset_occ_keyword.json`:

```
occurrences.py -l keyword dataset_preproc.csv dataset_terms.csv > dataset_occ_keyword.json
```

## `dtm.py`

- ACTION: Calculates the document-terms matrix
- INPUT: The terms-documents JSON produced by `occurrences.py`
- OUTPUT: A CSV file containing the matrix; terms are on the rows, documents IDs are on the columns

Document IDs match with the ones assigned by `ris2csv.py`.

### Example of usage

Calculates the document-terms matrix starting from `dataset_occ_keyword.json` and storing the matrix in `dataset_dtm.csv`:

```
dtm.py dataset_occ_keyword.json > dataset_dtm.csv
```

## `cosine_similarity.py`

- ACTION: Calculates the cosine similarity of the document-terms matrix (generated by `dtm.py`)
- INPUT: CSV file with document-terms matrix
- OUTPUT: CSV file with the cosine similarity of terms

### Example of usage

```
cosine_similarity.py dataset_dtm.csv > dataset_cosine_similarity.csv
```

## `embeddings.py`

- ACTION: Create words embeddings based on Word2Vec and computed documents similarity
- INPUT: CSV with corpus preprocessed (`preprocess.py) , CSV file with document-terms matrix
- OUTPUT: CSV file with the similarity of documents vectors

### Example of usage

```
ebbedings.py dataset_preproc.csv dataset_dtm.csv > dataset_w2v_similarity.csv
```

## `supervised_clustering.py`

- ACTION: Perform semi-supervised clustering with pairwise constraints
- INPUT: JSON file with a precomputed ground-truth from `parse_pairings.py`
- OUTPUT: CSV file with documents divided into clusters

### Example of usage

```
supervised_clustering.py ground_truth.json > pckmeans_clusters.csv
```

## `lda.py`

- ACTION: Train an LDA model and outputs the extracted topics and the association between topics and documents.
- INPUT: The TSV file produced by `preprocess.py` (it works on the column `abstract_lem`) and the terms TSV file classified with FAWOC.
- OPTIONAL INPUT: One or more files with additional keyword and acronyms.
- OUTPUT: A JSON file with the description of extracted topics and a JSON file with the association between topics and documents.

This script outputs the topics in `<outdir>/lda_terms-topics_<date>_<time>.json` and the topics assigned
to each document in `<outdir>/lda_docs-topics_<date>_<time>.json`.
### Arguments:

Positional:

- `preproc_file` path to the preprocess file with the text to elaborate.
- `terms_file` path to the file with the classified terms.
- `outdir` path to the directory where to save the results. If omitted, the current directory is used.

Optional:

- `--additional-terms FILENAME [FILENAME ...], -T FILENAME [FILENAME ...]`
                      Additional keywords files
- ` --acronyms ACRONYMS, -a ACRONYMS` TSV files with the approved acronyms
- `--topics TOPICS`       Number of topics. If omitted 20 is used
- `--alpha ALPHA`         alpha parameter of LDA. If omitted "auto" is used
- `--beta BETA`           beta parameter of LDA. If omitted "auto" is used
- `--no_below NO_BELOW   Keep tokens which are contained in at least this number of documents. If
                      omitted 20 is used
- `--no_above NO_ABOVE`   Keep tokens which are contained in no more than this fraction of documents
                      (fraction of total corpus size, not an absolute number). If omitted 0.5 is
                      used
- `--seed SEED`           Seed to be used in training
- `--ngrams`              if set use all the ngrams
- `--model`               if set, the lda model is saved to directory `<outdir>/lda_model`. The model is
                      saved with name "model".
- `--no-relevant`        if set, use only the term labelled as keyword
- `--load-model LOAD_MODEL`
                      Path to a directory where a previously trained model is saved. Inside this
                      directory the model named "model" is searched. the loaded model is used with
                      the dataset file to generate the topics and the topic document association
- `--placeholder PLACEHOLDER, -p PLACEHOLDER`
                        Placeholder for barrier word. Also used as a prefix for the relevant words. 
                        Default: "@"

### Example of usage 
Extracts topics from dataset `dataset_preproc.csv` using the classified terms in `dataset_terms.csv` and saving the result in `/path/to/outdir`:
```
lda.py dataset_preproc.csv dataset_terms.csv /path/to/outdir
```
# Additional scripts

## `analyze-occ.py`

- ACTION: Generates the report of which document (abstract) contains which terms; for each document, reports all the contained terms, and the count.
- INPUT: The JSON file produced by `occurrences.py`.
- OUTPUT: A CSV file containing the list of documents (abstracts) containing the terms and the corresponding information.

## `noise-stats.py`

- ACTION: Calculate a statistic regarding noise words; it calculates, for each word, the ratio of the words labelled as noise (plus unlabelled words) against the total number of that word
- INPUT: The CSV file with the terms extracted by `gen-n-grams.py`.
- OUTPUT: A CSV files with one word (not a term!) per row, with its total count, number of noise labels and unlabelled items, plus the calculation of an index of noisiness

Notice that a word is not a term. In the term `this term important` there are the three words `this`, `term` and `important`.
This statistic could help to spot wrong labelling and/or words that are likely to be noise across several datasets.

It is an utility program that may not directly enter the main workflow, but can start providing interesting insights regarding noise words that can help, in the future, to spot possible noise words earlier, or to spot possible errors in the classification.


## `clear-postponed.py`

- ACTION: Removes the label `postponed` from the input file.
- INPUT: The CSV file with the terms extracted by `gen-n-grams.py`.
- OUTPUT: The same input file without the `postponed`.

TODO: being able to specify on the command line the label to remove.

## `cmp-terms.py`

- ACTION: Compare two CSV containing the same list of terms with possibly different labelling
- INPUT: The two CSV files in the format produced by `gen-n-grams.py`; they should containg the same list of terms
- OUTPUT: The list of terms that have different labels in the two files

## `copy-labels.py`

- ACTION: Copy the labels from the terms in the input CSV to the corresponding terms in the destination CSV.
- INPUT: The two CSV files in the format produced by `gen-n-grams.py`.
- OUTPUT: The list of terms in the destination CSV with labels assigned as in the input CSV.

This script is useful when doing experiments with subsets of a list of terms that was already labelled.
This type of experiments are indicated to save processing time during the development of scripts and algorithms.

## `gen-td-idf.py`

- ACTION: Calculates the TD-IDF index for the terms contained in the abstracts
- INPUT: The list of abstracts generated by `preprocess.py`
- OUTPUT: CSV containing the words with the top index

NOTE: At the moment, this script works on the complete lemmatized abstracts. It could be made better to work on the JSON output of `occurrences.py`.

## `match-occ-counts.py`

- ACTION: Serve per generare il file di report con keyword + not-relevant per ciascun articolo in modo da studiarne il comportamento
- INPUT:
- OUTPUT:

## `parse_pairings.py`

- ACTION: Parse a file of a manual clustering session to create a ground-truth for a semi-supervised clustering
- INPUT: Text file where each line represents a cluster and documents ID with format: 'cluster_label:2,3,5,34,[...]'
- OUTPUT: JSON file with format: 'id' : ['label1', 'label2'] (a document may belong to multiple clusters)

### Example of usage

```
parse_pairings.py manual_pairings.txt > ground_truth.json
```

## `evaluate_clusters.py`

- ACTION: Analyze clustering performance comparing results with a ground truth
- INPUT: Clusters and manually labeled documents (from `parse_pairings.py`)
- OUTPUT: Multiple files with confusion matrices, pairs overlappings and other metrics

### Example of usage

```
evaluate_clusters.py pckmeans_clusters.csv ground_truth.json
```

## `topic_report.py`

- ACTION: Generate reports for various stats regarding topics and papers.
- INPUT: the RIS file containing data for all papers and the json docs file containing results from LDA
- OUTPUT: Set of tables in csv format saved authomatically in a directory with the dataset name and a graph for topic-year evolution.
    Also a markdown template will be automatically filled

### Arguments

- `ris_file`: path to the RIS file
- `json_file`: path to the json docs file, generated by `lda.py`
- `dataset_name`: name of the dataset to be analysed
- `md_template`: path to the markdown template. The script always interprets this path as relative to the current directory.

### Example of usage

```
topic_report.py dsm.ris dsm_docs.json dsm report_template.md
```

there are also 2 templates for this script the first is `report_template.md` which is automatically filled by the script, the second is `report_template.tex`
which needs to be filled with the csv tables and the graph saved by the script.
