from typing import Sequence
from typing import Optional
from git import Repo

import os
import sys
import re
import io


from pathlib import Path


class MUB:
    MUB_COMMENT = "// Module included in the following assemblies:"
    EXCLUDE_DIRS = ["modules"]
    INCLUDE_PATTERN = re.compile("^include::modules\/(.+\.adoc)")
    repo = None
    repodir = None  # This directory can be relative to the repo.
    otherdirs = []
    assemblies = []
    used_by = {}

    def __init__(self, filename: str):
        fullpath = os.path.abspath(filename)
        self.repo = Repo(fullpath, search_parent_directories=True)

    def get_repo(self):
        return f"{self.repo}"

    def find_assembly_dirs(self, relative_path: str = None):
        self.repodir = Path(self.repo.working_dir)
        if (relative_path):
            self.repodir = self.repodir.joinpath(relative_path)
        if (False == self.repodir.exists()):
            raise FileNotFoundError("Repodir does not exist: %s", self.repodir)

        self.otherdirs = [
            p for p in self.repodir.iterdir() if p.is_dir() and p.match("[a-z]*") and p.name not in self.EXCLUDE_DIRS
        ]

    def find_assembly_files(self):
        for d in self.otherdirs:
            for f in d.rglob("*.adoc"):
                self.assemblies.append(f)

    def get_used_by_from_search(self):
        for f in self.assemblies:
            with f.open() as lines:
                for line in lines:
                    match = self.INCLUDE_PATTERN.match(line)
                    if not match:
                        continue
                    if match.group(1) not in self.used_by.keys():
                        self.used_by[match.group(1)] = []
                    self.used_by[match.group(1)].append(
                        str(f.relative_to(self.repodir)))

    # Read the file as a list of strings.
    # If the file has the "Modules..." string in a comment, then
    # compare those with the comments that were retrieved from
    # the file search.
    # Return values:
    # If the function returns nothing, then there is no update to make.
    # If the function returns a list of strings, the list is the new file
    # content.
    def update_used_by_info(self, file: Path, lines: "list[str]") -> "list[str]":
        from_comments = []  # Assume the heading is not present.
        comment_end_lineno = 0  # If no heading, add new heading at line 0.

        # Use "Module " so that typos for assemblies are ignored.
        has_intro_comment = any("// Module " in line for line in lines)
        if has_intro_comment:
            comment_end_lineno, from_comments = self.get_used_by_from_comments(
                lines)

        try:
            from_search = self.used_by[file.name]
        except KeyError as ke:
            print("Module is not used by any assemblies: ", file.name)
            return

        search_set = frozenset(from_search)
        comments_set = frozenset(from_comments)

        diff = search_set.symmetric_difference(comments_set)
        if len(diff) == 0:
            return
        comment = [self.MUB_COMMENT + '\n', "//\n"]
        for x in sorted(search_set):
            comment.append("// * {}\n".format(x))
        comment.append('\n')
        return comment + lines[comment_end_lineno:]

    def get_used_by_from_comments(self, lines: "list[str]") -> "tuple[int, list[str]]":
        line_count = len(lines)
        line_no = 0
        matches = []
        while line_no < line_count:
            line = lines[line_no].strip()
            match = re.match("^//\s*\*?(.+\.adoc)", line)
            if match:
                matches.append(match.group(1).strip())
            line_no += 1
            if re.match(("^[ =\[\w]|\s*$"), line):
                # If the line after the last comment is not blank,
                # such as `[id=...`, then back up to the last comment line.
                if len(lines[line_no].strip()) != 0:
                    line_no -= 1
                break
        return line_no, matches


def fix_file():
    files_modified = False
    filenames = []

    for filename in sys.argv:
        if re.search('modules', filename):
            filenames.append(filename)

    if 0 == len(filenames):
        return 0

    mub = MUB(filenames[0])
    if None == mub.repo:
        print(f"Failed to locate the git repository from: {filenames[0]}")
        os._exit(2)

    mub.find_assembly_dirs()
    mub.find_assembly_files()
    mub.get_used_by_from_search()

    for fname in filenames:
        file = Path(fname)

        with file.open(mode='r') as f:
            lines = f.readlines()

        modlines = mub.update_used_by_info(file, lines)
        if None == modlines:
            continue

        print(f'Fixing {str(file)}')
        with file.open(mode="w") as f:
            f.seek(0)
            f.truncate()
            f.write(''.join(modlines))
            files_modified = True

    if False == files_modified:
        return 0
    return 1


def main():
    mub = MUB(sys.argv[1])
    if None == mub.repo:
        print(f"Failed to locate the git repository from: {sys.argv[1]}")
        os._exit(2)

    mub.find_assembly_dirs()
    mub.find_assembly_files()
    mub.get_used_by_from_search()

    for fname in sys.argv[1:]:
        file = Path(fname)

        from_search = mub.used_by[file.name]
        from_comments = ()

        print("File '{}' used by:".format(file.name))
        print("From search: {}".format(mub.used_by[file.name]))
        with file.open() as f:
            lines = f.readlines()
            line_no, from_comments = mub.get_used_by_from_comments(lines)
            print("From comments: ", from_comments)

        search_set = frozenset(from_search)
        comments_set = frozenset(from_comments)

        diff = search_set.difference(comments_set)
        if len(diff):
            print("Difference: ", str(diff))


if __name__ == "__main__":
    exit(main())
