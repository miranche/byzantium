#!/usr/bin/env python

#
#  makeindex.py  -- generate the index for THoB podcast, scraping the podcast WordPress site
#
#    Usage: makeindex.py <index file> [<num records>]
#
#  <index file>  - can be an empty template, or a partly generated index file
#                  see episode-index-template.html for template format
#  <num records> - (optional) only process a specified number of records and stop
#                  useful for testing and for minimizing web traffic.
#                  by default, the entire site will be scraped.
#  

import sys
import os.path
import re
from enum import Enum, auto
from pyquery import PyQuery as pq
from datetime import datetime


###  Three types of publication: announcement, regular podcast episode, special episode
class PubType(Enum):
    news = auto()
    podcast = auto()
    special = auto()


###  Understands a THoB podcast blog post and renders it into the index
class Publication:

    ###  Read webpage
    ###
    ###    url: the byzantium podcast blog post currently being scraped
    def __init__(self, url):
        self.url = url
        self.type = PubType.news # podcast, special, news
        self.next = None      # newer publication

        self.urltitle = ''    # full page title
        self.title = ''       # main heading, pared down if needed
        self.episode = ''     # numeric code, for podcast or special episodes
        self.series = None    # for special episodes
        self.period = ''      # when specified

        # read the web page
        print("Reading %s ..." % url, file=sys.stderr);
        self.D = pq(url=url);

        # find the next episode, if any
        self.next = self.D('div.nav-next > a').attr('href')

        # get podcast post title
        self.urltitle = urltitle = self.D('h1.entry-title').text().\
          replace('&nbsp;',' ').replace(' ',' ').replace('&#8211;','–').replace('￼','');
        #print(urltitle, file=sys.stderr)

        # determine type of publication from post title: look for string "Episode N – "
        #   regular episodes start with the string, special episodes contain it later in the title
        title = urltitle # will possibly be shortened
        epmatch = re.search('Episode [0-9]+[a-z]? – ', urltitle)
        if epmatch:
            # regular podcast episode: extract episode number and title from pub title
            if epmatch.start() == 0:
                self.type = PubType.podcast
                podmatch = re.search('^Episode ([0-9]+[a-z]?) – (.*)$', urltitle)
                self.episode = podmatch.group(1)
                title = podmatch.group(2)

            # special episode
            else:
                self.type = PubType.special
                epmatch = re.search('^([A-Za-z ]+)[.]? Episode ([0-9]+[a-z]?) – (.*)$', urltitle)
                title = epmatch.group(3)

                # determine series by series name
                sername = epmatch.group(1)

                # byzantine stories: further look for episode part number, if any
                if sername == 'Byzantine Stories':
                    self.series = 'stories';
                    eppath = [ epmatch.group(2) ]
                    ptmatch = re.search(' Part ([0-9]+) – ', title)
                    if ptmatch:
                        eppath.append(ptmatch.group(1))
                    self.episode = '.'.join(eppath)

                # backer rewards: easy
                elif sername == 'Backer Rewards':
                    self.series = 'rewards';
                    self.episode = epmatch.group(2)

                # unknown special ep series (shouldn't happen): treat as announcement
                else:
                    print('Not a special episode "%s"' % sername, file=sys.stderr)
                    self.type = PubType.news
                    title = urltitle
                    self.episode = ''

        # no "Episode N – ": announcement
        else : 
            # a few news headlines can be condensed
            for shortit in [
                'Cage Match Podcast',
                'An interview with Robert Horvat',
                'An interview with Barry Strauss',
                ]:
                if urltitle.find(shortit) == 0:
                    title = shortit
                    break

        self.title = title

        # any of the three types may have a time period associated with it (years from-to, century etc.)
        self.period = self.getPeriod();

        #print(self.title, self.next, self.type, self.episode, self.period, file=sys.stderr)


    ###  Determine period, from-to in years
    ###
    ###     return: period string, '' by default
    def getPeriod(self):
        # one episode has period in the title, hard-code it
        if self.title == 'Cyprus: 565 – 965 AD':
            return '565-965'

        # others have a line in content text that specifies the period, usually in from[-to] format
        period = ''
        periodEls = self.D('#content p:contains("Period:")')
        #print(periodEls, len(periodEls), file=sys.stderr)

        # find text "Period: X" and parse it
        for pi in range(0, len(periodEls)):
            currEl = periodEls[pi]
            # the text could be lower down, for example in a span
            while currEl.getchildren():
                currEl = currEl.getchildren()[0]
            pertext = currEl.text.replace(' ',' ')
            #print(pertext, file=sys.stderr)

            # parse period string: either from-to or ... something else (only once in practice)
            permatch = re.search('^Period: (.*)$', pertext)
            if permatch:
                #print(permatch, file=sys.stderr)
                # look for from-to in years
                yrsmatch = re.search('^Period: ([1-9][0-9][0-9-]+)', pertext)
                if yrsmatch:
                    period = yrsmatch.group(1)
                    fromto = period.split('-')
                    # in from-to, "to" could be smaller, if in the same decade or century. expand fully
                    if len(fromto) > 1:
                        fr = int(fromto[0])
                        to = int(fromto[1])
                        if to < 10:
                            to = fr//10*10 + to
                        elif to < 100:
                            to = fr//100*100 + to
                        period = '%d-%d' % (fr, to)

                # no years - free text, such as century (only once as of ep. 332)
                else:
                    period = permatch.group(1).replace(' ',' ').replace('century','c.')

        # return any period string found, or default
        return period


    ###  Add the current page to the index
    ###
    ###    iDom: index html traversal object, modified in the method
    ###    return: nothing
    def addToIndex(self, iDom):

        # URL on the skip list: don't change visible html, note that we skipped it
        skipme = iDom('span.skip[data-url="%s"]' % self.url)
        if skipme:
            print('  Skipping: "%s"' % self.title, file=sys.stderr)
            # remove the URL from the skip list, clean up some blanks
            skipme.remove();
            clnhtml = re.sub('\n *(\n *)+', '\n  ', iDom('#makeindex-data').html())
            iDom('#makeindex-data').html(clnhtml)
            # nothing added

        else:
            # not skipped: add row(s) to index tables
            # formats for an anchor and the table row
            aFormat = '<a target="_blank" href="%s" title="%s">%s</a>'
            trFormat = '<tr><td>{episode:s}</td><td>{title:s}</td><td>{period:s}</td></tr>\n'
            cells = {
                'episode' : '',
                'title'   : '',
                'period'  : self.period
                }
                # generate row cells: if episode number code exists, link from it. otherwise, link from title
            if self.episode:
                cells['episode'] = aFormat % (self.url, self.urltitle, self.episode)
                cells['title'] = self.title
            else:
                cells['title'] = aFormat % (self.url, self.urltitle, self.title)

            # format the new table row
            tr = trFormat.format(**cells)

            # special episode: only add to its own panel
            if self.type == PubType.special:
                print('  %s %s: "%s"' % (self.series.title(), self.episode, self.title), file=sys.stderr)

                # byzantine stories 1.2-1.4 are on one URL but need three lines in the index
                # unique case, hard coded
                if self.title == 'John Chrysostom. Parts 2, 3 and 4.':
                    for cells in [{
                        'epcode' : '1.2',
                        'title'   : 'John Chrysostom. Part 2 – Building Orthodoxy',
                        'period'  : '349-397'
                    },{
                        'epcode' : '1.3',
                        'title'   : 'John Chrysostom. Part 3 – The Snake Pit',
                        'period'  : '397-400'
                    },{
                        'epcode' : '1.4',
                        'title'   : 'John Chrysostom. Part 4 – A Byzantine Story',
                        'period'  : '400-407'
                    }]:
                        cells['episode'] = aFormat % (self.url, self.urltitle, cells['epcode'])
                        tr = trFormat.format(**cells)
                        iDom('div.panel.special[data-series="%s"] table' % self.series).append(tr);

                # add table row for special episode
                else:
                    iDom('div.panel.special[data-series="%s"] table' % self.series).append(tr);

            # news or podcast: add both to the complete list and to a century panel
            else:
                # by default, use the most recent century panel
                century = iDom('#state').attr('data-curr-century')

                # podcast: potentially advance to the new century
                if self.type == PubType.podcast : 
                    print('  Podcast %s: "%s"' % (self.episode, self.title), file=sys.stderr)

                    # if episode code is numeric, compare with starting episode for next century
                    if re.search('^[0-9]+$', self.episode):
                        epnum = int(self.episode)

                        # look for the next century panel
                        nextcpanel = iDom('div.panel.century[data-century="%s"] + div.panel.century' % century)
                        if nextcpanel:
                            nextcepnum = int(nextcpanel.attr('data-first-ep'))
                            # compare current episode number with the start of the next century
                            if epnum >= nextcepnum:
                                # advance to the new century, note it in the index
                                century = nextcpanel.attr('data-century')
                                iDom('#state').attr('data-curr-century', century)

                # announcement: use the default (latest) century panel
                elif self.type == PubType.news :
                    print('  Announcement: "%s"' % self.title, file=sys.stderr)

                # add table row to the century panel and to the list of all episodes
                iDom('div.panel.century[data-century="%s"] table' % century).append(tr);
                iDom('div.panel.all table').append(tr);

        # the date as of which the index is current. the pub date if there is a next pub, today if not
        if self.next:
            curdate = self.D('meta[property="article:published_time"]').attr('content')[:10]
        else:
            curdate = datetime.today().strftime('%Y-%m-%d')
        iDom('#state').attr('data-curr-index-date', curdate)

        # record that the index now reflects the current url
        iDom('#state').attr('data-curr-pub', self.url)
        return;


