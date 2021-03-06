#!/usr/bin/env python
#
# corenlp  - Python interface to Stanford Core NLP tools
# Copyright (c) 2012 Dustin Smith
#   https://github.com/dasmith/stanford-corenlp-python
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.


import json, optparse, os, re, sys, time, traceback
import pexpect
from progressbar import ProgressBar, Fraction
from unidecode import unidecode
from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCServer
import nltk, nltk.data


class bc:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'


VERBOSE = True
STATE_START, STATE_TEXT, STATE_WORDS, STATE_TREE, STATE_DEPENDENCY, STATE_COREFERENCE = 0, 1, 2, 3, 4, 5
WORD_PATTERN = re.compile('\[([^\]]+)\]')
CR_PATTERN = re.compile(r"\((\d*),(\d)*,\[(\d*),(\d*)\)\) -> \((\d*),(\d)*,\[(\d*),(\d*)\)\), that is: \"(.*)\" -> \"(.*)\"")

class ProcessError(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class ParserError(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class TimeoutError(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

def clean_raw_text():
    #cleans all files contained in the directory "files/raw_text/" and places
    #them into the "files/clean_text" directory.
    import re
    import nltk, nltk.data

    sent_detector=nltk.data.load('tokenizers/punkt/english.pickle')

    raw_files=['files/raw_text/' + f for f in os.listdir('files/raw_text/')]
    clean_files=['files/clean_' + raw[10:-4] + '_clean.txt' for raw in raw_files]

    for raw, clean in zip(raw_files, clean_files):
        raw_text=open(raw, 'r').read()
        text=re.sub(r'-+(\n)\s*', '', raw_text)
        text=re.sub(r'(\n)+', '', text)
        text= ' '.join([' '.join(nltk.word_tokenize(sent)) for sent in sent_detector.tokenize(text.strip())])
        open(clean, 'w').write(text)


def remove_id(word):
    """Removes the numeric suffix from the parsed recognized words: e.g. 'word-2' > 'word' """
    return word.count("-") == 0 and word or word[0:word.rindex("-")]


def parse_bracketed(s):
    '''Parse word features [abc=... def = ...]
    Also manages to parse out features that have XML within them
    '''
    word = None
    attrs = {}
    temp = {}
    # Substitute XML tags, to replace them later
    for i, tag in enumerate(re.findall(r"(<[^<>]+>.*<\/[^<>]+>)", s)):
        temp["^^^%d^^^" % i] = tag
        s = s.replace(tag, "^^^%d^^^" % i)
    # Load key-value pairs, substituting as necessary
    for attr, val in re.findall(r"([^=\s]*)=([^=\s]*)", s):
        if val in temp:
            val = temp[val]
        if attr == 'Text':
            word = val
        else:
            attrs[attr] = val
    return (word, attrs)

def parse_xml_output():
    import os
    import nltk, nltk.data
    import xmltodict
    from collections import OrderedDict
    """Because interaction with the command-line interface of the CoreNLP
    tools is limited to very short text bits, it is necessary to parse xml
    output"""
    #First, we change to the directory where we place the xml files from the
    #parser:

    os.chdir('files/xml')

    #we get a list of the cleaned files that we want to parse:

    files=['../clean_text/' + f for f in os.listdir('../clean_text')]

    #creating the file list of files to parse

    write_files=open('../files.txt', 'w').write('\n'.join(files))

    sent_detector=nltk.data.load('tokenizers/punkt/english.pickle')
    lines=[]
    #extracting the sentences from the text:

    [lines.extend(sent_detector.tokenize(open(text, 'r').read().strip())) for text in files]

    command='java -Xmx3g -cp ../../corenlp-wrapper/stanford-corenlp-full-2013-04-04/stanford-corenlp-1.3.5.jar:../../corenlp-wrapper/stanford-corenlp-full-2013-04-04/stanford-corenlp-1.3.5-models.jar:../../corenlp-wrapper/stanford-corenlp-full-2013-04-04/xom.jar:../../corenlp-wrapper/stanford-corenlp-full-2013-04-04/joda-time.jar:../../corenlp-wrapper/stanford-corenlp-full-2013-04-04/jollyday.jar edu.stanford.nlp.pipeline.StanfordCoreNLP -props ../../corenlp-wrapper/corenlp/default.properties -filelist ../files.txt'

    #creates the xml file of parser output:

    os.system(command)

    #reading in the raw xml file:
    xml=open(os.listdir('.')[0], 'r').read()

    #turning the raw xml into a raw python dictionary:
    raw_dict=xmltodict.parse(xml)

    #making a raw sentence list of dictionaries:
    raw_sent_list=raw_dict[u'root'][u'document'][u'sentences'][u'sentence']
    #making a raw coref dictionary:
    raw_coref_list=raw_dict[u'root'][u'document'][u'coreference'][u'coreference']

    #cleaning up the list ...the problem is that this doesn't come in pairs, as the command line version:

    coref_list=[[[eval(raw_coref_list[j][u'mention'][i]['sentence'])-1, eval(raw_coref_list[j][u'mention'][i]['head'])-1, eval(raw_coref_list[j][u'mention'][i]['start'])-1, eval(raw_coref_list[j][u'mention'][i]['end'])-1] for i in range(len(raw_coref_list[j][u'mention']))] for j in range(len(raw_coref_list))]

    [[coref.insert(0,' '.join(lines[coref[0]].split()[coref[-2]:coref[-1]])) for coref in coref_list[j]] for j in range(len(coref_list))]
    os.chdir('../..')

    coref_list=[[[coref_list[j][i], coref_list[j][0]] for i in range(len(coref_list[j]))] for j in range(len(coref_list))]

    sentences=[{'dependencies': [[dep['dep'][i]['@type'], dep['dep'][i]['governor']['#text'], dep['dep'][i]['dependent']['#text']] for dep in raw_sent_list[j][u'dependencies'] for i in range(len(dep['dep'])) if dep['@type']=='basic-dependencies'], 'text': lines[j], 'parsetree': str(raw_sent_list[j]['parse']), 'words': [[str(token['word']), OrderedDict([('NamedEntityTag', str(token['NER'])), ('CharacterOffsetEnd', str(token['CharacterOffsetEnd'])), ('CharacterOffsetBegin', str(token['CharacterOffsetBegin'])), ('PartOfSpeech', str(token['POS'])), ('Lemma', str(token['lemma']))])] for token in raw_sent_list[j]['tokens'][u'token']]} for j in range(len(lines))]

    results={'coref':coref_list, 'sentences':sentences}

    return results

def parse_parser_results(text):
    """ This is the nasty bit of code to interact with the command-line
    interface of the CoreNLP tools.  Takes a string of the parser results
    and then returns a Python list of dictionaries, one for each parsed
    sentence.
    """
    results = {"sentences": []}
    state = STATE_START
    for line in unidecode(text.decode('utf-8')).split("\n"):
        line = line.strip()

        if line.startswith("Sentence #"):
            sentence = {'words':[], 'parsetree':[], 'dependencies':[]}
            results["sentences"].append(sentence)
            state = STATE_TEXT

        elif state == STATE_TEXT:
            sentence['text'] = line
            state = STATE_WORDS

        elif state == STATE_WORDS:
            if not line.startswith("[Text="):
                raise ParserError('Parse error. Could not find "[Text=" in: %s' % line)
            for s in WORD_PATTERN.findall(line):
                sentence['words'].append(parse_bracketed(s))
            state = STATE_TREE

        elif state == STATE_TREE:
            if len(line) == 0:
                state = STATE_DEPENDENCY
                sentence['parsetree'] = " ".join(sentence['parsetree'])
            else:
                sentence['parsetree'].append(line)

        elif state == STATE_DEPENDENCY:
            if len(line) == 0:
                state = STATE_COREFERENCE
            else:
                split_entry = re.split("\(|, ", line[:-1])
                if len(split_entry) == 3:
                    rel, left, right = map(lambda x: remove_id(x), split_entry)
                    sentence['dependencies'].append(tuple([rel,left,right]))

        elif state == STATE_COREFERENCE:
            if "Coreference set" in line:
                if 'coref' not in results:
                    results['coref'] = []
                coref_set = []
                results['coref'].append(coref_set)
            else:
                for src_i, src_pos, src_l, src_r, sink_i, sink_pos, sink_l, sink_r, src_word, sink_word in CR_PATTERN.findall(line):
                    src_i, src_pos, src_l, src_r = int(src_i)-1, int(src_pos)-1, int(src_l)-1, int(src_r)-1
                    sink_i, sink_pos, sink_l, sink_r = int(sink_i)-1, int(sink_pos)-1, int(sink_l)-1, int(sink_r)-1
                    coref_set.append(((src_word, src_i, src_pos, src_l, src_r), (sink_word, sink_i, sink_pos, sink_l, sink_r)))

    return results


class StanfordCoreNLP(object):
    """
    Command-line interaction with Stanford's CoreNLP java utilities.
    Can be run as a JSON-RPC server or imported as a module.
    """
    def __init__(self, corenlp_path="stanford-corenlp-full-2013-04-04/", memory="3g"):
        """
        Checks the location of the jar files.
        Spawns the server as a process.
        """

        # TODO: Can edit jar constants
        # jars = ["stanford-corenlp-1.3.5.jar",
        #         "stanford-corenlp-1.3.5-models.jar",
        #         "joda-time.jar",
        #         "xom.jar"]
        jars = ["stanford-corenlp-1.3.5.jar",
                "stanford-corenlp-1.3.5-models.jar",
                "xom.jar",
                "joda-time.jar",
                "jollyday.jar"]

        java_path = "java"
        classname = "edu.stanford.nlp.pipeline.StanfordCoreNLP"
        # include the properties file, so you can change defaults
        # but any changes in output format will break parse_parser_results()
        property_name = "default.properties"
        current_dir_pr = os.path.dirname(os.path.abspath( __file__ )) +"/"+ property_name
        if os.path.exists(property_name):
            props = "-props %s" % (property_name)
        elif os.path.exists(current_dir_pr):
            props = "-props %s" % (current_dir_pr)
        else:
            raise Exception("Error! Cannot locate: default.properties")

        # add and check classpaths
        jars = [corenlp_path +"/"+ jar for jar in jars]
        for jar in jars:
            if not os.path.exists(jar):
                raise Exception("Error! Cannot locate: %s" % jar)

        # add memory limit on JVM
        if memory:
            limit = "-Xmx%s" % memory
        else:
            limit = ""

        # spawn the server
        start_corenlp = "%s %s -cp %s %s %s" % (java_path, limit, ':'.join(jars), classname, props)
        if VERBOSE: print "===========================================\n", start_corenlp
        self.corenlp = pexpect.spawn(start_corenlp)

        # show progress bar while loading the models
        if VERBOSE:
            widgets = ['Loading Models: ', Fraction()]
            pbar = ProgressBar(widgets=widgets, maxval=5, force_update=True).start()
        self.corenlp.expect("done.", timeout=20) # Load pos tagger model (~5sec)
        if VERBOSE: pbar.update(1)
        self.corenlp.expect("done.", timeout=200) # Load NER-all classifier (~33sec)
        if VERBOSE: pbar.update(2)
        self.corenlp.expect("done.", timeout=600) # Load NER-muc classifier (~60sec)
        if VERBOSE: pbar.update(3)
        self.corenlp.expect("done.", timeout=600) # Load CoNLL classifier (~50sec)
        if VERBOSE: pbar.update(4)
        self.corenlp.expect("done.", timeout=200) # Loading PCFG (~3sec)
        if VERBOSE: pbar.update(5)
        self.corenlp.expect("Entering interactive shell.")
        if VERBOSE: pbar.finish()

        # interactive shell
        self.corenlp.expect("\nNLP> ", timeout=3)

    def close(self, force=True):
        self.corenlp.terminate(force)

    def isalive(self):
        return self.corenlp.isalive()

    def __del__(self):
        # If our child process is still around, kill it
        if self.isalive():
            self.close()

    def _parse(self, text):
        """
        This is the core interaction with the parser.

        It returns a Python data-structure, while the parse()
        function returns a JSON object
        """

        # CoreNLP interactive shell cannot recognize newline
        if '\n' in text or '\r' in text:
            to_send = re.sub("[\r\n]", " ", text).strip()
        else:
            to_send = text

        # clean up anything leftover
        def clean_up():
            while True:
                try:
                    self.corenlp.read_nonblocking (8192, 0.1)
                except pexpect.TIMEOUT:
                    print 'Well this is what happened: it hung up in the clean up!'
                    break
        clean_up()
        bytes_written = self.corenlp.sendline(to_send)
        print bc.HEADER, "bytes written", bytes_written, bc.ENDC

        # How much time should we give the parser to parse it?
        # the idea here is that you increase the timeout as a
        # function of the text's length.
        # max_expected_time = max(5.0, 3 + len(to_send) / 5.0)
        max_expected_time = max(300.0, len(to_send) / 3.0)*9000000000

        # repeated_input = self.corenlp.except("\n")  # confirm it
        t = self.corenlp.expect(["\nNLP> ", pexpect.TIMEOUT, pexpect.EOF],
                                timeout=max_expected_time)
        incoming = self.corenlp.before
        if t == 1:
            # TIMEOUT, clean up anything when raise pexpect.TIMEOUT error
            clean_up()
            print >>sys.stderr, {'error': "timed out after %f seconds" % max_expected_time,
                                 'input': to_send,
                                 'output': incoming}
            raise TimeoutError("Timed out after %d seconds" % max_expected_time)
        elif t == 2:
            # EOF, probably crash CoreNLP process
            print >>sys.stderr, {'error': "CoreNLP terminates abnormally while parsing",
                                 'input': to_send,
                                 'output': incoming}
            self.corenlp.close()
            raise ProcessError("CoreNLP process terminates abnormally while parsing")

        if VERBOSE: print "%s\n%s" % ('='*40, incoming)
        try:
            results = parse_parser_results(incoming)
        except Exception, e:
            if VERBOSE: print traceback.format_exc()
            raise e

        return results

    def raw_parse(self, text):
        """
        This function takes a text string, sends it to the Stanford parser,
        reads in the result, parses the results and returns a list
        with one dictionary entry for each parsed sentence.
        """
        return self._parse(text)

    def parse(self, text=''):
        """
        This function takes a text string, sends it to the Stanford parser,
        reads in the result, parses the results and returns a list
        with one dictionary entry for each parsed sentence, in JSON format.
        """
        if text:
            return json.dumps(self._parse(text))
        else:
            clean_raw_text()
            return str(parse_xml_output())


if __name__ == '__main__':
    """
    The code below starts an JSONRPC server
    """
    VERBOSE = True
    parser = optparse.OptionParser(usage="%prog [OPTIONS]")
    parser.add_option('-p', '--port', default='8080',
                      help='Port to serve on (default 8080)')
    parser.add_option('-H', '--host', default='127.0.0.1',
                      help='Host to serve on (default localhost; 0.0.0.0 to make public)')
    parser.add_option('-S', '--corenlp', default="stanford-corenlp-full-2013-04-04",
                      help='Stanford CoreNLP tool directory (default stanford-corenlp-full-2013-04-04/)')
    options, args = parser.parse_args()
    # server = jsonrpc.Server(jsonrpc.JsonRpc20(),
    #                         jsonrpc.TransportTcpIp(addr=(options.host, int(options.port))))
    try:
        server = SimpleJSONRPCServer((options.host, int(options.port)))

        nlp = StanfordCoreNLP(options.corenlp)
        server.register_function(nlp.parse)

        print 'Serving on http://%s:%s' % (options.host, options.port)
        # server.serve()
        server.serve_forever()
    except KeyboardInterrupt:
        print >>sys.stderr, "Bye."
        exit()
