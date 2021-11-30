"""Class that implements a pre-commit hook for updating AsciiDoc
file module-used-by block comments.
"""

import re
import os
import sys

from pathlib import Path
from git import Repo


class MUB:
    """MUB: module used by

    Provides a pre-commit hook implementation to update AsciiDoc files
    with accurate module-used-by block comments.
    """
    MUB_COMMENT = "// Module included in the following assemblies:"
    include_pattern = re.compile(r"^include::(modules\/.+\.adoc)")
    ignore_dirs = ["modules"]
    ignore_files = ["modules/common-attributes.adoc"]
    repo = None
    repodir = None  # This directory can be relative to the repo.
    otherdirs = []
    assemblies = []
    used_by = {}

    def __init__(self, filename: str):
        fullpath = os.path.abspath(filename)
        self.repo = Repo(fullpath, search_parent_directories=True)

    def get_repo(self):
        """Return the path to the Git repository as a string."""
        return f"{self.repo}"

    def find_assembly_dirs(self, relative_path: str = None):
        """Gather the list of top-level directories in the Git repository.

        Top-level directory names must match the regex '[a-z]*'.
        You can explicitly ignore some direcotory names by specifying the name
        in an `ignore_dirs` command-line argument.

        Args:
            relative_path (str): Optional path that is relative to the repository root.

        Returns:
            None
        """
        self.repodir = Path(self.repo.working_dir)
        if relative_path:
            self.repodir = self.repodir.joinpath(relative_path)
        if self.repodir.exists() is False:
            raise FileNotFoundError(f"Repodir does not exist: {self.repodir}")

        self.otherdirs = [
            p for p in self.repodir.iterdir()
            if p.is_dir() and p.match("[a-z]*") and p.name not in self.ignore_dirs
        ]

    def find_assembly_files(self):
        """Search the top-level directories for AsciiDoc files.

        Following the Red Hat repository layout conventions, the AsciiDoc
        files in the top-level directories (excluding `modules`) are
        assembly files. These assembly files use the `include::...[]` directive
        to include module files.

        Args:
            None

        Returns:
            None
        """
        for directory in self.otherdirs:
            for file in directory.rglob("*.adoc"):
                self.assemblies.append(file)

    def get_used_by_from_search(self):
        """Search the AsciiDoc files (assemblies) for included modules.

        Args:
            None

        Returns:
            None
        """
        for file in self.assemblies:
            with file.open() as lines:
                for line in lines:
                    match = self.include_pattern.match(line)
                    if not match:
                        continue
                    if match.group(1) not in self.used_by.keys():
                        self.used_by[match.group(1)] = []
                    self.used_by[match.group(1)].append(
                        str(file.relative_to(self.repodir)))

    def get_includes_from_file(self, lines: "list[str]") -> "list[str]":
        """Read the include directives and module file names from an assembly.

        Args:
            lines (list[str]): The content of the assembly file as a list of strings.

        Returns:
            list[str]: A list of module file names.
        """
        included_modules = []
        for line in lines:
            match = self.include_pattern.match(line)
            if not match:
                continue
            if match.group(1) in self.ignore_files:
                continue
            included_modules.append(match.group(1))
        return included_modules

    # Read the file as a list of strings.
    # If the file has the "Modules..." string in a comment, then
    # compare those with the comments that were retrieved from
    # the file search.
    # Return values:
    # If the function returns nothing, then there is no update to make.
    # If the function returns a list of strings, the list is the new file
    # content.

    def update_used_by_info(self, file: Path, lines: "list[str]") -> "list[str]":
        """Get the file contents with an accurate module-used-by block comment.

        The module is not updated in the file system.  See the `Returns` information.

        Args:
            file (Path): The module file as a Path object.
            lines (list[str]): The content of the module file as a list of strings.

        Returns:
            list[str] or None: If the return value is None, then the existing
            block comment is accurate. Otherwise, the return value is a list of
            strings that represents an accurate block comment and the file contents.
        """
        relative_filename = str(file.resolve().relative_to(self.repodir))
        from_comments = []  # Assume the heading is not present.
        comment_end_lineno = 0  # If no heading, add new heading at line 0.

        # Search for "Module " so that typos and variations are tolerated.
        has_intro_comment = any("// Module " in line for line in lines)
        if has_intro_comment:
            comment_end_lineno, from_comments = get_used_by_from_comments(
                lines)

        try:
            from_search = self.used_by[relative_filename]
        except KeyError:
            print("Module is not used by any assemblies: ", file.name)
            return None

        search_set = frozenset(from_search)
        comments_set = frozenset(from_comments)

        diff = search_set.difference(comments_set)
        if len(diff) == 0:
            return None
        comment = [self.MUB_COMMENT + '\n', "//\n"]
        for assembly_name in sorted(search_set):
            comment.append(f"// * {assembly_name}\n")
        # If the first line that follows the original comment
        # is not a blank line, pad with an additional blank line.
        if len(lines[comment_end_lineno]) > len('\n'):
            comment.append('\n')
        return comment + lines[comment_end_lineno:]