############################  MAIN  ############################
argv = sys.argv

# process command line arguments
if len(argv) < 2:
    sys.exit('Usage: %s <index file> [<num records>]' % argv[0])

# input file name, either index template or a potentially incomplete index
indexFname = argv[1]
if not os.path.isfile(indexFname):
    sys.exit('File "%s" not found!' % indexFname)

# max number of pages to scrape, if any
try :
    maxPubs = int(argv[2]) if len(argv) > 2 else None
except ValueError:
    sys.exit('Usage: %s <index file> [<num records>]' % argv[0])

# read the input file, determine the first step
iDom = pq( filename = indexFname )
newUrl = None

# index reflects a current (latest) pub: check if there's a newer one
currUrl = iDom('#state').attr('data-curr-pub')
if currUrl :
    currPub = Publication(currUrl)
    # if there's a newer publication, proceed
    newUrl = currPub.next

# empty index: start from the beginning
else:
    newUrl = iDom('#state').attr('data-first-pub')

# while there's a next page to read, proceed
npubs = 0
while newUrl:
    # add next publication to the index
    newPub = Publication( newUrl )
    newPub.addToIndex( iDom )
    npubs += 1

    newUrl = newPub.next if (maxPubs is None or npubs <= maxPubs) else None
    #newUrl = newPub.next

# done: write the new index html to standard output
print("<!doctype html>\n%s" % iDom.outerHtml())
print("Done!", file=sys.stderr)
