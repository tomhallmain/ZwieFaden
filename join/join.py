# A Python class called JoinMulti that consumes multiple text data files and prints a list of all the lines in any of the files, followed by the name of the files in which they appeared.

import math
import os
import pickle
import pprint
import re
import time
from collections import defaultdict


def format_percent(percent, decimal_place):
    rounded = round(percent * 100, decimal_place)
    return f"{rounded}%"

def string_distance(s, t):
    # create two work vectors of integer distances
    v0 = [0] * (len(t) + 1)
    v1 = [0] * (len(t) + 1)

    # initialize v0 (the previous row of distances)
    # this row is A[0][i]: edit distance from an empty s to t;
    # that distance is the number of characters to append to  s to make t.
    for i in range(len(t) + 1):
        v0[i] = i

    for i in range(len(s)):
        # calculate v1 (current row distances) from the previous row v0

        # first element of v1 is A[i + 1][0]
        # edit distance is delete (i + 1) chars from s to match empty t
        v1[0] = i + 1

        for j in range(len(t)):
            # calculating costs for A[i + 1][j + 1]
            deletion_cost = v0[j + 1] + 1
            insertion_cost = v1[j] + 1
            substitution_cost = v0[j] if s[i] == t[j] else v0[j] + 1
            v1[j + 1] = min(deletion_cost, insertion_cost, substitution_cost)
        # copy v1 (current row) to v0 (previous row) for next iteration
        v0,v1 = v1,v0
    # after the last swap, the results of v1 are now in v0
    return v0[len(t)]

def longest_common_substring(str1, str2):
    m = [[0] * (1 + len(str2)) for _ in range(1 + len(str1))]
    longest, x_longest = 0, 0
    for x in range(1, 1 + len(str1)):
        for y in range(1, 1 + len(str2)):
            if str1[x - 1] == str2[y - 1]:
                m[x][y] = m[x - 1][y - 1] + 1
                if m[x][y] > longest:
                    longest = m[x][y]
                    x_longest = x
            else:
                m[x][y] = 0
    return str1[x_longest - longest: x_longest]

def invert_dict(d):
    inverted_dict = defaultdict(list)
    for k, v in d.items():
        inverted_dict[v].append(k)
    return inverted_dict


class Grouping:
    def __init__(self, name, files):
        self.name = name
        self.files = files
        self.other_names = {}

    def merge(self, files, other_name):
        for file in files:
            if file not in self.files:
                self.files.append(file)
            self.other_names[file] = other_name

    def is_merged(self):
        return len(self.other_names) > 0

    def __str__(self):
        if self.is_merged():
            return f"Name: {self.name}\nFiles: {pprint.pformat(self.files)}\nOther Names:{pprint.pformat(self.other_names)}"
        else:
            return f"Name: {self.name}\nFiles: {pprint.pformat(self.files)}"

class UnconfirmedGrouping:
    def __init__(self, l0, files0, l1, files1, string_distance):
        self.l0 = l0
        self.files0 = files0
        self.l1 = l1
        self.files1 = files1
        self.string_distance = string_distance

    def display_value(self):
        return f"\"{self.l0}\" <> \"{self.l1}\""

    def __str__(self):
        return f"Name 0: {self.l0}\nFiles 0: {pprint.pformat(self.files0)}\nName 1: {self.l1}\nFiles 1: {pprint.pformat(self.files1)}\nString Distance: {self.string_distance}"

