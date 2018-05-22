#!/usr/bin/python

# (C) Dan White <dan@whiteaudio.com>

# Imports for Python 2 compatibility
from __future__ import print_function, with_statement

import argparse
import os
import re
import sys

from decimal import Decimal


# TODO:
# - allow comments in input file
# - passthru (header) comments
# - system info + datetime in output header


def info(s):
    if args.verbose:
        print('INFO:', s)

def error(s):
    print('ERROR:', s)
    sys.exit(1)


def warn(s):
    print('WARNING:', s)


def expand_bus_notation(names):
    nodes = []
    for n in names:
        # parse into:  name[left:right]suffix
        name, lbrack, tail = n.partition('[')
        left, colon, end = tail.partition(':')
        right, rbrack, suffix = end.partition(']')

        # only expand a complete bus notation
        if lbrack and colon and rbrack:
            try:
                start = int(left)
                stop = int(right)
            except ValueError:
                warn('Incomplete or non-integer range, passing thru: %s' % n)
                nodes.append(n)
            else:
                inc = 1 if (stop > start) else -1

                for i in range(start, (stop + inc), inc):
                    s = '%s[%i]%s' % (name, i, suffix)
                    nodes.append(s)
        else:  # pass-thru all others as-is
            nodes.append(n)

    return nodes



def generate_waveform(d):
    t = Decimal('0.0')

    #first bit interval starts at t=0, start from this value
    lastbit = d[0]
    bitv = Decimal(lastbit) * (bithigh - bitlow) + bitlow
    s = '+ 0 %s' % str(bitv)
    output(s)

    trf = risefall
    tb = bittime - risefall
    t += trf + tb
    for bit in d[1:]:
        # only output a point when there is a change
        if bit != lastbit:
            ti = t + trf
            tf = ti + tb
            lastbitv = Decimal(lastbit) * (bithigh - bitlow) + bitlow
            bitv = Decimal(bit) * (bithigh - bitlow) + bitlow
            output('+ %s %s' % (str(t), str(lastbitv)))
            output('+ %s %s' % (str(ti), str(bitv)))
            #output('+ %s %s' % (str(tf), str(bitv)))

        t += trf + tb
        lastbit = bit



RE_UNIT = re.compile(r'^([0-9e\+\-\.]+)(t|g|meg|x|k|mil|m|u|n|p|f)?')
def unit(s):
    """Takes a string and returns the equivalent float.
    '3.0u' -> 3.0e-6"""
    mult = {'t'  :Decimal('1.0e12'),
            'g'  :Decimal('1.0e9'),
            'meg':Decimal('1.0e6'),
            'x'  :Decimal('1.0e6'),
            'k'  :Decimal('1.0e3'),
            'mil':Decimal('25.4e-6'),
            'm'  :Decimal('1.0e-3'),
            'u'  :Decimal('1.0e-6'),
            'n'  :Decimal('1.0e-9'),
            'p'  :Decimal('1.0e-12'),
            'f'  :Decimal('1.0e-15')}

    m = RE_UNIT.search(s.lower())
    try:
        if m.group(2):
            return Decimal(Decimal(m.group(1)))*mult[m.group(2)]
        else:
            return Decimal(m.group(1))
    except:
        error("Bad unit: %s" % s)



def read_params(f):
    """Read name=value lines from the input file.
    Validate agains required parameters.
    Return dict of the pairs.
    """
    requiredParams = ('risefall', 'bittime', 'bitlow', 'bithigh')
    params = {'clockdelay':None, 'clockrisefall':None}

    #get parameters
    fposition = f.tell()
    line = f.readline()
    while '=' in line:
        name, value = line.split('=')
        name = name.strip()
        value = value.strip()
        params[name] = value
        fposition = f.tell()
        line = f.readline()

    #fixup file position back to start of next line
    f.seek(fposition)

    #check
    for p in requiredParams:
        if p not in params:
            error("%s is not specified, aborting." % p)

    info('Parameters:')
    for p,v in params.items():
        info('  %s = %s' % (p, v))

    return params



def parse_words(words):
    """Accepts a list of strings.
    Returns a list of '1' or '0' strings.
    """
    bits = []
    for w in words:
        if w.startswith('0x'):
            n = 4 * (len(w) - 2)
            w = bin(int(w[2:], 16))[2:].zfill(n)
        elif w.startswith('0b'):
            w = w[2:]

        bits.extend([b for b in w])
    return bits



def read_vectors(f, nodes):
    """Read the data vectors from the rest of the file.
    """
    signals = {n:[] for n in nodes}
    n_signals = len(nodes)

    for line in f:
        line = line.strip()
        words = line.split()
        bits = parse_words(words)

        if len(bits) != n_signals:
            error("Must have same # characters as column labels: %s" % line)

        for i in range(n_signals):
            signals[nodes[i]].append(bits[i])

    return signals



def read_busfile(bus):
    #read in the bus definition file
    with open(bus) as f:
        params = read_params(f)

        #next line is column labels
        line = f.readline()
        names = [c.strip() for c in line.strip().split()]
        nodes = expand_bus_notation(names)
        params['nodes'] = nodes
        info("Columns: %s" % nodes)

        #read in signal vectors
        signals = read_vectors(f, nodes)
        params['signals'] = signals

    return params






if __name__ == '__main__':
    # python 2 vs 3 compatibility
    try:
        dict.iteritems
    except AttributeError:
        #this is python3
        def iteritems(d):
            return iter(d.items())
    else:
        def iteritems(d):
            return d.iteritems()

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description = "Parse a .bus file into a SPICE PWL file")
    parser.add_argument(
        'busfile',
        help = "File with specifying input and clock parameters")
    parser.add_argument(
        '-v', '--verbose',
        help = "Increase output verbosity",
        action = 'store_true')
    args = parser.parse_args()

    # Basic error checking on input file
    if not args.busfile.endswith('.bus'):
        print("Error: Input file must have '.bus' extension")
        sys.exit(1)

    # Read and parse input file
    params = read_busfile(args.busfile)

    #get the numbers
    risefall = unit(params['risefall'])
    bittime = unit(params['bittime'])
    bitlow = unit(params['bitlow'])
    bithigh = unit(params['bithigh'])

    #generate output file
    pwl_name = args.busfile.replace('.bus', '.pwl')
    with open(pwl_name, 'w') as fpwl:
        output = lambda s: print(s, file=fpwl)
        #output clock definition if specified
        if params['clockdelay']:
            #calculate clock high time
            if params['clockrisefall']:
                clockrisefall = unit(params['clockrisefall'])
            else:
                clockrisefall = risefall

            clockhigh = Decimal('0.5') * (bittime - clockrisefall)
            clockperiod = bittime

            params['clockrisefall'] = str(clockrisefall)
            params['clockhigh'] = str(clockhigh)
            params['clockperiod'] = str(clockperiod)

            clk = 'Vclock clock 0 pulse(%(bitlow)s %(bithigh)s %(clockdelay)s %(clockrisefall)s %(clockrisefall)s %(clockhigh)s %(clockperiod)s)' % params
            info(clk)

            output(clk)
            output('')


        #output each input source
        for name, signal in iteritems(params['signals']):
            #first line
            s = 'V%s %s 0 PWL' % (name, name)
            info(s)
            output(s)

            generate_waveform(signal)
            output('')

        info('Output file: ' + pwl_name)
