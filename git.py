##
# pitweb - Web interface for git repository written in python
# ------------------------------------------------------------
# Copyright (c)2010 Daniel Fiser <danfis@danfis.cz>,
#           (c)2011 David Guerizec <david@guerizec.net>
#
#
#  This file is part of pitweb.
#
#  pitweb is free software; you can redistribute it and/or modify
#  it under the terms of the GNU Lesser General Public License as
#  published by the Free Software Foundation; either version 3 of
#  the License, or (at your option) any later version.
#
#  pitweb is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
##

import re
import datetime
from subprocess import Popen, PIPE, STDOUT
import stat

basic_patterns = {
    'id' : r'[0-9a-fA-F]{40}',
    'epoch' : r'[0-9]+',
    'tz'    : r'[\+-][0-9]+',
}

patterns = {
    'person'    : re.compile(r'[^ ]* (.*) ({epoch}) ({tz})$'.format(**basic_patterns)),
    'person2'   : re.compile(r'(.*) <(.*)>'),
	'diff-tree' : re.compile(r'^:([0-7]{6}) ([0-7]{6}) ([0-9a-fA-F]{40}) ([0-9a-fA-F]{40}) (.)([0-9]{0,3})\t(.*)$'),
	'diff-tree-patch' : re.compile(r'^diff --git'),
}


class GitComm(object):
    """ This class is 1:1 interface to git commands. Meaning of most
        parameters of most methods should be obvious after reading man pages
        of corresponding git commands.

        Each method returns whole output of corresponding git command
        without any modifications (no parsing is performed).

        Meaning of this class is as thin layer between git commands and
        python which is easier to use. All commands are run in other
        process using subprocess module and connected to currect process
        using pipe - subsequently, whole output is read and returned.

        The only argument of constructor is pathname to directory where git
        repository is located (see doc of git --git-dir).
    """

    def __init__(self, dir, gitbin = '/usr/bin/git'):
        self._dir = dir
        self._gitbin = gitbin

    def _gitPipe(self, args):
        comm = [self._gitbin, '--git-dir={0}'.format(self._dir)]
        comm.extend(args)

        pipe = Popen(comm, stdout = PIPE, stderr = STDOUT)
        return pipe

    def _git(self, args):
        pipe = self._gitPipe(args)
        out = pipe.stdout.read()
        pipe.stdout.close()

        return out

    def revList(self, obj = 'HEAD', parents = False, header = False,
                      max_count = -1, all = False):
        """ git-rev-list(1)
                Lists commit objects in reverse chronological order.
        """

        comm = ['rev-list']

        if parents:
            comm.append('--parents')
        if header:
            comm.append('--header')
        if max_count > 0:
            comm.append('--max-count={0}'.format(max_count))

        if not all and obj:
            comm.append(obj)
        if all:
            comm.append('--all')

        return self._git(comm)

    def forEachRef(self, format = None, sort = None, pattern = None):
        """ git-for-each-ref(1)
                Output information on each ref.
        """

        comm = ['for-each-ref']

        if format:
            comm.append('--format={0}'.format(format))
        if sort:
            comm.append('--sort={0}'.format(sort))

        if pattern:
            if type(pattern) == list:
                for p in pattern:
                    comm.append(p)
            else:
                comm.append(pattern)

        return self._git(comm)


    def catFile(self, obj = 'HEAD', type = 'commit', size = False,
                      pretty = False):
        """ git-cat-file(1)
                Provide content or type and size information for repository objects.
        """

        comm = ['cat-file']

        comm.append(type)

        #if type:
        #    comm.append('-t')
        if size:
            comm.append('-s')
        if pretty:
            comm.append('-p')

        comm.append(obj)
        return self._git(comm)

    def diffTree(self, obj = 'HEAD', parent = None, patch = False):
        comm = ['diff-tree']

        comm.append('-r')
        comm.append('--no-commit-id')
        comm.append('-M')
        comm.append('--root')
        comm.append('-a')

        if patch:
            comm.append('--patch-with-raw')

        if parent:
            comm.append(parent)
        else:
            comm.append('-c')

        comm.append(obj)
        return self._git(comm)

    def lsTree(self, obj = 'HEAD', recursive = False, long = False,
                     full_tree = False, zeroterm = True):
        comm = ['ls-tree']

        if recursive:
            comm.append('-r')
        if long:
            comm.append('--long')
        if full_tree:
            comm.append('--full-tree')
        if zeroterm:
            comm.append('-z')

        comm.append(obj)
        return self._git(comm)

    def formatPatch(self, id, id2):
        comm = ['format-patch']

        comm.append('-n')
        comm.append('--root')
        comm.append('--stdout')
        comm.append('--encoding=utf8')

        if id2 is None:
            comm.append('-1')
            comm.append(id)
        else:
            comm.append(id + '..' + id2)

        return self._git(comm)

    def archive(self, id, format = 'tar', prefix = 'a/', compress = None):
        comm = ['archive']
        comm.append('--format={0}'.format(format))
        comm.append('--prefix={0}'.format(prefix))
        comm.append(id)

        if compress:
            pipe = self._gitPipe(comm)
            compressor = Popen([compress], stdout = PIPE, stderr = STDOUT, stdin = pipe.stdout)
            s = compressor.stdout.read()
            compressor.stdout.close()
            return s
        else:
            return self._git(comm)

