# vim: set fileencoding=utf-8

from __future__ import print_function, division

"""
This module was written to read a MacJournal file and provide tools to interact
with it.
"""
import os
import xml.dom.minidom
import gzip
import collections
import datetime
# import dateutil.parser      # Useful so I don't have to create a parser


class mjdoc(object):
    """
    mjdoc is a class that contains all the information about a MacJournal
    document.
    """

    def __init__(self, path, verbose=False, **kwargs):
        super(mjdoc, self).__init__()
        self.verbose = verbose

        if not os.path.isdir(path):
            raise OSError("The MacJournal document {} doesn't exist".
                          format(path))

        # Set up some paths
        self.path = os.path.normpath(path)
        self.abs_path = os.path.abspath(path)
        self.Content = os.path.join(self.path, "Content")

        # Path relative to MacJournal directory
        self.rel_path = ''

        # Get the xml index
        self.indexPath = os.path.join(self.path, "index.mjml.gz")
        print(self.indexPath)

        gz = gzip.GzipFile(self.indexPath, 'r')
        self.index = xml.dom.minidom.parse(gz)
        gz.close()

        self.macjournalml = self.index.getElementsByTagName('macjournalml')[0]
        self.bookcase = self.macjournalml.getElementsByTagName('bookcase')[0]

        # Get all the journals
        self.Journals = collections.OrderedDict()
        children = self.bookcase.getElementsByTagName('children')[0]
        for child in children.childNodes:
            J = _childFactory(child, Parent=self, verbose=self.verbose,
                              **kwargs)
            self.Journals[J.name] = J

    def __repr__(self): return self.path

    def FullName(self): return None

    def RelativePath(self): return self.rel_path

    def AbsolutePath(self): return self.abs_path

    def RealPath(self): return self.abs_path

    def keywords(self): return []

    def hierarchy(self, limit='journals'):
        """
        hierarchy will print the hierarchy of the MacJournal journals and
        entries.

        limit: To what limit should the hierarchy be printed.  The default value
            is 'journals' which means that only journals are printed to the
            screen.  If limit == 'entries' then the entries will also be
            printed.
        """
        for journal in self.Journals.values():
            journal.hierarchy(limit=limit, level=0)

    def MakeLaTeX(self, LT, texdir, level=0):
        """
        MakeLateX will create the directory structure for the LaTeX files and
        will create LaTeX files for each entry.

        LT: LaTeX.LaTeXTemplate object
        texdir: Where should the files/folders be created.
        level: What level of LaTeX (i.e., \section, \subsection, etc.) is
            current
        """
        self._texdir = texdir

        for journal in self.Journals.values():
            journal.MakeLaTeX(LT, self._texdir, level=level)

    def MakeXMLFile(self, filename):
        """
        MakeXMLFile will write the internal XML file to the provided filename.
        """
        xmlfile = open(filename, 'w')
        xmlfile.write(self.macjournalml.toprettyxml(indent='    ',
                                                    encoding='utf-8'))
        xmlfile.close()


def _childFactory(xml, Parent, verbose=False):
    """
    _childFactory will figure out what kind of child is passed and return
    the appropriate object.

    xml: xml element object
    Parent: What is the parent object
    verbose: For debugging purposes
    """
    nodeName = xml.nodeName
    if nodeName == "smart_journal":
        if verbose:
            print("Smart Journal\n\tid={}".format(
                xml.attributes.getNamedItem('id').value))
        return smart_journal(xml, Parent=Parent, verbose=verbose)
    elif nodeName == "journal":
        if verbose:
            print("Journal\n\tid={}".format(
                xml.attributes.getNamedItem('id').value))

        # Check if it is the Trash journal
        name = xml.getElementsByTagName('name')[0].firstChild.wholeText
        if name == 'Trash':
            return TrashJournal(xml, Parent=Parent, verbose=verbose)
        else:
            return journal(xml, Parent=Parent, verbose=verbose)
    elif nodeName == "entry":
        return entry(xml, Parent=Parent, verbose=verbose)
    else:
        raise NotImplementedError(
            "I don't know how to deal with child type: {}".format(nodeName))
        return None


