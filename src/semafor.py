import logging as log
import subprocess
from os.path import join, dirname, isfile
from os import remove
import tempfile
import ConfigParser
import sys
import simplejson as json
from nltk.tokenize.punkt import PunktSentenceTokenizer
import socket

config = ConfigParser.ConfigParser()
config.read(join(dirname(__file__),'../config/semanticparsing.conf'))

def semafor_remote(text):
    # tokenize and parse with MALT
    malt = join(dirname(__file__),'../{0}/bin/runMalt.sh'.format(config.get('semafor', 'base_dir')))
    input_file = join(dirname(__file__),'../{0}/bin/in.txt'.format(config.get('semafor', 'base_dir')))
    with open(input_file, 'w') as f:
        tokenizer = PunktSentenceTokenizer()
        sentences = tokenizer.tokenize(text)
        f.write('\n'.join(sentences))
    output_dir = join(dirname(__file__),'../{0}/bin/'.format(config.get('semafor', 'base_dir')))
    process = subprocess.Popen([malt, input_file, output_dir],
                           shell=False)
    out, err = process.communicate(text)
    if err:
        log.debug(err)

    # read the output of MALT and pass it to the Semafor server
    parsed_file = join(dirname(__file__),'../{0}/bin/conll'.format(config.get('semafor', 'base_dir')))
    with open(parsed_file, 'r') as f:
        parsed = f.read()
    print parsed

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((config.get('semafor', 'server'), config.get('semafor', 'port')))
    s.sendall(parsed)
    s.shutdown(socket.SHUT_WR)
    while 1:
        data = s.recv(1024)
        if data == "":
            break
        print "Received:", repr(data)
    print "Connection closed."
    s.close()
    return None, None

def semafor_local(text):
    semafor = join(dirname(__file__),'../{0}/bin/runSemafor.sh'.format(config.get('semafor', 'base_dir')))
    input_file = join(dirname(__file__),'../{0}/bin/in.txt'.format(config.get('semafor', 'base_dir')))
    with open(input_file, 'w') as f:
        tokenizer = PunktSentenceTokenizer()
        sentences = tokenizer.tokenize(text)
        f.write('\n'.join(sentences))
    output_file = join(dirname(__file__),'../{0}/bin/out.txt'.format(config.get('semafor', 'base_dir')))
    if isfile(output_file):
        remove(output_file)
    process = subprocess.Popen([semafor, input_file, output_file, '1'],
                           shell=False)
    out, err = process.communicate(text)
    if err:
        log.debug(err)

    sentences_semantics = []
    with open(output_file) as f:
        # semafor outputs an invalid JSON, with one dictionary per line
        for line in f:
            sentence_dict = json.loads(line.rstrip())
            sentences_semantics.append(sentence_dict)
    return sentences, sentences_semantics

def parse(text):
    if config.get('semafor', 'mode') == 'local':
        sentences, sentences_semantics = semafor_local(text)
    elif config.get('semafor', 'mode') == 'remote':
        sentences, sentences_semantics = semafor_remote(text)

    # process the output from Semafor
    predicates = dict()
    relations = []
    token_offset = 0
    frames = dict()
    for sentence in sentences_semantics:
        for frame in sentence['frames']:
            # predicate from frame type
            for span in frame['target']['spans']:
                variable_frame = 'x{0}-{1}'.format(span['start']+token_offset, span['end']+token_offset)
                predicate_frame = {'token_end': span['end']-1+token_offset,
                             'token_start': span['start']+token_offset,
                             'symbol': span['text'],
                             'sense': '0',
                             'variable': variable_frame,
                             'type': 'v'}
                if not variable_frame in predicates:
                    predicates[variable_frame] = predicate_frame
                frames[variable_frame] = frame['target']['name']
            # predicates from frame elements
            for frame_element in frame['annotationSets'][0]['frameElements']:
                for span in frame_element['spans']:
                    variable = 'x{0}-{1}'.format(span['start']+token_offset, span['end']+token_offset)
                    predicate = {'token_end': span['end']-1+token_offset,
                                 'token_start': span['start']+token_offset,
                                 'symbol': span['text'],
                                 'sense': '0',
                                 'variable': variable,
                                 'type': 'n'}
                    if not variable in predicates:
                        predicates[variable] = predicate

                relation = {'arg1': variable_frame,
                            'arg2': variable,
                            'symbol': frame_element['name']}
                relations.append(relation)
        token_offset += (len(sentence['tokens'])-1)

    semantics = {'predicates': predicates.values(),
     'namedentities': [],
     'identities': [],
     'relations': relations,
     'frames': frames}

    return semantics, '\n'.join(sentences)