class GitDate(object):
    def __init__(self, epoch, tz):
        self.gmt      = None
        self.local    = None
        self.local_tz = None

        self._parseEpochTz(epoch, tz)

    def format(self, format):
        return self.local.strftime(format)

    def __str__(self):
        date = ''
        if self.local:
            date += self.local.strftime('%Y-%m-%d %H:%M:%S')
        if self.local_tz:
            date += ' ' + self.local_tz

        return '<GitDate {0}>'.format(date)
    def str(self):
        date = ''
        if self.local:
            date += self.local.strftime('%Y-%m-%d %H:%M:%S')
        if self.local_tz:
            date += ' ' + self.local_tz

        return date

    def _parseEpochTz(self, epoch, tz):
        epoch = int(epoch)

        # prepare gmt epoch
        h = int(tz[1:3])
        m = int(tz[4:])
        if tz[0] == '+':
            gmtepoch = epoch - ((h + m/60) * 3600)
        else:
            gmtepoch = epoch + ((h + m/60) * 3600)

        date = datetime.datetime.fromtimestamp(epoch)
        gmtdate = datetime.datetime.fromtimestamp(gmtepoch)

        self.gmt      = gmtdate
        self.local    = date
        self.local_tz = tz

class GitPerson(object):
    def __init__(self, person, date):
        self.person = person
        self.date   = date

    def __str__(self):
        return '<GitPerson person={0}, date={1}>'.format(self.person, str(self.date))

    def name(self):
        global patterns
        m = patterns['person2'].match(self.person)
        if not m:
            return self.person
        return m.group(1)

class GitObj(object):
    def __init__(self, git, id = None):
        self.git = git
        self.id  = id

    def __str__(self):
        return '<{0} id={1}>'.format(self.__class__.__name__, self.id)

    def modeIsGitlink(self, mode_oct):
        return stat.S_IFMT(mode_oct) == 0160000

    def modeStr(self, mode_oct):
        if self.modeIsGitlink(mode_oct):
            return 'm---------'
        elif stat.S_ISDIR(mode_oct):
            return 'drwxr-xr-x'
        elif stat.S_ISREG(mode_oct):
            # git cares only about the executable bit
            if mode_oct & stat.S_IXUSR:
                return '-rwxr-xr-x'
            else:
                return '-rw-r--r--'
        elif stat.S_ISLNK(mode_oct):
            return 'lrwxrwxrwx'
        else:
            return '----------'

    def fileType(self, mode):
        if mode == 0:
            return ''

        if self.modeIsGitlink(mode):
            return "submodule";
        elif stat.S_ISDIR(mode):
            return 'directory'
        elif stat.S_ISREG(mode):
            return 'file'
        elif stat.S_ISLNK(mode):
            return 'symlink'
        else:
            return 'unknown'

class GitCommit(GitObj):
    def __init__(self, git, id, tree, parents, author, committer, comment):
        super(GitCommit, self).__init__(git, id)

        self.tree      = tree
        self.parents   = parents
        self.author    = author
        self.committer = committer
        self.comment   = comment

        self.tags    = []
        self.heads   = []
        self.remotes = []

    def commentFirstLine(self):
        lines = self.comment.split('\n', 1)
        return lines[0]

    def commentRestLines(self):
        lines = self.comment.split('\n', 1)
        if len(lines) == 1:
            return ''

        return lines[1]

class GitTag(GitObj):
    def __init__(self, git, id, objid = None, name = '', msg = '', tagger = None):
        super(GitTag, self).__init__(git, id)

        self.objid = objid
        self.name  = name
        self.msg   = msg
        self.tagger = tagger