class _MJElement(object):
    """
    _MJElement is a base class for all the MacJournal elements.  The elements
    are:
        journal
            smart_journal
        entry
    """
    def __init__(self, xml, Parent, verbose=False, **kwargs):
        super(_MJElement, self).__init__()
        self.xml = xml
        self.Parent = Parent
        self.verbose = verbose
        self._realpath = ''

        self._childNodes = self.xml.childNodes

        # Get the dates of the MacJournal element
        for attr in ['date', 'created', 'modified']:
            dateNode = [node for node in self._childNodes
                        if node.nodeName == attr][0]
            setattr(self, attr,
                    datetime.datetime.strptime(dateNode.firstChild.nodeValue))

    def FullName(self):
        name = self.Parent.FullName()
        if name:
            return "{}/{}".format(name, self.name)
        else:
            return self.name

    def RelativePath(self):
        """
        RelativePath is the relative path of the journa/entry if the
        journals/entries were arranged hierarchically.  It is all relative to
        the top of the MacJournal hierarchy.
        """
        return os.path.join(self.Parent.RelativePath(), self.name)

    def AbsolutePath(self):
        """
        RelativePath is the absolute path of the journa/entry if the
        journals/entries were arranged hierarchically.
        """
        return os.path.join(self.Parent.AbsolutePath(), self.name)

    def RealPath(self):
        """
        RealPath returns the actual path to the journal/entry file
        """
        if self._realpath:
            return os.path.join(self.Parent.RealPath(), self._realpath)
        else:
            return self.Parent.RealPath()

    def keywords(self):
        """
        keywords will create a list of keywords. It includes all the keywords
        from the Parent.
        """
        # Don't recalculate keywords if they are already known
        if hasattr(self, '_keywords'):
            return self._keywords

        # Get parent keywords
#       self._keywords = self.Parent.keywords()
        self._keywords = []

        if hasattr(self, "_keywordsElements"):
            keywordElements = (
                self._keywordsElements.getElementsByTagName('keyword'))

            # Get keyword child which is just the text element
            if keywordElements:
                for keyword in keywordElements:
                    word = keyword.firstChild.wholeText
                    if word not in self._keywords:
                        self._keywords.append(keyword.firstChild.wholeText)

        return self._keywords

    def MakeLaTeX(self, texdir):
        raise NotImplementedError("MakeLaTeX")


class journal(_MJElement):
    """
    journal is the class that handles all aspects of a journal
    """
    def __init__(self, xml, Parent, verbose=False, **kwargs):
        super(journal, self).__init__(xml, Parent, verbose, **kwargs)

        nameElement = self.xml.getElementsByTagName('name')[0]
        self.name = nameElement.firstChild.wholeText
        if self.verbose:
            print("\tname: {}".format(self.FullName()))

        # There is no real path for a journal; i.e., it doesn't exist as a
        # directory
        self._realpath = None

        self.Entries = []
        self.Journals = collections.OrderedDict()

        # Parse the contents of the journal
        self._parseContents(**kwargs)

    def _parseContents(self, **kwargs):
        """
        _parseContents will parse the contents of the journal. This is created
        so that it is easy to subclass this class.
        """
        # Figure out the contents of the journal
        self.children = []
        children = self.xml.getElementsByTagName('children')
        if children:
            for childNode in children[0].childNodes:
                child = _childFactory(childNode, Parent=self,
                                      verbose=self.verbose, **kwargs)
                self.children.append(child)

                if isinstance(child, journal):
                    self.Journals[child.name] = child
                elif isinstance(child, entry):
                    self.Entries.append(child)
                else:
                    raise NotImplementedError(
                        "I don't know where to store child type: {}".format(
                            child))

            # Prepare to find keywords
            prototype = self.xml.getElementsByTagName('prototype')
            if prototype:
                proto = prototype[0]

                # Look for 'keywords' element(s)
                keywordsElements = proto.getElementsByTagName('keywords')
                if keywordsElements:
                    self._keywordsElements = keywordsElements[0]

    def __repr__(self): return "Journal: {}".format(self.FullName())

    def hierarchy(self, limit='journals', level=0):
        """
        hierarchy will print the hierarchy of the MacJournal journals and
        entries.

        limit: To what limit should the hierarchy be printed.  The default value
            is 'journals' which means that only journals are printed to the
            screen.  If level == 'entries' then the entries will also be
            printed.
        level: The level of the hierarchy
        """
        if self.verbose:
            print(u"{}{}\t({})".format("  "*level,
                                       self.name, len(self.Entries)))

        if limit == 'journals':
            iterator = self.Journals.values()
        elif limit == 'entries':
            iterator = self.children

        # Write hierarchy for children
        for child in iterator:
            child.hierarchy(limit=limit, level=level+1)

    def MakeLaTeX(self, LT, texdir, level=0):
        """
        MakeLateX will create the directory structure for the LaTeX files and
        will create LaTeX files for each entry.

        LT: LaTeX.LaTeXTemplate object
        texdir: Where should the files/folders be created.
        level: What level of LaTeX (i.e., \section, \subsection, etc.) is
            current
        """
        self._texdir = os.path.join(texdir, self.name)
        print(self._texdir)
        if not os.path.isdir(self._texdir):
            os.mkdir(self._texdir)

        texLevel = LT.LaTeXLevels[level]
        LT.lines.append(u"\n\n\\{}{{{}}}".format(texLevel, self.name))
        self._includes = []
        # Iterate over all the journals and entries
        for child in self.children:
            self._includes = child.MakeLaTeX(LT, self._texdir, level=level+1)