class JoinMulti:
    STORE_LOCATION = "../configs/join_multi_store.pkl"
    ANALYSIS_LOCATION = "../configs/join_multi_analysis.txt"

    def __init__(self, file_paths, similars=False, file_path_op=os.path.basename):
        self.file_paths = file_paths
        self.file_path_op = file_path_op
        self.line_files = defaultdict(list)
        self.line_files_list = []
        self.groupings = {}
        self.maybe_groupings = []
        self.ungrouped = {}
        self.similars = similars
        self.restored = False
        self.name = ""

    def set_name(self):
        # Extract base names from the file paths
        base_names = [os.path.splitext(os.path.basename(path))[0] for path in self.file_paths]

        # Find the longest common substring
        longest_common_sub = base_names[0]
        for i in range(1, len(base_names)):
            longest_common_sub = longest_common_substring(longest_common_sub, base_names[i])

        # strip non-alphanumeric characters
        longest_common_sub = re.sub('^[^A-Za-z]+', '', longest_common_sub)
        longest_common_sub = re.sub('[^A-Za-z]+$', '', longest_common_sub)

        # If there is a common word, set it as the name, else set name as UNNAMED
        if longest_common_sub and longest_common_sub != "":
            self.name = longest_common_sub
        else:
            self.name = 'UNNAMED'

    def has_unconfirmed_groupings(self):
        return len(self.maybe_groupings) > 0

    def do_join(self):
        self.process_files()
        self.sort_and_set_groupings()
        self.basic_output()
        if self.similars:
            self.find_similars()
            self.grouping_output()
            self.find_common_uniques()

    def basic_output(self, cutoff=1):
        with open(JoinMulti.ANALYSIS_LOCATION, 'w') as f:
            for line, files in self.line_files_list:
                if len(files) > cutoff:
                    output = f'{line} ::: {", ".join(files)}'
                    print(output)
                    f.write(output + '\n')

    def sort_and_set_groupings(self):
        self.line_files_list = sorted(self.line_files.items(), key=lambda x: (-len(x[1]), x[0]))
        self.groupings = {}
        for tup in self.line_files_list:
            if len(tup[1]) > 1:
                self.groupings[tup[0]] = Grouping(tup[0], tup[1])
            else:
                self.ungrouped[tup[0]] = tup[1][0]

    def grouping_output(self, cutoff=0):
        for grouping in self.groupings.values():
            grouping.files.sort()
        line_files_list_groupings = sorted(self.groupings.items(), key=lambda x: (-len(x[1].files), x[0]))

        with open(JoinMulti.ANALYSIS_LOCATION, 'w') as f: # overwrite the file
            output = "\nGROUPINGS:\n"
            print(output)
            f.write(output + '\n')
            for line, grouping in line_files_list_groupings:
                if len(grouping.files) > cutoff:
                    output = f'{line} ::: {", ".join(grouping.files)}'
                    print(output)
                    f.write(output + '\n')

            output = "\nUNGROUPED:\n"
            print(output)
            f.write(output + '\n')
            output = pprint.pformat(invert_dict(self.ungrouped))
            print(output)
            f.write(output + '\n')
            # for file, lines in sorted(invert_dict(self.ungrouped).items(), key=lambda x: x[0]):
            #     output = f'{file} ::: {lines}'
            #     print(output)
            #     f.write(output + '\n')

    def process_files(self):
        for file_path in self.file_paths:
            with open(file_path, 'r') as file:
                name_id = self.file_path_op(file_path)
                for line in file:
                    line = line.strip().lower()
                    ls = self.line_files[line]
                    if not name_id in ls:
                        ls.append(name_id)

    # TODO maybe refector using numpy roll + apply_along_axis
    def find_similars(self):
        """
        Python function using string distance to find similarity between lines
        and group their data together for later merging.
        """
        pairs = [(i, j) for i in range(len(self.line_files_list)) for j in range(i+1, len(self.line_files_list))]
        total = len(pairs)
        count = 0
        for pair in pairs:
            count += 1
            if count % 2500000 == 0:
                print("Sleeping for 10s")
                time.sleep(10)
            percent_complete = count / total * 100
            if percent_complete % 10 == 0:
                print(str(int(percent_complete)) + f"% data gathered: {count} / {total}")
            tup0 = self.line_files_list[pair[0]]
            tup1 = self.line_files_list[pair[1]]
            files0 = tup0[1]
            files1 = tup1[1]
            if any(item in files0 for item in files1):
                continue
            l0 = tup0[0]
            l1 = tup1[0]
            l_distance = string_distance(l0, l1)
            min_len = min(len(l0), len(l1))
            if min_len == len(l0):
                weighted_avg_len = (len(l0) + len(l1) / 2) / 2
            else:
                weighted_avg_len = (len(l0) / 2 + len(l1)) / 2
            threshold = int(weighted_avg_len / 2.1) - int(math.log(weighted_avg_len))
            threshold = min(threshold, int(min_len * 0.8))
            # if count % 10000 == 0:
            #     print(f"\"{l0}\" \"{l1}\" {weighted_avg_len} {threshold} {l_distance}")
            if l_distance < threshold: # set a threshold for similarity here
                self.maybe_groupings.append(UnconfirmedGrouping(l0, files0, l1, files1, l_distance))
                print(f"\"{l0}\" and \"{l1}\", from files {files0[0]}, {files1[0]}, are similar with a distance of {l_distance}")
                if len(self.maybe_groupings) > 3:
                    break

    def merge_similars(self, unconfirmed_grouping):
        l0 = unconfirmed_grouping.l0
        l1 = unconfirmed_grouping.l1
        files0 = unconfirmed_grouping.files0
        files1 = unconfirmed_grouping.files1
        grouping0 = self.groupings[l0] if l0 in self.groupings else None
        grouping1 = self.groupings[l1] if l1 in self.groupings else None
        target_grouping = None

        if grouping0:
            if grouping1:
                if len(grouping0.files) == len(grouping1.files):
                    if len(grouping0.name) > len(grouping1.name):
                        target_grouping = grouping1
                    else:
                        target_grouping = grouping0
                elif len(grouping0.files) > len(grouping1.files):
                    target_grouping = grouping0
                else:
                    target_grouping = grouping1
                del self.ungrouped[grouping1.name]
            else:
                target_grouping = grouping0
            try:
                del self.ungrouped[grouping0.name]
            except KeyError:
                print("No ungrouped to delete: " + grouping0.name)
        elif grouping1:
            target_grouping = grouping1
            try:
                del self.ungrouped[grouping1.name]
            except KeyError:
                print("No ungrouped to delete: " + grouping1.name)
        else:
            target_name = l0 if len(l0) <= len(l1) else l1
            target_grouping = Grouping(target_name, [])

        remove_grouping1 = grouping1 and target_grouping.name == grouping1.name
        target_grouping.merge(files0, l0)
        target_grouping.merge(files1, l1)
        if remove_grouping1 and grouping1:
            del self.groupings[grouping1.name]
        elif grouping0:
            del self.groupings[grouping0.name]
        self.groupings[target_grouping.name] = target_grouping
        return target_grouping

    def find_common_uniques(self, files_threshold=3, exclusivity_threshold=0.1, all_files_threshold=0.1):
        # Initialize a dictionary to store the unique strings and the files they are found in
        unique_strings = defaultdict(set)
        all_files = set()
        for string, files in self.line_files.items():
            # Only consider strings that appear in more than files_threshold files
            if len(files) > files_threshold:
                unique_strings[string].update(files)
                all_files.update(files)
        # Initialize a dictionary to store the pairs of strings and the proportion of files they share in common
        string_pairs = {}
        # Iterate over all pairs of unique strings
        unique_strings_items = list(unique_strings.items())
        for i in range(len(unique_strings_items)):
            string1, files1 = unique_strings_items[i]
            for j in range(i+1, len(unique_strings_items)):
                string2, files2 = unique_strings_items[j]
                # Calculate the intersection of the sets of files the two strings are found in
                intersection = files1.intersection(files2)
                # Calculate the proportion of files they share in common
                exclusiveness_proportion = len(intersection) / len(files1.union(files2))
                all_files_proportion = len(files1.union(files2)) / len(all_files)
                # If the proportion is less than the threshold, they are considered to be exclusive.
                # NOTE if the proportion is 0 (length of intersection is also 0), they are mutually exclusive.
                if exclusiveness_proportion < exclusivity_threshold:
                    string_pairs[(string1, string2)] = (intersection, exclusiveness_proportion, all_files_proportion)
        # Return the dictionary of exclusive pairs, their intersection and their proportion
        with open(JoinMulti.ANALYSIS_LOCATION, "a") as f: # append to the file
            for str_tuple, data_tuple in sorted(string_pairs.items(), key=lambda x: (x[1][1], -x[1][2])):
                line = "\nString combination: " + str(str_tuple)
                f.write(line + "\n")
                print(line)
                if len(data_tuple[0]) > 0:
                    line = "Files intersection: " + str(data_tuple[0])
                    f.write(line + "\n")
                    print(line)
                line = "Commonality: " + format_percent(data_tuple[1], 1)
                f.write(line + "\n")
                print(line)
                line = "All files weight: " + format_percent(data_tuple[2], 1)
                f.write(line + "\n")
                print(line)
        return string_pairs

    def store(self):
        with open(JoinMulti.STORE_LOCATION, "wb") as store:
            pickle.dump(self, store)

    @staticmethod
    def get_stored_or_new():
        if os.path.exists(JoinMulti.STORE_LOCATION):
            try:
                print("Loading stored data from: " + os.path.abspath(JoinMulti.STORE_LOCATION))
                with open(JoinMulti.STORE_LOCATION, "rb") as f:
                    stored_join = pickle.load(f)
                    stored_join.restored = True
                    return stored_join
            except Exception as e:
                print("Failed to restore data from prior session with error:\n" + str(e))
                return JoinMulti([])
        else:
            return JoinMulti([])

    @staticmethod
    def remove_store():
        if os.path.exists(JoinMulti.STORE_LOCATION):
            os.remove(JoinMulti.STORE_LOCATION)

        return JoinMulti([])