class GitHead(GitObj):
    def __init__(self, git, id, name = ''):
        super(GitHead, self).__init__(git, id)

        self.name  = name

    def commit(self):
        c = self.git.revList(self.id, max_count = 1)
        return c[0]

class GitDiffTree(GitObj):
    def __init__(self, git, from_mode, to_mode, from_id, to_id, status,
                            similarity, from_file, to_file, patch = ''):
        self.from_mode = from_mode
        self.to_mode   = to_mode
        self.from_id   = from_id
        self.to_id     = to_id
        self.status    = status
        self.similarity = similarity
        self.from_file = from_file
        self.to_file   = to_file
        self.patch     = patch

        self.from_mode_oct = int(self.from_mode, 8)
        self.to_mode_oct   = int(self.to_mode, 8)
        self.from_file_type = self.fileType(self.from_mode_oct)
        self.to_file_type   = self.fileType(self.to_mode_oct)

        if len(self.similarity) > 0:
            self.similarity = '{0}%'.format(int(self.similarity))

class GitTree(GitObj):
    def __init__(self, git, id, name, mode, size):
        super(GitTree, self).__init__(git, id)

        self.name = name
        self.mode = mode
        self.size = size

        self.mode_oct = int(mode, 8)

class GitBlob(GitObj):
    def __init__(self, git, id, name = '', mode = '', size = '', data = ''):
        super(GitBlob, self).__init__(git, id)

        self.name = name
        self.mode = mode
        self.size = size
        self.data = data

        self.mode_oct = -1
        if len(self.mode) > 0:
            self.mode_oct = int(mode, 8)