class smart_journal(journal):
    """
    smart_journal is what you think it is.  Rather than being a real journal, it
    is a journal comprised of everything found for a particular search result.
    """
    def __repr__(self): return "SJournal: {}".format(self.name)

    def MakeLaTeX(self, texdir, level=0):
        """
        MakeLateX will create the directory structure for the LaTeX files and
        will create LaTeX files for each entry.

        texdir: Where should the files/folders be created.
        level: What level of LaTeX (i.e., \section, \subsection, etc.) is
            current
        """
        pass
#       self._texdir = texdir

#       for journal in self.Journals.values():
#           journal.MakeLaTeX(self._texdir, level=level)


class TrashJournal(journal):
    """
    TrashJournal is a special journal for the Trash journal.
    """
    def _parseContents(self, **kwargs):
        """
        _parseContents doesn't do anything at the moment for a Trash Journal
        """
        print(" _parseContents doesn't do anything at the moment for Trash")


class entry(_MJElement):
    """
    entry is simply a journal entry.
    """
    def __init__(self, xml, Parent, verbose=False, **kwargs):
        super(entry, self).__init__(xml, Parent, verbose, **kwargs)

        topicElement = self.xml.getElementsByTagName('topic')
        if topicElement:
            self.topic = self.name = topicElement[0].firstChild.wholeText
        else:
            self.topic = self.name = ""

        # Prepare to find keywords
        keywordsElements = self.xml.getElementsByTagName('keywords')
        if keywordsElements:
            self._keywordsElements = keywordsElements[0]

        self.content = \
            dict(self.xml.getElementsByTagName('content')[0].attributes.items())

        # Filename
        garbage, extension = os.path.splitext(self.content['type'])
        self.filename = self.content['id']+extension
        # Where is the actual file
        self._realpath = os.path.join('Content', self.filename)

    def __repr__(self): return self.topic

    def WordCount(self):
        """
        WordCount will return the number of words in the entry as defined by
        MacJournal.
        """
        return int(
            self.xml.getElementsByTagName('word_count')[0].firstChild.wholeText)

    def latitude(self):
        """
        latitude will return a floating point value of the latitude where the
        entry was created. If there is no data, this function will return None.
        """
        locElement = self.xml.getElementsByTagName('location')
        if locElement:
            latitude = float(locElement[0].getAttribute('latitude'))
            return latitude
        else:
            return None

    def longitude(self):
        """
        longitude will return a floating point value of the latitude where the
        entry was created. If there is no data, this function will return None.
        """
        locElement = self.xml.getElementsByTagName('location')
        if locElement:
            longitude = float(locElement[0].getAttribute('longitude'))
            return longitude
        else:
            return None

    def location(self):
        """
        location will return a tuple containing: (latitude, longitude) of the
        location the entry was created. If the location data is non-existent,
        then this function will return None.

        This simply makes calls to the latitude and longitude functions.
        """

        lat = self.latitude()
        lon = self.longitude()

        if lat is None:
            return None
        else:
            return (lat, lon)

    def timezone(self):
        """
        Return the timezone value.
        """
        return (
            self.xml.getElementsByTagName('time_zone')[0].firstChild.wholeText)

    def hierarchy(self, limit='journals', level=0):
        """
        hierarchy will print the hierarchy of the MacJournal journals and
        entries.

        limit: To what limit should the hierarchy be printed.  The default value
            is 'journals' which means that only journals are printed to the
            screen.  If level == 'entries' then the entries will also be
            printed.
        level: The level of the hierarchy
        """
        print(u"{}{}".format("  "*level, self.name))

    def MakeLaTeX(self, LT, texdir, level=0):
        """
        MakeLateX will create the directory structure for the LaTeX files and
        will create LaTeX files for each entry.

        LT: LaTeX.LaTeXTemplate object
        texdir: Where should the files/folders be created.
        level: What level of LaTeX (i.e., \section, \subsection, etc.) is
            current
        """
        self._texdir = texdir
        path = os.path.join(self._texdir, self.name)

        texLevel = LT.LaTeXLevels[level]
        LT.lines.append(u"\n\n\\{}*{{{}}}".format(texLevel, self.name))

        return path


if __name__ == "__main__":
    print("\nI'm interacting with MacJournal data.\n")

    import argparse

    parser = argparse.ArgumentParser(description="Extract Macjournal data")
    parser.add_argument('mjdoc', nargs='+', type=str,
                        help='MacJournal document location.')
    parser.add_argument('--xml', type=str, default=None,
                        help='Write XML file for human readability')

    args = parser.parse_args()

    mjDoc = mjdoc(args.mjdoc[0], verbose=True)

    if args.xml:
        mjDoc.MakeXMLFile(args.xml)