def get_used_by_from_comments(lines: "list[str]") -> "tuple[int, list[str]]":
    """Read the module-used-by block comment from a module file.

    Args:
        lines (list[str]): The content of the module file as a list of strings.

    Returns:
        tuple[int, list[str]]: The integer indicates the last line number of
        the module-used-by block comment. The list indicates the assembly file
        names from the block comment.
    """
    line_count = len(lines)
    line_no = 0
    matches = []
    while line_no < line_count:
        line = lines[line_no].strip()
        match = re.match(r"^//\s*\*?(.+\.adoc)", line)
        if match:
            matches.append(match.group(1).strip())
        if not re.match((r"^//"), line):
            break
        line_no += 1
    return line_no, matches


def process_args(args: "list[str]") -> "dict":
    """Identify optional arguments from staged file names.

    Args:
        args (list[str]): A list of all command-line arguments.

    Returns:
        dict: A dictionary with three keys:
            "files": The staged files to process.
            "ignore_dirs": An optional list of directories to ignore so they
            are not searched for assemblies.
            "ignore_files": An optional list of file names to ignore so they
            are not processed for the module-used-by block comment.
    """
    ret = {
        "files": [],
        "ignore_dirs": [],
        "ignore_files": []
    }

    dir_pattern = re.compile("--ignore-dir=(.+)")
    file_pattern = re.compile("--ignore-file=(.+)")

    for arg in args:
        dir_match = re.match(dir_pattern, arg)
        if dir_match:
            ret["ignore_dirs"].append(dir_match.group(1).strip())
            continue

        file_match = re.match(file_pattern, arg)
        if file_match:
            ret["ignore_files"].append(file_match.group(1).strip())
            continue

        ret["files"].append(arg)
    return ret


def fix_file():
    """Entrypoint function for the hook.

    Staged files are processed to check whether the module-used-by
    block comment is accurate or to update it.

    Returns:
        int: 0 indicates that no files were modified.
        1 indicates that at least one file was modified.
    """
    files_modified = False
    filenames = []
    result = process_args(sys.argv[1:])

    mub = MUB(result["files"][0])
    if mub.repo is None:
        print(
            f"Failed to locate the git repository from: {result['files'][0]}")
        sys.exit(2)

    mub.ignore_dirs += result["ignore_dirs"]
    mub.ignore_files += result["ignore_files"]

    for filename in result["files"]:
        parent = str(Path(filename).parent)

        if filename in mub.ignore_files:
            print(f"File explicitly ignored: {filename}")
        elif re.search('modules', filename):
            filenames.append(filename)
        # ignore_dirs includes `modules`. After accumulating module file
        # names in the preceding condition, filter assemblies from the
        # directories to ignore.
        elif parent in mub.ignore_dirs:
            print(
                f"File is in an explicitly ignored directory {parent}, file: {filename}")
        else:
            # For assemblies, find the `include::` directive, and
            # add those modules to the list of modules to check.
            with Path(filename).open(encoding="utf-8") as file:
                lines = file.readlines()
                candidates = mub.get_includes_from_file(lines)
                for include in candidates:
                    if os.path.exists(include) and os.path.isfile(include):
                        filenames.append(include)
                    else:
                        print(
                            f"In assembly '{filename}' included file does not exist or is not a file: '{include}'")

    mub.find_assembly_dirs()
    mub.find_assembly_files()
    mub.get_used_by_from_search()

    filenames = list(set(filenames))

    for filename in filenames:
        adoc_file = Path(filename)

        with adoc_file.open(mode='r', encoding="utf-8") as file:
            adoc_lines = file.readlines()

        return_lines = mub.update_used_by_info(adoc_file, adoc_lines)
        if return_lines is None:
            continue

        print(f'Fixing {str(filename)}')
        with adoc_file.open(mode="w", encoding="utf-8") as file:
            file.seek(0)
            file.truncate()
            file.write(''.join(return_lines))
            files_modified = True

    if files_modified is False:
        return 0
    return 1


def main():
    """Function for interactive hook development."""
    mub = MUB(sys.argv[1])
    if mub.repo is None:
        print(f"Failed to locate the git repository from: {sys.argv[1]}")
        sys.exit(2)

    mub.find_assembly_dirs()
    mub.find_assembly_files()
    mub.get_used_by_from_search()

    for filename in sys.argv[1:]:
        file = Path(filename)

        from_search = mub.used_by[file.name]
        from_comments = ()

        print(f"File '{file.name}' used by:")
        print(f"  from search: {mub.used_by[file.name]}")
        with file.open(encoding="utf-8") as file:
            lines = file.readlines()
            _, from_comments = get_used_by_from_comments(lines)
            print(f"  from comments: {from_comments}")

        search_set = frozenset(from_search)
        comments_set = frozenset(from_comments)

        diff = search_set.difference(comments_set)
        if len(diff):
            print("Difference: ", str(diff))


if __name__ == "__main__":
    sys.exit(main())