class Git(object):
    def __init__(self, dir, gitbin = '/usr/bin/git'):
        global patterns

        self._git = GitComm(dir, gitbin)
        self._patterns = patterns

    def revList(self, obj = 'HEAD', max_count = -1, all = False):
        # get raw data
        res = self._git.revList(obj, parents = True, header = True,
                                     max_count = max_count, all = all)

        # split into hunks (each corresponding with one commit)
        commits_str = res.split('\x00')

        # create GitCommit object from each string hunk
        commits = []
        for commit_str in commits_str:
            if len(commit_str) > 1:
                commits.append(self._parseCommit(commit_str))

        return commits

    def commit(self, id = 'HEAD'):
        c = self.revList(id, max_count = 1)
        if len(c) == 0:
            return None
        return c[0]

    def refs(self):
        format  = '%(objectname) %(objecttype) %(refname) <%(*objectname)> %(subject)%00%(creator)'

        tags    = []
        heads   = []
        remotes = []

        # tags
        res = self._git.forEachRef(format = format, sort = '-*authordate', pattern = 'refs/tags')
        lines = res.split('\n')
        for line in lines:
            tag = self._parseTag(line)
            if tag:
                tags.append(tag)


        # heads, remotes
        res = self._git.forEachRef(format = format,
                                   sort = '-committerdate', 
                                   pattern = ['refs/heads', 'refs/remotes'])
        lines = res.split('\n')
        for line in lines:
            d = line.split(' ')
            if len(d) < 3:
                continue

            if d[2][:11] == 'refs/heads/':
                id = d[0]
                name = d[2][11:]
                o = GitHead(self, id, name = name)
                heads.append(o)
            elif d[2][:13] == 'refs/remotes/':
                id = d[0]
                name = d[2][13:]
                o = GitHead(self, id, name = name)
                remotes.append(o)

        return (tags, heads, remotes, )


    def commitsSetRefs(self, commits, tags, heads, remotes):
        for c in commits:
            for t in tags:
                if t.objid == c.id:
                    c.tags.append(t)

            for h in heads:
                if h.id == c.id:
                    c.heads.append(h)

            for r in remotes:
                if r.id == c.id:
                    c.remotes.append(r)

        return commits


    def diffTree(self, id, parent, patch = False):
        s = self._git.diffTree(id, parent = parent, patch = patch)

        diff_trees = []

        lines = s.split('\n')
        patch_lines = []
        for i in range(0, len(lines)):
            line = lines[i]

            if len(line) == 0:
                patch_lines = lines[i+1:]
                break

            o = self._parseDiffTree(line)
            if o:
                diff_trees.append(o)

        if len(patch_lines) > 0:
            self._parseDiffTreePatch(diff_trees, patch_lines)

        return diff_trees

    def formatPatch(self, id, id2):
        return self._git.formatPatch(id, id2)

    def tree(self, id):
        s = self._git.lsTree(id, long = True, zeroterm = True)

        # try to detect older version of git which does not know --long
        # option and in this case simply omit size
        if s.startswith('usage'):
            s = self._git.lsTree(id, zeroterm = True)

        objs = []

        lines = s.split('\x00')
        for line in lines:
            if len(line) > 0:
                objs.append(self._parseTree(line))

        return objs

    def blob(self, id):
        s = self._git.catFile(id, 'blob')
        obj = GitBlob(self, id, data = s)
        return obj


    def archive(self, id, project, type):
        name = project + '-' + id

        if type == 'tgz':
            arch = self._git.archive(id, 'tar', name + '/', 'gzip')
            filename = name + '.tar.gz'
        elif type == 'tbz2':
            arch = self._git.archive(id, 'tar', name + '/', 'bzip2')
            filename = name + '.tar.bz2'
        elif type == 'txz':
            arch = self._git.archive(id, 'tar', name + '/', 'xz')
            filename = name + '.tar.xz'
        elif type == 'zip':
            arch = self._git.archive(id, 'zip', name + '/')
            filename = name + '.zip'

        return (arch, filename)



    def _parseTree(self, line):
        data, name = line.split('\t', 1)
        p = data.split()
        mode = p[0]
        type = p[1]
        id   = p[2]
        size = ''
        if len(p) > 3:
            size = p[3]
            
        if type == 'tree':
            obj = GitTree(self, id = id, mode = mode, size = size, name = name)
        else:
            obj = GitBlob(self, id = id, mode = mode, size = size, name = name)

        return obj

    def _parseDiffTree(self, line):
        global patterns

        diff_tree = None
        match = patterns['diff-tree'].match(line)
        if match:
            status = match.group(5)
            if status in ['R', 'C']:
                from_file, to_file = match.group(7).split('\t', 1)
            else:
                from_file = to_file = match.group(7)

            diff_tree = GitDiffTree(self, from_mode  = match.group(1),
                                          to_mode    = match.group(2),
                                          from_id    = match.group(3),
                                          to_id      = match.group(4),
                                          status     = status,
                                          similarity = match.group(6),
                                          from_file  = from_file,
                                          to_file    = to_file)

        return diff_tree

    def _parseDiffTreePatch(self, diff_trees, lines):
        global patterns

        cur = 0
        patch = ''
        for line in lines:
            match = patterns['diff-tree-patch'].match(line)
            if match and len(patch) > 0:
                diff_trees[cur].patch = patch
                cur += 1
                patch = ''

            patch += line + '\n'

        if len(patch) > 0 and cur < len(diff_trees):
            diff_trees[cur].patch = patch

    def _parsePerson(self, line):
        person = line
        epoch = '0'
        tz = '+0000'

        match = self._patterns['person'].match(line)
        if match:
            person = match.group(1)
            epoch  = match.group(2)
            tz     = match.group(3)

        date   = GitDate(epoch = epoch, tz = tz)
        person = GitPerson(person = person, date = date)
        return person

    def _parseIdParents(self, line):
        ids = line.split(' ')
        id      = ids[0]
        parents = []
        if len(ids) > 1:
            parents = ids[1:]
        return (id, parents, )

    def _parseCommit(self, s):
        lines = s.split('\n')

        id, parents = self._parseIdParents(lines.pop(0))
        tree        = None
        author      = None
        committer   = None
        comment     = ''
        for line in lines:
            if line[:4] == 'tree':
                tree = line[5:]
            if line[:6] == 'parent' and line[7:] not in parents:
                parents.append(line[7:])
            if line[:6] == 'author':
                author = self._parsePerson(line)
            if line[:9] == 'committer':
                committer = self._parsePerson(line)

            if line[:4] == '    ':
                comment += line[4:] + '\n'

        commit = GitCommit(self, id = id, tree = tree, parents = parents,
                                 author = author, committer = committer,
                                 comment = comment)
        return commit

    def _parseTag(self, s):
        lines = s.split('\x00')

        if len(lines) != 2:
            return None

        try:
            (objectname, objecttype, refname,
                    pobjectname, msg) = lines[0].split(' ', 4)
        except:
            return None

        try:
            (tagger, date, tz) = lines[1].rsplit(' ', 2)
        except:
            return None

        id = objectname
        if objecttype == "commit":
            # this is a lightweight tag
            objid = objectname
        else:
            objid = pobjectname[1:-1]

        # remove "refs/tags/"
        name = refname[10:]

        if not tagger:
            tagger = self._parsePerson('')
        else:
            tagger = self._parsePerson("tagger: "+lines[1])

        tag = GitTag(self, id = id, objid = objid, name = name, msg = msg, tagger = tagger)
        return tag

